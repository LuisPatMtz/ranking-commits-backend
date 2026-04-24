"""Assign created_by_user_id to groups that have NULL (created before auth was added)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    groups = conn.execute(text("SELECT id, nombre, created_by_user_id FROM grupos")).fetchall()
    users = conn.execute(text("SELECT id, username, rol FROM usuarios")).fetchall()

print("=== GRUPOS ===")
for g in groups:
    print(g)

print("\n=== USUARIOS ===")
for u in users:
    print(u)

null_groups = [g for g in groups if g[2] is None]
if null_groups:
    print(f"\n{len(null_groups)} grupo(s) sin propietario (created_by_user_id = NULL)")
    docentes = [u for u in users if u[2] == "docente"]
    if len(docentes) == 1:
        owner_id = docentes[0][0]
        print(f"Asignando propietario id={owner_id} ({docentes[0][1]}) a todos...")
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE grupos SET created_by_user_id = {owner_id} WHERE created_by_user_id IS NULL"))
        print("Listo.")
    else:
        print("Multiples docentes, no se puede asignar automaticamente.")
        print("Docentes disponibles:", docentes)
else:
    print("\nTodos los grupos tienen propietario asignado.")
