"""Exporta el esquema OpenAPI a stdout.

Usado por `make openapi` para regenerar los tipos TypeScript del frontend.
"""

from __future__ import annotations

import json
import sys

from softree_audit.main import create_app


def main() -> None:
    app = create_app()
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
