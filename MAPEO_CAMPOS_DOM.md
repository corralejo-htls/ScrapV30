# Mapeo de extracción DOM — Booking.com (hotel)

Basado en el análisis directo del DOM de los **20 archivos HTML** subidos
(4 hoteles × 5 idiomas: 75888 Grand Ferdinand, 75889 Prize/prizeotel,
75890 Motel One Hauptbahnhof, 75891 Motel One Westbahnhof). Todos comparten
la misma estructura, así que los selectores siguientes son estables entre
hoteles e idiomas salvo donde se indica.

## Hallazgo clave (afecta a `paginas.py`)

- **`h2[data-testid="property-header"]` ya NO existe en ninguna página.** Es el
  selector primario de `hotel_name` del scraper. El nombre real está en
  `h2.pp-header__title` (3.ª opción del fallback del scraper, que sí lo captura)
  y, de forma más fiable, en el bloque **JSON-LD**.
- Cada página incluye **un** `<script type="application/ld+json">` con un objeto
  `Hotel` de schema.org: es la fuente más limpia y multilingüe-estable para
  name, description, rating, reviewCount y dirección.
- Las **clases con hash** (`f63b14ab7a`, `b5cd09854e`, etc.) existen pero Booking
  las rota; usar `data-testid` o JSON-LD como fuente primaria.

---

## Tabla principal de campos

| Etiqueta | Descripción | XPath | Comentarios |
|----------|-------------|-------|-------------|
| `hotel_name` | Nombre del hotel | `//h2[contains(@class,"pp-header__title")]` | Confirmado en los 20 archivos. El primario del scraper (`@data-testid="property-header"`) está **muerto**. Alternativa más robusta: JSON-LD `$.name`. |
| `hotel_description` | Descripción larga del hotel | `//div[@data-testid="property-description"]//p` | Unir todos los `<p>` (es multi-párrafo). Texto traducido por idioma. Alternativa estable: JSON-LD `$.description`. |
| `hotel_score` | Puntuación numérica de reseñas (0–10) | `//*[@data-testid="review-score-component"]//div[@aria-hidden="true"]` | Devuelve p.ej. `8.7`. El contenedor completo trae texto ruidoso («Scored 8.7 8.7 Rated fabulous … · 5,718 reviews»). Mejor: JSON-LD `$.aggregateRating.ratingValue`. |
| `review_word` | Valoración cualitativa | `//*[@data-testid="review-score-component"]//div[contains(text(),"Rated")]` | P.ej. «Rated fabulous». Cambia con el idioma. Opcional. |
| `review_count` | Nº de reseñas | `//script[@type="application/ld+json"]` → `$.aggregateRating.reviewCount` | P.ej. `5720`. En el DOM visible aparece como «· 5,718 reviews» (formateado, menos fiable). |
| `meta_name` | Meta-descripción (head) | `//meta[@name="description"]/@content` | La que ya usa el scraper. Resumen traducido. Fallback: `//meta[@property="og:description"]/@content`. |
| `og_title` | Título Open Graph | `//meta[@property="og:title"]/@content` | Nombre + ciudad + país. Buen respaldo para `hotel_name`. |
| `address_full` | Dirección visible completa | `//*[@data-testid="PropertyHeaderAddressDesktop-wrapper"]` | El texto incluye coletillas («Excellent location …»); limpiar. Más limpio en JSON-LD. |
| `street_address` | Calle | `//script[@type="application/ld+json"]` → `$.address.streetAddress` | Desde JSON-LD. |
| `postal_code` | Código postal | `//script[@type="application/ld+json"]` → `$.address.postalCode` | Desde JSON-LD. |
| `city` / `locality` | Localidad | `//script[@type="application/ld+json"]` → `$.address.addressLocality` | Desde JSON-LD. |
| `region` | Región/estado | `//script[@type="application/ld+json"]` → `$.address.addressRegion` | Desde JSON-LD. |
| `country` | País | `//script[@type="application/ld+json"]` → `$.address.addressCountry` | Desde JSON-LD. |
| `latitude`, `longitude` | Coordenadas | `//*[@data-atlas-latlng]/@data-atlas-latlng` | Devuelve `"48.2022…,16.3749…"`; separar por coma. No está en JSON-LD. |
| `image_main` | Imagen principal | `//meta[@property="og:image"]/@content` | **Imagen** → excluida del pipeline de texto por regla; útil sólo como metadato si se necesitara. JSON-LD `$.image` da otra resolución. |
| `canonical_url` | URL canónica del hotel | `//script[@type="application/ld+json"]` → `$.url` | P.ej. `…/grand-ferdinand.en-gb.html`. También `//link[@rel="canonical"]/@href`. |
| `booking_hotel_id` | ID interno de Booking | `(//*[contains(@data-hotel-id,"")])[1]/@data-hotel-id` | ⚠️ Es el ID **interno de Booking** (p.ej. 1467896), **distinto** del ID del CSV/BD (75888). No usar como clave de tu BD. |

