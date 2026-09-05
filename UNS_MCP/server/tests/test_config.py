from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings({})
    assert settings.silver_database_url == "postgresql://silver_reader:silverreaderpassword@uns_silver_postgres:5432/uns_silver"
    assert settings.mcp_api_key == "changeme-local-dev-key"
    assert settings.http_host == "0.0.0.0"
    assert settings.http_port == 8000


def test_env_overrides_defaults():
    settings = load_settings({"MCP_API_KEY": "real-key", "HTTP_PORT": "9000"})
    assert settings.mcp_api_key == "real-key"
    assert settings.http_port == 9000
