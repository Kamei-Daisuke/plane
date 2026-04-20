"""Post-reimport health check: compare page_updates_tiptap_fixed.jsonl against DB.

Focus on detecting actual content bloat (duplicated text), not markup-only
differences. The editor re-serializes HTML with extra attributes (data-id,
class names, nested styling wrappers) on every Y.js round-trip, so raw
byte-length comparisons produce false positives.

Checks:
  1. TEXT bloat — text-only ratio > 1.05x after stripping all tags
     (this is the signal for real duplication from Y.js merge-based bloat).
  2. TEXT loss — text-only ratio < 0.95x (may be intentional deletion or
     conversion loss; surface for review).
  3. Heading count increase — a secondary signal for structural duplication.
  4. Page link loss — internal Plane links dropped.

HTML-length mismatches that are purely markup (text ratio ~1.0) are treated
as OK and counted separately as informational.

Run inside API container:
  sudo docker exec -i <api-container> python manage.py shell < /tmp/health_check_pages.py
"""
import json
import re

from django.db import connection

TEXT_BLOAT_THRESHOLD = 1.05
TEXT_LOSS_THRESHOLD = 0.95


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "")


def count_headings(html: str) -> int:
    return len(re.findall(r"<h[1-6]", html or ""))


def count_plane_links(html: str) -> int:
    return len(re.findall(r'href="https://plane\.example\.com/keis/', html or ""))


cursor = connection.cursor()

# Load expected data
expected_html = {}
with open("/tmp/page_updates_tiptap_fixed.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            expected_html[d["id"]] = d["html"]
        except Exception:
            pass

print(f"Expected pages: {len(expected_html)}")

# Fetch DB
cursor.execute("SELECT id, name, description_html FROM pages WHERE deleted_at IS NULL")
db_rows = {}
db_names = {}
for row in cursor.fetchall():
    pid = str(row[0])
    db_rows[pid] = row[2] or ""
    db_names[pid] = row[1] or ""

print(f"DB pages: {len(db_rows)}")

# Compare
text_bloat = []
text_loss = []
heading_increase = []
link_loss = []
markup_only_diff = 0
exact_match = 0

for pid, exp_html in expected_html.items():
    db_html = db_rows.get(pid, "")

    exp_text = strip_tags(exp_html)
    db_text = strip_tags(db_html)

    if not exp_text:
        continue

    text_ratio = len(db_text) / len(exp_text)

    exp_h = count_headings(exp_html)
    db_h = count_headings(db_html)

    exp_links = count_plane_links(exp_html)
    db_links = count_plane_links(db_html)

    if db_html == exp_html:
        exact_match += 1
        continue

    # Real bloat: text content grew
    if text_ratio >= TEXT_BLOAT_THRESHOLD:
        text_bloat.append((pid, db_names.get(pid, "")[:45], text_ratio, len(db_text), len(exp_text)))

    # Real loss: text content shrank
    if text_ratio <= TEXT_LOSS_THRESHOLD:
        text_loss.append((pid, db_names.get(pid, "")[:45], text_ratio, len(db_text), len(exp_text)))

    # Heading bloat (secondary signal)
    if db_h > exp_h:
        heading_increase.append((pid, db_names.get(pid, "")[:45], exp_h, db_h))

    # Link loss
    if exp_links > 0 and db_links < exp_links:
        link_loss.append((pid, db_names.get(pid, "")[:45], exp_links, db_links))

    if text_ratio > TEXT_LOSS_THRESHOLD and text_ratio < TEXT_BLOAT_THRESHOLD and db_h == exp_h:
        markup_only_diff += 1

print("\nResults:")
print(f"  Exact byte match: {exact_match}")
print(f"  Markup-only diff (text matches, OK): {markup_only_diff}")
print(f"  TEXT BLOAT (ratio >= {TEXT_BLOAT_THRESHOLD}x): {len(text_bloat)}")
for b in text_bloat[:10]:
    print(f"    {b[0]} {b[1]:<45} x{b[2]:.2f} db_text={b[3]} exp_text={b[4]}")
print(f"  TEXT LOSS (ratio <= {TEXT_LOSS_THRESHOLD}x): {len(text_loss)}")
for b in text_loss[:10]:
    print(f"    {b[0]} {b[1]:<45} x{b[2]:.2f} db_text={b[3]} exp_text={b[4]}")
print(f"  Heading increases: {len(heading_increase)}")
for b in heading_increase[:10]:
    print(f"    {b[0]} {b[1]:<45} expected={b[2]} db={b[3]}")
print(f"  Pages with link loss: {len(link_loss)}")
for b in link_loss[:10]:
    print(f"    {b[0]} {b[1]:<45} expected={b[2]} db={b[3]}")

if not text_bloat and not text_loss and not heading_increase and not link_loss:
    print("\nALL OK")
else:
    total = len(text_bloat) + len(text_loss) + len(heading_increase) + len(link_loss)
    print(f"\nFAILED - {total} issues found")
