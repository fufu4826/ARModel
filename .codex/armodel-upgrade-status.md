# ARModel Upgrade Status

Current branch: `codex/armodel-hardening`
origin/main: `44e3ca3aea333304dd7368dcb8562f3c5a445003`
Current HEAD: `9f22f66`
Working tree: checkpoint update pending after verified Phase 14C commits
Current phase: 14D — Organize Flask routes/Blueprints where safe
Last completed phase: 14C — Extract analytics/audit/narration services
Last commit: `9f22f66 Extract narration service from Flask app`
Last full pytest: `107 passed, 79 subtests passed`; audit focused `77 passed, 73 subtests passed`; narration focused `77 passed, 73 subtests passed`
Last validator: passed; 121 R2 URLs verified
Last JS checks: passed for carousel, narration, dashboard
Browser QA: not yet run
Push status: not pushed
CI status: workflow added locally; remote run not started
Deployment status: not started
Production QA: not started
External blockers: none known
Next exact action: inventory all Flask route decorators, endpoint names, template/JavaScript `url_for` dependencies, auth/CSRF decorators, and error/after-request hooks; determine the smallest safe route-module boundary without changing URLs or endpoint names, then implement and regression-test it or document why Blueprint migration is disproportionate.

Completed commits:
- `6b1df15 Prevent hidden content exposure in public APIs`
- `070eca3 Harden production sessions and security headers`
- `7cc7a5b Normalize site settings serialization`
- `c0133fb Keep data validator compatible with managed assets`
- `2f830c8 Run regression checks in GitHub Actions`
- `6873c29 Protect admin mutations against CSRF`
- `8691bd1 Add persistent ARModel upgrade checkpoints`
- `82c3e4b Rate limit admin login attempts`
- `f5ede0c Make analytics writes safe for serverless concurrency`
- `3c108e7 Complete admin audit coverage and failure reporting`
- `79326e8 Align documentation with current production architecture`
- `67e2cc5 Remove obsolete duplicate root data files`
- `e27cc54 Clarify runtime and development dependencies`
- `67127cd Extract storage integrations from Flask app`
- `17cc479 Extract content repositories from Flask app`
- `790d544 Extract analytics service from Flask app`
- `5e5c1ce Extract audit service from Flask app`
- `9f22f66 Extract narration service from Flask app`
