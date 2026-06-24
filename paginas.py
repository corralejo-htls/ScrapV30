"""
Booking.com scraper con Playwright v5.8 — Multi-idioma + DAT + SQL Update
Sin ChromeDriver, Sin Brave, Sin Selenium
Playwright descarga automáticamente Chromium compatible
Ejecuta JavaScript nativamente -> pasa AWS WAF Challenge
archivo con lista de url : list_url.csv (2 columnas : h.id , h.url)

desactivar notificaciones emergentes de escritorio : NordVPN → Ajustes → Notificaciones

Instalación:
    instalado Python
    python.exe -m pip install --upgrade pip
    -> en CMD instalar :
     pip install playwright
     pip install playwright-stealth
     pip install requests 
     playwright install chromium     
     -> en CMD ejecutar : python paginas.py

Revisión RCA + requisitos de flujo:
    - PASO 1: filtra SÓLO URLs de Booking.com; descarta resto; luego aplica MAX_URLS_DOWNLOAD.
    - PASO 2: DAT en JSON puro, agrupado por ID; nombre DAT__<id>_.json (desde el DOM extraído).
    - PASO 3: SQL por lotes de hasta MAX_SQL_BATCH; nombre SQL__<MMDD>_<lote>_.sql.
       El PASO 3 LEE los DAT del disco y puede ejecutarse de forma INDEPENDIENTE
       -> en CMD ejecutar : [ Python paginas.py --solo-sql ]  o [ Python paginas.py --sql-only ] (son iguales).
       En --solo-sql el PASO 3 SIEMPRE genera el archivo SQL. Opcionalmente se
       pueden elegir ids (sólo con --solo-sql); sin ids se procesan TODOS en
       lotes de MAX_SQL_BATCH:
         Python paginas.py --solo-sql --ids=75888,75889
         Python paginas.py --solo-sql --ids 75888 75889
         Python paginas.py --solo-sql 75888 75889
       El HTML es sólo respaldo de adquisición; no se reprocesa el DAT desde el HTML salvo re-adquisición explícita.
    - Trazabilidad URL -> DOM -> DAT -> SQL.
    - Exclusión de imágenes, enlaces de imagen y URLs externas en los textos.
    - Escapado SQL robusto (backslash + comilla) para MariaDB 10.1.
    - VPN configurable (ENABLE_VPN / VPN_REQUIRED) para no perder datos en silencio.
    - REGLA de sobrescritura: HTML/DAT/SQL existentes SIEMPRE se sobrescriben
      (sin comprobación ni confirmación; escritura atómica vía _safe_write).
    - REGLA de preservación : no se preserva datos histórico en (HTML DAT SQL).
    - agregar parametros lenguajes_activos_SQL para armar SQL con solo los idiomas preseleccionados, tener en cuenta si lenguajes_activos_SQL=lenguajes_activos, se toman por defecto los valores de lenguajes_activos.

Cambios v5.4 (correcciones de auditoría DAT vs HTML):
    - [FIX alta] Selector primario de la descripción: el nodo
      data-testid="property-description" ES el propio <p>, por lo que el
      selector de <p> DESCENDIENTE resolvía 0 nodos. Ahora se lee el elemento
      directamente; se elimina el respaldo "#basiclayout p" (que arrastraba
      párrafos ajenos). JSON-LD queda como último recurso.
    - [FIX alta] Contaminación de hotel_description: se eliminan las coletillas
      de interfaz/atribución que Booking adosa al bloque (p. ej. la atribución
      de distancias "... © OpenStreetMap"), que se persistían en la BD.
    - [FIX baja] Alcance de idiomas: validación en arranque de que TODOS los
      idiomas de lenguajes_activos tienen plantilla de URL; se documenta el
      alcance real (20 idiomas, incl. CJK/RTL) y se marcan esos scripts.

Cambios v5.5 (auditoría DAT vs HTML — correcciones de integridad de datos):
    - [REGLA] SIN FORMATO en el DAT: los textos se guardan EXACTAMENTE como se
      extraen del scraping. Se ELIMINA la conversión de saltos de línea a
      "<br />" y cualquier transformación en el PASO 2. El DAT refleja el DOM.
    - [NUEVO] Proceso de limpieza PASO 2.5 (clean_text_for_sql): se aplica
      DESPUÉS del DAT (PASO 2) y ANTES del SQL (PASO 3). Lee el texto CRUDO del
      DAT, elimina medios/URLs y contaminación de interfaz/atribución (OSM,
      valoración de ubicación, "score from N reviews", "Real guests", "show
      map", etc.) y normaliza sin formato. NO modifica el DAT en disco
      (el DAT sólo cambia ante nueva adquisición). Robusto ante DAT antiguos
      con "<br />".
    - [Finding 6] Idiomas: 20 base + "it" añadido AL FINAL del proceso = 21.
      Documentación y conteo reconciliados (sin "20" fijo erróneo).
    - [Finding 3] lenguajes_activos_SQL implementado de verdad (get_sql_languages);
      por defecto = lenguajes_activos. LOCALE_MAP opcional (código -> locale BD).
    - [Finding 1] Fallback en inglés: si la descripción NO-inglesa es idéntica a
      la inglesa (Booking sin traducción), NO se escribe inglés como traducción
      (SKIP_ENGLISH_FALLBACK_TRANSLATIONS).
    - [Finding 2] Preservación del DAT: registros vacíos (sin nueva adquisición)
      NO pisan datos previos (PRESERVE_DAT_ON_EMPTY).
    - [Finding 8] Aviso cuando un campo queda VACÍO en todos los idiomas.
    - [Finding 13] JSON-LD por @type (Hotel/LodgingBusiness) en vez de .first;
      score_review numérico; locale vía db_locale().
    - [Windows] Escritura segura (_safe_write): reintentos atómicos ante
      bloqueo de archivo (PermissionError/WinError 32) sin fallo silencioso.
      --solo-sql ya no exige privilegios de administrador.

Cambios v5.6 (cambio de política de traducciones):
    - [POLÍTICA] NO se omite NINGUNA traducción. Se MANTIENEN todos los textos
      y datos tal cual, INCLUSO si están en inglés (fallback de Booking en una
      ficha sin traducción para ese idioma). SKIP_ENGLISH_FALLBACK_TRANSLATIONS
      pasa a False por defecto; la detección de fallback se conserva sólo a
      título INFORMATIVO (cuenta, no descarta).

Cambios v5.7 (política: texto TAL CUAL, no se elimina nada):
    - [POLÍTICA] El texto se guarda y se vuelca al SQL EXACTAMENTE como se
      extrae. NO se elimina NADA: ni "OpenStreetMap" u otra contaminación de
      interfaz/atribución, ni medios/URLs, ni saltos de línea. clean_text_for_sql
      es PASS-THROUGH (CLEAN_TEXT_BEFORE_SQL=False). Sólo se aplica el escapado
      SQL obligatorio (sql_escape), que inserta el texto literal sin alterarlo.

Cambios v5.8 (limpieza de código y simplificación de configuración):
    - [VERSIÓN] Título y banner unificados con la versión real (v5.8). Antes
      mostraban v5.4 mientras el comportamiento era v5.7.
    - [CSV] El CSV pasa a 2 columnas (id,url). Se ELIMINA la columna de idioma.
      El idioma por defecto del sistema destino es DEFAULT_LANG ('en'), usado en
      el UPDATE de la tabla `hotel` (configurable para futuras actualizaciones).
    - [LIMPIEZA DE CÓDIGO] Se ELIMINA el código de limpieza desactivado
      (clean_text_for_sql, strip_media_and_links, strip_all_formatting,
      marcadores/patrones de contaminación, flag CLEAN_TEXT_BEFORE_SQL). El texto
      va al SQL TAL CUAL. La limpieza futura será un proceso aparte ("Format_DAT")
      entre el DAT y el SQL (no implementado en esta revisión).
    - [BACKUPS] Los respaldos HTML se guardan con extensión .html (antes .md);
      los diagnósticos con .txt.
    - [MEMORIA] Los datos por hotel viven en una variable LOCAL que se libera al
      cambiar de URL (antes se acumulaban en un dict global).
    - [DOCSTRING] Corregida la descripción del alcance de idiomas (sin la nota
      errónea "20 base + 'it' al final"); `lenguajes` es un CATÁLOGO y los
      idiomas activos varían según necesidad.
    - [ROBUSTEZ] Validación de que el id del hotel es numérico antes de
      interpolarlo en el SQL.
    - [M1] Corrección del mapeo de CIUDAD: el JSON-LD `addressLocality` de Booking
      contiene la CALLE, no la ciudad. Ahora `locality` conserva ese valor crudo
      (fiel al origen) y `city` se deriva de `streetAddress` usando el código
      postal como ancla (independiente del idioma: Vienna/Wien/维也纳/ウィーン...).
      No se inventan datos: si no es determinable, `city` queda vacío.
    - [CONFIG] validate_language_config: si un idioma activo NO tiene plantilla de
      URL en `lenguajes`, ahora AVISA y lo OMITE (antes abortaba con [FATAL]);
      sólo aborta si no queda ningún idioma activo válido.
    - [M3] Secciones (servicios/normas_casa/info_importante/info_destacada): se
      sustituyen los XPaths ABSOLUTOS (frágiles y, en el caso de servicios,
      muertos) por selectores ESTABLES por id/data-testid/clase mapeados del DOM
      real de Booking, con respaldos en cascada. Nueva ayuda _section_css() (se
      eliminan _section_text/_xpath_text). Se prioriza el contenedor de contenido
      [data-testid="property-section--content"], que excluye encabezados y botones
      ("See availability"/"Reserve"). Validado en 124 páginas (21 idiomas, incl.
      CJK y RTL): 100% de cobertura por el selector preferido.
    - [OPCIÓN] HTML_DOWNLOAD: controla si se GUARDA en disco el HTML de respaldo
      (carpeta html_downloads). El DOM siempre se descarga (de él sale el DAT);
      este flag sólo afecta al respaldo. HTML_DOWNLOAD=True guarda; cualquier otro
      valor NO guarda. El diagnóstico de fallos (html_diagnostic) se mantiene.
    - [SIMPLIFICACIÓN] Sobrescritura: se elimina OVERWRITE_EXISTING y la
      comprobación "ya existe" del HTML. Los archivos SIEMPRE se sobrescriben
      (escritura atómica vía _safe_write), sin comprobación ni confirmación.
    - [LOG] Modo silencioso (no interactivo: el proceso nunca pide confirmación).
      Toda la salida de consola se DUPLICA en logs/run_<fecha_hora>.log con marca
      de tiempo por línea, para poder DETECTAR ERRORES a posteriori. Las
      excepciones no controladas se vuelcan con traza completa (sys.excepthook);
      los errores de descarga incluyen idioma, URL e intento.
    - [BANDERA] SQL_GENERATE (por defecto False): activa/desactiva el PASO 3
      AUTOMÁTICO al final de un run completo (y los procesos asociados, p. ej. la
      futura limpieza Format_DAT). True = se genera el SQL al terminar el scraping;
      cualquier otro valor = no. En modo --solo-sql el PASO 3 SIEMPRE se ejecuta
      (es su propósito), con independencia de SQL_GENERATE.
    - [PASO 3] Selección de ids (sólo con --solo-sql): se pueden procesar ids
      concretos en lugar de todos los DAT. ÚNICO formato: --ids=75888,75889,75890
      (separados por coma). Sin ids -> TODOS los DAT en lotes de MAX_SQL_BATCH.
      Los ids sin DAT en disco se avisan por log.
    NOTA: el PASO 3 (SQL) sigue escribiendo sólo long_description y score_review;
    el resto de campos quedan COMPLETOS en el DAT y se volcarán a SQL en una
    revisión futura.
"""

