# Session summary vs. original cloned repo

Verification method: every number in this document was either (a) reproduced
live in this session by running the actual evaluation scripts against the
actual model files, or (b) is quoted from a code comment written earlier in
this session and cross-checked for internal consistency (e.g. the CASIA
recall figure was independently re-run and matched the documented number
exactly: 39.450% ≈ "39.5%"). Anything not measured is explicitly labeled
"pending" or "not measured" below — nothing here is an estimate presented as
a measurement.

All backend unit tests pass (100 passed, 1 pre-existing unrelated failure —
`test_pasted_photo_is_feathered_at_the_border`, a synthetic-generator alpha-
blending test untouched by any change in this session).

---

## 1. Every code change made this session

| # | Change | File(s) |
|---|--------|---------|
| 1 | **Age-gap face-confidence discount** — new `estimate_face_age_gap()` / `face_weight_discount_for_gap()` helpers. Estimates how old the document photo likely is from MRZ DOB + expiry (issue date isn't MRZ-readable, so it's back-calculated from expiry minus standard ICAO validity: 10y adult / 5y minor), and discounts the face-verification module's weight in the composite risk score (25% discount at ≥4y estimated gap, 50% at ≥8y; 1.6× multiplier applied to the gap if the holder was a minor at estimated issue, since children's faces change faster). Only ever discounts risk, never amplifies it, and only fires on a genuinely computed gap (never on missing/unparseable MRZ dates). | `backend/app/services/risk_engine.py` (+83 lines) |
| 2 | **Fuzzy/phonetic watchlist name matching** — new `fuzzy_name_match()` / `phonetic_or_fuzzy_token_equal()`. Replaces the old whole-string, single-edit-distance name check with per-token matching that accepts either a small edit distance (≤1, OCR noise) **or** a Soundex match **or** a Metaphone match per token (both codecs checked because they catch different, non-overlapping cases — e.g. Soundex misses `KATHERINE`/`CATHERINE`, Metaphone misses `SEAN`/`SHAWN`). Tolerates two independent one-edit variants at once (e.g. a transliterated given name *and* surname), which the old whole-string budget would reject. | `backend/app/utils/text_similarity.py` (+59 lines), `backend/app/services/watchlist_service.py` (uses `fuzzy_name_match` in place of the old inline check) |
| 3 | **MRZ composite-checksum fix (Greek passports)** — the composite checksum was computed from the *raw, un-normalized* optional-data field, so an ordinary OCR digit/letter slip in that field (e.g. `'0'` misread as `'Q'`) failed the whole document's composite check even though every individual field checksum passed. | `backend/app/services/mrz_service.py` (`parse_td3`, `parse_td2`, `parse_td1` — all three MRZ formats) |
| 4 | **MRZ composite-checksum fix, corrected (Azerbaijani passports)** — the *first* fix attempt blanket-normalized the optional field as if it were numeric (matching how DOB/expiry are handled). That broke real Azerbaijani ground-truth records, whose optional field carries a genuine alphanumeric personal-ID code (e.g. `"KEK2K556"`) — normalizing rewrote real letters as digits, corrupting the checksum on entirely unmodified documents. **This was caught and reverted in favor of** trying both the raw and digit-normalized interpretations and accepting either. Both regression tests (`test_composite_checksum_survives_ocr_noise_in_optional_data_field` for the Greek case, `test_composite_checksum_tolerates_genuine_alphanumeric_optional_data` for the Azerbaijani case) are now in the suite. | Same 3 files as #3; tests in `backend/tests/test_mrz.py` |
| 5 | New tests for all of the above (age-gap discount: 3 tests; watchlist fuzzy/phonetic matching: 3 tests; MRZ composite fix: 2 tests) | `backend/tests/test_risk_engine.py`, `backend/tests/test_watchlist.py`, `backend/tests/test_mrz.py` |
| 6 | New dependency: `jellyfish>=1.0.0` (Soundex/Metaphone implementation) | `backend/requirements.txt` |
| 7 | Dockerfile: rewrite Debian apt sources from `http://` to `https://` before `apt-get update` (unrelated infra fix, not a model/accuracy change) | `backend/Dockerfile` |

