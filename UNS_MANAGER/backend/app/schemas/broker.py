from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BrokerCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=1883, ge=1, le=65535)
    api_port: int = Field(default=18083, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool = False


class BrokerUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    api_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None


class BrokerRead(_Base):
    id: str
    label: str
    host: str
    port: int
    api_port: int
    username: str | None
    use_tls: bool
    created_at: datetime
    updated_at: datetime
    # password intentionally omitted


class BrokerStatus(BaseModel):
    connected: bool
    version: str | None = None
    node: str | None = None
    error: str | None = None


class BrokerTestResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None
