# ARModel Upgrade Plan

Status values: `TODO`, `IN_PROGRESS`, `PASS`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.

| Phase | Status | Scope |
| --- | --- | --- |
| 0 | PASS | Baseline and repository safety |
| 1 | PASS | Hidden public API protection |
| 2 | PASS | Session/security baseline |
| 3 | PASS | JSON deterministic normalization |
| 4 | PASS | Validator repair |
| 5 | PASS | GitHub Actions CI |
| 6 | PASS | CSRF protection |
| 7 | PASS | Serverless-safe Admin login rate limiting |
| 8 | PASS | CSP/security-policy evaluation |
| 9 | PASS | Serverless-safe analytics event architecture |
| 10 | PASS | Audit Log completeness and failure visibility |
| 11 | PASS | README/documentation reconciliation |
| 12 | PASS | Duplicate root JSON cleanup |
| 13 | PASS | Dependency management |
| 14A | PASS | Extract R2/GitHub storage services |
| 14B | PASS | Extract content repositories |
| 14C | PASS | Extract analytics/audit/narration services |
| 14D | NOT_APPLICABLE | Blueprint migration deferred: 41 stable routes and 252 endpoint references make namespace churn disproportionate after service extraction |
| 15 | PASS | Post-refactor security review |
| 16 | PASS | Content/data integrity review |
| 17 | PASS | Final automated regression |
| 18 | PASS | Local browser QA |
| 19 | IN_PROGRESS | Final Git audit |
| 20 | TODO | Integrate latest origin/main |
| 21 | TODO | Push and remote CI |
| 22 | TODO | Vercel deployment |
| 23 | TODO | Production read-only QA |
