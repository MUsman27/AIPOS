"""Engine, session factory, and database URL."""

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_local_env() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _require_supabase_url(configured: str) -> str:
    parts = urlsplit(configured)
    scheme = parts.scheme.lower()
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+psycopg"
    elif scheme not in {"postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("FastAPI connects only to Supabase Postgres. SQLite and pos.db are not used.")
    host = (parts.hostname or "").lower()
    if not (host.endswith(".supabase.co") or host.endswith(".pooler.supabase.com")):
        raise RuntimeError("DATABASE_URL must be a Supabase Postgres host.")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunsplit(parts._replace(scheme=scheme, query=urlencode(query)))


def database_url() -> str:
    """Supabase Postgres connection string. Never falls back to pos.db."""
    _load_local_env()
    configured = os.environ.get("DATABASE_URL", "").strip()
    if not configured:
        raise RuntimeError(
            "DATABASE_URL is required. FastAPI connects only to Supabase Postgres."
        )
    return _require_supabase_url(configured)


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(database_url())
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Session:
    get_engine()
    assert _session_factory is not None
    return _session_factory()


def init_db() -> None:
    """Apply Alembic migrations so the catalog schema is current."""
    from alembic import command
    from alembic.config import Config

    engine = get_engine()
    root = Path(os.environ.get("AIPOS_BACKEND_ROOT", _PROJECT_ROOT))
    config_path = Path(os.environ.get("AIPOS_ALEMBIC_CONFIG", root / "alembic.ini"))
    migrations_path = Path(os.environ.get("AIPOS_MIGRATIONS_DIR", root / "migrations"))
    cfg = Config(str(config_path))
    cfg.set_main_option("script_location", str(migrations_path))
    cfg.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "products" in tables:
        command.stamp(cfg, "0001_products")
    command.upgrade(cfg, "head")
