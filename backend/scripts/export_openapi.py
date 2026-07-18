"""Export the canonical FastAPI contract for frontend type generation."""

import argparse
import json
import os
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))
os.environ.setdefault("APP_ENV", "development")

from main import app  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
