# Backend/frontend code review — issues found and fixed

Scope: `backend/` and `frontend/` application logic (API routes, validation,
state handling, edge cases). Datasets, trained model weights, and ML
architecture were explicitly out of scope and were not touched — confirmed
via `git diff` showing zero changes to `backend/app/ml/tamper_model.py`,
`scripts/train_tamper_cnn.py`, `scripts/generate_tamper_training_data.py`,
or any `.pth` checkpoint.

Process followed for every fix below: write/extend a test that reproduces
the bug → run it and confirm it fails → apply the fix → confirm the same
test now passes → run the full backend suite (not just the new test) before
moving to the next issue. Every "confirmed fails" and "confirmed passes"
claim below was actually executed, not assumed.

**Final state: 106 passed, 1 failed** (`test_pasted_photo_is_feathered_at_the_border`
in `test_synthetic_generator.py` — pre-existing, unrelated to anything in
this pass; already failing before this review started).

---

## 1. Full issue list (as reported before any fix was made)

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | CRITICAL | `backend/app/services/audit_service.py` | `verify_chain` never checked a block's `previous_hash` against the *actual* preceding block's `entry_hash` — only self-consistency. A tamperer could edit a record and re-sign just that record's own hash undetected. |
| 2 | HIGH | `backend/app/services/mrz_service.py` (×3) | Any garbled MRZ sex character was silently coerced to `'M'` during parsing, before Rule 7 (`SEX_CODE_FORMAT`) ever saw it — making that rule permanently unreachable against real OCR'd data. |
| 3 | HIGH | `frontend/src/pages/CaseDetailPage.tsx` | Document image URL built via `.split('/').pop()` on a raw OS path; on Windows (confirmed against the live DB) the path is backslash-separated, so the split does nothing and the image breaks. |
| 4 | MEDIUM | `backend/app/api/routes/screening.py`, `demo.py` | Random case-number generation had no collision handling against the unique DB constraint — a collision raised an unhandled 500. |
| 5 | MEDIUM | `backend/app/api/routes/dashboard.py` | "Cases requiring review" KPI hardcoded `risk_score >= 25.0`, ignoring the officer-editable `threshold_low` policy. |
| 6 | MEDIUM | `backend/app/services/rules_engine.py` | RULE 4's substring-containment tolerance had no length floor — a near-degenerate short OCR reading trivially "matched" any longer document number. |
| 7 | LOW/MEDIUM | `backend/app/services/face_service.py` | Document-side face detection had no multiple-face check, unlike the symmetric live-capture side. |
| 8 | LOW | `frontend/src/components/CaseHeader.tsx` | Officer-decision form state seeded once via `useState`, never resynced after a "Refresh" fetches different server data. |

---

## 2. Each fix, in order, with test evidence

### 1. Audit chain linkage never verified (CRITICAL)

**Test:** `backend/tests/test_api.py::test_chain_verification_detects_a_block_tampered_and_self_resigned` — runs a demo scenario, directly edits one real `AuditLog` row's `action` field and re-signs *only that row's own* `entry_hash` (exactly what an attacker with DB access and knowledge of the hash algorithm — no secret key involved — would do), then asserts `GET /api/audit/verify` reports `valid: False`.

**Confirmed failing before the fix:** `assert False is True` — the tampered chain reported `valid: True`.

