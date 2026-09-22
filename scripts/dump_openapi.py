"""Dump the app's OpenAPI schema to a JSON file for refactor diffing."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app

out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
print(f"written: {out}")
