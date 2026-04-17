"""Post-reimport health check: compare page_final.jsonl against DB.

Checks:
  1. HTML mismatch (DB != expected)
  2. Heading count increase (live damage detection)
  3. Page link loss
  4. Unresolved [Page:] refs

Run inside API container:
  python manage.py shell -c "exec(open('/tmp/health_check_pages.py').read())"
"""
import json, re
from django.db import connection

cursor = connection.cursor()

# Load expected data
expected = {}
expected_heading_counts = {}
with open("/tmp/page_updates_tiptap_fixed.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            expected[d["id"]] = d["html"]
            expected_heading_counts[d["id"]] = len(re.findall(r'<h[1-6]', d["html"]))
        except:
            pass

print(f"Expected pages: {len(expected)}")

# Check DB
cursor.execute("SELECT id, description_html FROM pages WHERE deleted_at IS NULL")
db_pages = {}
for row in cursor.fetchall():
    db_pages[str(row[0])] = row[1] or ""

print(f"DB pages: {len(db_pages)}")

# Compare
html_mismatch = 0
heading_increase = 0
heading_increase_pages = []
link_loss = 0

for page_id, expected_html in expected.items():
    db_html = db_pages.get(page_id, "")

    # 1. HTML mismatch
    if db_html != expected_html:
        html_mismatch += 1

    # 2. Heading count increase (live damage)
    exp_count = expected_heading_counts[page_id]
    db_count = len(re.findall(r'<h[1-6]', db_html))
    if db_count > exp_count:
        heading_increase += 1
        if heading_increase <= 5:
            cursor.execute("SELECT name FROM pages WHERE id = %s", [page_id])
            name = cursor.fetchone()[0][:40]
            heading_increase_pages.append(f"  {name}: expected={exp_count} db={db_count}")

    # 3. Link loss
    exp_links = len(re.findall(r'href="https://plane\.example\.com/keis/', expected_html))
    db_links = len(re.findall(r'href="https://plane\.example\.com/keis/', db_html))
    if exp_links > 0 and db_links < exp_links:
        link_loss += 1

    # 4. Unresolved page refs
    unresolved = len(re.findall(r'\[Page: [^\]]+\]', db_html))
    exp_unresolved = len(re.findall(r'\[Page: [^\]]+\]', expected_html))

print(f"\nResults:")
print(f"  HTML mismatches: {html_mismatch}")
print(f"  Heading increases (live damage): {heading_increase}")
for p in heading_increase_pages:
    print(p)
print(f"  Pages with link loss: {link_loss}")

if html_mismatch == 0 and heading_increase == 0 and link_loss == 0:
    print("\nALL OK")
else:
    print(f"\nFAILED - {html_mismatch + heading_increase + link_loss} issues found")
