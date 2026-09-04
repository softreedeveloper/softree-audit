# Softree Audit — API

Backend de Softree Audit: FastAPI, SQLAlchemy asíncrono, Alembic y worker arq.

Documentación en `../../docs/`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn softree_audit.main:app --reload
```
