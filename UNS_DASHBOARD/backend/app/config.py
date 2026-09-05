from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard"
    historian_database_url: str = "postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian"
    emqx_host: str = "localhost"
    emqx_port: int = 1883
    emqx_api_port: int = 18083
    emqx_api_username: str | None = None
    emqx_api_password: str | None = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    stream_maxlen: int = 1000
    mcp_server_url: str = "http://uns_mcp_server:8000/mcp"
    mcp_api_key: str = ""
    llm_provider_type: str = "none"
    llm_base_url: str = "http://uns_ollama:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:14b-instruct"


settings = Settings()
