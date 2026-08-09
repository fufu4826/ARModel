# ARModel Upgrade Runbook

Every run begins by reading the plan, status, and this runbook.

`READ PLAN -> READ STATUS -> VERIFY GIT -> SELECT FIRST TODO/IN_PROGRESS PHASE -> INSPECT -> MAKE SMALLEST SAFE CHANGE -> REVIEW DIFF -> RUN FOCUSED TESTS -> FIX -> RETEST -> RUN REQUIRED REGRESSION -> COMMIT -> UPDATE PLAN -> UPDATE STATUS -> START NEXT PHASE`

Permanent invariants:

- Never force-push `main` or discard unknown work.
- Never weaken tests to make them pass or modify Production content to mask code failures.
- Preserve Thai UTF-8 and never expose secrets.
- `#projects` remains a normal static Project grid/list. Never reintroduce a Project carousel.
- News slider remains the carousel; preserve Landing slider and narration behavior.
- Project cards show narration status only, never playback buttons.
- Preserve narration pending/confirm/cancel token, prefix, conflict, and safe-deletion protections.
- Use temporary/mock/local data for destructive browser tests.
- Integrate newer Production Admin-content commits safely.
- Never claim a verification that was not actually performed.
- Before a run ends, update plan and status with the exact next action and leave a clean tree when safely possible.
