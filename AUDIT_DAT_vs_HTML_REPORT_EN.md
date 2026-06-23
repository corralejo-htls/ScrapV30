# Technical Audit — DAT vs HTML Cross-Reference (ScrapV30 / `paginas.py` v5.4)

**Date:** 2026-06-23
**Subject:** `DAT__75888_.json`, `DAT__75890_.json`, `DAT__75891_.json`, `DAT__75910_.json`
**Source of truth:** `HTML/HTML__*.md` snapshots in the GitHub repo (3 hotels × 21 languages = 63 files)
**Codebase reviewed:** `paginas.py` v5.4
**Audit type:** Read-only. Findings and action plan only — no code was modified.

---

## 1. Method

Each DAT field was reproduced from the source HTML using a **faithful port of the extraction logic in `paginas.py`** (same JSON-LD path, same CSS/XPath selectors, same sanitizers and `<br />` substitution), then compared field-by-field against the uploaded DAT.

- **Exact-match fields** (must be byte-identical to source): name, score, review count, all `address.*` components, coordinates, main image, Booking internal ID, meta description — sourced from JSON-LD, page metadata and DOM attributes.
- **Long-text fields** (`hotel_description`): compared after whitespace/`<br />` normalization.
- **DOM section fields** (`servicios`, `normas_casa`, `info_importante`, `info_destacada`): validated by token-coverage against the full page text (these are extracted from the live, hydrated DOM, so exact length differs from the static snapshot by design).

> **Caveat:** `DAT__75910_` (hotelgeblergassevienna) has **no HTML in the repository**, so it was validated for internal consistency only, not against a source.

---

## 2. Fidelity verification — what is correct (no data loss)

| Check | Result |
|-------|--------|
| Exact fields DAT vs HTML (3 hotels × 21 langs × 14 fields) | **882 / 882 match** |
| `hotel_description` DAT vs HTML (normalized) | **63 / 63 match** |
| `servicios` content present in source HTML (≥95% tokens) | **63 / 63** |
| `normas_casa` content present in source HTML | **63 / 63** |
| `info_importante` content present in source HTML | **63 / 63** |
| `info_destacada` content present in source HTML | **63 / 63** |
| Description contamination in DAT (`OpenStreetMap`) | **0 / 63** |
| Description contamination (location-rating sentence) | **0 / 63** |
| `review_word` localization (Fabulous / Fabuloso / すばらしい / رائع …) | Correct |
| Cross-language invariants per hotel (score, lat/long, booking_id, review_count) | Single value each — consistent |

**Conclusion of this section:** the DAT is **lossless and faithful** to the HTML for every extractable field. The two v5.4 fixes (direct description node; boilerplate stripping) **held in the production DAT**: no OpenStreetMap attribution and no location-rating sentence leaked into any of the 63 description records.

---

## 3. Findings

### Severity overview

| # | Severity | Finding |
|---|----------|---------|
| 1 | **Critical** | English fallback descriptions stored as genuine translations, with no detection |
| 2 | **High** | Latent data-loss: `OVERWRITE_EXISTING=False` skip path returns an empty record and overwrites the DAT |
| 3 | **High** | `lenguajes_activos_SQL` is documented as a requirement but not implemented |
| 4 | Medium | `city` / `locality` hold a **street**, not a city, and are duplicates |
| 5 | Medium | `address_full` carries a **review count that conflicts** with the canonical value (locales `en`, `tl`) |
| 6 | Medium | Documentation says **20 languages**; the pipeline runs **21** |
| 7 | Medium | `info_destacada` uses a deep positional XPath with **no anchor fallback**; captures the location-score box |
| 8 | Medium | `info_importante` is **empty in all 21 languages** for hotel 75910, with no surfaced warning |
| 9 | Low | `country` / `street_address` stored as **localized text** (15–18 variants), not canonical |
| 10 | Low | Description fallback chain over-captures; the cleaner only filters `OpenStreetMap` |
| 11 | Low | `region` keeps the literal `" (state)"` suffix |
| 12 | Low | `og_title` / `canonical_url` documented but never extracted; `servicios` is the summary box only |
| 13 | Info | SQL robustness: locale `'en'` vs `'en_GB'` match risk; default locale double-written; score quoted as string; JSON-LD `.first` fragile |

---

### Finding 1 — English fallback persisted as a translation (Critical)

For **hotel 75888 (Grand Ferdinand)**, only **7 of 21** languages carry a genuinely translated `hotel_description` (de, es, fi, fr, it, nl, pl). The other **14 are byte-identical to the English text** (ar, da, en, hu, id, ja, ko, ms, no, pt, sv, th, tl, zh).

Hotels 75890, 75891 and 75910 are fully translated (21/21 unique), so the ratio is **hotel-dependent**, and the served `<html lang>` attribute is correctly localized. The root cause is therefore **Booking's translation availability** (English is served as a fallback when no translation exists) — **not** the hard-coded `locale="en-GB"` browser context.

