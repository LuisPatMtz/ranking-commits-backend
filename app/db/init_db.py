from sqlalchemy import inspect, text

from app.db.session import Base, engine
from app.models import commit, evaluation, group, group_share_token, group_user, participant, ranking, repository, user


def sync_group_columns() -> None:
    inspector = inspect(engine)
    if "grupos" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("grupos")}

    with engine.begin() as connection:
        columns_to_drop = [column for column in ("turno", "periodo") if column in existing_columns]
        for column_name in columns_to_drop:
            connection.execute(text(f"ALTER TABLE grupos DROP COLUMN IF EXISTS {column_name}"))

        if "created_by_user_id" not in existing_columns:
            connection.execute(text("ALTER TABLE grupos ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_grupos_created_by_user_id ON grupos (created_by_user_id)"))


def sync_group_share_token_columns() -> None:
    inspector = inspect(engine)
    if "group_share_tokens" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("group_share_tokens")}

    with engine.begin() as connection:
        if "invited_docente_id" not in existing_columns:
            connection.execute(text("ALTER TABLE group_share_tokens ADD COLUMN IF NOT EXISTS invited_docente_id INTEGER"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_group_share_tokens_invited_docente_id "
                    "ON group_share_tokens (invited_docente_id)"
                )
            )


def init_db() -> None:
    sync_group_columns()
    sync_group_share_token_columns()
    Base.metadata.create_all(bind=engine)
