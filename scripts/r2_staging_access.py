"""Check (and optionally extend) R2 access for the separate staging site, using the locally stored
Cloudflare token. Never prints secret values.

  python scripts/r2_staging_access.py            # read-only: buckets and current CORS
  python scripts/r2_staging_access.py --add-cors # add the staging origin to the bucket CORS rules
"""
import json
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_cloud_d1 import stored_token

STAGING_ORIGIN = "https://phuphan-ar-review.vercel.app"


def call(account, token, path, method="GET", payload=None):
    request = Request(f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/{path}", method=method,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = json.loads(error.read() or b"{}")
        return {"success": False, "status": error.code, "errors": body.get("errors")}


def main():
    account = tomllib.loads((Path.home() / ".armodel-secrets/d1-target.toml").read_text(encoding="utf-8"))["account_id"]
    token = stored_token()
    buckets = call(account, token, "buckets")
    if not buckets.get("success"):
        print("bucket list not allowed:", buckets.get("status"), buckets.get("errors"))
        return 1
    names = [b["name"] for b in buckets["result"]["buckets"]]
    print("buckets:", names)
    for name in names:
        cors = call(account, token, f"buckets/{name}/cors")
        print(name, "cors:", cors.get("result") if cors.get("success") else (cors.get("status"), cors.get("errors")))
        domain = call(account, token, f"buckets/{name}/domains/managed")
        print(name, "public dev domain:", (domain.get("result") or {}).get("domain"))
    if "--add-cors" in sys.argv:
        bucket = sys.argv[sys.argv.index("--add-cors") + 1]
        rules = call(account, token, f"buckets/{bucket}/cors")["result"]["rules"]
        for rule in rules:
            origins = rule.setdefault("allowed", {}).setdefault("origins", [])
            if STAGING_ORIGIN not in origins:
                origins.append(STAGING_ORIGIN)
        result = call(account, token, f"buckets/{bucket}/cors", "PUT", {"rules": rules})
        print("cors update:", result.get("success"), result.get("errors"))
        print("now:", call(account, token, f"buckets/{bucket}/cors").get("result"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