import os
import time
import subprocess
import random
import sys
import re
import csv
import json
from datetime import datetime, timezone
import traceback

# ============================================================
# === PARÁMETROS PRINCIPALES (AL INICIO DEL CÓDIGO) ==========
# ============================================================
# Todos los parámetros de configuración PRINCIPALES van JUNTOS y AL INICIO.
# El log del proceso, la configuración secundaria y las demás funciones están
# MÁS ABAJO, debajo de esta selección de parámetros.

# Idiomas activos a scrapear (el orden marca el orden de scraping). Configurable
# según necesidad; sus plantillas de URL salen del catálogo `lenguajes`.
lenguajes_activos = ["en","es","fr","it","de","pt","ru","ar","nl","tl","id","ms","ja","ko","th","hu","pl","no","fi","sv","da","hi","zh"]

# Idiomas a incluir al ARMAR el SQL (PASO 3). [] (o = lenguajes_activos) => se
# usan los de lenguajes_activos. Permite un subconjunto, p.ej. ["en","es","de"].
lenguajes_activos_SQL = []

# Idioma por defecto del sistema destino (PASO 3, tabla `hotel`: language='en').
DEFAULT_LANG = "en"

# CATÁLOGO de plantillas de URL por idioma. De aquí se seleccionan los activos.
lenguajes = {
    "en": "en-gb.html?lang=en-gb",
    "es": "es.html?lang=es",
    "fr": "fr.html?lang=fr",
    "it": "it.html?lang=it",
    "de": "de.html?lang=de",
    "pt": "pt.html?lang=pt",
    "ru": "ru.html?lang=ru",
    "ar": "ar.html?lang=ar",
    "nl": "nl.html?lang=nl",
    "tl": "tl.html?lang=tl",
    "id": "id.html?lang=id",
    "ms": "ms.html?lang=ms",
    "ja": "ja.html?lang=ja",
    "ko": "ko.html?lang=ko",
    "th": "th.html?lang=th",
    "hu": "hu.html?lang=hu",
    "pl": "pl.html?lang=pl",
    "no": "no.html?lang=no",
    "fi": "fi.html?lang=fi",
    "sv": "sv.html?lang=sv",
    "da": "da.html?lang=da",
    "hi": "hi.html?lang=hi",
    "zh-tw": "zh-tw.html?lang=zh-tw",
    "zh": "zh-cn.html?lang=zh-cn",
}

# Preservación del DAT: al re-ejecutar SIN nueva adquisición (HTML omitido o
# extracción vacía), NO se pisa el DAT existente con registros vacíos.
PRESERVE_DAT_ON_EMPTY = True

# Límite de URLs (sólo Booking.com) a descargar desde list_url.csv.
MAX_URLS_DOWNLOAD = 300

# Tamaño máximo de lote (ids / URLs base) por archivo SQL.
MAX_SQL_BATCH = 100

# BANDERA MAESTRA del PASO 3 AUTOMÁTICO (al final de un run completo):
#   True -> al terminar el scraping se genera el SQL.
#   cualquier otro valor -> NO se genera (run normal = PASO 1+2, sin SQL).
# En modo --solo-sql el PASO 3 SIEMPRE se ejecuta, con independencia de esto.
SQL_GENERATE = False

# ============================================================
# === LOG DEL PROCESO (modo silencioso, no interactivo) ======
# ============================================================
# El proceso NO pide confirmaciónes en ningún punto (modo silencioso).
# Para poder DETECTAR ERRORES a posteriori, toda la salida de consola se DUPLICA
# en un fichero de log con marca de tiempo por línea, en la carpeta 'logs'. Si el
# log no puede abrirse, el proceso continúa igualmente (sólo consola).

LOG_DIR = "logs"

class _Tee:
    """Duplica la escritura de un flujo (stdout/stderr) en un fichero de log,
    anteponiendo una marca de tiempo al inicio de cada línea. No bloquea ni
    pregunta nada; si el fichero falla, sigue escribiendo en consola."""
    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh
        self._at_line_start = True
    def write(self, data):
        try:
            self._stream.write(data)
        except Exception:
            pass
        if data and self._fh is not None:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                out = []
                for line in data.splitlines(keepends=True):
                    if self._at_line_start:
                        out.append(f"[{ts}] {line}")
                    else:
                        out.append(line)
                    self._at_line_start = line.endswith(("\n", "\r"))
                self._fh.write("".join(out))
                self._fh.flush()
            except Exception:
                pass
        return len(data) if data else 0
    def flush(self):
        for t in (self._stream, self._fh):
            try:
                t.flush()
            except Exception:
                pass

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_path = os.path.join(LOG_DIR, datetime.now().strftime("run_%Y%m%d_%H%M%S.log"))
    _log_fh = open(_log_path, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, _log_fh)
    sys.stderr = _Tee(sys.stderr, _log_fh)
    # Cualquier excepción NO controlada se vuelca (con traza completa) al log.
    def _log_excepthook(exc_type, exc, tb):
        print("[FATAL] Excepción no controlada durante el proceso:")
        traceback.print_exception(exc_type, exc, tb)
    sys.excepthook = _log_excepthook
    print(f"[LOG] Registro del proceso: {_log_path}")
except Exception as _e:
    print(f"[LOG] No se pudo crear el fichero de log ({str(_e)[:80]}); se continúa sólo en consola.")

# ============================================================
# === CONFIGURACIÓN SECUNDARIA Y FUNCIONES (DEBAJO DE LOS PARÁMETROS) ===
# ============================================================

# --- MODO DE EJECUCIÓN: PASO 3 independiente desde los DAT del disco ---
# python paginas.py --solo-sql  (o --sql-only): omite el scraping y genera SQL
# a partir de los DAT existentes. En este modo el PASO 3 SIEMPRE se ejecuta.
SQL_ONLY = any(a in ("--solo-sql", "--sql-only") for a in sys.argv[1:])

