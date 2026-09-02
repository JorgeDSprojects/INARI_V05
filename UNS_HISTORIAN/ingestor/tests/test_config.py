# UNS_HISTORIAN/ingestor/tests/test_config.py
from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings(env={})
    assert settings.emqx_host == "emqx"
    assert settings.emqx_port == 1883
    assert settings.mqtt_topic_filter == "#"
    assert settings.flush_max_rows == 500


def test_overrides_from_env():
    settings = load_settings(env={"EMQX_HOST": "custom-broker", "FLUSH_MAX_ROWS": "10"})
    assert settings.emqx_host == "custom-broker"
    assert settings.flush_max_rows == 10
