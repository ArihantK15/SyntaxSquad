# CLAUDE.md — Standing Rules for This Project

These rules apply to all future work on this project (BorderMesh). They are
not suggestions — they are the standard this project has been held to
already (see `SESSION_SUMMARY.md` and prior commit messages, e.g. the tamper
CNN's honest synthetic-only-baseline disclosure, the SIDTD revert, the
liveness heuristic's asymmetric moire/halftone recall, the two failed face
fine-tuning attempts). Maintain that standard. Do not relax it as a deadline
approaches — that is exactly when it matters most.

## Verification discipline

- Never state a test result, a "before/after" number, or "confirmed working"
  without actually running the command and showing the real output in this
  session. A claim that isn't backed by output shown in this session is a
  guess, not a result.
- If something can't be verified (no browser access, no dataset available,
  no way to run it in this environment), say so explicitly rather than
  assuming it's fine or letting the claim stand unqualified.
- When reporting results back, distinguish clearly between what was
  personally verified (ran a command, saw the output) and what is being
  inferred or assumed. Don't blend the two into one confident-sounding
  sentence.

## No guessing

- Don't guess package names, file paths, API signatures, or install
  commands. If unsure, check first — search docs, inspect the actual
  file/package/schema — rather than trying a plausible-sounding guess and
  fixing it after it fails.
- The same applies to numbers: don't state an accuracy figure, a threshold,
  or a dataset size from memory when it can be checked against the actual
  code, script output, or committed artifact.

## Honesty over confidence

- If a fix, a number, or a claim has a real caveat or limitation, state it
  plainly in the same breath as the result — not buried at the end of a
  long message, not omitted, not left for the user to ask about.
- Never round an uncomfortable number to make it sound better (e.g., don't
  round 39.5% recall up to "around 40%" if the exact number is what matters
  in context). Precision is part of honesty here, not pedantry.
- Disclose synthetic-only validation, non-certified heuristics, reverted
  attempts, and known gaps as plainly as `KNOWN_LIMITATIONS.md` and
  `SESSION_SUMMARY.md` already do. New work should meet that same bar, not
  a lower one.

## Scope discipline

- When asked to investigate, investigate and report — don't start building
  until explicitly told to proceed.
- Before building something described as "already scoped" or "as previously
  discussed," check whether it already exists in the codebase first. Audit
  and verify real, working code rather than blindly re-implementing it.
- If a request would require something not actually achievable (real
  government API access, certified hardware, a production KMS, etc.), say
  so directly instead of building a fake or simulated version without
  clearly flagging that it's fake.

## Reference material

- `SESSION_SUMMARY.md` — the standard for how measured numbers are reported:
  verification method stated up front, every number labeled as measured /
  quoted-from-comment / pending, before/after comparisons reproduced live
  where feasible.
- `KNOWN_LIMITATIONS.md` — the standard for how limitations and known gaps
  are disclosed: plainly, with real numbers, with the honest "why," no
  spin.
- Prior commit messages on this project's history for the expected level of
  rigor before claiming something works, is fixed, or is validated.