# --- SELECCIÓN DE IDs PARA EL PASO 3 (sólo con --solo-sql) ---
# ÚNICO formato admitido:  --ids=75888,75889,75890  (separados por coma).
# Sólo se interpreta con --solo-sql; sin ids se procesan TODOS los DAT en lotes
# de MAX_SQL_BATCH.  Ej.:  python paginas.py --solo-sql --ids=75888,75889,75890
def parse_sql_ids(args):
    """Devuelve la lista de ids (str numéricos) para el PASO 3 desde el ÚNICO
    formato admitido: --ids=75888,75889,75890 (separados por coma).
    Devuelve [] si no se indicó."""
    for a in args:
        if a.startswith("--ids="):
            vals = a[len("--ids="):].split(",")
            return [v.strip() for v in vals if v.strip().isdigit()]
    return []

# Sólo tiene efecto en modo --solo-sql.
SQL_IDS = parse_sql_ids(sys.argv[1:]) if SQL_ONLY else []

# --- Idiomas efectivos del PASO 3 (subconjunto preseleccionado o lenguajes_activos) ---
def get_sql_languages():
    """Idiomas efectivos para el PASO 3 (SQL): subconjunto preseleccionado
    (lenguajes_activos_SQL) o, por defecto, lenguajes_activos. Conserva el ORDEN
    de lenguajes_activos."""
    if not lenguajes_activos_SQL or list(lenguajes_activos_SQL) == list(lenguajes_activos):
        return list(lenguajes_activos)
    # respeta el orden de lenguajes_activos y descarta códigos no activos
    sel = set(lenguajes_activos_SQL)
    return [l for l in lenguajes_activos if l in sel]

# --- Mapeo OPCIONAL código de idioma -> locale de la BD (PASO 3) ---
# Vacío => se usa el código corto tal cual (p.ej. 'en'). Si la BD usa 'en_GB',
# 'es_ES', etc., defínalo aquí para evitar UPDATEs que no casan ninguna fila.
LOCALE_MAP = {}   # p.ej. {"en": "en_GB", "es": "es_ES", "pt": "pt_PT"}

def db_locale(lang):
    """Devuelve el locale de BD para un código de idioma (identidad si no hay mapeo)."""
    return LOCALE_MAP.get(lang, lang)

# --- PASO 3 — POLÍTICA DE TRADUCCIONES ---
# Se MANTIENEN TODAS las traducciones/textos tal cual vienen del DAT, INCLUSO si
# Booking sirvió el INGLÉS como fallback. NINGUNA traducción se omite; la
# detección de fallback es sólo INFORMATIVA.
#   - False (por defecto): NO se omite ninguna traducción (requisito vigente).
#   - True: omitiría las que son fallback en inglés (NO recomendado aquí).
SKIP_ENGLISH_FALLBACK_TRANSLATIONS = False

# --- POLÍTICA DE TEXTO ---
# El texto se guarda y se usa EXACTAMENTE como se extrae. NO se elimina ni
# transforma nada (ni contaminación de interfaz, ni medios/URLs, ni saltos de
# línea). La limpieza se hará en una actualización posterior (proceso
# "Format_DAT"), entre el PASO 2 (DAT) y el PASO 3 (SQL), sin modificar el DAT.
# (No implementado en esta revisión.)

# --- Scripts no latinos presentes en lenguajes_activos (sólo informativo/trazabilidad) ---
LANGS_CJK = {"zh", "ja", "ko", "th"}
LANGS_RTL = {"ar"}

def validate_language_config():
    """
    Verifica en arranque la configuración de idiomas e informa del alcance real.
    - AVISA (no aborta) si algún idioma de lenguajes_activos NO tiene plantilla
      de URL en `lenguajes`: lo OMITE de la lista activa y continúa con el resto.
      El aviso es VISIBLE, así que no hay scrapes silenciosamente omitidos.
    - Sólo aborta si, tras el filtrado, no queda NINGÚN idioma activo válido.
    - Marca los scripts CJK/RTL para trazabilidad. La extracción es independiente
      del script (JSON-LD + atributos), por lo que estos idiomas no requieren
      ajustes.
    """
    # --- AVISO: idioma(s) activo(s) SIN plantilla de URL en `lenguajes` ---
    sin_plantilla = [l for l in lenguajes_activos if l not in lenguajes]
    if sin_plantilla:
        print(f"[AVISO] Idioma(s) activo(s) SIN plantilla de URL en 'lenguajes': "
              f"{sin_plantilla}. Se OMITEN del scraping. Añada su plantilla en "
              f"'lenguajes' o quítelos de 'lenguajes_activos'.")
        # Se retiran de la lista activa (mutación in situ -> afecta a todo el
        # pipeline) para no provocar errores al construir la URL.
        lenguajes_activos[:] = [l for l in lenguajes_activos if l in lenguajes]
    if not lenguajes_activos:
        print("[FATAL] No queda ningún idioma activo con plantilla de URL válida.")
        sys.exit(1)
    # lenguajes_activos_SQL (si se usa) debe ser subconjunto de lenguajes_activos
    if lenguajes_activos_SQL:
        fuera = [l for l in lenguajes_activos_SQL if l not in lenguajes_activos]
        if fuera:
            print(f"[FATAL] lenguajes_activos_SQL contiene idiomas no activos: {fuera}")
            sys.exit(1)
    cjk = sorted(set(lenguajes_activos) & LANGS_CJK)
    rtl = sorted(set(lenguajes_activos) & LANGS_RTL)
    print(f"[OK] Config de idiomas válida: {len(lenguajes_activos)} idiomas activos.")
    print(f"     SQL: {len(get_sql_languages())} idioma(s) -> {get_sql_languages()}")
    print(f"     CJK: {cjk or 'ninguno'} | RTL: {rtl or 'ninguno'} "
          f"(extracción JSON-LD/atributos, independiente del script).")

# ============================================================

# --- VPN / red ---
ENABLE_VPN = True          # False = no usar NordVPN (útil para pruebas)
VPN_REQUIRED = False       # True = si la VPN falla se OMITE el hotel;
                           # False = continúa sin VPN (no se pierden datos en silencio)

# --- Sobrescritura ---
# REGLA: los archivos (HTML, DAT, SQL) SIEMPRE se sobrescriben, sin comprobación
# ni confirmación. La escritura es atómica (_safe_write).

# --- Guardado del HTML de respaldo (carpeta html_downloads) ---
# El DOM SIEMPRE se descarga (de él se extrae el DAT); este flag sólo decide si
# además se GUARDA en disco el HTML como respaldo/trazabilidad.
#   HTML_DOWNLOAD = True          -> SÍ guarda las páginas HTML
#   HTML_DOWNLOAD = cualquier otro valor -> NO guarda las páginas HTML
HTML_DOWNLOAD = True

# --- Mapeo ORM / esquema (evita desincronización silenciosa) ---
TRANSLATIONS_TABLE = "accommodation_translations"
TRANSLATIONS_OBJECT_CLASS = "Application\\ModelBundle\\Entity\\Hotel"  # Nombre de clase Doctrine (FQCN)
TRANSLATIONS_FIELD = "longDescription"


# Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Stealth (opcional)
try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# --- COMPROBACIÓN DE ADMINISTRADOR (sólo Windows) ---
def is_admin():
    if os.name != "nt":
        return True  # En Linux/Mac no se exige admin; 
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

if not SQL_ONLY and not is_admin():
    print("ERROR: Ejecuta como ADMINISTRADOR.")
    sys.exit(1)

# Indicador de plataforma para subprocess (CREATE_NO_WINDOW sólo existe en Windows)
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# --- CONFIGURACIÓN ---
NORDVPN_PATH = r"C:\Program Files\NordVPN\nordvpn.exe"

VPN_COUNTRIES = [
    "Jersey", "Glasgow", "Adelaide", "Argentina", "Brasil", "Brisbane",
    "Melbourne", "Perth", "Sydney", "Sweden", "Switzerland", "Belgium",
    "Denmark", "Norway", "Poland", "Ireland", "Czech Republic", "Cyprus",
    "Finland", "Serbia", "Austria", "Slovakia", "France", "Slovenia",
    "Bulgaria", "Hungary", "Latvia", "Romania", "Spain", "Germany",
    "Portugal", "Luxembourg", "Italy", "Greece", "Estonia", "Iceland",
    "Albania", "Croatia", "Moldova", "Georgia", "Lithuania", "Canada",
    "Barcelona", "United States"
]

OUTPUT_DIR = "html_downloads"
DIAG_DIR = "html_diagnostic"
DAT_DIR = "data"
SQL_DIR = "data"
if HTML_DOWNLOAD is True:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DIAG_DIR, exist_ok=True)
os.makedirs(DAT_DIR, exist_ok=True)
os.makedirs(SQL_DIR, exist_ok=True)

# --- COMPROBACIÓN DE Playwright (no requerida en modo --solo-sql) ---
if not PLAYWRIGHT_AVAILABLE and not SQL_ONLY:
    print("[FATAL] Playwright no instalado.")
    print("  1. pip install playwright")
    print("  2. playwright install chromium")
    sys.exit(1)

