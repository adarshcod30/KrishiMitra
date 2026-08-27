# Datasets to obtain — prioritised shopping list

Researched 2026-08-27. Each entry says **what it fixes**, the **exact source**,
the **columns we need**, and **where to drop the file**.

Drop everything into `ml-service/data/` and tell me the filename; I wire it in.
If a Kaggle file is large, keep only the columns listed — we do not need the rest.

Legend: **P0** = a capability is broken/absent without it. **P1** = makes a
claim honest or adds real value. **P2** = quality improvement.

---

## P0-1. Crop recommendation that includes wheat and Indian staples

**Problem it fixes.** `Crop_dataset.csv` (2,200 rows) covers 22 crops but has
**no wheat, sugarcane, mustard, bajra, jowar, potato, onion, tomato, soybean or
groundnut**. "What to Grow" literally cannot recommend India's biggest rabi
staple. It is also the well-known semi-synthetic Kaggle set, so the 99.3%
accuracy is real arithmetic on an easy problem, not field accuracy.

**Best source — government, real observations:**
- Area/Production/Yield (APY), district × crop × season × year
  https://data.desagri.gov.in/website/crops-apy-report-web
  or https://indiadataportal.com/p/area-production-yield-apy
  or AIKosh: https://aikosh.indiaai.gov.in/home/datasets/details/district_crop_area_production_yield_dataset.html

**Kaggle mirrors (faster to grab):**
- https://www.kaggle.com/datasets/pyatakov/india-agriculture-crop-production (1997–2021)
- https://www.kaggle.com/datasets/nikhilmahajan29/crop-production-statistics-india

**Columns needed:** `state, district, crop, season, year, area, production` (yield derivable).

**How I would use it.** Replace the "guess the crop from NPK" toy with a
defensible model: *what actually grows well in your district and season*,
ranked by real yield, then refined by your soil test. That is a materially
more honest product — and it finally includes wheat.

---

## P0-2. Crop disease IMAGES (the photo upload currently does nothing)

**Problem it fixes.** Pest photos are uploaded and stored but **never
analysed** — `image_hint` is written to the DB and ignored. The diagnosis is
text-only.

**IMPORTANT finding — do not just grab PlantVillage.** PlantVillage (54,303
images, 38 classes) covers apple, blueberry, cherry, grape, orange, peach,
pepper, potato, raspberry, soybean, squash, strawberry, tomato, corn. It has
**no rice, wheat, cotton, sugarcane or chilli** — i.e. almost none of what our
farmers grow. Useful as a pretraining base only.
- https://www.kaggle.com/datasets/mohitsingh1804/plantvillage
- https://github.com/spmohanty/plantvillage-dataset

**What we actually want — India-relevant crops:**
- Top Agriculture Crop Disease India (cotton, jute, rice, sugarcane, wheat)
  https://www.kaggle.com/datasets/kamal01/top-agriculture-crop-disease
- Rice: Dhan-Shomadhan; Wheat: "Wheat Disease Detection" (Kaggle)
- Cotton leaf disease set (8 classes, ~2.1k original images)

**Format:** folders named `<crop>___<disease>/` containing JPGs. A few hundred
images per class is enough for transfer learning.

**Honest cost note.** This is the one item that needs real compute (fine-tuning
a small CNN, e.g. MobileNetV3) and will add ~30–60 MB to the serving image.
Worth it: photo-based diagnosis is the feature farmers actually want.

---

## P1-3. Soil Health Card district nutrient data

**Problem it fixes.** Soil Check asks a farmer to type N/P/K/pH from a report
many do not have. With SHC district baselines we can pre-fill sensible defaults
("typical for Karnal, Haryana") and flag how their field compares.

**Source:** Nutrient Dashboard, https://soilhealth.dac.gov.in/nutrient-dashboard
(12 parameters; district-level aggregates). Scraped district examples exist,
e.g. https://github.com/deepanshu-yadav/soil_data_analysis

**Columns needed:** `state, district, N_low/medium/high %, P_*, K_*, pH, OC, EC`
(percentage-of-samples buckets are fine — that is how SHC publishes).

---

## P1-4. Historical mandi prices (real trends, not fake arrows)

**Problem it fixes.** Market rows currently show a **"Steady" badge computed
from a single day's snapshot** — meaningless. With history we can show a real 7/30-day
trend and a "sell now vs hold" signal.

**Sources:**
- data.gov.in daily mandi prices (the live API we already use)
  https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi
- **CEDA (Ashoka University) — cleaned, downloadable history:** https://agmarknet.ceda.ashoka.edu.in/
- Kaggle: https://www.kaggle.com/datasets/arjunyadav99/indian-agricultural-mandi-prices-20232025
- Kaggle: https://www.kaggle.com/datasets/ishankat/daily-wholesale-commodity-prices-india-mandis

**Columns needed:** `date, state, district, market, commodity, variety, min_price, max_price, modal_price`.
Even 12 months for the top ~20 commodities is plenty.

---

## P1-5. Rainfall normals (better irrigation advice)

**Problem it fixes.** "When to Water" uses a single user-entered rainfall
number. District normals let us compare *this season vs normal* and adjust the
schedule — the actual agronomic question.

**Sources:**
- IMD gridded 0.25° daily rainfall, 1901–2024: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html
- District rainfall statistics: https://mausam.imd.gov.in/imd_latest/contents/rainfall_statistics.php
- data.gov.in rainfall catalogue: https://www.data.gov.in/catalog/rainfall

**Columns needed (simplest useful form):** `state, district, month, normal_rainfall_mm`.
The NetCDF gridded set is powerful but heavy — the district-month CSV is enough.

---

## P2-6. Crop-wise fertilizer recommendations (replace invented thresholds)

**Problem it fixes.** The fertilizer and irrigation "models" are Random Forests
fitted on **rule-generated synthetic data invented in code** (thresholds like
N<45). The advice is sane but the provenance is not defensible.

**Source:** ICAR / state agricultural university package-of-practices tables —
recommended N:P:K kg/ha per crop per state, and split-application schedules.
Also crop coefficient (Kc) tables from FAO-56 (we already use these in satellite-ml).

**Columns needed:** `crop, state (or agro-climatic zone), N_kg_ha, P_kg_ha, K_kg_ha, basal_%, split_2_%, split_3_%, notes, source_url`.

---

## What I do NOT need
- More scheme data — the 12-scheme catalog is committed and source-cited.
- More text disease rows — 100 rows / 47 diseases already committed.
- Farming tips — 16 bilingual articles already committed.
- Satellite imagery — `satellite-ml/` generates its own and can pull Sentinel via GEE.

## Ground rules for anything you send
1. **Licence must permit redistribution** (data.gov.in = NDSAP open; Kaggle
   varies — check the licence tab). Tell me the licence and I record it.
2. Raw file as-downloaded is fine; I will clean, subset and document it.
3. If it is over ~50 MB, we keep it out of git and load it at build time.
