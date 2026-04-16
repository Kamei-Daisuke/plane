"""Update page HTML from fixed JSONL. Run in API container."""
import json
from django.db import connection

cursor = connection.cursor()
count = 0
errors = 0

with open("/tmp/page_updates_tiptap_fixed.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            cursor.execute(
                "UPDATE pages SET description_html = %s, description_binary = NULL, description_json = %s WHERE id = %s",
                [d["html"], "{}", d["id"]]
            )
            count += 1
        except json.JSONDecodeError:
            errors += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"Error: {e}")

print(f"Updated {count} pages, {errors} errors")
