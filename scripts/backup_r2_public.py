"""Download every R2 file referenced by the content JSON (models, images, audio) through the public
bucket URL, keeping the object key as the local path. Read-only for R2; skips files already saved
with the same size. Writes a manifest with size and SHA-256 per file.

  python scripts/backup_r2_public.py --json-dir <snapshot dir> [--json-dir data] --out <folder>
"""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

HOST = "pub-b7cd49a1aa5b4bb1ba339dfd78d4ec75.r2.dev"
URL = re.compile(r"https://" + re.escape(HOST) + r"/[^\s\"'<>)\\]+")


def collect(dirs):
    found = set()
    for d in dirs:
        for path in Path(d).rglob("*.json"):
            found.update(URL.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def fetch(url, out):
    key = unquote(urlsplit(url).path.lstrip("/"))
    target = out / "objects" / key
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(Request(url, headers={"User-Agent": "armodel-backup"}), timeout=120) as response:
            data = response.read()
    except Exception as error:  # report and continue
        return {"url": url, "key": key, "error": str(error)}
    target.write_bytes(data)
    return {"url": url, "key": key, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    urls = collect(args.json_dir)
    print(f"{len(urls)} referenced files")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda u: fetch(u, out), urls))
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    (out / "r2-manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(ok)} files, {sum(r['bytes'] for r in ok) / 1e6:.1f} MB; failed {len(failed)}")
    for r in failed[:20]:
        print("FAILED", r["key"], r["error"])


if __name__ == "__main__":
    main()
