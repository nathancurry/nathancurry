#!/usr/bin/env python3
"""Check that every page about me agrees with about.toml.

    python3 check_about.py                     # fetch and check every public page
    python3 check_about.py --page site=index.md  # check that page from a local file
    python3 check_about.py --about URL_OR_PATH --only resume --page resume=base/resume.md

Public pages are fetched from raw.githubusercontent.com. --page NAME=PATH
checks a local copy instead, so a pull request is checked before it merges.
Standard library only (Python 3.11+ for tomllib).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"


def load_about(source: str) -> dict:
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=20) as resp:
            return tomllib.loads(resp.read().decode("utf-8"))
    return tomllib.loads(Path(source).read_text(encoding="utf-8"))


def fetch(page: dict) -> str:
    url = RAW.format(repo=page["repo"], ref=page.get("ref", "main"), path=page["path"])
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8")


def normalize(text: str) -> str:
    """Reduce Markdown or HTML to plain lowercase text with single spaces."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", text)  # *em* / _em_
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))
    text = re.sub(r"\s+", " ", text)
    # Re-join a phrase split by a tag, e.g. "by <a>Nathan</a> ," -> "by Nathan,".
    text = re.sub(r" ([,.;:)])", r"\1", text)
    return text.strip().lower()


def check(name: str, page: dict, text: str, bio: dict) -> list[str]:
    body = normalize(text)
    problems: list[str] = []

    for key in page.get("require", []):
        values = bio[key] if isinstance(bio[key], list) else [bio[key]]
        for value in values:
            if normalize(value) not in body:
                problems.append(f"missing {key}: {value!r}")

    for phrase in bio.get("retired", []):
        if normalize(phrase) in body:
            problems.append(f"retired phrase: {phrase!r}")

    if page.get("check_roles"):
        for role in bio.get("roles", []):
            stamp = f"{role['employer']} | {role['start']}"
            if normalize(stamp) not in body:
                problems.append(f"role date: expected {stamp!r}")

    if not page.get("allow_previous_certs"):
        for cert in bio.get("certs_previous", []):
            if normalize(cert) in body:
                problems.append(f"lapsed cert named: {cert!r}")

    return [f"{name} ({page['repo']}/{page['path']}): {p}" for p in problems]


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--about", default=str(here / "about.toml"), help="about.toml path or https URL")
    parser.add_argument("--page", action="append", default=[], metavar="NAME=PATH", help="check a local file for NAME")
    parser.add_argument("--only", action="append", default=[], metavar="NAME", help="check only these pages")
    args = parser.parse_args()

    bio = load_about(args.about)
    local = dict(item.split("=", 1) for item in args.page)
    pages = bio["pages"]
    names = args.only or [n for n, p in pages.items() if not p.get("private") or n in local]

    problems: list[str] = []
    for name in names:
        page = pages[name]
        try:
            text = Path(local[name]).read_text(encoding="utf-8") if name in local else fetch(page)
        except Exception as exc:  # network or missing file: report, don't crash the rest
            problems.append(f"{name}: could not read ({exc})")
            continue
        found = check(name, page, text, bio)
        problems.extend(found)
        print(f"{'FAIL' if found else 'ok  '}  {name}")

    for p in problems:
        print(f"  {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
