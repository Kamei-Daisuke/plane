#!/usr/bin/env python3
"""Compare pre-v7 page HTML (backup) vs new v7 dry-run output (--dump).

Counts key structural features in each version and reports per-page drops
(feature X existed before, now fewer/none). Exits non-zero if any page
has a drop so callers can block --apply on regressions.

Usage:
  python diff_reconvert.py --backup-sql <pages.sql[.gz]> --dump <v7.jsonl>

The --backup-sql file must be a `pg_dump -t pages` output (plain or .gz).
We extract description_html per page via COPY body parsing.
"""
import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from typing import Dict

FEATURES = [
    ("image-component", re.compile(r"<image-component\b")),
    ("colwidth", re.compile(r'\bcolwidth="')),
    ("data-text-color", re.compile(r'\bdata-text-color="')),
    ("data-background-color", re.compile(r'\bdata-background-color="')),
    ("data-code-content", re.compile(r'\bdata-code-content="')),
    ("horizontalRule", re.compile(r'data-type="horizontalRule"')),
    ("callout-component", re.compile(r'data-block-type="callout-component"')),
    ("table", re.compile(r"<table\b")),
    ("href", re.compile(r'<a\s[^>]*href="')),
    ("taskList", re.compile(r'data-type="taskList"')),
]


def count_features(html: str) -> Dict[str, int]:
    return {name: len(rx.findall(html)) for name, rx in FEATURES}


def load_backup(path: str) -> Dict[str, str]:
    """Parse `pg_dump -t pages` output; extract id → description_html."""
    opener = gzip.open if path.endswith(".gz") else open
    pages: Dict[str, str] = {}
    in_copy = False
    col_idx = {}
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(r"\."):
                in_copy = False
                continue
            if line.startswith("COPY public.pages ") and " FROM stdin" in line:
                # Extract column order
                m = re.search(r"COPY public\.pages \((.*?)\) FROM stdin", line)
                if m:
                    cols = [c.strip() for c in m.group(1).split(",")]
                    col_idx = {c: i for i, c in enumerate(cols)}
                    in_copy = True
                continue
            if not in_copy:
                continue
            parts = line.rstrip("\n").split("\t")
            if "id" not in col_idx or "description_html" not in col_idx:
                continue
            try:
                pid = parts[col_idx["id"]]
                html = parts[col_idx["description_html"]]
            except IndexError:
                continue
            if html == r"\N":
                html = ""
            # Postgres COPY escapes: \n, \t, \r, \\
            html = (
                html.replace(r"\\", "\x00")
                .replace(r"\n", "\n")
                .replace(r"\t", "\t")
                .replace(r"\r", "\r")
                .replace("\x00", "\\")
            )
            pages[pid] = html
    return pages


def load_dump(path: str) -> Dict[str, str]:
    pages: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            pages[d["id"]] = d["html"]
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup-sql", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--show", type=int, default=10, help="Sample pages per feature")
    args = ap.parse_args()

    print(f"Loading backup from {args.backup_sql}...", file=sys.stderr)
    pre = load_backup(args.backup_sql)
    print(f"  {len(pre)} pages", file=sys.stderr)

    print(f"Loading dump from {args.dump}...", file=sys.stderr)
    post = load_dump(args.dump)
    print(f"  {len(post)} pages", file=sys.stderr)

    # Aggregate deltas
    totals_pre = defaultdict(int)
    totals_post = defaultdict(int)
    drop_counts = defaultdict(int)  # pages that dropped in this feature
    drop_samples = defaultdict(list)  # sample page ids with drops
    gain_counts = defaultdict(int)

    for pid, new_html in post.items():
        old_html = pre.get(pid, "")
        old_cnt = count_features(old_html)
        new_cnt = count_features(new_html)
        for feat in old_cnt:
            totals_pre[feat] += old_cnt[feat]
            totals_post[feat] += new_cnt[feat]
            if new_cnt[feat] < old_cnt[feat]:
                drop_counts[feat] += 1
                if len(drop_samples[feat]) < args.show:
                    drop_samples[feat].append(
                        f"{pid}: {old_cnt[feat]} → {new_cnt[feat]}"
                    )
            elif new_cnt[feat] > old_cnt[feat]:
                gain_counts[feat] += 1

    print()
    print(f"{'feature':<24} {'pre':>10} {'post':>10} {'Δ':>10} {'drop_pages':>12} {'gain_pages':>12}")
    print("-" * 82)
    worst = 0
    for feat, _ in FEATURES:
        pre_sum = totals_pre[feat]
        post_sum = totals_post[feat]
        delta = post_sum - pre_sum
        print(
            f"{feat:<24} {pre_sum:>10} {post_sum:>10} {delta:>+10} {drop_counts[feat]:>12} {gain_counts[feat]:>12}"
        )
        if drop_counts[feat]:
            worst = max(worst, drop_counts[feat])

    print()
    if worst == 0:
        print("✓ No regressions (no page has fewer of any feature).", file=sys.stderr)
        sys.exit(0)

    print("!! Pages with feature drops (sample):", file=sys.stderr)
    for feat, samples in drop_samples.items():
        if samples:
            print(f"\n  {feat}:", file=sys.stderr)
            for s in samples:
                print(f"    {s}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