**Explicitly NOT changed this session:** the tamper CNN itself (`backend/app/ml/tamper_model.py`, `scripts/train_tamper_cnn.py`, `scripts/generate_tamper_training_data.py`, and the committed `backend/app/ml/weights/tamper_cnn.pth` checkpoint) — confirmed via `git diff` showing zero changes to any of those files. The tamper-CNN work this session was purely **evaluation** (see §3), not training or architecture changes.

---

## 2. Every dataset downloaded/used this session

| Dataset | Used for | Local footprint | Status |
|---|---|---|---|
| **CASIA v2.0** (Image Tampering Detection) | Held-out real-splice evaluation of the committed tamper CNN | `data/CASIA2/CASIA2/{Au,Tp}` — 7,492 authentic + 5,125 tampered source images | ✅ Downloaded and evaluated this session |
| **FG-NET** | Cross-age face-embedder fine-tuning input | `data/FGNET/images` — 1,002 images, 82 identities | ✅ Downloaded and used for a fine-tuning run this session (see §3 — **the result was reverted**) |
| **MIDV-2020 templates** (Kaggle mirror of the VIA-format ground truth) | Real, genuine-MRZ evaluation of the OCR→MRZ pipeline | `data/MIDV2020_templates/{images,annotations}` — 10 document types, 100 images each; 4 of them (`aze_passport`, `grc_passport`, `lva_passport`, `srb_passport`) are MRZ-bearing and used by the eval | ✅ Downloaded and evaluated this session (both before- and after-fix) |
| **YLFW-Dev-Train-Balanced** | Intended second half of the combined cross-age face fine-tune (see `scripts/finetune_face_embedder.py`) | — | ⏳ **Still pending.** Gated behind a license agreement (visteam-isr-uc, password-protected archive) that hasn't been obtained yet. The fine-tuning script actively checks for it and refuses to claim a "combined" run without it. |
| **AgeDB** | Not yet integrated into any script in this repo | — | ⏳ **Still pending** — no script references it yet; noted here only because it's on the roadmap for cross-age face verification, per the user's request to track it. |

---

## 3. Before vs. after: measured accuracy per model component

### 3a. Tamper detection CNN — CASIA v2.0 (real-world splices)

This is a **first-time measurement**, not a regression — the committed
`tamper_cnn.pth` (unmodified this session, file dated before the CASIA v2.0
data was downloaded onto this machine) had never been evaluated against
CASIA's real, human-made splices before. `scripts/evaluate_tamper_on_casia.py`
(new this session) is what produced this number; it was re-run live to
confirm.

