"""本机服务与 Apple 目录、翻译接口的端到端检查。服务没开时跳过。"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from katock.adapters.catalog import Catalog
from katock.adapters.translator import Translator

QUEEN = "https://music.apple.com/cn/album/bohemian-rhapsody/6781027361?i=6781027645"
API = "http://127.0.0.1:8765"


@pytest.mark.live
def test_catalog_resolves_bohemian_rhapsody(tmp_path) -> None:
    track = asyncio.run(Catalog(tmp_path / "cache").song("cn", "6781027645"))
    assert track.title == "Bohemian Rhapsody"
    assert track.artist == "Queen"
    assert track.track_id == "6781027645"
    assert track.duration_s > 300


@pytest.mark.live
def test_translator_connection_from_environment() -> None:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        pytest.skip("OPENAI_API_KEY 未设置")
    result = None
    for _ in range(2):
        result = asyncio.run(
            Translator().test_connection(
                "https://api.chatanywhere.tech/v1",
                "deepseek-v4.1-flash-1017",
                key,
            )
        )
        if result.ok or result.failed_at != "base_url":
            break
    assert result is not None
    assert result.ok is True
    assert result.failed_at == ""


@pytest.mark.live
def test_running_api_health_settings_and_resolve() -> None:
    try:
        with httpx.Client(base_url=API, timeout=60) as client:
            health = client.get("/api/health")
            settings = client.get("/api/settings")
            resolved = client.post("/api/resolve", json={"text": QUEEN})
            tested = client.post("/api/settings/translator/test", json={})
    except httpx.HTTPError as exc:
        pytest.skip(f"本机接口未就绪：{exc.__class__.__name__}")
    assert health.status_code == 200
    body = health.json()
    assert len(body["items"]) == 9
    assert {item["item"] for item in body["items"]} >= {
        "docker",
        "wrapper",
        "ffmpeg",
        "output_root",
        "disk",
    }
    assert settings.status_code == 200
    current = settings.json()
    assert current["translatorBaseUrl"] == "https://api.chatanywhere.tech/v1"
    assert current["translatorModel"] == "deepseek-v4.1-flash-1017"
    assert current["translatorKeySet"] is True
    assert "apiKey" not in current
    assert resolved.status_code == 200
    payload = resolved.json()
    assert payload["direct"] is True
    assert payload["tracks"][0]["title"] == "Bohemian Rhapsody"
    assert payload["tracks"][0]["trackId"] == "6781027645"
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
