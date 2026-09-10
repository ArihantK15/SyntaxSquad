# Case Detail Declutter & Real Risk Breakdown — Design

Date: 2026-09-10
Status: Approved by user, pending implementation plan

## Problem

`CaseDetailPage` renders all screening results — case header, risk score,
risk breakdown, OCR, MRZ, tamper forensics, face verification, evidence
list, and audit trail — as one uninterrupted vertical scroll. There is no
way to jump between sections, making the page hard to read at a glance.

Separately, the "Risk Breakdown" card on that page does not reflect the
backend's real computation. `risk_engine.py` already computes genuine
per-factor weighted contributions (`raw_risk`, `weighted_contribution`,
`top_signals` per factor), but this result is only returned once in the
risk-calculation step's HTTP response and is never persisted. When the
page is loaded or refreshed, the frontend reconstructs an approximation
from whatever fields happen to be on `analysis` (e.g. `raw_risk: 70` if
any MRZ rule failed, regardless of real severity) — CaseDetailPage.tsx
lines 54–90. This is misleading on the exact page meant to explain the
score.

## Scope

Two changes, bundled because they touch the same page:

1. Restructure `CaseDetailPage` layout to reduce clutter (tabs).
2. Persist and surface the risk engine's real breakdown so the page shows
   genuine numbers wherever real data exists.

Out of scope: any other page, the screening upload flow, ML model
changes (tracked separately as the "accuracy" sub-project), and
regenerating seed data (see Decision below).

## Part 1 — Frontend: Tabbed Case Detail Layout

**Always visible** (top of page, unchanged from today):
- Back / Refresh bar
- `CaseHeader` (officer decision form)
- `RiskScore` (score gauge)
- `RiskBreakdown` (factor summary)

**Tabbed below** (one panel visible at a time):
- OCR (`OCRResults`)
- MRZ (`MRZValidator`)
- Tamper (`TamperHeatmap`)
- Face (`FaceVerification`)
- Evidence (`EvidenceList`)
- Audit Trail (`AuditTimeline`)

Implementation: a new small reusable `Tabs` component
(`frontend/src/components/Tabs.tsx`) matching the existing dark
slate/cyan theme (same visual language as the toggle buttons already
used in `TamperHeatmap.tsx` and `ReviewQueuePage.tsx`), taking a list of
`{id, label, icon?}` and a `children` render-per-tab pattern. No new npm
dependency.

`CaseDetailPage.tsx` keeps its existing data-fetching (`fetchCase`) and
just changes the JSX structure below the risk row. None of the six
detail components change internally — they're relocated into tab panels
as-is. Default active tab: OCR (first in the pipeline order); tab state
resets to default on `caseId` change (i.e. not preserved across
navigating to a different case).

## Part 2 — Backend: Real Risk Breakdown Persistence

**Model** (`backend/app/models/__init__.py`): add
`risk_breakdown = Column(JSON, nullable=True)` to `DocumentAnalysis`.
No migration tooling exists in this project (schema is created via
`Base.metadata.create_all`); a fresh DB (SQLite file or the Postgres
container's volume) picks up the new column automatically. Existing
running containers/DB files need a re-create (already the recommended
path for schema changes in this prototype), and re-seeding for
demo data.

**Persistence sites** — both callers of `risk_engine.calculate()`:
- `backend/app/api/routes/screening.py` (risk step): set
  `analysis.risk_breakdown = risk_res["breakdown"]` before `db.commit()`.
- `backend/app/api/routes/demo.py` (demo scenario runner): pass
  `risk_breakdown=risk_res["breakdown"]` into the `DocumentAnalysis(...)`
  constructor.

**Schema** (`backend/app/schemas/__init__.py`): add
`risk_breakdown: Optional[List[RiskFactorBreakdown]] = None` to
`DocumentAnalysisOut`, reusing the existing `RiskFactorBreakdown` model.

**Frontend consumption** (`CaseDetailPage.tsx`): use
`analysis?.risk_breakdown` directly when present. When absent (seeded
demo cases — see Decision below), keep the current client-side estimate
as a fallback, with a one-line comment explaining why the fallback
exists (seeded cases never ran the real pipeline, so there's no genuine
per-signal data to draw from).

## Decision: Seeded Demo Data

The 20 cases from `scripts/seed_cases.py` are hand-authored fixtures,
not run through the real OCR/MRZ/tamper/face/risk pipeline — they have
no genuine signal data to build a real breakdown from regardless of this
change. Per user decision, we leave `seed_cases.py` untouched and keep
the frontend's existing best-effort estimate as a fallback for cases
with `risk_breakdown: null`. Cases run through actual screening
(including the 5 "demo scenario" buttons, which do run the real
pipeline via `demo.py`) will show genuine numbers.

## Testing

- Frontend: manual check — open a seeded case (falls back to estimate,
  unchanged behavior) and a freshly-screened case (real breakdown
  numbers match what the risk step returned), confirm tab switching
  works and no console errors.
- Backend: existing `backend/tests/test_risk_engine.py` and
  `backend/tests/test_api.py` should continue to pass unmodified (the
  new field is additive/nullable); add one assertion that a screened
  case's persisted `risk_breakdown` is non-null and matches the shape
  returned by the risk step.

## Isolation

All work happens in a dedicated git worktree (per user request), so the
currently-running docker-compose stack (backend/frontend/postgres, up
and serving) is untouched until the user reviews and decides to merge.
