"""Export verified BhumiAI correction feedback for controlled offline HTR work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402,F401
from services.training_feedback import export_verified_feedback_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local dataset from VERIFIED_SAMPLE feedback only.")
    parser.add_argument("--output-root", default=str(BACKEND_ROOT / "training_exports"))
    args = parser.parse_args()
    # The diagnostic can be run independently of a web-server startup; this is
    # additive only and never changes any existing recognition or record data.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = export_verified_feedback_dataset(db, args.output_root)
        db.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
