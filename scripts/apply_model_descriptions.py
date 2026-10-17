"""Update only the `description` field of selected models from an approved plan file.

Plan format (docs/model_descriptions_20261017.json):
  "replace": {model name: new text}   -> description = new text (+ the old image-credit line, if any)
  "append":  {model name: sentence}   -> description = old text + newline + sentence (idempotent)

Default is a dry run. --apply writes one guarded D1 batch (stale-revision protected), then
re-reads and verifies that every other field of every model is unchanged.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from armodel.repositories.database import Database

CREDIT = re.compile(r"(?:ขอบคุณภาพ|รูปภาพจาก)[^\n]*$", re.S)
EXCLUDED = ("ไก่ดำภูพาน3", "ไก่ดำภูพาน4")  # pending confirmation with the centre


def build(models, plan, keep_credit=True):
    by_name = {}
    for model in models:
        by_name.setdefault(model["name"], []).append(model)
    updated = copy.deepcopy(models)
    index = {id(m): i for i, m in enumerate(models)}
    expected = {}
    for mode in ("replace", "append"):
        for name, text in plan.get(mode, {}).items():
            if name.startswith(EXCLUDED):
                raise SystemExit(f"Refusing excluded model: {name}")
            matches = by_name.get(name, [])
            if len(matches) != 1:
                raise SystemExit(f"Model name must match exactly one model: {name!r} ({len(matches)})")
            original = matches[0]
            old = original.get("description") or ""
            if mode == "replace":
                new = text.strip()
                credit = CREDIT.search(old) if keep_credit else None
                if credit and credit.group(0).strip() not in new:
                    new += "\n" + credit.group(0).strip()
            else:
                new = old if text.strip() in old else old.rstrip() + "\n" + text.strip()
            updated[index[id(original)]]["description"] = new
            expected[original["id"]] = new
    return updated, expected


def verify(before, after, expected):
    problems = []
    if [m["id"] for m in before] != [m["id"] for m in after]:
        problems.append("model order or IDs changed")
    after_by_id = {m["id"]: m for m in after}
    for old in before:
        new = after_by_id.get(old["id"])
        if new is None:
            problems.append(f"missing {old['id']}")
            continue
        for key in set(old) | set(new):
            if key == "description" and old["id"] in expected:
                if new.get(key) != expected[old["id"]]:
                    problems.append(f"{old['name']}: description not as planned")
            elif old.get(key) != new.get(key):
                problems.append(f"{old['name']}: field {key} changed")
    return problems


def main(argv=None, database=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/model_descriptions_20261017.json")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--local-path", type=Path)
    target.add_argument("--cloud", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if database is None:
        if args.cloud:
            from scripts.prepare_cloud_d1 import cloud_database
            database = cloud_database()
        elif args.local_path:
            database = Database(local_path=args.local_path)
        else:
            parser.error("Choose --local-path or --cloud")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    before, revision = database.read("models")
    updated, expected = build(before, plan, plan.get("_keep_credit_lines", True))
    changed = [m for m, n in zip(before, updated) if m.get("description") != n.get("description")]
    print(f"models: {len(before)}, planned: {len(expected)}, actually changing: {len(changed)}, revision: {revision}")
    for model, new in zip(before, updated):
        if model.get("description") != new.get("description"):
            print(f"  {model['name']}: {len(model.get('description') or '')} -> {len(new['description'])} chars")
    if not args.apply:
        print("Dry run only; nothing written.")
        return expected
    if changed:
        database.save("models", updated, revision)
    after, new_revision = database.read("models")
    problems = verify(before, after, expected)
    if problems:
        raise SystemExit("VERIFY FAILED:\n" + "\n".join(problems[:30]))
    print(f"PASS: only planned descriptions changed; every other field of all {len(after)} models unchanged "
          f"(revision {revision} -> {new_revision})")
    return expected


if __name__ == "__main__":
    main()
