#!/usr/bin/env python3
"""Diff current DB html (old) vs reconverted html (new) for the spreadsheet
pages, ignoring the intended excel table/link additions, to catch regressions.

Usage: python diff_spreadsheet_pages.py <old.jsonl> <new.jsonl>
Each file has one {"id":..,"html":..} per line.
"""
import difflib
import json
import re
import sys

old_path = sys.argv[1] if len(sys.argv) > 1 else "jira_migrate_scripts/data/old23.jsonl"
new_path = sys.argv[2] if len(sys.argv) > 2 else "jira_migrate_scripts/data/out23.jsonl"


def load(p):
    d = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            o = json.loads(line)
            d[o["id"]] = o["html"]
    return d


def strip_excel(h):
    """Remove the intended excel additions: <table>..</table> and the 📊 link."""
    h = re.sub(r"<table>.*?</table>", "", h, flags=re.DOTALL)
    h = re.sub(r'<p class="[^"]*">\s*📊\s*<a[^>]*>.*?</a></p>', "", h, flags=re.DOTALL)
    return h


def norm(s):
    # Old html had an empty <p> where the excel macro produced nothing.
    s = re.sub(r'<p class="editor-paragraph-block">\s*</p>', "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tokens(h):
    return re.findall(r"<[^>]+>|[^<]+", h)


def safe(s):
    return s.encode("ascii", "backslashreplace").decode()


old = load(old_path)
new = load(new_path)

clean = 0
for pid in new:
    # Strip table/📊-link from BOTH sides: old may already contain native HTML
    # tables (and abfedb45 already has the excel table from the 1-page test),
    # so we compare only the non-table prose/links to catch real regressions.
    o = norm(strip_excel(old.get(pid, "")))
    n = norm(strip_excel(new[pid]))
    if o == n:
        clean += 1
        continue
    add, rem = [], []
    for d in difflib.unified_diff(tokens(o), tokens(n), lineterm="", n=0):
        if d.startswith("+") and not d.startswith("+++"):
            add.append(d[1:])
        elif d.startswith("-") and not d.startswith("---"):
            rem.append(d[1:])
    print(f"=== {pid}  +{len(add)} -{len(rem)} ===")
    for a in add[:10]:
        if a.strip():
            print("  +", safe(a[:140]))
    for r in rem[:10]:
        if r.strip():
            print("  -", safe(r[:140]))

print(f"\nCLEAN {clean}/{len(new)} pages (no non-excel diff)")
