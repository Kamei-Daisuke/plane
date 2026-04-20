#!/usr/bin/env python3
"""Extract description_html for specific page UUIDs from a pg_dump COPY-format backup.

Usage:
    zcat backup.sql.gz | python3 extract_backup_html.py UUID1 UUID2 UUID3

Writes /tmp/restore_<uuid>.html for each target.
"""
import sys


def unescape_pg_copy(s: str) -> str:
    # pg_dump COPY escapes: \b, \f, \n, \r, \t, \v, \\, \NNN (octal), \xHH (hex).
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= len(s):
            out.append(c)
            break
        nxt = s[i + 1]
        mapping = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}
        if nxt in mapping:
            out.append(mapping[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main():
    targets = set(sys.argv[1:])
    if not targets:
        print("Usage: zcat backup.sql.gz | extract_backup_html.py UUID1 UUID2 ...", file=sys.stderr)
        sys.exit(2)

    in_copy = False
    found = {}
    for line in sys.stdin:
        if line.startswith("COPY public.pages "):
            in_copy = True
            continue
        if in_copy and (line.startswith("\\.") or line.rstrip() == "\\."):
            break
        if not in_copy:
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 6:
            continue
        page_id = cols[2]
        if page_id in targets and page_id not in found:
            found[page_id] = unescape_pg_copy(cols[5])

    for pid, html in found.items():
        out_path = f"/tmp/restore_{pid}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"{pid}: len={len(html)} -> {out_path}")

    missing = targets - set(found.keys())
    if missing:
        print(f"Missing from backup: {missing}", file=sys.stderr)


if __name__ == "__main__":
    main()
