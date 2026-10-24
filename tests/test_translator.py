"""翻译接口的失败点必须能指认。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from katock.adapters.translator import Translator


def _client_factory(transport: httpx.MockTransport):
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real(*args, **kwargs)  # type: ignore[arg-type]

    return factory


def test_translate_accepts_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content.decode())
        assert body["model"] == "deepseek-v4.1-flash-1017"
        content = '```json\n{"lines": ["这是真实的人生吗？", "（呜）"]}\n```'
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"total_tokens": 18},
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))
    result = asyncio.run(
        Translator().translate(
            ["Is this the real life?", "(Ooh)"],
            base_url="https://example.invalid/v1",
            model="deepseek-v4.1-flash-1017",
            api_key="secret",
        )
    )
    assert result.lines == ("这是真实的人生吗？", "（呜）")
    assert result.token_usage == 18


def test_translate_rejects_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"lines": ["只有一句"]}'}}]},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))
    with pytest.raises(Exception, match="句数"):
        asyncio.run(
            Translator().translate(
                ["one", "two"],
                base_url="https://example.invalid/v1",
                model="m",
                api_key="secret",
            )
        )


def test_connection_points_at_the_failing_part(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/models"):
            if request.headers.get("authorization") == "Bearer bad":
                return httpx.Response(401)
            return httpx.Response(200, json={"data": [{"id": "other-model"}]})
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))
    translator = Translator()
    denied = asyncio.run(translator.test_connection("https://example.invalid/v1", "m", "bad"))
    assert denied.ok is False
    assert denied.failed_at == "api_key"
    missing = asyncio.run(
        translator.test_connection("https://example.invalid/v1", "deepseek-v4.1-flash-1017", "ok")
    )
    assert missing.failed_at == "model"
    assert "deepseek-v4.1-flash-1017" in missing.detail
    assert calls
