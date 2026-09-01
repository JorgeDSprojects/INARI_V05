from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://unsadmin:unspassword@localhost:5432/unsdb"
    emqx_host: str = "localhost"
    emqx_port: int = 1883
    emqx_client_id: str = "uns_manager"


settings = Settings()
