from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings({})
    assert settings.database_url == "postgresql://silver:silverpassword@uns_silver_postgres:5432/uns_silver"
    assert settings.historian_database_url == "postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian"
    assert settings.poll_interval_seconds == 10.0
    assert settings.batch_size == 2000
    assert settings.max_flatten_depth == 6
    assert settings.max_flatten_keys == 500
    assert settings.raw_compress_after_days == 7
    assert settings.raw_retention_days == 90
    assert settings.agg_1m_retention_days == 0
    assert settings.agg_1h_retention_days == 0


def test_env_overrides_defaults():
    settings = load_settings({"NORMALIZER_BATCH_SIZE": "50", "RAW_RETENTION_DAYS": "30"})
    assert settings.batch_size == 50
    assert settings.raw_retention_days == 30
