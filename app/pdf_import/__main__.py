"""Import every PDF in pos/Itemlisting into the catalog."""

from pathlib import Path

from app.infrastructure.database.session import get_session, init_db
from app.pdf_import.load import import_folder


def main() -> None:
    init_db()
    folder = Path(__file__).resolve().parents[2] / "Itemlisting"
    session = get_session()
    try:
        import_folder(session, folder)
    finally:
        session.close()


if __name__ == "__main__":
    main()
