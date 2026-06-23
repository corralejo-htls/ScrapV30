# Technical Report — Code Modifications `paginas.py` v5.5

**Date:** 2026-06-23
**File delivered:** `paginas.py` (same name, modified) — ready for download
**Role:** Senior Analysis & Programming Specialist / Data-Integrity Auditor
**Scope:** Data-loss, silent failures, incomplete pipeline, schema/ORM desync, Windows locks. Trace: DOM → extraction → persistence → API.
**Validation:** the modified code was executed in `--solo-sql` mode against the four real DAT files (`75888`, `75890`, `75891`, `75910`) and the generated SQL was inspected.

---

## 1. Requested changes (implemented exactly)

### 1.1 No formatting in the DAT — text saved exactly as scraped
The PASO 2 (DAT) no longer transforms text. The previous `<br />` line-break conversion (`replace_line_breaks`) and the per-field cleaning (`_clean_field`, `_LONG_TEXT_FIELDS`, `_RAW_FIELDS`) were **removed**. `build_dat_structure` now stores each field verbatim:

```python
dat["hotels"][lang] = {k: ("" if d.get(k) is None else str(d.get(k))) for k in DATA_FIELDS}
```

The description boilerplate strip that ran at extraction time was also removed, so the DAT is a faithful mirror of the DOM.

### 1.2 New cleaning process between DAT (step 2) and SQL (step 3)
A new function `clean_text_for_sql()` runs in **PASO 2.5** — after the DAT is read and **before** SQL is built — without modifying the DAT on disk (the DAT only changes on a new acquisition). It:

1. normalizes any legacy `<br />` (so old DATs are handled too),
2. drops contaminated lines (UI/attribution): `OpenStreetMap` (universal marker), location-rating widgets (`9.7/10`, `rated it 9.7`, `score from N reviews`, `Top location`, `particularly like`, `Real guests`, `show map`),
3. removes images, image links and external URLs (original exclusion rule),
4. collapses all whitespace to a single line — **no formatting**.

It is applied to the descriptions inside `generate_sql_updates` (default locale and every translation).

### 1.3 Finding 6 — `it` added at the end (20 base + it = 21)
```python
_LENGUAJES_BASE_20 = ["en","es","fr","de","pt","ar","nl","zh","tl","id","ms","ja","ko","th","hu","pl","no","fi","sv","da"]
lenguajes_activos  = _LENGUAJES_BASE_20 + ["it"]   # it is appended last
```
The validator now prints "21 idiomas activos (20 base + 'it' al final)"; the hard-coded "20" inconsistency is resolved.

---

## 2. Additional integrity fixes (from the audit, traced end-to-end)

| Finding | Stage in the data path | Fix |
|---------|------------------------|-----|
| 1 — English fallback stored as translation | persistence → API | `SKIP_ENGLISH_FALLBACK_TRANSLATIONS`: if a non-English description equals the English one (Booking served a fallback), the `accommodation_translations` UPDATE for that locale is **skipped**. |
| 2 — Empty record overwrites the DAT | persistence | `PRESERVE_DAT_ON_EMPTY` + `_merge_preserve_existing`: a language block that is empty (no new acquisition) does **not** overwrite a previous non-empty DAT block. |
| 3 — `lenguajes_activos_SQL` missing | extraction → SQL | Implemented via `get_sql_languages()`; defaults to `lenguajes_activos`; validated as a subset at start-up. |
| 8 — Section empty for a whole hotel | extraction | Warning emitted when a field is empty across **all** languages of a hotel (e.g. `info_importante` in 75910). |
| 13 — JSON-LD `.first` fragile | DOM → extraction | `read_jsonld_hotel` now iterates all `ld+json` blocks and selects the one whose `@type` is `Hotel`/`LodgingBusiness`. |
| 13 — locale `'en'` vs `'en_GB'` | SQL → DB | Optional `LOCALE_MAP` + `db_locale()` maps short codes to DB locales (identity by default). |
| 13 — score quoted as string | SQL → DB | `h.score_review` is emitted **numeric** when the value is a valid number. |
| Windows locks | persistence | `_safe_write`: atomic write (`tmp` + `os.replace`) with retries on `PermissionError`/WinError 32, so a file open in another program does not cause a silent failure. |
| Admin in `--solo-sql` | runtime | The admin requirement is skipped in `--solo-sql` mode (no scraping). |

The DAT remains the canonical artifact; all cleaning happens downstream, so re-running `--solo-sql` regenerates clean SQL without touching the DAT.

---

## 3. Validation evidence (live run)

Running `python paginas.py --solo-sql` over the four uploaded DATs produced:

```
[OK] Config de idiomas válida: 21 idiomas activos (20 base + 'it' al final).
     SQL: 21 idioma(s) -> [...,'da','it']
[SQL] Traducciones OMITIDAS por ser fallback en inglés: 13
[SQL] Archivo UPDATE generado (4 IDs): data/SQL__0623_001_.sql
```

Inspection of the generated SQL:

| Check | Result |
|-------|--------|
| Contains `<br />` | **No** (formatting removed) |
| Contains `OpenStreetMap` | **No** (contamination removed) |
| `h.score_review` | **numeric** (`= 8.7`, unquoted) |
| Translation locales for 75888 | **8** (en + de, es, fi, fr, it, nl, pl) — the 13 English fallbacks excluded |
| Translation locales for 75890 / 75891 / 75910 | **21 each** (fully translated) |
| `it` position in language list | **last** |

Cleaning unit tests (contaminated input):

- `"… © OpenStreetMap\nCouples particularly like … rated it 9.7"` → `"Opened in 2015, lovely hotel."`
- `"Great hotel.<br /><br />Rooms are nice.<br />Visit https://… and see img.jpg"` → `"Great hotel. Rooms are nice. Visit and see"`
- Noisy address block (`rated 9.7/10!`, `score from 5625 reviews`, `Real guests`, `Show map`) → only the real address line survives.

Subset + locale mapping (`lenguajes_activos_SQL=["en","es","de"]`, `LOCALE_MAP={"en":"en_GB","es":"es_ES"}`): SQL emitted only `en_GB`, `es_ES`, `de`, and the hotel `WHERE h.language` used `en_GB`.

---

## 4. Notes and residual items

- **75910** has no HTML in the repository and `info_importante` is empty in all 21 languages; the new warning surfaces this, but the section should be re-acquired to confirm whether it is genuinely absent or a selector miss.
- The fallback detection compares against the **English** text; if a hotel's default language is non-English and Booking falls back to a different base language, extend the comparison accordingly.
- Contamination markers beyond the universal `OpenStreetMap` are heuristic (English/structural); add localized markers if a specific language shows residual UI text.
- `city`/`locality` (street, duplicate), `region` (`" (state)"` suffix) and `country` (localized text) remain raw in the DAT by design (no SQL impact today); normalize them downstream if a consumer needs canonical values.

---

## 5. Summary

The delivered `paginas.py` implements the three explicit requirements (raw DAT with no formatting; a new cleaning process between DAT and SQL; `it` appended last) and the high-value integrity fixes (English-fallback skipping, DAT preservation, `lenguajes_activos_SQL`, type-aware JSON-LD, numeric score, locale mapping, Windows-safe writes). All changes were verified by executing the code against the four real DAT files; the generated SQL is clean, unformatted, free of English-fallback translations, and consistent with the configured language scope.
