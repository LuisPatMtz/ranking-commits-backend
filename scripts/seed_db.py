"""
Seed inicial de la base de datos.
Crea el usuario admin si no existe y muestra los INSERT INTO equivalentes.

Uso:
    python scripts/seed_db.py
    python scripts/seed_db.py --password MiPasswordSeguro123
"""

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.security import get_password_hash
from app.db.session import engine
from app.models.user import User, UserRole
from sqlalchemy.orm import Session


DEFAULT_ADMIN = {
    "nombre": "Administrador",
    "username": "admin",
    "password": "Admin1234!",
}


def seed(password: str) -> None:
    password_hash = get_password_hash(password)

    with Session(engine) as db:
        exists = db.query(User).filter(User.username == DEFAULT_ADMIN["username"]).first()

        if exists:
            print(f"  -- El usuario '{DEFAULT_ADMIN['username']}' ya existe (id={exists.id}). No se creó nada.")
        else:
            admin = User(
                nombre=DEFAULT_ADMIN["nombre"],
                username=DEFAULT_ADMIN["username"],
                password_hash=password_hash,
                rol=UserRole.admin,
                activo=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"  OK  Usuario admin creado (id={admin.id})")

    print()
    print("=== INSERT INTO equivalente ===")
    print("(puedes ejecutarlo directamente en psql si prefieres)\n")
    print(f"""INSERT INTO usuarios (nombre, username, password_hash, rol, activo)
VALUES (
  '{DEFAULT_ADMIN["nombre"]}',
  '{DEFAULT_ADMIN["username"]}',
  '{password_hash}',
  'admin',
  TRUE
)
ON CONFLICT (username) DO NOTHING;
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", default=DEFAULT_ADMIN["password"], help="Password del admin (default: Admin1234!)")
    args = parser.parse_args()
    seed(args.password)