**Fix:** `AuditService.verify_chain` now walks the chain tracking an `expected_prev_hash` accumulator and additionally checks `log.previous_hash == expected_prev_hash` (the actual preceding block's real hash) at every step, not just each block's internal self-consistency. Also had to decide what "verify this one case's chain" (`/api/audit/cases/{id}/verify`, currently unused by the frontend UI) means once the walk is chain-wide: it now always walks the *full* global ledger (the only sequence a hash chain's links are meaningful over — a case's own entries are interleaved with every other case's), while still reporting `total_records`/`head_hash` scoped to that case for display.

**Confirmed passing after the fix**, and the test restores the tampered block to its original state in a `finally` block afterward (this suite shares one persistent sqlite DB across runs — a broken chain would otherwise fail *every* later chain check, in this run and future ones). One earlier iteration of this test run, before that cleanup existed, did leave the DB in a broken state; it was manually detected and repaired before finalizing.

**Full suite after this fix: 101 passed** (up from the session baseline of 100), no regressions.

### 2. MRZ sex-code silently defaulted to 'M' (HIGH)

**Test:** `backend/tests/test_mrz.py::test_garbled_sex_code_is_preserved_not_silently_defaulted_to_m` — builds a genuine, checksum-valid TD3 MRZ pair with the sex character OCR'd as `'G'` (a plausible misread, not M/F/X/`<`), and asserts `parse_td3` returns `sex == "G"` rather than `"M"`.

**Confirmed failing before the fix:** `AssertionError: assert 'M' == 'G'`.

**Fix:** All three occurrences (`parse_td3`, `parse_td2`, `parse_td1`) changed from *"map anything unrecognized to `'M'`"* to *"map only literal `'<'` filler to `'X'` (ICAO's own 'unspecified' code); pass everything else through uppercased, untouched."* This lets Rule 7 (`SEX_CODE_FORMAT` in `rules_engine.py`) actually see and flag a genuinely malformed code from real OCR output, which it could never do before.

**Confirmed passing after the fix.** Full MRZ + rules suite: **29 passed** (`test_mrz.py` + `test_rules.py`).

**Measured behavior change (per the "report real numbers" rule) — re-ran `scripts/evaluate_mrz_on_midv2020.py`, both before and after, against real MIDV-2020 data (n=400):**

| Metric | Before this fix | After this fix |
|---|---|---|
| End-to-end ICAO checksum pass rate | 134/400 (33.5%) | 134/400 (33.5%) — **unchanged** |
| Sex field-level exact-match rate | **322/362 (89.0%)** ← corrected | 344/362 (95.0%) ← was measured *before* today's fix, in `SESSION_SUMMARY.md` |

Read this the right way round: the field-match rate for `sex` **dropped** from 95.0% to 89.0% after the fix, and that drop is *correct, not a regression*. The old 95.0% figure was artificially inflated — every garbled sex character was being silently force-corrected to `'M'`, which coincidentally matched MIDV-2020's ground truth often enough (most specimens are male) to look better than it really was. 89.0% is the honest number: real OCR misreads of the sex character are now reported as what they are (mismatches) instead of being quietly papered over. No other field's match rate or the checksum pass rate moved at all, confirming the fix is scoped precisely to the sex field.

### 3. Windows-broken document image URL (HIGH)

**Test:** No frontend test framework exists in this repo at all (`frontend/package.json` has no test script, `node_modules` isn't installed, nothing is set up). Rather than add a new framework for one fix, verified with a standalone Node script (no dependencies) reproducing `CaseDetailPage.tsx`'s exact logic against a real path pulled from the live `border_mesh.db`:
`C:\Users\Sharaj R Shetty\Downloads\SyntaxSquad\uploads\documents\seed_BM-2026-10020.jpg`

**Confirmed failing before the fix:** old logic produced
`/uploads/documents/C:\Users\Sharaj R Shetty\Downloads\SyntaxSquad\uploads\documents\seed_BM-2026-10020.jpg` — the entire absolute path, unsplit, appended after `/uploads/documents/`.

**Fix:** extracted the logic into `frontend/src/lib/paths.ts` (`basenameFromPath` / `buildUploadedDocumentUrl`), splitting on `/[\\/]/` (either slash) instead of `'/'` alone. `CaseDetailPage.tsx` now calls this instead of inlining the broken logic.

**Confirmed passing after the fix** via the same standalone script against three cases: the real Windows path (now correctly extracts `seed_BM-2026-10020.jpg`), a POSIX-style path, and an already-absolute `http(s)://` URL (passthrough, unchanged) — all three now produce the correct result.

**Honest limitation:** this is verified logic, not an integrated automated test, because none exists for the frontend yet. If you want this covered going forward, adding `vitest` (a few-line config for a Vite project) is the natural next step — flagging it rather than silently deciding to add a whole new toolchain mid-bug-fix.

### 4. Case-number collision has no retry (MEDIUM)

**Test:** `backend/tests/test_api.py::test_upload_survives_a_random_case_number_collision` — pre-creates a `Case` with a specific number, monkeypatches `random.randint` to return that exact colliding value on its first call (and behave normally after), then uploads a document and asserts it still succeeds with a *different* case number.

**Confirmed failing before the fix:** `sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: cases.case_number`, unhandled, surfacing as a 500.

**Fix:** `screening.py` now has `_create_case_with_unique_number()`, retrying up to 5 times on `IntegrityError` with a fresh random number each time. Applied the same pattern to `demo.py`'s scenario endpoint (same underlying gap, lower-probability 16⁵ space) — and while there, decoupled the specimen image filenames from the possibly-colliding `case_number` (they now use the already-unique `case_uid`), so a retry never has to throw away already-generated synthetic images.

**Confirmed passing after the fix**, including a re-run to confirm the test's own setup is idempotent against this suite's shared, persistent DB.

**Full suite after this fix: 103 passed.**

### 5. Dashboard KPI ignores the configured policy threshold (MEDIUM)

**Test:** `backend/tests/test_api.py::test_dashboard_requiring_review_kpi_respects_the_configured_low_threshold` — creates a probe case (`risk_score=30`, `officer_decision=PENDING`), then at two different `threshold_low` policy values (10 and 60) asserts the dashboard's reported `cases_requiring_review` count exactly equals an independently-computed expected count (`PENDING AND risk_score >= <the live threshold_low>`) — not a fixed number, so the assertion is meaningful regardless of what else is in this suite's shared, non-empty DB.

**Confirmed failing before the fix** (verified twice: once naturally during development, and once more rigorously by `git stash`-ing the fix, re-running this exact final test version against the reverted code, confirming failure, then restoring the fix).

**Fix:** `dashboard.py` now calls `get_policy(db).threshold_low` instead of a hardcoded `25.0`.

**Confirmed passing after the fix.** Full suite after this fix: **104 passed.**

### 6. RULE 4 substring match has no length floor (MEDIUM)

**Test:** `backend/tests/test_rules.py::test_document_number_crosscheck_rejects_a_trivially_short_ocr_reading` — OCR'd document number `"7"` (a near-total OCR failure) against MRZ document number `"X1234567"` (which happens to contain a `'7'`), asserting this must still be flagged as an inconsistency.

**Confirmed failing before the fix:** `assert False` — the single-character reading was silently treated as consistent via substring containment.

**Fix:** added a `MIN_SUBSTRING_MATCH_LENGTH = 5` floor — substring containment is now only trusted when the shorter of the two cleaned strings is at least 5 characters, leaving the bounded fuzzy-edit check and genuinely-truncated real partial reads (still ≥5 chars) unaffected.

**Confirmed passing after the fix.** All 10 `test_rules.py` tests pass, including the pre-existing "survives a single OCR slip" test (8-character strings, well above the new floor) and "still catches a real mismatch" test — confirming the fix didn't loosen or break either existing behavior.

**Full suite after this fix: 105 passed.** No MIDV-2020/CASIA benchmark re-run needed — this rule isn't exercised by either evaluation script (both measure raw OCR/checksum extraction, not the rules engine's cross-check signals), so no measured number changed.

### 7. Document-side face detection has no multiple-face check (LOW/MEDIUM)

**Test:** new file `backend/tests/test_face_service.py` — a fake detector that returns two face boxes on its first call (the document side) and one box thereafter (the live side), isolating the document-side gap specifically from the live-side check that already exists. Uses lightweight PIL-generated images and a monkeypatched detector rather than loading the real MTCNN/InceptionResnetV1 models.

**Confirmed failing before the fix**, and confirmed *how* it failed matters here: it didn't just get the wrong status — it crashed with `AttributeError: '_FakeDetector' object has no attribute 'check_quality'`, because execution ran straight past where it should have short-circuited, all the way into full verification. That's the clearest possible evidence the check didn't exist at all.

**Fix:** added a `len(doc_faces) > 1` branch mirroring the existing live-side one, returning `status: "MULTIPLE_FACES"` with a document-specific signal and explanation before any embedding/comparison work happens.

**Confirmed passing after the fix. Full suite after this fix: 106 passed.**

This only fires when the detector finds multiple plausible face regions in the *document* image specifically — the LFW calibration benchmark (`scripts/calibrate_face_threshold.py`, 98.0%/0.60%/3.40%, reported in `SESSION_SUMMARY.md`) uses single pre-cropped face pairs and never exercises this path, so that benchmark is unaffected by this fix.

### 8. Officer-decision form state goes stale after Refresh (LOW)

**Fix:** added a `useEffect` in `CaseHeader.tsx` keyed on `[caseData.officer_decision, caseData.officer_notes]` that resyncs local `decision`/`notes` state whenever the *server* value actually changes (a Refresh reveals new data, or another officer's decision lands) — while never touching local state on an unrelated `caseData` update (e.g. a biometrics purge), so an officer's own in-progress, not-yet-submitted note is never silently overwritten.

**Honest limitation:** same as issue #3 — no frontend test framework exists, so this was verified by code/dependency-list reasoning (confirmed the `useEffect` only re-fires when the two specific server-sourced values change, not on every re-render or unrelated prop update), not by an executed test. Lowest-severity item on the list; flagging the verification gap rather than overstating it.

---

## 3. Honest accounting

**Verified by an actually-executed, failing-then-passing test:** issues #1, #2, #4, #5, #6, #7 (all backend).

**Verified by an actually-executed standalone script (not an integrated test, because no frontend test framework exists in this repo):** issue #3.

**Verified by code reasoning only, not execution** (lowest severity, and the same missing-frontend-test-framework constraint applies): issue #8.

**Measured, not just asserted "fixed"** (per the instruction that anything with a number attached needs before/after, not a bare claim): issue #2's MRZ sex-field match rate, 95.0% → 89.0%, with the explanation for *why* the number correctly went down.

**Not touched, as instructed:** `backend/app/ml/tamper_model.py`, `scripts/train_tamper_cnn.py`, `scripts/generate_tamper_training_data.py`, the committed `tamper_cnn.pth` checkpoint, and everything else under `backend/app/ml/weights/`.

**Full backend suite, final state:** 106 passed, 1 failed (pre-existing, unrelated, predates this review).
