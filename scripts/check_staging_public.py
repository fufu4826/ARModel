"""Read-only smoke test of the public staging site: every page answers, and every 3D model, image
and audio file it references loads with CORS allowed for the staging origin.

  python scripts/check_staging_public.py [--base https://phuphan-ar-review.vercel.app]
"""
import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

ASSET = re.compile(r"https://pub-[a-z0-9]+\.r2\.dev/[^\s\"'<>)]+")


def get(url, origin=None, head_bytes=None):
    headers = {"User-Agent": "armodel-staging-check"}
    if origin:
        headers["Origin"] = origin
    if head_bytes:
        headers["Range"] = f"bytes=0-{head_bytes}"
    with urlopen(Request(url, headers=headers), timeout=60) as response:
        return response.status, dict(response.headers), response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://phuphan-ar-review.vercel.app")
    base = parser.parse_args().base.rstrip("/")
    failures = []
    pages = ["/", "/home", "/models", "/robots.txt"]
    _, _, models_html = get(base + "/models")
    _, _, home_html = get(base + "/home")
    models = sorted(set(re.findall(r'href="(/models/[^"#?/]+)"', models_html.decode())))
    projects = sorted(set(re.findall(r'href="(/projects/[^"#?]+)"', home_html.decode() + models_html.decode())))
    pages += models + projects
    print(f"pages: {len(pages)} (models {len(models)}, projects {len(projects)})")
    assets = set()

    def check_page(path):
        try:
            status, _, body = get(base + path)
            found = set(ASSET.findall(body.decode("utf-8", "replace")))
            return path, status, found
        except Exception as error:
            return path, str(error), set()

    with ThreadPoolExecutor(8) as pool:
        for path, status, found in pool.map(check_page, pages):
            if status != 200:
                failures.append(f"page {path}: {status}")
            assets |= found
    print(f"r2 assets referenced: {len(assets)}")

    def check_asset(url):
        try:
            status, headers, _ = get(url, origin=base, head_bytes=64)
            allow = headers.get("Access-Control-Allow-Origin") or headers.get("access-control-allow-origin")
            return url, status, allow
        except Exception as error:
            return url, str(error), None

    with ThreadPoolExecutor(8) as pool:
        for url, status, allow in pool.map(check_asset, sorted(assets)):
            if status not in (200, 206):
                failures.append(f"asset {url}: {status}")
            elif allow not in (base, "*"):
                failures.append(f"asset CORS {url}: {allow}")
    print("FAILURES:" if failures else "all pages and assets OK")
    for line in failures:
        print(" ", line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
