# ARModel Upgrade Status

Current branch: `codex/armodel-hardening`
origin/main: `44e3ca3aea333304dd7368dcb8562f3c5a445003`
Current HEAD: `e27cc54`
Working tree: clean after coordination checkpoint commit
Current phase: 14A — Extract R2/GitHub storage services
Last completed phase: 13 — Dependency management
Last commit: `e27cc54 Clarify runtime and development dependencies`
Last full pytest: `91 passed, 79 subtests passed`
Last validator: passed; 121 R2 URLs verified
Last JS checks: passed for carousel, narration, dashboard
Browser QA: not yet run
Push status: not pushed
CI status: workflow added locally; remote run not started
Deployment status: not started
Production QA: not started
External blockers: none known
Next exact action: map the dependency boundaries of `github_api_request`, GitHub JSON read/write, `r2_signed_request`, and R2 get/list/upload/delete/copy helpers; extract them behind compatibility wrappers so existing monkeypatch-based tests remain valid.

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