---

## Notas de extracción y trazabilidad

- **Fuente recomendada por campo:** preferir **JSON-LD** para `name`,
  `description`, `ratingValue`, `reviewCount` y dirección (estable entre idiomas
  y sin clases con hash). Usar el DOM visible (`data-testid`) para `review_word`
  y coordenadas (`data-atlas-latlng`), que no están en JSON-LD.
- **Lectura del JSON-LD (un solo nodo):**
  `//script[@type="application/ld+json"]/text()` → `json.loads(...)` → leer las
  rutas `$.…` indicadas arriba.
- **Idioma:** `hotel_description`, `meta_name` y `review_word` cambian por
  idioma; `ratingValue`, `reviewCount`, coordenadas y dirección son idénticos en
  los 5 idiomas (verificado: 75888=8.7/5720, 75889=8.3/22442, 75890=8.5/17375,
  75891=8.6/14390).
- **Imágenes / enlaces externos:** por la regla del proyecto, las imágenes
  (`og:image`, `$.image`) y cualquier URL no se vuelcan al texto extraído; se
  listan aquí sólo como referencia del DOM.
- **Categoría de estrellas:** los selectores `rating-stars` / `rating-squares`
  **no aparecen** en estas 4 propiedades; si se necesita, tratarlo como campo
  opcional y verificar por propiedad.
- **Clave de unión URL → DOM → DAT → SQL:** usar el ID del nombre de archivo
  (`75888`), que es el `h.id` de tu BD, **no** el `booking_hotel_id` del DOM.

---

## Campos definitivos que se vuelcan al DAT (JSON), por idioma

Tomados **tal cual** aparecen en cada página/idioma (sin normalización cruzada;
eso queda para flujos posteriores). Fuente preferida indicada entre paréntesis.

`hotel_name` (JSON-LD `$.name`) · `hotel_description` (DOM `property-description`)
· `meta_name` (`meta[name=description]`) · `hotel_score` (`$.aggregateRating.ratingValue`)
· `review_word` (componente de reseñas) · `review_count` (`$.aggregateRating.reviewCount`)
· `address_full` (DOM dirección) · `street_address` · `postal_code` · `city`* ·
`locality` · `region` · `country` (todos de `$.address`) · `latitude` · `longitude`
(`data-atlas-latlng`) · `image_main` (`og:image`, URL conservada) ·
`booking_hotel_id` (`input[name=hotel_id]`).

\* `city` y `locality` salen del mismo tag `addressLocality` (Booking no expone
una ciudad aparte; a veces ese tag trae la calle). Se guarda verbatim.

## Secciones añadidas (XPaths verificados en los 20 HTML)

| Etiqueta DAT | Sección | XPath usado | Respaldo / nota |
|--------------|---------|-------------|-----------------|
| `servicios` | Servicios / instalaciones | `//*[@id="hp_facilities_box"]` | El XPath posicional propuesto (`…/div/section/div/div[2]/div[2]`) resuelve a un nodo **vacío** en los 4 hoteles; se usa el ancla `#hp_facilities_box` (texto completo de la caja). |
| `normas_casa` | Normas de la casa | `//*[@id="policies"]/div/div[2]` | Verificado OK; respaldo `#policies`. |
| `info_importante` | Información importante | `//*[@id="important_info"]/div/div[2]` | Verificado OK; respaldo `#important_info`. |
| `info_destacada` | Información destacada | `//*[@id="basiclayout"]/div[1]/div[3]/div/div[2]/div/div[2]/div/div[1]` | Verificado OK en los 4 hoteles. Sin respaldo amplio (evita capturar todo `#basiclayout`). |

Cada sección se lee con `_section_text()`: intenta el XPath indicado y, si viene
vacío, recurre al ancla por `id`. El texto se sanitiza (imágenes/URLs fuera) y se
le aplican `<br />` antes de guardarlo.

---

## Correspondencia con `paginas.py` (acción sugerida)

| Campo scraper | Selector actual primario | Estado | Sugerencia |
|---------------|--------------------------|--------|------------|
| `hotel_name` | `h2[data-testid="property-header"]` | ❌ no existe | Anteponer JSON-LD `$.name`; mantener `h2.pp-header__title` como fallback DOM. |
| `hotel_description` | `[data-testid="property-description"] p` | ✅ válido | Confirmar unión multi-párrafo (ya corregido en v5.3). |
| `hotel_score` | `[data-testid="review-score-component"] div` | ⚠️ ruidoso | Tomar `div[@aria-hidden="true"]` o JSON-LD `$.aggregateRating.ratingValue`. |
| `meta_name` | `meta[name="description"]` | ✅ válido | Sin cambios. |
