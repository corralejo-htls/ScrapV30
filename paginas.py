"""
Booking.com scraper con Playwright v5.4 — Multi-idioma + DAT + SQL Update
Sin ChromeDriver, Sin Brave, Sin Selenium
Playwright descarga automáticamente Chromium compatible
Ejecuta JavaScript nativamente -> pasa AWS WAF Challenge
archivo con lista de url : list_url.csv (3 columnas : h.id , h.language, h.url)

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
       El HTML es sólo respaldo de adquisición; no se reprocesa el DAT desde el HTML salvo re-adquisición explícita.
    - Trazabilidad URL -> DOM -> DAT -> SQL.
    - Exclusión de imágenes, enlaces de imagen y URLs externas en los textos.
    - Escapado SQL robusto (backslash + comilla) para MariaDB 10.1.
    - VPN configurable (ENABLE_VPN / VPN_REQUIRED) para no perder datos en silencio.
    - REGLA de sobrescritura: HTML/DAT/SQL existentes se sobrescriben (OVERWRITE_EXISTING).
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

# ============================================================
# === PARÁMETROS PRINCIPALES (AL INICIO DEL CÓDIGO) ==========
# ============================================================

# --- PARÁMETROS INICIALES REQUERIDOS ---
# Límite de URLs (sólo Booking.com) a descargar desde list_url.csv
MAX_URLS_DOWNLOAD = 300
# Tamaño máximo de lote (IDs / URLs base) por archivo SQL
MAX_SQL_BATCH = 100

# --- MODO DE EJECUCIÓN ---
# El PASO 3 (SQL) lee SIEMPRE los DAT del disco. Además puede ejecutarse de
# forma INDEPENDIENTE, sin volver a scrapear, para regenerar el SQL a partir
# de los DAT existentes.  Uso:  python paginas.py --solo-sql  (o python paginas.py --sql-only)
SQL_ONLY = any(a in ("--solo-sql", "--sql-only") for a in sys.argv[1:])

# ============================================================
# --- CONFIGURACIÓN DE IDIOMAS
# ============================================================
# Alcance real del pipeline: 20 idiomas, incluidos scripts CJK
# (zh, ja, ko, th) y RTL (ar). La extracción primaria se apoya en JSON-LD y en
# atributos (data-testid / data-atlas-latlng), independientes del script, por
# lo que estos idiomas se tratan igual que los latinos. validate_language_config()
# verifica en arranque que todos tengan plantilla de URL en `lenguajes`.
lenguajes_activos = ["en","es","fr","it","de","pt","ar","nl","zh","tl","id","ms","ja","ko","th","hu","pl","no","fi","sv","da" ]

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
    "zh": "zh.html?lang=zh",
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
}

# Scripts no latinos presentes en lenguajes_activos (solo informativo/trazabilidad).
LANGS_CJK = {"zh", "ja", "ko", "th"}
LANGS_RTL = {"ar"}

def validate_language_config():
    """
    Verifica en arranque que TODOS los idiomas de lenguajes_activos tengan
    plantilla de URL en `lenguajes`. Falla rápido ante códigos desconocidos
    (evita scrapes silenciosamente omitidos). Informa del alcance real y marca
    los scripts CJK/RTL para trazabilidad. La extracción es independiente del
    script (JSON-LD + atributos), por lo que estos idiomas no requieren ajustes.
    """
    desconocidos = [l for l in lenguajes_activos if l not in lenguajes]
    if desconocidos:
        print(f"[FATAL] Idiomas en lenguajes_activos sin plantilla en 'lenguajes': {desconocidos}")
        sys.exit(1)
    cjk = sorted(set(lenguajes_activos) & LANGS_CJK)
    rtl = sorted(set(lenguajes_activos) & LANGS_RTL)
    print(f"[OK] Config de idiomas válida: {len(lenguajes_activos)} idiomas activos.")
    print(f"     CJK: {cjk or 'ninguno'} | RTL: {rtl or 'ninguno'} "
          f"(extracción JSON-LD/atributos, independiente del script).")

# ============================================================

# --- VPN / red ---
ENABLE_VPN = True          # False = no usar NordVPN (útil para pruebas)
VPN_REQUIRED = False       # True = si la VPN falla se OMITE el hotel;
                           # False = continúa sin VPN (no se pierden datos en silencio)

# --- Sobrescritura ---
# REGLA: si un archivo (HTML, DAT o SQL) ya existe, se SOBRESCRIBE , sin confirmación y sin omitir.
OVERWRITE_EXISTING = True

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

if not is_admin():
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
    Lee list_url.csv (id,idioma_predeterminado,url_base), CONSERVA sólo las
    URLs de Booking.com, DESCARTA el resto y luego aplica el límite max_urls
    (MAX_URLS_DOWNLOAD). Orden: parse -> filtro Booking -> límite.
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
            if len(row) >= 3:
                hotel_id, default_lang, url_base = row[0].strip(), row[1].strip(), row[2].strip()
            elif len(row) == 2:
                hotel_id, default_lang, url_base = row[0].strip(), "en", row[1].strip()
            else:
                continue
            if hotel_id and url_base:
                parsed.append((hotel_id, default_lang, url_base))

    total_parsed = len(parsed)

    # --- Filtro Booking.com (descarta cualquier otra URL) ---
    entries = []
    descartadas = []
    for e in parsed:
        if is_booking_url(e[2]):
            entries.append(e)
        else:
            descartadas.append(e)

    for hid, _lang, u in descartadas:
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
# --- SANITIZADOR: excluir imágenes, enlaces de imagen y URLs externas
# ============================================================
_IMG_TAG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
_MD_IMG_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)')
_URL_RE = re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE)
_IMG_EXT_RE = re.compile(r'\S+\.(?:png|jpe?g|gif|webp|svg|bmp|tiff?|ico|avif)\b', re.IGNORECASE)

def strip_media_and_links(text):
    """
    Elimina del texto cualquier imagen, enlace de imagen o URL externa.
    (Requisito: no procesar imágenes, enlaces de imagen ni URLs externas.)
    """
    if not text:
        return ""
    text = _IMG_TAG_RE.sub('', text)      # <img ...>
    text = _MD_IMG_RE.sub('', text)       # ![alt](src)
    text = _IMG_EXT_RE.sub('', text)      # foo.jpg, cdn/x.webp ...
    text = _URL_RE.sub('', text)          # http(s):// y www.
    # Normalizar espacios sobrantes que dejó la limpieza
    text = re.sub(r'[ \t]{2,}', ' ', text).strip()
    return text

# ============================================================
# --- REEMPLAZO DE SALTOS DE LÍNEA
# ============================================================
def replace_line_breaks(text):
    """Reemplaza saltos de línea por <br /> (tras sanitizar medios/URLs)."""
    if not text:
        return ""
    text = strip_media_and_links(text)
    text = text.replace('\r\n', '<br />')
    text = text.replace('\r', '<br />')
    text = text.replace('\n', '<br />')
    return text

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
# --- LIMPIEZA DE LA DESCRIPCIÓN (quita atribución/coletillas de interfaz)
# ============================================================
# Booking adosa al bloque de descripción texto que NO forma parte de la
# descripción del alojamiento. "OpenStreetMap" es una constante presente en
# todos los idiomas (atribución del cálculo de distancias). Al leer el nodo
# correcto (data-testid="property-description") normalmente ya no aparece, pero
# se elimina como salvaguarda independiente del idioma.
_DESC_BOILERPLATE_MARKERS = ("openstreetmap",)

def _strip_description_boilerplate(text):
    """
    Elimina líneas de interfaz/atribución adosadas a la descripción
    (p. ej. la atribución de distancias "... © OpenStreetMap"). Trabaja por
    líneas para no recortar contenido legítimo; conserva el resto intacto.
    """
    if not text:
        return ""
    kept = []
    for line in re.split(r'(?:\r\n|\r|\n)', text):
        low = line.strip().lower()
        if any(m in low for m in _DESC_BOILERPLATE_MARKERS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()

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

def _xpath_text(page, xp, timeout=2000):
    """inner_text de la primera coincidencia de un XPath, o '' si no aparece."""
    try:
        loc = page.locator(f"xpath={xp}").first
        loc.wait_for(state="attached", timeout=timeout)
        return loc.inner_text().strip()
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

def _section_text(page, primary_xp, anchor_id=None):
    """
    Lee una sección: intenta el XPath indicado y, si viene vacío, recurre
    al ancla por id (#anchor_id) que es estable entre páginas/idiomas.
    """
    t = _xpath_text(page, primary_xp)
    if not t and anchor_id:
        t = _xpath_text(page, f'//*[@id="{anchor_id}"]')
    return t

def read_jsonld_hotel(page):
    """Lee el bloque JSON-LD schema.org/Hotel (fuente estable entre idiomas)."""
    try:
        loc = page.locator('script[type="application/ld+json"]').first
        if loc.count() == 0:
            return {}
        raw = loc.text_content(timeout=2500)
        obj = json.loads(raw) if raw else {}
        return obj if isinstance(obj, dict) else {}
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
    # Salvaguarda: quita atribución/coletillas de interfaz que no son descripción.
    data["hotel_description"] = _strip_description_boilerplate(data["hotel_description"])

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
    data["city"] = addr.get("addressLocality", "")      # Booking no expone city aparte
    data["locality"] = addr.get("addressLocality", "")  # mismo tag schema.org
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

    # --- SECCIONES (XPaths indicados + ancla por id como respaldo) ---
    data["servicios"] = _section_text(
        page, '//*[@id="hp_facilities_box"]/div/section/div/div[2]/div[2]',
        anchor_id="hp_facilities_box")
    data["normas_casa"] = _section_text(
        page, '//*[@id="policies"]/div/div[2]', anchor_id="policies")
    data["info_importante"] = _section_text(
        page, '//*[@id="important_info"]/div/div[2]', anchor_id="important_info")
    data["info_destacada"] = _section_text(
        page, '//*[@id="basiclayout"]/div[1]/div[3]/div/div[2]/div/div[2]/div/div[1]')

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
# Campos de TEXTO largo: se les aplica replace_line_breaks (que ya sanitiza
# imágenes/URLs). El resto son valores cortos / metadatos.
_LONG_TEXT_FIELDS = {"hotel_description", "meta_name", "servicios",
                     "normas_casa", "info_importante", "info_destacada"}
# Campos que NO se sanitizan (URLs/valores que deben conservarse intactos).
_RAW_FIELDS = {"image_main", "latitude", "longitude", "booking_hotel_id",
               "postal_code", "hotel_score", "review_count"}

def _clean_field(key, value):
    value = value or ""
    if key in _RAW_FIELDS:
        return value
    if key in _LONG_TEXT_FIELDS:
        return replace_line_breaks(value)   # sanitiza medios/URLs + <br />
    return strip_media_and_links(value)

def build_dat_structure(hotel_id, name, url_base, default_lang, all_lang_data):
    """
    FLUJO PASO 2 — Estructura DAT (JSON) basada en el DOM, agrupada por ID.
    Relación directa: ID -> DOM estructurado -> DAT. los campos tomados tal cual por idioma (sin normalización cruzada).
    """
    now = datetime.now(timezone.utc)
    dat = {
        "id": hotel_id,
        "name": name,
        "scraped_at": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat() + "Z",
        "url": url_base,
        "default_language": default_lang,
        "hotels": {}
    }
    for lang, d in all_lang_data.items():
        dat["hotels"][lang] = {k: _clean_field(k, d.get(k, "")) for k in DATA_FIELDS}
    return dat

def write_dat_file(hotel_id, dat_structure):
    """
    Escribe el DAT como JSON puro. Nombre: DAT__<id>_.json
    """
    dat_path = os.path.join(DAT_DIR, f"DAT__{hotel_id}_.json")
    if os.path.exists(dat_path):
        print(f"  -> [OVERWRITE] {dat_path} existe; se sobrescribirá.")
    with open(dat_path, 'w', encoding='utf-8') as f:   # 'w' trunca/sobrescribe
        json.dump(dat_structure, f, indent=2, ensure_ascii=False)
    print(f"  -> [DAT] Guardado (JSON): {dat_path}")
    return dat_path

# ============================================================
# --- GENERADOR DE SQL UPDATE (MariaDB 10.1)
# ============================================================
_sql_file_counter = 0

def generate_sql_updates(dat_structures):
    """
    FLUJO PASO 3 — Genera SQL derivado del DAT (JSON) estructurado.
    Procesa en lotes de hasta MAX_SQL_BATCH (100 IDs / URLs base).
    Garantiza consistencia ID <-> DAT <-> SQL (cada UPDATE referencia el id
    del DAT). Nombre de archivo: SQL__<MMDD>_<lote>_.sql
.
    """
    global _sql_file_counter
    if not dat_structures:
        return None

    sql_lines = ["START TRANSACTION;"]

    for dat in dat_structures:
        hotel_id = dat.get("id", "")
        default_lang = dat.get("default_language", "en")
        scraped_date = dat.get("scraped_at", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        hotels = dat.get("hotels", {})

        score_value = ""
        for lang in [default_lang, "en", "es", "de", "fr", "it"]:
            if lang in hotels and hotels[lang].get("hotel_score"):
                score_value = parse_score(hotels[lang]["hotel_score"])
                if score_value:
                    break

        default_desc = hotels.get(default_lang, {}).get("hotel_description", "")

        set_clauses = []
        if default_desc:
            set_clauses.append(f"    h.long_description = '{sql_escape(default_desc)}'")
        if score_value:
            set_clauses.append(f"    h.score_review = '{score_value}'")
        set_clauses.append(f"    h.updated_at = '{scraped_date}'")

        sql_lines.append("UPDATE hotel h SET")
        sql_lines.append(", ".join(set_clauses))
        sql_lines.append(f"WHERE h.id = {hotel_id} AND h.`language` = '{default_lang}';")

        for lang in lenguajes_activos:
            desc = hotels.get(lang, {}).get("hotel_description", "")
            if desc:
                sql_lines.append(
                    f"UPDATE {TRANSLATIONS_TABLE} t SET t.content = '{sql_escape(desc)}' "
                    f"WHERE t.foreign_key = {hotel_id} "
                    f"AND t.object_class = '{sql_escape(TRANSLATIONS_OBJECT_CLASS)}' "
                    f"AND t.field = '{TRANSLATIONS_FIELD}' AND t.locale = '{lang}';"
                )

    sql_lines.append("COMMIT;")

    _sql_file_counter += 1
    stamp = datetime.now(timezone.utc).strftime("%m%d")
    sql_path = os.path.join(SQL_DIR, f"SQL__{stamp}_{_sql_file_counter:03d}_.sql")
    if os.path.exists(sql_path):
        print(f"[OVERWRITE] {sql_path} existe; se sobrescribirá.")
    with open(sql_path, 'w', encoding='utf-8') as f:   # 'w' trunca/sobrescribe
        f.write("\n".join(sql_lines))
    print(f"\n[SQL] Archivo UPDATE generado ({len(dat_structures)} IDs): {sql_path}")
    return sql_path

# ============================================================
# --- PASO 3 (INDEPENDIENTE): leer los DAT del DISCO y generar SQL por lotes
# ============================================================
def load_dat_files_from_disk(dat_dir=DAT_DIR):
    """
    Lee TODOS los archivos DAT__<id>_.json de `dat_dir` y los devuelve como
    lista de estructuras DAT (dicts), ordenada por id.

    Ésta es la ÚNICA fuente del PASO 3: el SQL se deriva del DAT en disco
    (artefacto canónico), NO de datos en memoria. El HTML es sólo respaldo de
    adquisición; el DAT no se reconstruye desde el HTML salvo re-adquisición
    explícita (otro flujo).
    """
    dats = []
    if not os.path.isdir(dat_dir):
        print(f"[SQL] No existe el directorio de DAT: {dat_dir}")
        return dats

    nombres = sorted(
        n for n in os.listdir(dat_dir)
        if n.startswith("DAT__") and n.endswith("_.json")
    )
    for nombre in nombres:
        ruta = os.path.join(dat_dir, nombre)
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if isinstance(obj, dict) and obj.get("id"):
                dats.append(obj)
            else:
                print(f"[SQL] [WARN] DAT inválido o sin 'id', omitido: {nombre}")
        except Exception as e:
            print(f"[SQL] [WARN] No se pudo leer {nombre}: {str(e)[:120]}")

    # Orden estable por id (numérico si procede)
    def _key(d):
        i = str(d.get("id", ""))
        return (0, int(i)) if i.isdigit() else (1, i)
    dats.sort(key=_key)

    print(f"[SQL] DAT leídos del disco: {len(dats)} (en {dat_dir})")
    return dats

def run_sql_step(dat_dir=DAT_DIR, batch_size=MAX_SQL_BATCH):
    """
    PASO 3 ejecutable de forma INDEPENDIENTE.
    Carga los DAT del disco y genera SQL en lotes de hasta `batch_size`
    (MAX_SQL_BATCH). Devuelve la lista de rutas SQL generadas.
    """
    dats = load_dat_files_from_disk(dat_dir)
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

    # REGLA: si el HTML ya existe se SOBRESCRIBE (no se omite).
    if os.path.exists(output_file):
        if OVERWRITE_EXISTING:
            print(f"  -> [OVERWRITE] {output_file} existe; se sobrescribirá.")
        else:
            print(f"  -> [SKIP] Ya existe {output_file} (OVERWRITE_EXISTING=False).")
            return True, extracted_data

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
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"  -> [OK] {reason} | Guardado: {output_file}")
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
            print("  -> [ERROR] Timeout de Playwright")
            if context:
                context.close()
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, extracted_data
        except Exception as e:
            print(f"  -> [ERROR] {str(e)[:200]}")
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
print(" Playwright + Chromium + VPN v5.4")
print(" Multi-idioma | DAT | SQL Update | Retry | Cookie | Stealth | RCA-fixes")
print(f" MAX_URLS_DOWNLOAD={MAX_URLS_DOWNLOAD} | MAX_SQL_BATCH={MAX_SQL_BATCH} | VPN={ENABLE_VPN}")
print("=" * 60)

# Validación de configuración de idiomas (alcance real: 20 idiomas, incl. CJK/RTL).
validate_language_config()

# === MODO INDEPENDIENTE: sólo PASO 3 (SQL desde los DAT del disco) ===
if SQL_ONLY:
    print("[MODE] --solo-sql: se OMITE el scraping. PASO 3 desde los DAT en disco.")
    run_sql_step(DAT_DIR, MAX_SQL_BATCH)
    print("Proceso (solo SQL) finalizado.")
    sys.exit(0)

url_entries = load_urls_from_csv("list_url.csv", MAX_URLS_DOWNLOAD)

success_count = 0
fail_count = 0
skipped_count = 0
dat_files_written = 0

dat_accumulator = {}

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

        for idx, (hotel_id, default_lang, url_base) in enumerate(url_entries):
            name = extract_name_from_url(url_base)
            print(f"\n[PROCESS] {idx+1}/{len(url_entries)} "
                  f"ID={hotel_id} | DefaultLang={default_lang} | Name={name} | Base={url_base}")

            dat_accumulator[hotel_id] = {}

            # VPN por cada URL base
            pais = random.choice(VPN_COUNTRIES)
            if not connect_vpn(pais):
                if VPN_REQUIRED:
                    print(f"  -> [SKIP] VPN falló y VPN_REQUIRED=True. Saltando ID {hotel_id}")
                    skipped_count += 1
                    continue
                else:
                    print(f"  -> [WARN] VPN falló; continuando SIN VPN (VPN_REQUIRED=False)")

            for lang in lenguajes_activos:
                url_final = build_language_url(url_base, lang)
                print(f"\n  [LANG] {lang.upper()} -> {url_final}")

                filename = f"HTML__{hotel_id}__{lang}__{name}__.md"
                diagname = f"DIAG__{hotel_id}__{lang}__{name}__.md"
                full_path = os.path.join(OUTPUT_DIR, filename)
                diag_path = os.path.join(DIAG_DIR, diagname)

                success, extracted_data = download_with_playwright(
                    browser, url_final, full_path, diag_path, lang
                )
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                dat_accumulator[hotel_id][lang] = extracted_data

                time.sleep(random.randint(3, 7))

            # DAT por hotel (PASO 2): se escribe a disco como artefacto canónico
            if dat_accumulator.get(hotel_id):
                dat_struct = build_dat_structure(hotel_id, name, url_base, default_lang,
                                                 dat_accumulator[hotel_id])
                write_dat_file(hotel_id, dat_struct)
                dat_files_written += 1

            print("-" * 60)
            time.sleep(random.randint(5, 12))

        browser.close()
        print("[OK] Browser cerrado")

    # === PASO 3: SQL leyendo los DAT del DISCO (independiente de la extracción) ===
    print("\n[PASO 3] Generando SQL a partir de los DAT en disco...")
    run_sql_step(DAT_DIR, MAX_SQL_BATCH)

finally:
    disconnect_vpn()
    print("\n" + "=" * 60)
    print(f" RESUMEN: {success_count} OK | {fail_count} FALLIDOS | {skipped_count} OMITIDOS")
    print(f" DAT files generados: {dat_files_written}")
    print("=" * 60)
    print("Proceso finalizado.")