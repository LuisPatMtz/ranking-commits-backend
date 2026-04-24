from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Ranking API"
    env: str = "dev"
    secret_key: str = "change_me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ranking_commits"
    github_token: str | None = None


settings = Settings()
