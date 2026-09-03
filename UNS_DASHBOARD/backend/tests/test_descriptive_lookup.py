import json

import httpx
import pytest

from app.services.descriptive_lookup import get_descriptive_signal_meta


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


@pytest.mark.asyncio
async def test_returns_unit_and_range_when_signals_map_has_the_key(monkeypatch):
    descriptive = {"signals": {"Amb_Temp_Avg": {"unit": "°C", "range": [-20, 120]}}}

    async def fake_get(self, url, **kwargs):
        return _FakeResponse(200, {"payload": json.dumps(descriptive)})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    meta = await get_descriptive_signal_meta("a/b", "Amb_Temp_Avg")
    assert meta == {"unit": "°C", "min": -20, "max": 120}


@pytest.mark.asyncio
async def test_returns_none_when_signal_not_in_descriptive_map(monkeypatch):
    descriptive = {"signals": {}}

    async def fake_get(self, url, **kwargs):
        return _FakeResponse(200, {"payload": json.dumps(descriptive)})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    assert await get_descriptive_signal_meta("a/b", "Missing_Key") is None


@pytest.mark.asyncio
async def test_returns_none_on_404():
    async def fake_get(self, url, **kwargs):
        return _FakeResponse(404, {})

    import httpx as httpx_module
    orig = httpx_module.AsyncClient.get
    httpx_module.AsyncClient.get = fake_get
    try:
        assert await get_descriptive_signal_meta("a/b", "Amb_Temp_Avg") is None
    finally:
        httpx_module.AsyncClient.get = orig
