from fastapi import APIRouter

from app.api.v1.endpoints import (
	auth,
	commits,
	evaluations,
	github,
	groups,
	ranking,
	repositories,
	users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(groups.router)
api_router.include_router(repositories.router)
api_router.include_router(github.router)
api_router.include_router(commits.router)
api_router.include_router(evaluations.router)
api_router.include_router(ranking.router)
