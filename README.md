# backend-rc

Backend base para plataforma de ranking academico.

## Requisitos
- Python 3.12+
- PostgreSQL local

## Configuracion local
1. Crea una base de datos local, por ejemplo: `ranking_commits`.
2. Copia `.env.example` a `.env` y ajusta `DATABASE_URL`.
3. Crea y activa un entorno virtual:
   - Windows PowerShell:
     `python -m venv .venv`
     `.\.venv\Scripts\Activate.ps1`
   - Linux/macOS:
     `python3 -m venv .venv`
     `source .venv/bin/activate`
4. Instala dependencias:
   `python -m pip install -r requirements.txt`
5. Crea tablas iniciales:
   `python scripts/init_db.py`
   Si cambiaste el modelo de datos y quieres rehacer tablas locales:
   `python scripts/reset_db.py`
6. Inicia API:
   `python -m uvicorn app.main:app --reload`

## Endpoints base
- GET /health
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/usuarios
- GET /api/v1/usuarios
- POST /api/v1/participantes
- GET /api/v1/participantes
- GET /api/v1/grupos
- GET /api/v1/repositorios
- POST /api/v1/github/sync/{usuario_id}
- GET /api/v1/commits/{usuario_id}
- GET /api/v1/evaluaciones
- GET /api/v1/ranking
- GET /api/v1/ranking/grupo/{grupo_id}

## Nota de modelo
- `usuarios`: nombre, username, password_hash, rol y estado.
- `participantes`: datos de alumnos (relacion 1:1 con usuarios rol alumno) y github_username.
