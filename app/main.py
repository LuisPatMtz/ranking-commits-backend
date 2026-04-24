from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


app.include_router(api_router, prefix="/api/v1")
