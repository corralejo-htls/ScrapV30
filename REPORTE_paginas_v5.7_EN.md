# Technical Report — `paginas.py` v5.7 (final state)

**Date:** 2026-06-24
**File delivered:** `paginas.py` (same name, modified) — ready for download
**Pipeline:** Booking.com scraper (Playwright) → DAT (JSON) → SQL UPDATE
**Validation:** executed in `--solo-sql` mode against the four processed DAT files
(`75888`, `75890`, `75891`, `75898`); generated SQL inspected.

---

## 1. Current text/data policy

The pipeline now follows a strict **"store and persist exactly as extracted"** policy.

| Stage | Behavior |
|-------|----------|
| PASO 2 — DAT | Text is stored **verbatim** from the DOM. No formatting, no `<br />`, no normalization, no cleaning. The DAT is a faithful mirror of the scraped DOM. |
| PASO 2.5 — cleaning hook | **Pass-through** (`CLEAN_TEXT_BEFORE_SQL = False`). Nothing is removed — not UI/attribution text ("OpenStreetMap"), not media/URLs, not line breaks. |
| PASO 3 — SQL | The DAT text is written to SQL **exactly as-is**, with only the mandatory `sql_escape` (backslash/quote), which inserts the literal text without altering content. |

Result: the text that lands in the database is identical to what was scraped, including line breaks and any attribution/UI fragments.

---

## 2. Translation policy

**No translation is ever omitted.** Every active language is written to
`accommodation_translations`, including languages where Booking served the
**English text as a fallback** (a property with no real translation for that
language).

- `SKIP_ENGLISH_FALLBACK_TRANSLATIONS = False` (default).
- A fallback **detector remains** but is **informational only**: it counts how
  many languages match the English text and reports them; it does **not**
  discard anything.

---

## 3. Language scope

```python
_LENGUAJES_BASE_20 = ["en","es","fr","de","pt","ar","nl","zh","tl","id","ms",
                      "ja","ko","th","hu","pl","no","fi","sv","da"]
lenguajes_activos  = _LENGUAJES_BASE_20 + ["it"]   # "it" appended last → 21
```

20 base languages **plus `it` (Italian) added at the end** = **21** active
languages. The start-up validator prints `21 idiomas activos (20 base + 'it' al final)`.

`lenguajes_activos_SQL` (default `[]` → uses `lenguajes_activos`) allows building
SQL for a preselected subset. `LOCALE_MAP` (default `{}`) optionally maps short
codes to DB locales (e.g. `en` → `en_GB`) via `db_locale()`.

---

## 4. Data-integrity fixes carried in this build

Each item is traced along the data path DOM → extraction → persistence → SQL/API.

| Area | Behavior |
|------|----------|
| **DAT preservation** | `PRESERVE_DAT_ON_EMPTY = True` + `_merge_preserve_existing`: a language block that comes back empty (no new acquisition) does **not** overwrite a previous non-empty DAT block. Prevents silent data loss on re-runs. |
| **Empty-section warning** | A warning is emitted when a field is empty across **all** languages of a hotel (e.g. a missing `info_importante`), surfacing selector gaps. |
| **JSON-LD selection** | `read_jsonld_hotel` iterates all `ld+json` blocks and selects the one whose `@type` is `Hotel`/`LodgingBusiness`, instead of blindly taking the first block. |
| **Numeric score** | `h.score_review` is emitted as a number when the value is numeric. |
| **Locale mapping** | `db_locale()` maps language codes to DB locales for both the hotel `WHERE` and the translation `locale`. |
| **Windows file locks** | `_safe_write`: atomic write (temp file + `os.replace`) with retries on `PermissionError` / WinError 32, so a file open in another program does not cause a silent failure or a half-written file. |
| **Admin requirement** | `--solo-sql` (which performs no scraping) no longer requires running as Administrator. |

---

## 5. Validation evidence (live run)

`python paginas.py --solo-sql` over the four processed DATs produced:

```
[OK] Config de idiomas válida: 21 idiomas activos (20 base + 'it' al final).
[SQL] Traducciones en inglés (fallback) MANTENIDAS (no se omite ninguna): 22
[SQL] Archivo UPDATE generado (4 IDs): data/SQL__0624_001_.sql
```

| Check | Result |
|-------|--------|
| Translation locales written per hotel | **21 each** (75888, 75890, 75891, 75898) — none missing |
| English-fallback translations omitted | **0** (policy: keep all; 22 detected and kept) |
| SQL description vs DAT description | **identical** (verbatim, line breaks preserved, only `sql_escape` applied) |
| Pass-through with `"… © OpenStreetMap … https://x.com … img.jpg"` | output **identical** to input — OpenStreetMap, URL and image all kept |
| `it` position in language list | **last** |

Informational fallback breakdown for the processed batch (languages served in
English, now **kept**):

| Hotel | English-fallback languages (kept) |
|-------|-----------------------------------|
| 75888 — Grand Ferdinand | 13: pt, ar, zh, tl, id, ms, ja, ko, th, hu, no, sv, da |
| 75898 — Superbude Hostel Wien Prater | 9: ar, zh, tl, ms, ja, ko, th, no, sv |
| 75890 — Motel One Hauptbahnhof | 0 (all translated) |
| 75891 — Motel One Westbahnhof | 0 (all translated) |

The DAT files are not modified by `--solo-sql` (it only reads the DAT and writes the SQL).

---

## 6. Configuration summary (defaults as delivered)

```python
lenguajes_activos                   = 20 base + "it"   # 21 languages
lenguajes_activos_SQL               = []               # [] → uses lenguajes_activos
LOCALE_MAP                          = {}               # {} → short code as-is
SKIP_ENGLISH_FALLBACK_TRANSLATIONS  = False            # keep all translations
CLEAN_TEXT_BEFORE_SQL               = False            # text exactly as extracted
PRESERVE_DAT_ON_EMPTY               = True             # no data loss on empty re-run
```

---

## 7. Notes

- Because the text is kept verbatim, any attribution/UI fragment present in a
  raw description (e.g. "OpenStreetMap") will appear in the database. This is the
  intended policy; re-enable cleaning by setting `CLEAN_TEXT_BEFORE_SQL = True`
  if that ever changes.
- The English-fallback figures are informational; they indicate where Booking
  lacks a real translation, not a scraper error. A future re-acquisition will
  pick up translations if Booking publishes them.
- `city`/`locality` (street value, duplicated), `region` (`" (state)"` suffix)
  and `country` (localized text) remain raw in the DAT by design; normalize
  downstream if a canonical value is needed (no SQL impact today).
