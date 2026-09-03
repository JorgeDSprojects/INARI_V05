from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    emqx_host: str
    emqx_port: int
    redis_host: str
    redis_port: int
    stream_maxlen: int
    mqtt_client_id: str


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        emqx_host=e.get("EMQX_HOST", "emqx"),
        emqx_port=int(e.get("EMQX_PORT", "1883")),
        redis_host=e.get("REDIS_HOST", "redis"),
        redis_port=int(e.get("REDIS_PORT", "6379")),
        stream_maxlen=int(e.get("STREAM_MAXLEN", "1000")),
        mqtt_client_id=e.get("MQTT_CLIENT_ID", "uns-dashboard-bridge"),
    )