if PLAYWRIGHT_AVAILABLE:
    print("[OK] Playwright disponible")
    if STEALTH_AVAILABLE:
        print("[OK] playwright-stealth disponible")
    else:
        print("[INFO] playwright-stealth NO instalado. Usando stealth manual.")

# ============================================================
# --- FILTRO DE DOMINIO: sólo Booking.com
# ============================================================
def is_booking_url(url):
    """
    True sólo si el host pertenece a booking.com (incluye subdominios
    como www.booking.com o secure.booking.com). Descarta cualquier otro.
    """
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "booking.com" or host.endswith(".booking.com")

# ============================================================
# --- CARGADOR CSV ( 3 campos: id, idioma_predeterminado, url)
# ============================================================
def load_urls_from_csv(csv_path="list_url.csv", max_urls=MAX_URLS_DOWNLOAD):
    """
    FLUJO PASO 1 — Filtrado y descarga.
    Lee list_url.csv (2 columnas: id,url_base), CONSERVA sólo las URLs de
    Booking.com, DESCARTA el resto y luego aplica el límite max_urls
    (MAX_URLS_DOWNLOAD). Orden: parse -> filtro Booking -> límite.

    NOTA: el CSV ya NO incluye columna de idioma. El idioma por defecto del
    sistema de destino es DEFAULT_LANG ('en'). Por compatibilidad, si una fila
    trae 3 columnas (formato antiguo id,idioma,url) se toma la ÚLTIMA como URL.
    Devuelve tuplas (id, url_base).
    """
    parsed = []
    if not os.path.exists(csv_path):
        print(f"[FATAL] No se encontró {csv_path}")
        sys.exit(1)

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].strip().startswith('#'):
                continue
            if len(row) >= 2:
                # La URL es SIEMPRE la última columna (tolera el formato antiguo).
                hotel_id, url_base = row[0].strip(), row[-1].strip()
            else:
                continue
            if hotel_id and url_base:
                parsed.append((hotel_id, url_base))

    total_parsed = len(parsed)

    # --- Filtro Booking.com (descarta cualquier otra URL) ---
    entries = []
    descartadas = []
    for e in parsed:
        if is_booking_url(e[1]):
            entries.append(e)
        else:
            descartadas.append(e)

    for hid, u in descartadas:
        print(f"[FILTER] Descartada (no Booking.com): ID={hid} URL={u}")

    print(f"[OK] CSV: {total_parsed} filas | Booking.com: {len(entries)} | descartadas: {len(descartadas)}")

    # --- Límite de descarga ---
    if max_urls is not None and len(entries) > max_urls:
        print(f"[OK] Limitado a MAX_URLS_DOWNLOAD={max_urls} (de {len(entries)})")
        entries = entries[:max_urls]

    print(f"[OK] Idiomas activos: {lenguajes_activos}")
    print(f"[OK] Scrapes totales a realizar: {len(entries) * len(lenguajes_activos)}")
    return entries

# ============================================================
# --- CONSTRUCTOR DE URL
# ============================================================
def build_language_url(url_base, lang_code):
    """
    Construye URL final para un idioma específico.
    Sólo elimina el .html FINAL.
    """
    if lang_code not in lenguajes:
        raise ValueError(f"Código de idioma no válido: {lang_code}")

    url_sin_html = re.sub(r'\.html$', '', url_base)
    url_final = f"{url_sin_html}.{lenguajes[lang_code]}"
    return url_final

def extract_name_from_url(url_base):
    """Extrae el nombre del hotel desde el slug de la URL."""
    last_segment = url_base.split('/')[-1]
    name = re.sub(r'\.html$', '', last_segment)
    return name or "unknown"

# ============================================================
# --- ANALIZADOR DE PUNTUACIÓN (SCORE)
# ============================================================
def parse_score(score_text):
    """Extrae el valor numérico del score de cualquier idioma."""
    if not score_text:
        return ""
    match = re.search(r'(\d+[.,]\d+)', score_text)
    if match:
        return match.group(1).replace(',', '.')
    return ""

# ============================================================
# --- DERIVACIÓN DE CIUDAD (corrección de mapeo de dirección — Finding M1)
# ============================================================
def derive_city(street_address, postal_code):
    """
    Devuelve la CIUDAD a partir de la dirección completa (JSON-LD streetAddress).

    Motivo (M1): en Booking, el campo JSON-LD `addressLocality` NO contiene la
    ciudad sino la CALLE (p. ej. "Schubertring 10-12"). La ciudad real sólo
    aparece dentro de `streetAddress`, en el segmento que sigue al código postal:
        "<calle>, <distrito>, <CP> <Ciudad>, <País>"
    El código postal es numérico e independiente del idioma, por lo que sirve de
    ancla fiable en todos los idiomas:
        "1010 Vienna" / "1010 Wien" / "1010 ウィーン" / "1010 维也纳" ...

    Esto NO es limpieza de contenido: es un mapeo estructurado de un campo de
    metadatos. NO inventa datos: si no puede determinar la ciudad con fiabilidad,
    devuelve "" (cadena vacía).
    """
    if not street_address or not postal_code:
        return ""
    m = re.search(re.escape(str(postal_code)) + r'\s+([^,]+)', str(street_address))
    if not m:
        return ""
    return m.group(1).strip()

# ============================================================
# --- LIMPIEZA DE TEXTO: NO se realiza en esta revisión
# ============================================================
# POLÍTICA (vigente): el texto se guarda en el DAT y se vuelca al SQL EXACTAMENTE
# como se extrae del origen url/idioma. NO se elimina ni transforma nada. El DAT
# es un reflejo fiel del contenido de la página.
#
# La limpieza de textos contaminados (atribución "OpenStreetMap", widgets de
# valoración, medios/URLs, etc.) se implementará en una ACTUALIZACIÓN POSTERIOR
# como un proceso independiente llamado "Format_DAT", que se aplicará DESPUÉS del
# PASO 2 (DAT) y ANTES del PASO 3 (SQL): NO modificará el DAT en disco, pero sus
# resultados sí se reflejarán en el SQL. (No implementado en esta revisión.)

# ============================================================
# --- AYUDANTE DE ESCAPADO SQL (MariaDB: escapa barra invertida y comilla)
# ============================================================
def sql_escape(text):
    """
    Escapa para literales de cadena MariaDB/MySQL (modo por defecto).
    IMPORTANTE: el backslash debe escaparse PRIMERO. con '\\'.
    """
    if not text:
        return ""
    text = text.replace("\\", "\\\\")   # barra invertida primero
    text = text.replace("'", "\\'")     # comilla simple
    text = text.replace("\x00", "")     # NUL no permitido
    return text

# ============================================================
# --- ESCRITURA SEGURA (evita fallos silenciosos por bloqueo de archivo)
# ============================================================
def _safe_write(path, content, encoding='utf-8', retries=3, delay=1.5):
    """
    Escribe `content` en `path` de forma robusta frente a BLOQUEOS DE ARCHIVO,
    típicos en Windows cuando el HTML/DAT/SQL está abierto en otro programa
    (Editor/Excel/Bloc de notas) -> PermissionError [WinError 32].
    Reintenta y, si persiste, AVISA claramente en lugar de fallar en silencio.
    Escritura atómica (archivo temporal + os.replace) para no dejar ficheros
    a medias si el proceso se interrumpe.
    """
    tmp = f"{path}.tmp"
    last_err = None
    for intento in range(1, retries + 1):
        try:
            with open(tmp, 'w', encoding=encoding, newline='') as f:
                f.write(content)
            os.replace(tmp, path)   # atómico en el mismo volumen
            return True
        except PermissionError as e:
            last_err = e
            print(f"  -> [LOCK] '{path}' bloqueado (¿abierto en otro programa?). "
                  f"Reintento {intento}/{retries} en {delay}s...")
            time.sleep(delay)
        except Exception as e:
            last_err = e
            break
    # limpieza del temporal si quedó
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    print(f"  -> [ERROR] No se pudo escribir '{path}': {str(last_err)[:120]}")
    return False

# ============================================================
# --- VPN
# ============================================================
def get_public_ip():
    """Devuelve la IP pública. Funciona con o sin 'requests' (fallback urllib)."""
    try:
        import requests as std_requests
        return std_requests.get('https://api.ipify.org', timeout=5).text.strip()
    except ImportError:
        try:
            import urllib.request
            with urllib.request.urlopen('https://api.ipify.org', timeout=5) as r:
                return r.read().decode('utf-8').strip()
        except Exception:
            return None
    except Exception:
        return None

