"""Remove stale drawing upload parts and file rows that have no bytes on disk.

    python scripts/sweep_drawing_uploads.py
"""

import json

from app.drawings import reconcile_drawing_files


def main() -> None:
    print(json.dumps(reconcile_drawing_files(), ensure_ascii=False))


if __name__ == "__main__":
    main()
