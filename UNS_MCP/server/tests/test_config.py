from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings({})
    assert settings.silver_database_url == "postgresql://silver_reader:silverreaderpassword@uns_silver_postgres:5432/uns_silver"
    assert settings.mcp_api_key == "changeme-local-dev-key"
    assert settings.http_host == "0.0.0.0"
    assert settings.http_port == 8000
    # Must include the container DNS name, not just loopback -- the SDK's own
    # default would 421 every container-to-container call.
    assert settings.allowed_hosts == [
        "localhost:*", "127.0.0.1:*", "[::1]:*", "uns_mcp_server:*",
    ]
    assert settings.allowed_origins == [
        "http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*",
    ]
    # Fails closed: the default key is refused unless explicitly opted into.
    assert settings.allow_default_api_key is False


def test_env_overrides_defaults():
    settings = load_settings({
        "MCP_API_KEY": "real-key",
        "HTTP_PORT": "9000",
        "MCP_ALLOWED_HOSTS": "example.internal:*, other.internal:8000 ,",
        "MCP_ALLOWED_ORIGINS": "https://example.internal",
        "MCP_ALLOW_DEFAULT_KEY": "TRUE",
    })
    assert settings.mcp_api_key == "real-key"
    assert settings.http_port == 9000
    # Whitespace trimmed, empty entries from a trailing comma dropped.
    assert settings.allowed_hosts == ["example.internal:*", "other.internal:8000"]
    assert settings.allowed_origins == ["https://example.internal"]
    assert settings.allow_default_api_key is True


def test_allow_default_api_key_is_false_for_non_true_values():
    for value in ("false", "0", "yes", "", "  "):
        assert load_settings({"MCP_ALLOW_DEFAULT_KEY": value}).allow_default_api_key is False
