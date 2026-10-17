"""Download the legacy per-event objects that the old site wrote to R2 (analytics/events/, audit/)
into a local folder, read-only, so they can be imported with scripts/import_d1_events.py.

Keys are read from ~/.armodel-secrets/r2-events-readonly.env (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
and never printed. Objects are saved under <out>/<prefix>/... with their original key.

  python scripts/export_r2_events.py --out C:\\Users\\fufu\\ARModel-backups\\r2-events-20261017
"""
import argparse
import json
import sys
from pathlib import Path

ACCOUNT = "7166a0c3703b6e795739064e6ab3be35"
BUCKET = "phuphan-ar-assets"
PREFIXES = {"analytics": "analytics/events/", "audit": "audit/"}


def credentials():
    values = {}
    path = Path.home() / ".armodel-secrets" / "r2-events-readonly.env"
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    if not values.get("R2_ACCESS_KEY_ID") or not values.get("R2_SECRET_ACCESS_KEY"):
        sys.exit("Key file is empty; paste the read-only R2 keys first")
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    import boto3
    from botocore.config import Config

    keys = credentials()
    s3 = boto3.client("s3", endpoint_url=f"https://{ACCOUNT}.r2.cloudflarestorage.com",
                      aws_access_key_id=keys["R2_ACCESS_KEY_ID"], aws_secret_access_key=keys["R2_SECRET_ACCESS_KEY"],
                      region_name="auto", config=Config(signature_version="s3v4"))
    out = Path(args.out)
    summary = {}
    for kind, prefix in PREFIXES.items():
        count = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith(".json"):
                    continue
                target = out / kind / key[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.stat().st_size != item["Size"]:
                    target.write_bytes(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
                count += 1
        summary[kind] = count
        print(f"{kind}: {count} objects under {prefix}")
    (out / "export-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