def connect_vpn(country):
    if not ENABLE_VPN:
        return True
    print(f"\n[VPN] Conectando a: {country}...")
    try:
        subprocess.run([NORDVPN_PATH, "-d"], creationflags=_CREATE_NO_WINDOW)
        time.sleep(3)
        ip_antes = get_public_ip()
        print(f"  -> IP inicial: {ip_antes}")
        subprocess.run([NORDVPN_PATH, "-c", "-g", country], creationflags=_CREATE_NO_WINDOW)
    except FileNotFoundError:
        print(f"  -> [WARN] NordVPN no encontrado en {NORDVPN_PATH}")
        return False

    print("  -> Esperando cambio de IP ", end="", flush=True)
    for i in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        ip_ahora = get_public_ip()
        if ip_ahora and ip_antes and ip_ahora != ip_antes:
            print(f"\n  -> ÉXITO! IP: {ip_ahora}")
            return True
    print("\n  -> ERROR: IP no cambió (o no se pudo medir).")
    return False

def disconnect_vpn():
    if not ENABLE_VPN:
        return
    try:
        subprocess.run([NORDVPN_PATH, "-d"], creationflags=_CREATE_NO_WINDOW)
    except Exception:
        pass

# ============================================================
# --- VALIDACIÓN
# ============================================================
def is_valid_hotel_page(html, url):
    """Verifica si el HTML contiene contenido real de hotel (no challenge/bloqueo)."""
    if len(html) < 50000:
        return False, "Contenido muy corto (< 50K)"

    markers = [
        r'data-testid="property-header"',
        r'data-testid="property-section--property"',
        r'class="hp__hotel_title"',
        r'"hotelDescription"',
        r'"hotelFacilities"',
        r'property-card',
        r'hp__important_facility',
        r'hp-description',
        r'hp__hotel_name',
        r'hotel_header',
        r'id="basiclayout"',
        r'class="bui-grid__column"',
    ]
    found = sum(1 for m in markers if re.search(m, html, re.IGNORECASE))
    if found >= 2:
        return True, f"Marcadores encontrados: {found}"
    if len(html) > 500000:
        return True, "Contenido muy extenso (> 500K), asumiendo válido"
    return False, f"Marcadores insuficientes: {found}"

