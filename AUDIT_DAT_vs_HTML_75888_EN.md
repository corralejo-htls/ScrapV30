# Technical Audit — DAT vs HTML Extraction

**Subject:** `DAT__75888_.json` (Grand Ferdinand Vienna) vs. 20 HTML source snapshots
**Scope:** Data-extraction fidelity, tag/selector correctness, data loss
**Codebase reviewed:** `paginas.py` (v5.3), `MAPEO_CAMPOS_DOM.md`
**Languages covered:** en, es, fr, de, pt, ar, nl, zh, tl, id, ms, ja, ko, th, hu, pl, no, fi, sv, da (20)
**Audit type:** Read-only. Findings only — no code modifications or fixes applied.

---

## 1. Executive summary

The extraction is **lossless and accurate for every field sourced from JSON-LD and page metadata**: name, score, review count, address components, country, meta description, main image, coordinates, and Booking's internal ID all match the HTML byte-for-byte across all 20 languages, and no field is empty in any language.

The material risks lie in two places: the **documented primary selector for the long description is dead** (it matches zero nodes and the field survives only on a fragile fallback), and the **description text is contaminated with UI/attribution boilerplate that is persisted into the database** for all 20 locales. Several lower-severity data-quality and documentation issues are also reported.

### Severity overview

| # | Severity | Finding |
|---|----------|---------|
| 1 | High | Primary description selector matches **0 nodes** in all 20 files |
| 2 | High | `hotel_description` contaminated with UI/attribution text → written to DB |
| 3 | Medium | `city` / `locality` contain a **street**, not a city (and are duplicates) |
| 4 | Medium | `address_full` uncleaned; embeds a **stale, conflicting review count** |
| 5 | Low | `region` carries a `" (state)"` suffix verbatim |
| 6 | Low | `og_title` / `canonical_url` documented but **not extracted** |
| 7 | Low | `servicios` captures only the "most popular" summary, not the full list |
| 8 | Low | Spec validated on 5 languages; pipeline runs 20 (incl. CJK/RTL) |
| 9 | Info | Minor SQL-generation robustness issues |

---

## 2. Methodology

Each DAT field was compared against the corresponding HTML snapshot using:

- **JSON-LD** (`script[type="application/ld+json"]`, schema.org `Hotel`) for name, `aggregateRating.ratingValue`, `aggregateRating.reviewCount`, and all `address.*` components.
- **Page metadata**: `meta[name="description"]`, `meta[property="og:image"]`, `meta[property="og:title"]`, `link[rel="canonical"]`.
- **DOM nodes**: `[data-testid="property-description"]`, `[data-atlas-latlng]`, `input[name="hotel_id"]`, and the section anchors `#hp_facilities_box`, `#policies`, `#important_info`, plus the positional XPaths declared in `MAPEO_CAMPOS_DOM.md`.

Both `lxml` (XPath) and BeautifulSoup (CSS) were used to reproduce exactly what the scraper's selectors would resolve to. Text comparisons were whitespace-normalized; `<br />` markers in the DAT were converted back to spaces before comparing against HTML text.

> **Caveat:** The HTML files are static `page.content()` snapshots, whereas the scraper extracts from the live, hydrated DOM. Small length differences in the four long sections are attributable to this snapshot-vs-live difference and do **not** indicate data loss.

---

## 3. Verified-correct results (no data loss)

The following were confirmed **identical** between DAT and HTML in **all 20 languages**:

| Field | Source | Result |
|-------|--------|--------|
| `hotel_name` | JSON-LD `$.name` | Exact match (20/20) |
| `hotel_score` | JSON-LD `$.aggregateRating.ratingValue` (`8.7`) | Exact match (20/20) |
| `review_count` | JSON-LD `$.aggregateRating.reviewCount` (`5723`) | Exact match (20/20) |
| `street_address`, `postal_code` (`1010`), `country` (`Austria`) | JSON-LD `$.address.*` | Exact match (20/20) |
| `meta_name` | `meta[name=description]` | Exact match (20/20) |
| `image_main` | `meta[property=og:image]` | Exact match (20/20) |
| `latitude` / `longitude` (`48.202236…` / `16.374938…`) | `data-atlas-latlng` | Exact match (20/20) |
| `booking_hotel_id` (`1467896`) | `input[name=hotel_id]` | Exact match (20/20) |
| `review_word` | review component | Correctly localized (Fabulous / Fabuloso / すばらしい / رائع / …) |

**Empty-field scan:** none. Every one of the 21 fields is populated in all 20 languages.

---

## 4. Findings

### Finding 1 — Broken primary description selector (High)

**Where:** `MAPEO_CAMPOS_DOM.md` (main table + "correspondencia" table marked `✅ válido`); `paginas.py` line 552.

The documented primary selector for `hotel_description` is `//*[@data-testid="property-description"]//p` (XPath) / `[data-testid="property-description"] p` (CSS). Tested against all 20 files, this **descendant-`<p>` selector resolves to 0 nodes**, because the element carrying `data-testid="property-description"` *is itself the `<p>`* and has no child `<p>`:

```
<p class="b99b6ef58f f1152bae71" data-testid="property-description">Opened in autumn 2015, …</p>
```

The MAPEO "correspondencia" table marks this selector `✅ válido` — that assessment is incorrect for these files. The field is only populated because a later entry in the fallback chain (`#basiclayout p` / live-DOM grouping) catches it.

