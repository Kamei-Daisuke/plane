"""Post-reimport health check: compare page_final.jsonl against DB.
Run inside API container:
  python manage.py shell -c "exec(open('/tmp/health_check_pages.py').read())"
"""
import json, re
from django.db import connection

cursor = connection.cursor()

# Load expected data
expected = {}
with open("/tmp/page_updates_tiptap_fixed.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            expected[d["id"]] = d["html"]
        except:
            pass

print(f"Expected pages: {len(expected)}")

# Check DB
issues = []
cursor.execute("SELECT id, description_html FROM pages WHERE deleted_at IS NULL")
db_pages = {}
for row in cursor.fetchall():
    db_pages[str(row[0])] = row[1] or ""

print(f"DB pages: {len(db_pages)}")

# Compare
html_mismatch = 0
heading_dupes = 0
link_loss = 0

for page_id, expected_html in expected.items():
    db_html = db_pages.get(page_id, "")

    # 1. HTML mismatch
    if db_html != expected_html:
        html_mismatch += 1

    # 2. Heading duplication
    exp_headings = re.findall(r'<h[1-6][^>]*>([^<]+)</h', expected_html)
    db_headings = re.findall(r'<h[1-6][^>]*>([^<]+)</h', db_html)
    if len(db_headings) > len(exp_headings) * 1.5 and len(exp_headings) > 0:
        heading_dupes += 1
        if heading_dupes <= 5:
            print(f"  DUPE: {page_id} expected={len(exp_headings)} db={len(db_headings)}")

    # 3. Link loss
    exp_links = len(re.findall(r'href="https://plane\.example\.com/keis/', expected_html))
    db_links = len(re.findall(r'href="https://plane\.example\.com/keis/', db_html))
    if exp_links > 0 and db_links < exp_links:
        link_loss += 1
        if link_loss <= 5:
            print(f"  LINK LOSS: {page_id} expected={exp_links} db={db_links}")

    # 4. Unresolved page refs
    unresolved = len(re.findall(r'\[Page: [^\]]+\]', db_html))
    if unresolved > 0:
        exp_unresolved = len(re.findall(r'\[Page: [^\]]+\]', expected_html))
        if unresolved > exp_unresolved:
            issues.append(f"NEW UNRESOLVED: {page_id} expected={exp_unresolved} db={unresolved}")

print(f"\nResults:")
print(f"  HTML mismatches: {html_mismatch}")
print(f"  Heading duplications: {heading_dupes}")
print(f"  Pages with link loss: {link_loss}")
print(f"  New unresolved refs: {len(issues)}")
for i in issues[:10]:
    print(f"  {i}")

if html_mismatch == 0 and heading_dupes == 0 and link_loss == 0:
    print("\nALL OK")
else:
    print(f"\nFAILED - {html_mismatch + heading_dupes + link_loss} issues found")
