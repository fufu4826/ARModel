# ARModel Upgrade Status

Current branch: `codex/armodel-hardening`
origin/main: `44e3ca3aea333304dd7368dcb8562f3c5a445003`
Current HEAD: `67127cd`
Working tree: intentional Phase 14B in progress in `app.py`, `armodel/repositories/`, and checkpoint files
Current phase: 14B — Extract content repositories
Last completed phase: 14A — Extract R2/GitHub storage services
Last commit: `67127cd Extract storage integrations from Flask app`
Last full pytest: `91 passed, 79 subtests passed` (Phase 14A); Phase 14B focused `75 passed, 73 subtests passed`
Last validator: passed; 121 R2 URLs verified
Last JS checks: passed for carousel, narration, dashboard
Browser QA: not yet run
Push status: not pushed
CI status: workflow added locally; remote run not started
Deployment status: not started
Production QA: not started
External blockers: none known
Next exact action: remove the now-unreachable legacy body below `normalize_model`, make all model/project/slider/settings load-save wrappers delegate to `armodel.repositories.content`, add repository-focused tests, then run the full Phase 14B regression gate before committing `Extract content repositories from Flask app`.

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
