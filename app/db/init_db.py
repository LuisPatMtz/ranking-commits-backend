from sqlalchemy import inspect, text

from app.db.session import Base, engine
from app.models import commit, docente_invite, evaluation, group, group_share_token, group_student_invite, group_user, participant, peer_vote, project_evaluation, ranking, repository, user


def sync_group_columns() -> None:
    inspector = inspect(engine)
    if "grupos" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("grupos")}

    with engine.begin() as connection:
        for col in ("turno", "periodo"):
            if col in existing_columns:
                connection.execute(text(f"ALTER TABLE grupos DROP COLUMN IF EXISTS {col}"))

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


def sync_participant_columns() -> None:
    inspector = inspect(engine)
    if "participantes" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("participantes")}

    with engine.begin() as connection:
        if "github_contributions_total" not in existing_columns:
            connection.execute(text("ALTER TABLE participantes ADD COLUMN IF NOT EXISTS github_contributions_total INTEGER"))
        if "github_contributions_updated_at" not in existing_columns:
            connection.execute(text("ALTER TABLE participantes ADD COLUMN IF NOT EXISTS github_contributions_updated_at TIMESTAMPTZ"))


def sync_repositorios_columns() -> None:
    inspector = inspect(engine)
    if "repositorios" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("repositorios")}

    with engine.begin() as connection:
        if "proyecto_nombre" in existing_columns:
            connection.execute(text("ALTER TABLE repositorios DROP COLUMN IF EXISTS proyecto_nombre"))


def sync_evaluaciones_docente_columns() -> None:
    inspector = inspect(engine)
    if "evaluaciones_docente" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("evaluaciones_docente")}

    with engine.begin() as connection:
        if "puntos_importancia" in existing_columns:
            connection.execute(text("ALTER TABLE evaluaciones_docente DROP COLUMN IF EXISTS puntos_importancia"))


def sync_ranking_columns() -> None:
    inspector = inspect(engine)
    if "ranking" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        # Migrar columnas de INTEGER a DOUBLE PRECISION
        for col in ("puntos_commits", "puntos_docente", "puntos_proyecto", "total"):
            connection.execute(
                text(f"ALTER TABLE ranking ALTER COLUMN {col} TYPE DOUBLE PRECISION USING {col}::double precision")
            )
        # Corregir constraint de rango (antes era 0-500, ahora es 0-100 porque es promedio)
        connection.execute(text("ALTER TABLE ranking DROP CONSTRAINT IF EXISTS ck_total_range"))
        connection.execute(
            text("ALTER TABLE ranking ADD CONSTRAINT ck_total_range CHECK (total >= 0 AND total <= 100)")
        )


def sync_grupos_peer_voting_column() -> None:
    inspector = inspect(engine)
    if "grupos" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("grupos")}

    with engine.begin() as connection:
        if "peer_voting_enabled" not in existing_columns:
            connection.execute(text("ALTER TABLE grupos ADD COLUMN IF NOT EXISTS peer_voting_enabled BOOLEAN NOT NULL DEFAULT FALSE"))


def init_db() -> None:
    sync_group_columns()
    sync_group_share_token_columns()
    sync_participant_columns()
    sync_repositorios_columns()
    sync_evaluaciones_docente_columns()
    sync_ranking_columns()
    sync_grupos_peer_voting_column()
    Base.metadata.create_all(bind=engine)
