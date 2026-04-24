# backend-rc

Backend base para plataforma de ranking academico.

## Requisitos
- Python 3.12+
- PostgreSQL local

## Configuracion local
1. Crea una base de datos local, por ejemplo: `ranking_commits`.
2. Copia `.env.example` a `.env` y ajusta `DATABASE_URL`.
3. Instala dependencias:
   `c:/Users/luisp/Documents/Proyectos/ranking-commits/.venv/Scripts/python.exe -m pip install -r requirements.txt`
4. Crea tablas iniciales:
   `c:/Users/luisp/Documents/Proyectos/ranking-commits/.venv/Scripts/python.exe scripts/init_db.py`
5. Inicia API:
   `c:/Users/luisp/Documents/Proyectos/ranking-commits/.venv/Scripts/python.exe -m uvicorn app.main:app --reload`

## Endpoints base
- GET /health
- POST /api/v1/auth/login
- POST /api/v1/usuarios
- GET /api/v1/usuarios
- GET /api/v1/grupos
- GET /api/v1/repositorios
- POST /api/v1/github/sync/{usuario_id}
- GET /api/v1/commits/{usuario_id}
- GET /api/v1/evaluaciones
- GET /api/v1/ranking
- GET /api/v1/ranking/grupo/{grupo_id}
