from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

DATABASE_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_DIR / 'annotation_tool.db'}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _ensure_password_column(sync_conn):
    inspector = inspect(sync_conn)
    if "users" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "password_hash" not in columns:
            sync_conn.execute(
                text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''")
            )


def _ensure_unclear_case_column(sync_conn):
    inspector = inspect(sync_conn)
    if "annotations" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("annotations")]
        if "unclear_case" not in columns:
            sync_conn.execute(
                text("ALTER TABLE annotations ADD COLUMN unclear_case BOOLEAN NOT NULL DEFAULT 0")
            )


def _ensure_new_comment_columns(sync_conn):
    inspector = inspect(sync_conn)
    if "annotations" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("annotations")]
        if "social_identity_comments" not in columns:
            sync_conn.execute(
                text("ALTER TABLE annotations ADD COLUMN social_identity_comments TEXT NOT NULL DEFAULT ''")
            )
        if "view_point_comments" not in columns:
            sync_conn.execute(
                text("ALTER TABLE annotations ADD COLUMN view_point_comments TEXT NOT NULL DEFAULT ''")
            )
        if "narrative_roles_comments" not in columns:
            sync_conn.execute(
                text("ALTER TABLE annotations ADD COLUMN narrative_roles_comments TEXT NOT NULL DEFAULT ''")
            )


def _remove_unique_constraint(sync_conn):
    """Remove the old unique constraint from annotations table if it exists."""
    inspector = inspect(sync_conn)
    if "annotations" in inspector.get_table_names():
        try:
            constraints = inspector.get_unique_constraints("annotations")
            if any('uq_image_annotator' in str(c) for c in constraints):
                sync_conn.execute(text("DROP TABLE IF EXISTS annotations_backup;"))
                sync_conn.execute(text("""
                    CREATE TABLE annotations_backup AS SELECT * FROM annotations;
                """))
                sync_conn.execute(text("DROP TABLE annotations;"))
                Base.metadata.create_all(bind=sync_conn, tables=[Base.metadata.tables["annotations"]])
                sync_conn.execute(text("INSERT INTO annotations SELECT * FROM annotations_backup;"))
                sync_conn.execute(text("DROP TABLE annotations_backup;"))
        except Exception:
            pass


async def init_db():
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_password_column)
        await conn.run_sync(_ensure_unclear_case_column)
        await conn.run_sync(_ensure_new_comment_columns)
        await conn.run_sync(_remove_unique_constraint)


async def get_db():
    async with async_session() as session:
        yield session