**Risk:** Single point of failure with no error surfaced. If the fallback shifts, the description silently goes empty while the run still reports success.

---

### Finding 2 — Description contamination persisted to the database (High)

**Where:** extraction (`paginas.py` lines 551–559); propagation to SQL (lines 719–740).

In **all 20 languages**, `hotel_description` ends with non-description page furniture:

- An OpenStreetMap attribution line, localized per language. Example (EN): *"Distance in property description is calculated using © OpenStreetMap"*.
- A location-rating sentence. Example (EN): *"Couples particularly like the location — they rated it 9.7 for a two-person trip"*.

Neither line is part of the `property-description` `<p>` in the HTML; they were captured from adjacent DOM (over-capture). Because `hotel_description` is the exact value written to `h.long_description` (default locale) and to `accommodation_translations.content` for **every** locale, this boilerplate is **persisted into the database for all 20 languages**.

**Evidence:** the OSM attribution marker (`OpenStreetMap`) is present in the `hotel_description` of 20/20 languages.

---

### Finding 3 — `city` / `locality` hold a street address (Medium)

**Where:** `paginas.py` lines 595–596.

For all languages, `city` = `locality` = `"Schubertring 10-12"` — a street, not a city (the city is Vienna). Both are copied from JSON-LD `addressLocality`, so the extraction is *faithful to the source*, and MAPEO acknowledges the quirk.

**Two issues remain:**
1. The value is semantically wrong for any downstream "city" consumer.
2. `city` and `locality` are duplicate copies of the same `addressLocality` tag — one is redundant.

---

### Finding 4 — `address_full` uncleaned, with a conflicting review count (Medium)

**Where:** `paginas.py` line 591–592; cleaning expected per MAPEO ("limpiar").

`address_full` retains UI noise the spec says to strip. EN value:

```
Schubertring 10-12, 01. Innere Stadt, 1010 Vienna, Austria
Excellent location — rated 9.7/10!(score from 5629 reviews)
Real guests • Real stays • Real opinions
–Excellent location - show map–
Metro and railway access
0.7 mi walking from Wien Mitte station
```

The embedded **"5629 reviews" conflicts with the canonical `review_count` of 5723** in the same record — a stale figure that could mislead downstream consumers. The field also retains literal `\n` line breaks (it is not in `_LONG_TEXT_FIELDS`, so no `<br />` normalization is applied), giving it inconsistent line handling versus the other long fields.

---

### Finding 5 — `region` includes a parenthetical suffix (Low)

`region` = `"Vienna (state)"` verbatim from JSON-LD `addressRegion`. Faithful, but the `" (state)"` suffix will likely require stripping downstream.

---

### Finding 6 — Documented fields never extracted (Low)

`MAPEO_CAMPOS_DOM.md` defines `og_title` and `canonical_url`, and both exist in the HTML:

- `og:title` = "Grand Ferdinand Vienna – Your Hotel In The City Center, Vienna, Austria"
- canonical = `https://www.booking.com/hotel/at/grand-ferdinand.en-gb.html`

Neither appears in `DATA_FIELDS` (`paginas.py` lines 521–527) or in the DAT. Documentation and output are out of sync.

---

### Finding 7 — `servicios` is the summary box only (Low)

**Where:** `paginas.py` lines 614–616.

`servicios` faithfully equals the `#hp_facilities_box` text, but that box is the **"Most popular facilities"** summary (pool, parking, WiFi, family rooms, etc.) — not the full categorized facilities list. The documented positional XPath `//*[@id="hp_facilities_box"]/div/section/div/div[2]/div[2]` resolves to an **empty node in all 20 files**, so the anchor fallback supplies the value — exactly as MAPEO predicts. Flagged only against completeness expectations, not as a defect.

---

### Finding 8 — Spec/scope mismatch (Low)

`MAPEO_CAMPOS_DOM.md` states it is based on *"20 HTML files (4 hotels × 5 languages)"*. The deployed `lenguajes_activos` runs **20 languages**, including CJK and RTL scripts (ja, ko, zh, ar, th) that were never in the 5-language validation set. The selectors held up here, but the spec's "verified" claims do not cover the scripts actually in production.

---

### Finding 9 — Minor SQL-generation notes (Info)

**Where:** `paginas.py` `generate_sql_updates` (lines 692–752).

- `h.score_review = '{score_value}'` quotes a numeric score as a string literal — works via coercion, but is type-inconsistent if the target column is numeric.
- The score fallback language list `[default_lang, "en", "es", "de", "fr", "it"]` (line 713) includes `it`, which is not in `lenguajes_activos`. Dead entry, harmless.

---

## 5. Conclusion

| Dimension | Verdict |
|-----------|---------|
| JSON-LD / metadata fidelity | Pass — lossless, exact across 20 languages |
| Field completeness | Pass — no empty fields |
| Selector correctness | **Fail** — primary description selector is dead (Finding 1) |
| Text cleanliness | **Fail** — description and address carry UI/attribution noise (Findings 2, 4) |
| Semantic correctness | Partial — `city`/`locality`/`region` carry wrong or suffixed values (Findings 3, 5) |
| Documentation alignment | Partial — documented fields missing; scope mismatch (Findings 6, 8) |

The headline risks are **Finding 1** (the documented primary description selector matches nothing and the field survives only on a fragile fallback) and **Finding 2** (attribution/UI text is written into `long_description` and every translation row). Everything sourced from JSON-LD and page metadata is clean and lossless.

*End of report.*
