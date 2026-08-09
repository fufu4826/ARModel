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
| 14B | IN_PROGRESS | Extract content repositories |
| 14C | TODO | Extract analytics/audit/narration services |
| 14D | TODO | Organize Flask routes/Blueprints where safe |
| 15 | TODO | Post-refactor security review |
| 16 | TODO | Content/data integrity review |
| 17 | TODO | Final automated regression |
| 18 | TODO | Local browser QA |
| 19 | TODO | Final Git audit |
| 20 | TODO | Integrate latest origin/main |
| 21 | TODO | Push and remote CI |
| 22 | TODO | Vercel deployment |
| 23 | TODO | Production read-only QA |
