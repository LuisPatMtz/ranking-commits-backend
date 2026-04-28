from fastapi import APIRouter

from app.api.v1.endpoints import (
	auth,
	commits,
	github,
	groups,
	participants,
	ranking,
	repositories,
	users,
	votes,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(groups.router)
api_router.include_router(repositories.router)
api_router.include_router(participants.router)
api_router.include_router(github.router)
api_router.include_router(commits.router)
api_router.include_router(ranking.router)
api_router.include_router(votes.router)