**Risk:** the pipeline writes that English text into `accommodation_translations.content` for `locale='ja'`, `'ar'`, `'zh'`, etc., with **no flag distinguishing a real translation from a fallback**. The translation table is silently populated with English for untranslated locales.

---

### Finding 2 — Latent data-loss in the skip path (High)

In `download_with_playwright` (~line 906): when `OVERWRITE_EXISTING=False` and the HTML already exists, the function does `return True, extracted_data` where `extracted_data = empty_record()` (all fields blank). The main loop stores that blank record in `dat_accumulator`, and `build_dat_structure` then **overwrites the DAT** (the declared "canonical artifact") with empty fields for that language.

This contradicts the documented rule that "HTML is only an acquisition backup and the DAT is not reprocessed." It is latent today because the default is `True`, but flipping the flag silently empties the DAT/SQL for every already-downloaded HTML.

---

### Finding 3 — `lenguajes_activos_SQL` not implemented (High)

The header (line 33) documents `lenguajes_activos_SQL` as a requirement ("build SQL with only the preselected languages; default to `lenguajes_activos`"). The symbol is **defined nowhere** in the file; `generate_sql_updates` iterates directly over `lenguajes_activos` (line 805). The promised feature is missing.

---

### Finding 4 — `city` / `locality` contain a street (Medium)

Both copy JSON-LD `addressLocality`, which for these hotels is a street: `"Schubertring 10-12"` (75888), `"Gerhard-Bronner-Str. 11"` (75890). The real city (Vienna) is absent. Faithful to the source but semantically wrong for any "city" consumer, and the two fields are exact duplicates of the same tag. (Stored in the DAT only; not written to SQL.)

---

### Finding 5 — `address_full` carries a conflicting review count (Medium)

In the **`en` and `tl`** locales of all three repo hotels (6 records), `address_full` embeds a review count that disagrees with the canonical `review_count`:

| Hotel | `address_full` count | canonical `review_count` |
|-------|---------------------|--------------------------|
| 75888 | 5625 | 5716 / 5717 |
| 75890 | 16984 | 17352 / 17353 |
| 75891 | 14110 | 14363 |

The field also keeps literal `\n` line breaks (it is in neither `_LONG_TEXT_FIELDS` nor `_RAW_FIELDS`, so no `<br />` normalization is applied). 75910 has no such conflict.

---

### Finding 6 — 20 vs 21 languages (Medium)

`lenguajes_activos` has **21** entries and there are **21** HTML files and **21** DAT language blocks per hotel, but the docstrings state "20 idiomas" in three places (lines 46, 78, 1031). Code and documentation disagree. (`ru` is defined in the `lenguajes` map but unused — harmless.)

---

### Finding 7 — `info_destacada` is fragile and semantically inconsistent (Medium)

It uses the single positional XPath `//*[@id="basiclayout"]/div[1]/div[3]/…/div[1]` with `anchor_id=None` — the only section field **with no anchor fallback**. Any layout shift breaks it silently. In practice it captures the **location-score box**, which differs per hotel:

- 75888: *"Situated in the real heart of Vienna, this hotel has an excellent location score of 9.7 …"*
- 75890: *"Top location: Highly rated by recent guests (9.4) …"*

This is a marketing/location widget, not a stable "highlighted info" field.

---

### Finding 8 — `info_importante` empty for an entire hotel (Medium)

In `DAT__75910_`, `info_importante` is **empty in all 21 languages** — the only field that is 100% empty for any hotel. Because 75910 has no HTML in the repo, it cannot be determined whether the section is genuinely absent on the page or the selector failed. Either way, the run produces no warning for a wholly-missing field.

---

### Finding 9 — `country` / `street_address` are localized text (Low)

Across languages, `country` takes 15 distinct forms (Austria / Österreich / Autriche / オーストリア / النمسا / 奥地利 …) and `street_address` 18 forms. This is faithful (Booking localizes the JSON-LD address), but it means neither field is a canonical/ISO value; any downstream join or normalization on country must account for this.

---

### Finding 10 — Description fallback over-captures (Low)

The 4th selector in the chain, `.hp-description p`, returns more text than the clean node in **63/63** files. It only fires if the primary `[data-testid="property-description"]` fails, but if that happens the `_strip_description_boilerplate` cleaner — which filters only the `OpenStreetMap` marker — would **not** remove the location-rating sentence, reintroducing the v5.3 contamination.

---

### Finding 11 — `region` suffix (Low)

`region = "Vienna (state)"` is stored with the literal `" (state)"` suffix from JSON-LD `addressRegion`.

---

### Finding 12 — Documented fields missing; `servicios` partial (Low)

`og_title` and `canonical_url` are documented and present in the HTML but are not in `DATA_FIELDS` and never extracted. `servicios` captures only the "most popular facilities" summary box, not the full categorized list; its positional XPath resolves to 0 nodes, so the anchor fallback supplies the value.

---

### Finding 13 — SQL robustness (Info)

