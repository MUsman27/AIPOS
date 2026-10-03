"""Engine, session factory, and database URL."""

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def database_url() -> str:
    """SQLite file by default. Set DATABASE_URL to use PostgreSQL."""
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    data_dir = os.environ.get("AIPOS_DATA_DIR", "").strip()
    if data_dir:
        data_path = Path(data_dir).expanduser()
        data_path.mkdir(parents=True, exist_ok=True)
        db_path = data_path / "pos.db"
    else:
        db_path = Path(__file__).resolve().parents[3] / "pos.db"
    return "sqlite:///" + db_path.as_posix()


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args)
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
    root = Path(os.environ.get("AIPOS_BACKEND_ROOT", Path(__file__).resolve().parents[3]))
    config_path = Path(os.environ.get("AIPOS_ALEMBIC_CONFIG", root / "alembic.ini"))
    migrations_path = Path(os.environ.get("AIPOS_MIGRATIONS_DIR", root / "migrations"))
    cfg = Config(str(config_path))
    cfg.set_main_option("script_location", str(migrations_path))
    cfg.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "products" in tables:
        command.stamp(cfg, "0001_products")
    command.upgrade(cfg, "head")
