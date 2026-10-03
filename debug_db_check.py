from sqlalchemy import text

from app.infrastructure.database.session import get_engine


engine = get_engine()
with engine.connect() as conn:
    print("database", conn.execute(text("SELECT current_database()")).scalar())
    print(
        "tables",
        conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        ).fetchall(),
    )