- `t.locale = '{lang}'` uses short codes (`'en'`, `'es'`). If the database uses `'en_GB'` / `'es_ES'`, **no rows update, silently**. (Unverifiable without the schema.)
- The default locale is written **twice**: to `hotel.long_description` and to `accommodation_translations` (locale = default). May be intentional (Doctrine Translatable) — confirm.
- `h.score_review = '8.7'` quotes a numeric as a string (works via coercion; inconsistent if the column is numeric).
- `read_jsonld_hotel` takes `.first` `ld+json` block; only one Hotel block exists in all 63 files, but a future `BreadcrumbList` first block would yield empty data with no warning.
- `review_count` drifts across languages (e.g. 5716/5717) due to the time gap between per-language scrapes; low impact (SQL uses the default locale's value).

**Minor notes:** HTML files use a `.md` extension but are raw HTML; `is_admin()` is required even in `--solo-sql` mode, which does not scrape; the manual `STEALTH_SCRIPT` hard-codes `navigator.languages=['en-GB','en']` for every language.

---

## 4. Action plan

Prioritized, concrete remediation. Items are independent unless noted.

### P0 — Data integrity (do first)

1. **Detect and flag English fallbacks (Finding 1).** After extraction, for each non-English locale compare `hotel_description` against the `en` description; if identical, set a per-locale flag (e.g. `description_is_fallback: true`) in the DAT and **skip** that locale's `accommodation_translations` UPDATE (or write it to a separate review queue). Optionally also compare against `meta_name` to catch the same fallback in the meta field.
2. **Fix the skip path (Finding 2).** When `OVERWRITE_EXISTING=False` and the HTML exists, either (a) re-extract from the existing HTML file, or (b) load the existing DAT for that id/lang and preserve it — never return `empty_record()` into the accumulator. Add an assertion that refuses to write a DAT language block whose key fields are all empty.

### P1 — Missing/contracted behavior

3. **Implement `lenguajes_activos_SQL` (Finding 3).** Add the parameter near the other config constants; default to `lenguajes_activos` when unset or equal; in `generate_sql_updates`, iterate `lenguajes_activos_SQL` instead of `lenguajes_activos`.
4. **Reconcile language count (Finding 6).** Replace the hard-coded "20" in all docstrings with `len(lenguajes_activos)` in printed output, and correct the prose to 21 (or remove `ru` from the map if 20 is intended).
5. **Confirm the SQL contract (Finding 13).** Verify the real `accommodation_translations.locale` format and map short codes → DB locales (e.g. `en` → `en_GB`). Decide whether the default locale should be double-written. Make `h.score_review` numeric if the column is numeric.

### P2 — Data quality / cleaning

6. **Clean `address_full` (Finding 5).** Add it to the long-text path (so `<br />` normalization applies) and strip the `"rated X/10! (score from N reviews)"` and "Real guests • …" boilerplate, mirroring the description cleaner. Remove the embedded review count to avoid the conflict.
7. **Separate semantic city from `addressLocality` (Finding 4).** Source the city from a stable signal (e.g. the address string parse, or the `og_title` tail) rather than `addressLocality`; drop one of the duplicate `city`/`locality` fields or document the distinction.
8. **Normalize `region` and `country` (Findings 9, 11).** Strip the `" (state)"` suffix; if a canonical country is needed downstream, map the localized country text to an ISO code (or extract `addressCountry` only from the `en` locale as canonical).

### P3 — Selector resilience

9. **Add a fallback for `info_destacada` and re-scope it (Finding 7).** Give it a stable anchor (or drop the positional XPath) and decide what the field is meant to hold; today it captures the location-score widget inconsistently.
10. **Surface empty-section warnings (Finding 8).** Emit a per-field warning (already done for `hotel_name`/`hotel_description`) when a section is empty across all languages of a hotel, so cases like 75910 `info_importante` are visible. Re-acquire 75910 HTML to confirm whether the section exists.
11. **Harden the description fallback (Finding 10).** Either remove `.hp-description p` from the chain or extend `_DESC_BOILERPLATE_MARKERS` to also drop the location-rating sentence, so a future primary-selector failure does not reintroduce contamination.
12. **Make JSON-LD selection type-aware (Finding 13).** Iterate all `ld+json` blocks and pick the one whose `@type` is `Hotel`/`LodgingBusiness`, instead of `.first`.

### P4 — Hygiene

13. Add the documented `og_title` / `canonical_url` to `DATA_FIELDS` or remove them from the spec (Finding 12). Capture the full facilities list if completeness is required.
14. Rename HTML outputs to `.html`, or document the `.md` convention. Allow `--solo-sql` to bypass the admin check. Align `STEALTH_SCRIPT` languages with the target locale (cosmetic).

---

## 5. Conclusion

The DAT artifacts are **faithful and lossless** relative to the HTML for every extractable field (882/882 exact, 63/63 descriptions, all DOM sections present), and the v5.4 description-cleaning fixes are confirmed effective in production output.

The dominant operational risk is **Finding 1**: English fallback descriptions are stored as genuine translations with no detection, directly affecting the translation table. **Findings 2 and 3** (latent DAT corruption on a flag flip; a documented-but-missing feature) follow. The remaining items are data-quality, selector-resilience, and documentation issues that are individually low-risk but collectively worth addressing.
