"""Import page binaries from JSONL into DB.
Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/import_binaries.py').read())"
"""
import json, base64
from django.db import connection

cursor = connection.cursor()
count = 0
errors = 0

with open("/tmp/page_binaries.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            plane_id = d["id"]
            b64 = d["b"]
            binary_data = base64.b64decode(b64)
            cursor.execute(
                "UPDATE pages SET description_binary = %s WHERE id = %s",
                [binary_data, plane_id]
            )
            count += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"Error: {e}")

print(f"Updated {count} pages with binary, {errors} errors")

# Verify
cursor.execute("SELECT count(*) FROM pages WHERE deleted_at IS NULL AND description_binary IS NOT NULL")
print(f"Pages with binary: {cursor.fetchone()[0]}")