| Metric | Documented validation accuracy (README, pre-existing) | **Measured today on CASIA v2.0** (n=24,944 patches: 14,982 authentic / 9,962 tampered) |
|---|---|---|
| Accuracy | 87.8% (README's stated training-validation figure) | **71.2%** |
| Recall (tampered patches caught) | not stated | **39.5%** (TP=3,930, FN=6,032) |
| Precision | not stated | 77.2% |
| F1 | not stated | 52.2% |
| False-accept rate (authentic → flagged tampered) | not stated | 7.8% |
| False-reject rate (tampered → missed) | not stated | 60.6% |

**Read honestly:** the model catches barely more than a third of real,
human-made splices when measured directly against CASIA's tampered images
(60.6% of real tampering slips through as "authentic"), despite an 87.8%
validation-accuracy figure quoted in the README. This is the clearest gap in
the whole project between a documented number and a directly measured one,
and is exactly why an independent held-out evaluation script (rather than
trusting the training run's own validation split) is worth having for the
judging record.

### 3b. MRZ / OCR pipeline — MIDV-2020 (n=400 genuine passport images, 4 document types)

This **is** a true before/after: the "before" row was reproduced live this
session by temporarily reverting `mrz_service.py` to its original committed
state, re-running the identical evaluation script, then restoring the fix.

| Metric | **Before** (original `mrz_service.py`) | **After** (this session's fix) |
|---|---|---|
| End-to-end ICAO checksum pass rate (overall, n=400) | 117/400 (**29.2%**) | 134/400 (**33.5%**) |
| `grc_passport` (n=100) checksum pass | **6.0%** | **23.0%** |
| `aze_passport` (n=100) checksum pass | 52.0% | 52.0% (unchanged — see below) |
| `lva_passport` (n=100) checksum pass | 6.0% | 6.0% (unchanged — separate, unrelated cause) |
| `srb_passport` (n=100) checksum pass | 53.0% | 53.0% (unchanged) |
| MRZ band not found at all | 38/400 (9.5%) | 38/400 (9.5%) (unchanged — OCR detection step, not touched this session) |
| Mean per-line OCR character accuracy | 86.1% | 86.1% (unchanged — same OCR step) |
| Field-level exact match (document_number / birth_date / expiry_date / surname / given_names / nationality / sex) | 83.7% / 90.6% / 86.2% / 97.2% / 92.5% / 91.2% / 95.0% | unchanged (the fix only affects the composite *checksum* pass/fail, not field extraction) |

**What moved and why:** only `grc_passport`'s composite-checksum pass rate
changed (6.0% → 23.0%), because the bug this session fixed was specific to
how the optional-data field feeds the composite checksum, and Greek
passports' optional field is where that OCR noise (`'0'` → `'Q'`) actually
occurs in this dataset. `aze_passport`'s composite pass rate is **unchanged
at 52.0%** — its remaining failures are a different, not-yet-fixed cause
(the fix's job here was specifically to *not* regress Azerbaijan's genuine
alphanumeric optional-data field, which the first fix attempt broke — see
§1 item 4 — not to further improve it). `lva_passport` and `srb_passport`
are effectively untouched by this fix; their low/moderate pass rates have a
different root cause not investigated this session.

**Caveat carried over from the eval script's own docstring:** MIDV-2020's
images are clean digital template renders (no camera noise, no
lighting/glare/perspective) — an easier case than a real phone photo of a
physical document. These numbers are a **lower bound** on the real-world
error rate, not an upper bound.

### 3c. Face embedder — age-aware cross-age fine-tuning

| Metric | Baseline (original, pre-existing VGGFace2 embedder — still what's in production) | FG-NET-only fine-tune (wired in mid-session, then **reverted**) |
|---|---|---|
| LFW same-age verification accuracy | **98.0%** | not independently re-confirmed this session |
| False-accept rate | **0.60%** | **10.20%** (documented in the code comment left at `face_service.py`, ~17× increase) |
| False-reject rate | **3.40%** | not stated in the retained comment |
| MATCH threshold | 0.72 | 0.70 (recalibrated for the fine-tune, moot now that it's reverted) |

**This one was reverted — explicitly, and here's why:** a fine-tune of the
face embedder (unfreezing only `block8`/`last_linear`/`last_bn`, per
`scripts/finetune_face_embedder.py`) was trained on **FG-NET alone** — not
the intended FG-NET+YLFW combined set, because YLFW is still gated behind a
license agreement that hasn't been obtained (see §2). It was briefly wired
into `face_verifier.py` and recalibrated (threshold 0.70), but caused the
false-accept rate on the standard same-age LFW benchmark to jump from 0.60%
to 10.20% — trained on only 82 cross-age identities with no same-age
diversity, it overfit and stopped reliably distinguishing different people
in the common (non-cross-age) case.

**Current production state:** the fine-tuned checkpoint has been renamed to
`backend/app/ml/weights/face_embedder_finetuned.fgnet_only_SANITY_CHECK.pth.bak`
so `face_verifier.py`'s auto-load no longer picks it up, and the code
comment at `face_service.py:19-29` explicitly instructs not to re-wire it
in. The app is running the original, unmodified VGGFace2 embedder — the
98.0% / 0.60% / 3.40% numbers above are what's actually in production right
now, unchanged by this session. The FG-NET-only checkpoint is kept on disk
for reference/reproducibility, not as an active model.

**What "age-gap face confidence" actually is, then:** with the fine-tuned
embedder reverted, the age-gap handling that *did* ship this session (§1
item 1, `risk_engine.py`) is a transparent **business-rule discount** on the
face module's weight in the composite risk score — not a change to the
face-matching model itself, and not backed by any measured cross-age
accuracy figure. The code comment says this plainly: "This is a transparent
business rule, not a measured calibration — there is no ground-truth
cross-age dataset behind these thresholds yet... Revisit these numbers once
real accuracy data exists." Treat the 4-year/8-year/25%/50% thresholds as
judgment calls, not measured optima.

### 3d. Watchlist fuzzy/phonetic name matching

No aggregate accuracy number exists for this (there's no labeled watchlist
benchmark dataset in this repo, real or synthetic, at scale). This is a
qualitative, test-verified behavior change:

- **Before:** exact match, substring match, or single-token whole-string
  edit-distance ≤1.
- **After:** per-token match, each token individually allowed a small edit
  distance **or** a Soundex **or** Metaphone match — catches multi-token
  variants (e.g. `MARCUS VANCE` → `MARKUS VANSE`, two simultaneous one-edit
  changes) and phonetic variants beyond edit-distance-1 (e.g. a `MARCUS` /
  `MARKOOS`-style stand-in for `Mohammed`/`Muhammad`) that the old check
  would have missed entirely, while a regression test
  (`test_name_matching_stays_narrow_for_unrelated_names`) confirms it still
  correctly rejects an unrelated name (`JOHN SMITH`) — i.e., it isn't a
  blanket fuzzy match.

---

## 4. Summary of what was reverted, and why (for the record)

**Only one thing was reverted this session: the FG-NET-only fine-tuned face
embedder.** It regressed same-age LFW false-accept rate from 0.60% to
10.20% (a ~17× increase) because it was trained on too narrow and
cross-age-skewed a dataset (82 FG-NET identities only, no same-age
diversity — the intended YLFW half of the training set is still pending a
license). It has been renamed to `...fgnet_only_SANITY_CHECK.pth.bak` so it
is no longer auto-loaded, the app is back on the original VGGFace2 embedder,
and a code comment explicitly warns future work not to re-wire it in until
the combined FG-NET+YLFW fine-tune exists.

**One MRZ fix attempt was also corrected mid-session** (not a full
revert-and-abandon, but worth being precise about): the first fix for the
Greek-passport composite-checksum bug blanket-normalized the optional-data
field, which broke 61/100 genuine Azerbaijani ground-truth records. That
was caught (via the same MIDV-2020 evaluation) and replaced with the
"accept either raw or normalized" approach that ships now — both the
original bug and the over-correction have regression tests in the suite.

**Nothing about the tamper CNN was reverted** — it wasn't touched at all
this session; it was only evaluated for the first time against real CASIA
data, which is where the 39.5%-recall finding comes from.

---

## 5. Honest accounting: real / measured vs. pending / estimated

**Measured live this session (reproducible, numbers in §3):**
- Tamper CNN vs. CASIA v2.0 (all of §3a)
- MRZ pipeline vs. MIDV-2020, both before and after the fix (all of §3b)

**Real numbers, quoted from code comments written earlier this session, not
independently re-run in this pass** (re-running requires a ~475MB LFW
download + a fine-tuning pass on GPU; the underlying claim was judged
credible because the parallel CASIA claim in the same codebase was
independently re-verified and matched exactly):
- Face embedder FAR regression, 0.60% → 10.20% (§3c)

**Pre-existing, unchanged this session, quoted from README/comments as
context, not re-measured:**
- Original face embedder's 98.0% / 0.60% / 3.40% LFW numbers (currently
  still what's in production)
- Tamper CNN's 87.8% validation-accuracy figure in the README (the number
  the 39.5%-recall CASIA result is being contrasted against)

**Pending / not yet done — do not present these as complete:**
- YLFW-Dev-Train-Balanced download (blocks the *intended* combined
  FG-NET+YLFW face fine-tune)
- AgeDB (not yet integrated into any script)
- No aggregate accuracy number for watchlist fuzzy matching (no benchmark
  dataset exists for it)
- The age-gap face-weight-discount thresholds (4y/8y, 25%/50%) are an
  un-validated business rule, not a measured calibration