# ============================================================
# --- GESTOR DE CONSENTIMIENTO DE COOKIES
# ============================================================
def handle_cookie_consent(page):
    """Acepta/elimina banners de OneTrust. Usa wait_for (no is_visible)."""
    selectors = [
        "#onetrust-accept-btn-handler",
        "#onetrust-pc-btn-handler",
        ".ot-privacy-button",
        "button[id*='onetrust']",
        "button[class*='accept']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=2000)
            print(f"  -> [COOKIE] Click en: {sel}")
            loc.click()
            page.wait_for_timeout(1500)
            return True
        except Exception:
            continue
    return False

# ============================================================
# --- SCRIPT STEALTH MANUAL
# ============================================================
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
    get: () => ({ query: () => Promise.resolve({ state: 'prompt' }) })
});
if (navigator.__proto__) delete navigator.__proto__.webdriver;
"""

# ============================================================
# --- HELPER DE LECTURA SEGURA (reemplaza is_visible con timeout ignorado)
# ============================================================
def _read_text(page, selector, timeout=2500):
    """
    Devuelve el inner_text de la PRIMERA coincidencia esperando a que exista,
    o "" si no aparece. Evita el race condition de is_visible(timeout=...)
    (cuyo timeout Playwright IGNORA).
    """
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="attached", timeout=timeout)
        txt = loc.inner_text().strip()
        return txt
    except Exception:
        return ""

def _read_all_text(page, selector, timeout=2500, min_len=20):
    """Devuelve el texto unido de TODAS las coincidencias (multi-párrafo)."""
    try:
        loc = page.locator(selector)
        loc.first.wait_for(state="attached", timeout=timeout)
        parts = [t.strip() for t in loc.all_inner_texts() if t and t.strip()]
        joined = "\n".join(parts).strip()
        return joined if len(joined) >= min_len else ""
    except Exception:
        return ""

def _attr(page, selector, attr, timeout=1500):
    """Atributo de la primera coincidencia (sin exigir visibilidad)."""
    try:
        loc = page.locator(selector).first
        if loc.count() == 0:
            return ""
        v = loc.get_attribute(attr)
        return v.strip() if v else ""
    except Exception:
        return ""

def _section_css(page, selectors, timeout=2500, min_len=1):
    """
    Lee el texto de la PRIMERA selección CSS (de una lista en orden de
    preferencia) que exista y tenga contenido. Sustituye a los XPaths ABSOLUTOS
    (frágiles ante cambios de maquetación de Booking) por selectores ESTABLES
    basados en id / data-testid / clase, independientes del idioma/script.

    Orden recomendado: del más específico/limpio (contenedor de contenido
    [data-testid="property-section--content"]) al más amplio (wrapper de la
    sección) como respaldo. Devuelve '' si ninguno aplica.
    """
    for i, sel in enumerate(selectors):
        try:
            loc = page.locator(sel).first
            if i == 0:
                # En el preferido esperamos a que la sección esté presente.
                try:
                    loc.wait_for(state="attached", timeout=timeout)
                except Exception:
                    pass
            if loc.count() == 0:
                continue
            t = loc.inner_text().strip()
            if len(t) >= min_len:
                return t
        except Exception:
            continue
    return ""

_JSONLD_HOTEL_TYPES = {"Hotel", "LodgingBusiness", "BedAndBreakfast",
                       "Resort", "Motel", "Hostel", "Apartment"}

def _ld_is_hotel(obj):
    if not isinstance(obj, dict):
        return False
    t = obj.get("@type", "")
    types = t if isinstance(t, list) else [t]
    return any(x in _JSONLD_HOTEL_TYPES for x in types)

def read_jsonld_hotel(page):
    """
    Lee el bloque JSON-LD schema.org/Hotel (fuente estable entre idiomas).
    Recorre TODOS los bloques ld+json y elige el de @type Hotel/LodgingBusiness
    (Booking puede anteponer un BreadcrumbList u otros). Si ninguno casa, usa el
    primer dict como respaldo. Evita devolver datos vacíos/erróneos en silencio.
    """
    try:
        loc = page.locator('script[type="application/ld+json"]')
        n = loc.count()
        first_dict = {}
        for i in range(n):
            try:
                raw = loc.nth(i).text_content(timeout=2500)
            except Exception:
                continue
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            candidatos = obj if isinstance(obj, list) else [obj]
            for c in candidatos:
                if _ld_is_hotel(c):
                    return c
                if not first_dict and isinstance(c, dict):
                    first_dict = c
        return first_dict
    except Exception:
        return {}

# Plantilla de campos (usada también al inicializar en la descarga)
DATA_FIELDS = [
    "hotel_name", "hotel_description", "meta_name", "hotel_score",
    "review_word", "review_count", "address_full", "street_address",
    "postal_code", "city", "locality", "region", "country",
    "latitude", "longitude", "image_main", "booking_hotel_id",
    "servicios", "normas_casa", "info_importante", "info_destacada",
]

def empty_record():
    return {k: "" for k in DATA_FIELDS}

# ============================================================
# --- EXTRACTORES (JSON-LD primero, luego DOM; sin reinterpretar valores)
# ============================================================
def extract_hotel_data(page, lang):
    """
    Extrae los campos del DOM de Booking.com TAL CUAL aparecen en la página
    (sin normalizar entre idiomas). Prioriza JSON-LD (estable) y usa el DOM
    visible / XPath como respaldo o para campos no presentes en JSON-LD.
    """
    data = empty_record()
    ld = read_jsonld_hotel(page)
    addr = ld.get("address", {}) if isinstance(ld.get("address"), dict) else {}
    agg = ld.get("aggregateRating", {}) if isinstance(ld.get("aggregateRating"), dict) else {}

    # --- NOMBRE DEL HOTEL (JSON-LD -> h2.pp-header__title) ---
    data["hotel_name"] = ld.get("name", "") or _read_text(
        page, 'h2[class*="pp-header__title"]') or _read_text(
        page, 'h2[data-testid="property-header"]')

    # --- DESCRIPCIÓN (nodo directo -> respaldos -> JSON-LD) ---
    # El nodo data-testid="property-description" ES el propio <p>, así que un
    # selector de <p> DESCENDIENTE no resuelve nada: se lee el elemento
    # directamente. NO se usa "#basiclayout p" como respaldo porque arrastra
    # párrafos ajenos (atribución OSM, coletilla de valoración de ubicación).
    for sel in ['[data-testid="property-description"]',
                '[data-testid="property-description"] p',
                '#property-description p',
                '.hp-description p']:
        txt = _read_all_text(page, sel, min_len=20)
        if txt:
            data["hotel_description"] = txt
            break
    if not data["hotel_description"]:
        data["hotel_description"] = ld.get("description", "")
    # SIN limpieza aquí: el DAT guarda el texto CRUDO tal cual se extrae.
    # La limpieza (proceso "Format_DAT") se implementará en una actualización
    # posterior, entre el DAT y el SQL, sin modificar el DAT.

    # --- META DESCRIPCIÓN ---
    data["meta_name"] = (_attr(page, 'meta[name="description"]', 'content')
                         or _attr(page, 'meta[property="og:description"]', 'content'))

    # --- PUNTUACIÓN / RESEÑAS ---
    # score numérico: JSON-LD ratingValue -> div aria-hidden del componente
    data["hotel_score"] = str(agg.get("ratingValue", "")) or _read_text(
        page, '[data-testid="review-score-component"] div[aria-hidden="true"]')
    data["review_count"] = str(agg.get("reviewCount", ""))
    # palabra cualitativa (cambia por idioma; se toma tal cual)
    comp = _read_text(page, '[data-testid="review-score-component"]')
    if comp:
        # 1) preferir la línea con separador "·" -> "Fabulous · 5,718 reviews"
        for line in comp.splitlines():
            if "·" in line:
                data["review_word"] = line.split("·")[0].strip()
                break
        # 2) si no hay "·", primera línea sin dígitos
        if not data["review_word"]:
            for line in comp.splitlines():
                line = line.strip()
                if line and not any(ch.isdigit() for ch in line):
                    data["review_word"] = line
                    break
        if not data["review_count"]:
            m = re.search(r'([\d.,]+)\s*\w*review', comp, re.IGNORECASE)
            if m:
                data["review_count"] = m.group(1).replace(",", "").replace(".", "")

    # --- DIRECCIÓN ---
    data["address_full"] = _read_text(
        page, '[data-testid="PropertyHeaderAddressDesktop-wrapper"]')
    data["street_address"] = addr.get("streetAddress", "")
    data["postal_code"] = addr.get("postalCode", "")
    # M1: `addressLocality` de Booking contiene la CALLE, no la ciudad. Se
    # conserva tal cual como `locality` (valor crudo etiquetado, fiel al origen)
    # y la CIUDAD real se deriva de `streetAddress` con el CP como ancla.
    data["locality"] = addr.get("addressLocality", "")  # crudo: en Booking suele ser la calle
    city = derive_city(addr.get("streetAddress", ""), addr.get("postalCode", ""))
    # Salvaguarda: nunca dejar la calle como ciudad (city != calle/locality).
    if city and city == data["locality"]:
        city = ""
    data["city"] = city
    data["region"] = addr.get("addressRegion", "")
    data["country"] = addr.get("addressCountry", "")

    # --- COORDENADAS (sólo en el DOM, no en JSON-LD) ---
    latlng = _attr(page, '[data-atlas-latlng]', 'data-atlas-latlng')
    if latlng and "," in latlng:
        lat, lng = latlng.split(",", 1)
        data["latitude"], data["longitude"] = lat.strip(), lng.strip()

    # --- IMAGEN PRINCIPAL (URL conservada como metadato, NO sanitizada) ---
    data["image_main"] = _attr(page, 'meta[property="og:image"]', 'content')

    # --- ID INTERNO DE BOOKING (distinto del id de BD/CSV) ---
    data["booking_hotel_id"] = (_attr(page, 'input[name="hotel_id"]', 'value')
                                or _attr(page, '[data-hotel-id]', 'data-hotel-id'))

    # --- SECCIONES (selectores ESTABLES por id/data-testid/clase) ---
    # Cada lista va del selector más limpio/específico (contenedor de contenido)
    # al más amplio (wrapper de sección) como respaldo. Mapeado del DOM real de
    # Booking; independiente del idioma/script (validado en CJK y RTL).
    data["servicios"] = _section_css(page, [
        '#hp_facilities_box [data-testid="property-section--content"]',
        '#hp_facilities_box',
    ])
    data["normas_casa"] = _section_css(page, [
        '[data-testid="HouseRules-wrapper"] [data-testid="property-section--content"]',
        '#hp_policies_box [data-testid="property-section--content"]',
        '[data-testid="HouseRules-wrapper"]',
        '#policies',
    ])
    data["info_importante"] = _section_css(page, [
        '#important_info [data-testid="property-section--content"]',
        '[data-testid="PropertyFinePrintDesktop-wrapper"] [data-testid="property-section--content"]',
        '#important_info',
    ])
    data["info_destacada"] = _section_css(page, [
        '.property-highlights .ph-sections',
        '.property-highlights',
    ])

    # Avisos si faltan campos críticos
    if not data["hotel_name"]:
        print(f"  -> [WARN {lang.upper()}] hotel_name VACÍO (revisar selectores)")
    if not data["hotel_description"]:
        print(f"  -> [WARN {lang.upper()}] hotel_description VACÍO (revisar selectores)")

    print(f"  -> [EXTRACT {lang.upper()}] name=\"{data['hotel_name'][:40] or 'N/A'}\" | "
          f"desc={len(data['hotel_description'])} | score={data['hotel_score'] or 'N/A'} | "
          f"reviews={data['review_count'] or 'N/A'} | serv={len(data['servicios'])} | "
          f"normas={len(data['normas_casa'])} | imp={len(data['info_importante'])} | "
          f"dest={len(data['info_destacada'])}")
    return data

# ============================================================
# --- CONSTRUCTOR DAT
# ============================================================
# REGLA (requisito): el DAT (PASO 2) guarda los textos EXACTAMENTE como se
# extraen del scraping, SIN formato (no se añade <br />, no se normaliza) y SIN
# limpieza. El DAT es un reflejo FIEL del contenido url/idioma. Cualquier
# limpieza (proceso "Format_DAT") se hará DESPUÉS, entre el DAT y el SQL, sin
# modificar el DAT. El DAT no se modifica salvo nueva adquisición.

# Campos clave para decidir si un registro está "vacío" (preservación del DAT).
_KEY_FIELDS = ("hotel_name", "hotel_description")

def _is_empty_record(rec):
    """True si el registro carece de los campos clave (no hubo adquisición útil)."""
    if not isinstance(rec, dict):
        return True
    return not any(str(rec.get(k, "")).strip() for k in _KEY_FIELDS)

def build_dat_structure(hotel_id, name, url_base, all_lang_data):
    """
    FLUJO PASO 2 — Estructura DAT (JSON) basada en el DOM, agrupada por ID.
    Relación directa: ID -> DOM estructurado -> DAT. Los campos se guardan TAL
    CUAL por idioma (sin formato, sin normalización cruzada, sin limpieza).
    El idioma por defecto registrado es DEFAULT_LANG (ya no proviene del CSV).
    """
    now = datetime.now(timezone.utc)
    dat = {
        "id": hotel_id,
        "name": name,
        "scraped_at": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat() + "Z",
        "url": url_base,
        "default_language": DEFAULT_LANG,
        "hotels": {}
    }
    for lang, d in all_lang_data.items():
        # CRUDO: el valor se guarda exactamente como se extrajo (str(...) defensivo).
        dat["hotels"][lang] = {k: ("" if d.get(k) is None else str(d.get(k))) for k in DATA_FIELDS}
    return dat

def _merge_preserve_existing(dat_structure):
    """
    Preservación del DAT: si un registro de idioma del DAT nuevo está VACÍO
    (no hubo nueva adquisición: HTML omitido o extracción fallida) y existe un
    DAT previo con datos para ese idioma, se CONSERVA el registro previo en
    lugar de pisarlo con vacío. Evita pérdida de datos silenciosa. (Finding 2.)
    """
    if not PRESERVE_DAT_ON_EMPTY:
        return dat_structure
    hotel_id = dat_structure.get("id", "")
    path = os.path.join(DAT_DIR, f"DAT__{hotel_id}_.json")
    if not os.path.exists(path):
        return dat_structure
    try:
        with open(path, 'r', encoding='utf-8') as f:
            old = json.load(f)
    except Exception as e:
        print(f"  -> [WARN] No se pudo leer DAT previo para preservar: {str(e)[:80]}")
        return dat_structure
    old_hotels = old.get("hotels", {}) if isinstance(old, dict) else {}
    preserved = 0
    for lang, rec in list(dat_structure.get("hotels", {}).items()):
        if _is_empty_record(rec) and lang in old_hotels and not _is_empty_record(old_hotels[lang]):
            dat_structure["hotels"][lang] = old_hotels[lang]
            preserved += 1
    if preserved:
        print(f"  -> [PRESERVE] {preserved} idioma(s) sin nueva adquisición; "
              f"se conservan datos previos del DAT (no se pisan con vacío).")
    return dat_structure

def write_dat_file(hotel_id, dat_structure):
    """
    Escribe el DAT como JSON puro. Nombre: DAT__<id>_.json
    Antes de escribir, preserva registros previos para idiomas sin adquisición.
    """
    dat_structure = _merge_preserve_existing(dat_structure)
    dat_path = os.path.join(DAT_DIR, f"DAT__{hotel_id}_.json")
    if os.path.exists(dat_path):
        print(f"  -> [OVERWRITE] {dat_path} existe; se sobrescribirá.")
    _safe_write(dat_path, json.dumps(dat_structure, indent=2, ensure_ascii=False))
    print(f"  -> [DAT] Guardado (JSON): {dat_path}")
    return dat_path

# ============================================================
# --- GENERADOR DE SQL UPDATE (MariaDB 10.1)
# ============================================================
_sql_file_counter = 0

def generate_sql_updates(dat_structures):
    """
    FLUJO PASO 3 — Genera SQL derivado del DAT (JSON) estructurado.
    El texto se usa TAL CUAL está en el DAT (sin limpieza; ver nota Format_DAT).
    Procesa en lotes de hasta MAX_SQL_BATCH. Garantiza consistencia
    ID <-> DAT <-> SQL. Nombre de archivo: SQL__<MMDD>_<lote>_.sql

    Notas:
      - Sólo idiomas de get_sql_languages() (lenguajes_activos_SQL o, por
        defecto, lenguajes_activos).
      - El idioma de la tabla `hotel` es DEFAULT_LANG (de momento 'en').
      - locale de BD vía db_locale() (mapeo opcional 'en' -> 'en_GB', etc.).
      - score numérico sin comillas si es un número válido.
      - La detección de fallback en inglés es SÓLO informativa (no se omite
        ninguna traducción): el contenido se toma tal cual del origen.
    """
    global _sql_file_counter
    if not dat_structures:
        return None

    sql_langs = get_sql_languages()
    sql_lines = ["START TRANSACTION;"]
    omitidos_fallback = 0
    fallback_en = 0

    for dat in dat_structures:
        hotel_id = dat.get("id", "")
        default_lang = dat.get("default_language", DEFAULT_LANG) or DEFAULT_LANG
        scraped_date = dat.get("scraped_at", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        hotels = dat.get("hotels", {})

        # Validación defensiva del id (se interpola en SQL sin comillas).
        if not str(hotel_id).isdigit():
            print(f"[SQL] [WARN] id no numérico, hotel omitido: {hotel_id!r}")
            continue

        score_value = ""
        for lang in [default_lang] + list(lenguajes_activos):
            if lang in hotels and hotels[lang].get("hotel_score"):
                score_value = parse_score(hotels[lang]["hotel_score"])
                if score_value:
                    break

        # Texto TAL CUAL del DAT (sin limpieza en esta revisión).
        default_desc = hotels.get(default_lang, {}).get("hotel_description", "")
        # Referencia inglesa para detectar fallbacks (idéntico => no es traducción).
        en_desc = hotels.get("en", {}).get("hotel_description", "")

        set_clauses = []
        if default_desc:
            set_clauses.append(f"    h.long_description = '{sql_escape(default_desc)}'")
        if score_value:
            # score como NÚMERO si es válido; si no, como string escapado.
            if re.fullmatch(r'\d+(\.\d+)?', score_value):
                set_clauses.append(f"    h.score_review = {score_value}")
            else:
                set_clauses.append(f"    h.score_review = '{sql_escape(score_value)}'")
        set_clauses.append(f"    h.updated_at = '{scraped_date}'")

        sql_lines.append("UPDATE hotel h SET")
        sql_lines.append(", ".join(set_clauses))
        sql_lines.append(f"WHERE h.id = {hotel_id} AND h.`language` = '{sql_escape(db_locale(DEFAULT_LANG))}';")

        for lang in sql_langs:
            desc = hotels.get(lang, {}).get("hotel_description", "")
            if not desc:
                continue
            # Detección de fallback en inglés (SÓLO informativa): el contenido se
            # mantiene tal cual; la gestión de traducciones se resolverá aparte.
            es_fallback = (lang != "en" and en_desc and desc == en_desc)
            if es_fallback:
                fallback_en += 1
                if SKIP_ENGLISH_FALLBACK_TRANSLATIONS:
                    omitidos_fallback += 1
                    continue
            sql_lines.append(
                f"UPDATE {TRANSLATIONS_TABLE} t SET t.content = '{sql_escape(desc)}' "
                f"WHERE t.foreign_key = {hotel_id} "
                f"AND t.object_class = '{sql_escape(TRANSLATIONS_OBJECT_CLASS)}' "
                f"AND t.field = '{TRANSLATIONS_FIELD}' AND t.locale = '{sql_escape(db_locale(lang))}';"
            )

    sql_lines.append("COMMIT;")

    if SKIP_ENGLISH_FALLBACK_TRANSLATIONS and omitidos_fallback:
        print(f"[SQL] Traducciones OMITIDAS por ser fallback en inglés: {omitidos_fallback}")
    elif fallback_en:
        print(f"[SQL] Traducciones en inglés (fallback) MANTENIDAS (no se omite ninguna): {fallback_en}")

    _sql_file_counter += 1
    stamp = datetime.now(timezone.utc).strftime("%m%d")
    sql_path = os.path.join(SQL_DIR, f"SQL__{stamp}_{_sql_file_counter:03d}_.sql")
    if os.path.exists(sql_path):
        print(f"[OVERWRITE] {sql_path} existe; se sobrescribirá.")
    _safe_write(sql_path, "\n".join(sql_lines))
    print(f"\n[SQL] Archivo UPDATE generado ({len(dat_structures)} IDs): {sql_path}")
    return sql_path

# ============================================================
# --- PASO 3 (INDEPENDIENTE): leer los DAT del DISCO y generar SQL por lotes
# ============================================================
def load_dat_files_from_disk(dat_dir=DAT_DIR, ids=None):
    """
    Lee los archivos DAT__<id>_.json de `dat_dir` y los devuelve como lista de
    estructuras DAT (dicts), ordenada por id.

    Si `ids` (lista de ids) viene informado, SÓLO se cargan esos ids; el resto
    se ignora. Los ids pedidos que no existan en disco se AVISAN por log.

    Ésta es la ÚNICA fuente del PASO 3: el SQL se deriva del DAT en disco
    (artefacto canónico), NO de datos en memoria. El HTML es sólo respaldo de
    adquisición; el DAT no se reconstruye desde el HTML salvo re-adquisición
    explícita (otro flujo).
    """
    dats = []
    if not os.path.isdir(dat_dir):
        print(f"[SQL] No existe el directorio de DAT: {dat_dir}")
        return dats

    id_set = set(str(x) for x in ids) if ids else None

    nombres = sorted(
        n for n in os.listdir(dat_dir)
        if n.startswith("DAT__") and n.endswith("_.json")
    )
    encontrados = set()
    for nombre in nombres:
        ruta = os.path.join(dat_dir, nombre)
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if isinstance(obj, dict) and obj.get("id"):
                if id_set is not None and str(obj.get("id")) not in id_set:
                    continue   # filtro de ids: se omite
                dats.append(obj)
                encontrados.add(str(obj.get("id")))
            else:
                print(f"[SQL] [WARN] DAT inválido o sin 'id', omitido: {nombre}")
        except Exception as e:
            print(f"[SQL] [WARN] No se pudo leer {nombre}: {str(e)[:120]}")

    # Orden estable por id (numérico si procede)
    def _key(d):
        i = str(d.get("id", ""))
        return (0, int(i)) if i.isdigit() else (1, i)
    dats.sort(key=_key)

    if id_set is not None:
        faltan = [i for i in id_set if i not in encontrados]
        if faltan:
            print(f"[SQL] [WARN] ids solicitados SIN DAT en disco (se omiten): {sorted(faltan)}")
        print(f"[SQL] DAT leídos del disco: {len(dats)} (filtro de {len(id_set)} id solicitados) en {dat_dir}")
    else:
        print(f"[SQL] DAT leídos del disco: {len(dats)} (en {dat_dir})")
    return dats

def run_sql_step(dat_dir=DAT_DIR, batch_size=MAX_SQL_BATCH, ids=None):
    """
    PASO 3 ejecutable de forma INDEPENDIENTE.
    Carga los DAT del disco (todos, o sólo los `ids` indicados) y genera SQL en
    lotes de hasta `batch_size` (MAX_SQL_BATCH). Devuelve la lista de rutas SQL
    generadas.
    """
    dats = load_dat_files_from_disk(dat_dir, ids=ids)
    if not dats:
        print("[SQL] No hay DAT que procesar; no se genera SQL.")
        return []

    rutas = []
    for i in range(0, len(dats), batch_size):
        lote = dats[i:i + batch_size]
        print(f"[SQL] Lote {len(rutas) + 1}: {len(lote)} IDs "
              f"({i + 1}-{i + len(lote)} de {len(dats)})")
        ruta = generate_sql_updates(lote)
        if ruta:
            rutas.append(ruta)
    print(f"[SQL] Lotes SQL generados: {len(rutas)}")
    return rutas

# ============================================================
# --- DESCARGA CON PLAYWRIGHT + REINTENTO + EXTRACCIÓN
# ============================================================
def download_with_playwright(browser, url, output_file, diag_file, lang, max_retries=2):
    """Descarga HTML con JS real + reintento y extrae datos del DOM."""
    print(f"  -> Playwright: {url}")
    extracted_data = empty_record()

    for attempt in range(1, max_retries + 1):
        print(f"  -> Intento {attempt}/{max_retries}")
        context = None
        status = 0
        html = ""
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Europe/London",
                extra_http_headers={
                    "Accept-Language": "en-GB,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                              "image/avif,image/webp,image/apng,*/*;q=0.8",
                },
            )
            if not STEALTH_AVAILABLE:
                context.add_init_script(STEALTH_SCRIPT)

            page = context.new_page()
            if STEALTH_AVAILABLE:
                try:
                    stealth_sync(page)
                except Exception as e:
                    print(f"  -> [WARN] stealth_sync falló: {e}")

            if attempt == 1:
                wait_strategy, nav_timeout = "load", 30000
            else:
                wait_strategy, nav_timeout = "networkidle", 45000

            print(f"  -> Navegando (wait_until={wait_strategy}, timeout={nav_timeout}ms)...")
            response = page.goto(url, wait_until=wait_strategy, timeout=nav_timeout)
            status = response.status if response else 0
            print(f"  -> HTTP {status} | URL: {page.url}")

            handle_cookie_consent(page)

            content_selectors = [
                'h2[data-testid="property-header"]',
                '#hotel_header',
                '.hp__hotel_name',
                '[data-testid="property-section--property"]',
                '#basiclayout',
                '.hp-description',
            ]
            content_found = False
            for sel in content_selectors:
                try:
                    page.locator(sel).first.wait_for(timeout=8000)
                    print(f"  -> [WAIT] Contenido detectado: {sel}")
                    content_found = True
                    break
                except Exception:
                    continue

            if not content_found and attempt < max_retries:
                print("  -> [WARN] No se detectó contenido real. Reintentando...")
                if context:
                    context.close()
                time.sleep(2 ** attempt)
                continue

            html = page.content()
            print(f"  -> HTML extraído: {len(html)} chars")

            valid, reason = is_valid_hotel_page(html, url)
            if valid:
                if HTML_DOWNLOAD is True:
                    _safe_write(output_file, html)
                    print(f"  -> [OK] {reason} | HTML guardado: {output_file}")
                else:
                    print(f"  -> [OK] {reason} | HTML NO guardado (HTML_DOWNLOAD desactivado)")
                extracted_data = extract_hotel_data(page, lang)
                if context:
                    context.close()
                return True, extracted_data
            else:
                if attempt < max_retries:
                    print(f"  -> [RETRY] {reason}. Reintentando...")
                    if context:
                        context.close()
                    time.sleep(2 ** attempt)
                    continue
                else:
                    with open(diag_file, 'w', encoding='utf-8') as f:
                        f.write(f"STATUS: {status}\n")
                        f.write(f"URL: {page.url}\n")
                        f.write(f"LENGTH: {len(html)}\n")
                        f.write(f"REASON: {reason}\n")
                        f.write(f"ATTEMPTS: {attempt}\n")
                        f.write(f"HTML (primeros 8000 chars):\n{html[:8000]}")
                    print(f"  -> [DIAG] {reason} | Guardado en: {diag_file}")
                    if context:
                        context.close()
                    return False, extracted_data

        except PlaywrightTimeout:
            print(f"  -> [ERROR {lang.upper()}] Timeout de Playwright | intento {attempt}/{max_retries} | URL: {url}")
            if context:
                context.close()
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, extracted_data
        except Exception as e:
            print(f"  -> [ERROR {lang.upper()}] {type(e).__name__}: {str(e)[:200]} | "
                  f"intento {attempt}/{max_retries} | URL: {url}")
            traceback.print_exc()   # traza completa al log (Tee)
            if context:
                context.close()
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, extracted_data

    return False, extracted_data

# ============================================================
# --- PRINCIPAL (MAIN)
# ============================================================
print("=" * 60)
print(" Playwright + Chromium + VPN v5.8")
print(" Multi-idioma | DAT | SQL Update | Retry | Cookie | Stealth | RCA-fixes")
print(f" MAX_URLS_DOWNLOAD={MAX_URLS_DOWNLOAD} | MAX_SQL_BATCH={MAX_SQL_BATCH} | VPN={ENABLE_VPN}")
print("=" * 60)

# Validación de configuración de idiomas (alcance real: 20 idiomas, incl. CJK/RTL).
validate_language_config()

# === MODO INDEPENDIENTE: sólo PASO 3 (SQL desde los DAT del disco) ===
# En --solo-sql el PASO 3 SIEMPRE se ejecuta (es su propósito). Si se indicaron
# ids, se procesan SÓLO esos; si no, TODOS los DAT en lotes de MAX_SQL_BATCH.
if SQL_ONLY:
    print("[MODE] --solo-sql: se OMITE el scraping (PASO 1+2). Sólo PASO 3.")
    if SQL_IDS:
        print(f"[PASO 3] Generando SQL para los ids indicados ({len(SQL_IDS)}): {SQL_IDS}")
    else:
        print(f"[PASO 3] Generando SQL para TODOS los DAT en disco (lotes de {MAX_SQL_BATCH}).")
    run_sql_step(DAT_DIR, MAX_SQL_BATCH, ids=SQL_IDS or None)
    print("Proceso (solo SQL) finalizado.")
    sys.exit(0)

url_entries = load_urls_from_csv("list_url.csv", MAX_URLS_DOWNLOAD)

success_count = 0
fail_count = 0
skipped_count = 0
dat_files_written = 0

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        print("[OK] Browser Chromium lanzado (reutilizable entre URLs)")

        for idx, (hotel_id, url_base) in enumerate(url_entries):
            name = extract_name_from_url(url_base)
            print(f"\n[PROCESS] {idx+1}/{len(url_entries)} "
                  f"ID={hotel_id} | DefaultLang={DEFAULT_LANG} | Name={name} | Base={url_base}")

            # Datos de este hotel SÓLO en memoria local: se libera al cambiar de URL.
            hotel_lang_data = {}

            # VPN por cada URL base
            pais = random.choice(VPN_COUNTRIES)
            if not connect_vpn(pais):
                if VPN_REQUIRED:
                    print(f"  -> [SKIP] VPN falló y VPN_REQUIRED=True. Saltando ID {hotel_id}")
                    skipped_count += 1
                    continue
                else:
                    print("  -> [WARN] VPN falló; continuando SIN VPN (VPN_REQUIRED=False)")

            for lang in lenguajes_activos:
                url_final = build_language_url(url_base, lang)
                print(f"\n  [LANG] {lang.upper()} -> {url_final}")

                filename = f"HTML__{hotel_id}__{lang}__{name}__.html"
                diagname = f"DIAG__{hotel_id}__{lang}__{name}__.txt"
                full_path = os.path.join(OUTPUT_DIR, filename)
                diag_path = os.path.join(DIAG_DIR, diagname)

                success, extracted_data = download_with_playwright(
                    browser, url_final, full_path, diag_path, lang
                )
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                hotel_lang_data[lang] = extracted_data

                time.sleep(random.randint(3, 7))

            # DAT por hotel (PASO 2): se escribe a disco como artefacto canónico
            if hotel_lang_data:
                dat_struct = build_dat_structure(hotel_id, name, url_base, hotel_lang_data)
                # Aviso: campos vacíos en TODOS los idiomas (sección ausente o
                # selector fallido) -> visibilidad para casos como info_importante.
                _hotels = dat_struct.get("hotels", {})
                if _hotels:
                    for _f in DATA_FIELDS:
                        if all(not str(_hotels.get(_l, {}).get(_f, "")).strip() for _l in _hotels):
                            print(f"  -> [WARN] Campo '{_f}' VACÍO en los {len(_hotels)} idiomas "
                                  f"del hotel {hotel_id} (¿sección ausente o selector fallido?)")
                write_dat_file(hotel_id, dat_struct)
                dat_files_written += 1

            # Liberar memoria del hotel antes de pasar a la siguiente URL.
            hotel_lang_data.clear()
            del hotel_lang_data

            print("-" * 60)
            time.sleep(random.randint(5, 12))

        browser.close()
        print("[OK] Browser cerrado")

    # === PASO 3: SQL leyendo los DAT del DISCO (sólo si SQL_GENERATE is True) ===
    if SQL_GENERATE is True:
        print("\n[PASO 3] Generando SQL a partir de los DAT en disco...")
        run_sql_step(DAT_DIR, MAX_SQL_BATCH)
    else:
        print("\n[PASO 3] DESACTIVADO (SQL_GENERATE no es True). "
              "DAT generados; SQL omitido. Ponga SQL_GENERATE = True para activarlo.")

finally:
    disconnect_vpn()
    print("\n" + "=" * 60)
    print(f" RESUMEN: {success_count} OK | {fail_count} FALLIDOS | {skipped_count} OMITIDOS")
    print(f" DAT files generados: {dat_files_written}")
    print("=" * 60)
    print("Proceso finalizado.")