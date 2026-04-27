"""
Migración 3FN — aplica cambios de esquema a una base de datos existente.
Idempotente: se puede ejecutar múltiples veces sin romper nada.

Ejecutar desde la raíz del backend:
    python scripts/migrate_3nf.py
"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import inspect, text
from app.db.session import engine


def run(conn, label: str, sql: str) -> None:
    try:
        conn.execute(text(sql))
        print(f"  OK  {label}")
    except Exception as exc:
        print(f"  --  {label} (saltado: {exc})")


def migrate() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        print("\n=== repositorios ===")
        if "repositorios" in tables:
            cols = {c["name"] for c in inspector.get_columns("repositorios")}
            if "proyecto_nombre" in cols:
                run(conn, "DROP COLUMN proyecto_nombre", "ALTER TABLE repositorios DROP COLUMN IF EXISTS proyecto_nombre")
            run(
                conn,
                "UNIQUE (usuario_id, owner, repo)",
                "ALTER TABLE repositorios ADD CONSTRAINT uq_repositorios_usuario_owner_repo "
                "UNIQUE (usuario_id, owner, repo)",
            )
            run(
                conn,
                "INDEX ix_repositorios_usuario_activo",
                "CREATE INDEX IF NOT EXISTS ix_repositorios_usuario_activo ON repositorios (usuario_id, activo)",
            )

        print("\n=== grupo_usuarios ===")
        if "grupo_usuarios" in tables:
            run(
                conn,
                "PARTIAL UNIQUE activo (grupo_id, usuario_id) WHERE fecha_fin IS NULL",
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_grupo_usuarios_activo "
                "ON grupo_usuarios (grupo_id, usuario_id) WHERE fecha_fin IS NULL",
            )
            run(
                conn,
                "INDEX ix_grupo_usuarios_grupo_usuario",
                "CREATE INDEX IF NOT EXISTS ix_grupo_usuarios_grupo_usuario ON grupo_usuarios (grupo_id, usuario_id)",
            )

        print("\n=== evaluaciones_docente ===")
        if "evaluaciones_docente" in tables:
            cols = {c["name"] for c in inspector.get_columns("evaluaciones_docente")}
            if "puntos_importancia" in cols:
                run(
                    conn,
                    "DROP COLUMN puntos_importancia",
                    "ALTER TABLE evaluaciones_docente DROP COLUMN IF EXISTS puntos_importancia",
                )
                run(
                    conn,
                    "DROP CHECK ck_importancia_range",
                    "ALTER TABLE evaluaciones_docente DROP CONSTRAINT IF EXISTS ck_importancia_range",
                )
            run(
                conn,
                "INDEX ix_eval_docente_grupo_alumno",
                "CREATE INDEX IF NOT EXISTS ix_eval_docente_grupo_alumno ON evaluaciones_docente (grupo_id, alumno_id)",
            )
            run(
                conn,
                "INDEX ix_eval_docente_docente_grupo",
                "CREATE INDEX IF NOT EXISTS ix_eval_docente_docente_grupo ON evaluaciones_docente (docente_id, grupo_id)",
            )

        print("\n=== evaluaciones_proyecto ===")
        if "evaluaciones_proyecto" in tables:
            run(
                conn,
                "UNIQUE (alumno_id, docente_id, grupo_id)",
                "ALTER TABLE evaluaciones_proyecto ADD CONSTRAINT uq_eval_proyecto_alumno_docente_grupo "
                "UNIQUE (alumno_id, docente_id, grupo_id)",
            )
            run(
                conn,
                "INDEX ix_eval_proyecto_grupo_alumno",
                "CREATE INDEX IF NOT EXISTS ix_eval_proyecto_grupo_alumno ON evaluaciones_proyecto (grupo_id, alumno_id)",
            )
            run(
                conn,
                "INDEX ix_eval_proyecto_docente_grupo",
                "CREATE INDEX IF NOT EXISTS ix_eval_proyecto_docente_grupo ON evaluaciones_proyecto (docente_id, grupo_id)",
            )

        print("\n=== commits ===")
        if "commits" in tables:
            run(
                conn,
                "INDEX ix_commits_usuario_fecha",
                "CREATE INDEX IF NOT EXISTS ix_commits_usuario_fecha ON commits (usuario_id, fecha)",
            )

        print("\n=== participantes ===")
        if "participantes" in tables:
            run(
                conn,
                "UNIQUE github_username",
                "ALTER TABLE participantes ADD CONSTRAINT uq_participantes_github_username "
                "UNIQUE (github_username)",
            )

        print("\n=== ranking ===")
        if "ranking" in tables:
            run(
                conn,
                "ALTER puntos_commits → DOUBLE PRECISION",
                "ALTER TABLE ranking ALTER COLUMN puntos_commits TYPE DOUBLE PRECISION USING puntos_commits::double precision",
            )
            run(
                conn,
                "ALTER puntos_docente → DOUBLE PRECISION",
                "ALTER TABLE ranking ALTER COLUMN puntos_docente TYPE DOUBLE PRECISION USING puntos_docente::double precision",
            )
            run(
                conn,
                "ALTER puntos_proyecto → DOUBLE PRECISION",
                "ALTER TABLE ranking ALTER COLUMN puntos_proyecto TYPE DOUBLE PRECISION USING puntos_proyecto::double precision",
            )
            run(
                conn,
                "ALTER total → DOUBLE PRECISION",
                "ALTER TABLE ranking ALTER COLUMN total TYPE DOUBLE PRECISION USING total::double precision",
            )
            run(conn, "DROP CHECK ck_total_range (viejo)", "ALTER TABLE ranking DROP CONSTRAINT IF EXISTS ck_total_range")
            run(
                conn,
                "ADD CHECK ck_total_range (0-100)",
                "ALTER TABLE ranking ADD CONSTRAINT ck_total_range CHECK (total >= 0 AND total <= 100)",
            )
            run(
                conn,
                "UNIQUE (usuario_id, grupo_id)",
                "ALTER TABLE ranking ADD CONSTRAINT uq_ranking_usuario_grupo UNIQUE (usuario_id, grupo_id)",
            )
            run(
                conn,
                "INDEX ix_ranking_grupo_total",
                "CREATE INDEX IF NOT EXISTS ix_ranking_grupo_total ON ranking (grupo_id, total)",
            )

    print("\nMigración completada.")


if __name__ == "__main__":
    migrate()
