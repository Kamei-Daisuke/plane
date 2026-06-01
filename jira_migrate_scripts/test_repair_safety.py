#!/usr/bin/env python3
"""Apply the orphan-table repair to every page's current html and report which
pages it changes. A correct repair only touches pages with an unbalanced
</table> (orphan fragment); balanced tables must be left byte-identical.

Usage: python test_repair_safety.py <pages.jsonl>
"""
import json
import re
import sys


def repair(h):
    if h.count("</table>") <= len(re.findall(r"<table\b", h)):
        return h
    tag_re = re.compile(r"<table\b[^>]*>|</table>")
    out = []
    last = 0
    depth = 0
    for m in tag_re.finditer(h):
        if m.group(0) == "</table>":
            if depth > 0:
                depth -= 1
                continue
            seg = h[last : m.end()]
            cm = re.search(r"</?(?:td|th|tr|tbody|thead)\b", seg)
            if cm is None:
                out.append(seg)
            else:
                before = seg[: cm.start()]
                cells = seg[cm.start() : -len("</table>")]
                opener = "<table><tbody><tr>"
                if re.match(r"</(?:td|th)\b", cells):
                    opener += "<td>"
                out.append(before + opener + cells + "</table>")
            last = m.end()
        else:
            depth += 1
    out.append(h[last:])
    return "".join(out)


path = sys.argv[1] if len(sys.argv) > 1 else "jira_migrate_scripts/data/tablepages.jsonl"
changed = []
unbalanced = 0
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except Exception:
        continue
    h = o["html"]
    if h.count("</table>") > len(re.findall(r"<table\b", h)):
        unbalanced += 1
    r = repair(h)
    if r != h:
        changed.append(o["id"])
print(f"unbalanced(orphan) pages: {unbalanced}")
print(f"pages changed by repair: {len(changed)}")
for i in changed[:20]:
    print("  ", i)
