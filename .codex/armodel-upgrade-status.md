# ARModel Upgrade Status

Current branch: `codex/armodel-hardening`
Current HEAD: `6873c2951f297197b8f918baaad26ba7fb9d078a`
origin/main: `44e3ca3aea333304dd7368dcb8562f3c5a445003`
Working tree: `.codex/` coordination files are uncommitted
Current phase: 7 — Serverless-safe Admin login rate limiting
Last completed phase: 6 — CSRF protection
Last commit: `6873c29 Protect admin mutations against CSRF`
Last full pytest: `84 passed, 79 subtests passed`
Last validator: passed
Last JS checks: passed for carousel, narration, dashboard
Browser QA: not yet run
Push status: not pushed
CI status: workflow added locally; remote run not started
Deployment status: not started
Production QA: not started
External blockers: none known
Next exact action: implement `login_rate_limit_identity`, local/R2 immutable failed-attempt listing, and pre-login threshold enforcement in `app.py`; then add deterministic login tests.

Completed commits:
- `6b1df15 Prevent hidden content exposure in public APIs`
- `070eca3 Harden production sessions and security headers`
- `7cc7a5b Normalize site settings serialization`
- `c0133fb Keep data validator compatible with managed assets`
- `2f830c8 Run regression checks in GitHub Actions`
- `6873c29 Protect admin mutations against CSRF`
