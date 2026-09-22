"""Compute the `region_state` hashes for this repo's BASE marker regions.

    python tools/region_hashes.py            # print the manifest fragment
    python tools/region_hashes.py --check    # compare against the manifest

Hashing follows `/base:sync`'s `references/region-rewrite.md` exactly: the
content **between** the marker lines (markers excluded), normalised to LF, and
insensitive to a trailing newline.  Computing it any other way makes every
later `/base:sync` report a phantom hand-edit on a region nobody touched.

**Verification step:** this script's `--check` mode must also reproduce the
hashes already recorded in a *different* Sub (the sibling CardGenerator repo),
whose `region_state` was written by Base itself.  A hashing rule that agrees
only with its own output proves nothing.  Point it at another repo with:

    python tools/region_hashes.py --check --repo <path to that repo>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]

START = re.compile(r"<!--\s*BASE:(?P<id>[A-Za-z0-9_-]+):v(?P<rev>\d+)\s+START\s*-->")
END = re.compile(r"<!--\s*BASE:END\s*-->")

#: Which seeded files can carry regions.  Derived from the tree, not a list of
#: names: any tracked markdown file is scanned.
SCAN = ("*.md", "docs/*.md", ".claude/*.md")


def region_hash(content: str) -> str:
    normalised = content.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return "sha256:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def regions_in(text: str) -> Dict[str, Tuple[int, str]]:
    """``{region_id: (rev, content_between_markers)}`` for one file."""
    out: Dict[str, Tuple[int, str]] = {}
    lines = text.splitlines()
    open_at = None
    for i, line in enumerate(lines):
        match = START.search(line)
        if match:
            open_at = (i, match.group("id"), int(match.group("rev")))
            continue
        if END.search(line) and open_at is not None:
            start_i, region_id, rev = open_at
            out[region_id] = (rev, "\n".join(lines[start_i + 1 : i]))
            open_at = None
    return out


def collect(root: Path) -> Dict[str, dict]:
    state: Dict[str, dict] = {}
    seen = set()
    for pattern in SCAN:
        for path in sorted(root.glob(pattern)):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for region_id, (rev, content) in regions_in(text).items():
                state["{}#{}".format(rel, region_id)] = {
                    "rev": rev,
                    "hash": region_hash(content),
                }
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare against the repo's base-manifest.json")
    parser.add_argument("--repo", default=str(ROOT),
                        help="repo to scan (default: this one)")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    state = collect(root)

    if not args.check:
        print(json.dumps(state, indent=2))
        return 0

    manifest_path = root / ".claude" / "base-manifest.json"
    recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get(
        "region_state", {}
    )
    bad = 0
    for key in sorted(set(state) | set(recorded)):
        computed = state.get(key)
        stored = recorded.get(key)
        if computed is None:
            print("MISSING IN TREE   {} (manifest records it)".format(key))
            bad += 1
        elif stored is None:
            print("MISSING IN MANIFEST {}".format(key))
            bad += 1
        elif computed != stored:
            print("MISMATCH          {}\n  tree     {}\n  manifest {}".format(
                key, computed, stored))
            bad += 1
        else:
            print("ok                {} rev {}".format(key, computed["rev"]))
    print("\n{}: {} region(s), {} problem(s)".format(root.name, len(state), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
