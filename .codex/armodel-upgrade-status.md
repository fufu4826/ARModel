# ARModel Upgrade Status

Current branch: `codex/armodel-hardening`
origin/main: `44e3ca3aea333304dd7368dcb8562f3c5a445003`
Current HEAD: `17cc479`
Working tree: intentional Phase 14C analytics extraction in progress in `app.py`, `armodel/services/analytics.py`, `tests/test_analytics_service.py`, and checkpoint files
Current phase: 14C — Extract analytics/audit/narration services
Last completed phase: 14B — Extract content repositories
Last commit: `17cc479 Extract content repositories from Flask app`
Last full pytest: `96 passed, 79 subtests passed`; Phase 14C analytics focused `19 passed, 6 subtests passed`
Last validator: passed; 121 R2 URLs verified
Last JS checks: passed for carousel, narration, dashboard
Browser QA: not yet run
Push status: not pushed
CI status: workflow added locally; remote run not started
Deployment status: not started
Production QA: not started
External blockers: none known
Next exact action: make `_analytics_trend_ranges` and `dashboard_analytics_status` delegate fully to `armodel.services.analytics`, remove their duplicate legacy aggregation bodies, then run analytics/dashboard tests and full regression before committing the analytics extraction. After that inventory audit signing/redaction/listing boundaries.

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
