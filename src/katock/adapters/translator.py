"""OpenAI 兼容接口。一次提交整首，句数必须对齐。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from katock.domain.failures import TRANSLATION, suggestion

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class TranslationError(Exception):
    def __init__(self, summary: str) -> None:
        super().__init__(summary)
        self.kind = TRANSLATION
        self.summary = summary
        self.suggestion = suggestion(TRANSLATION)


@dataclass(frozen=True)
class Translation:
    lines: tuple[str, ...]
    token_usage: int


@dataclass(frozen=True)
class ConnectionTest:
    ok: bool
    failed_at: str
    detail: str


def _parse_lines(content: str, expected: int) -> tuple[str, ...]:
    text = content.strip()
    text = _FENCE.sub("", text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranslationError("译文不是合法 JSON") from exc
    raw: list[object] | None = None
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        for key in ("lines", "translations", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                raw = value
                break
    if raw is None or len(raw) != expected:
        raise TranslationError("译文句数与原文不一致")
    lines = tuple(str(item).strip() for item in raw)
    if any(not line for line in lines):
        raise TranslationError("译文存在空行")
    return lines


class Translator:
    async def translate(
        self,
        lines: list[str],
        *,
        base_url: str,
        model: str,
        api_key: str,
    ) -> Translation:
        if not api_key:
            raise TranslationError("还没有填写翻译接口密钥")
        numbered = [{"i": index + 1, "text": line} for index, line in enumerate(lines)]
        body = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是歌词译者。把用户给出的歌词逐句译成口语化中文。"
                        '只输出 JSON 对象 {"lines": ["译文", ...]}。'
                        "数组长度必须与输入句数完全相同，顺序一致，不要解释，不要编号。"
                    ),
                },
                {"role": "user", "content": json.dumps(numbered, ensure_ascii=False)},
            ],
        }
        url = base_url.rstrip("/") + "/chat/completions"
        timeout = httpx.Timeout(30.0)
        last_error = TranslationError("翻译请求失败")
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=body,
                    )
            except httpx.TimeoutException:
                last_error = TranslationError("翻译接口超时")
                continue
            except httpx.HTTPError as exc:
                last_error = TranslationError(f"翻译接口无法连接：{exc.__class__.__name__}")
                continue
            if response.status_code in {401, 403}:
                raise TranslationError("翻译接口密钥无效")
            if response.status_code == 404:
                raise TranslationError("翻译模型名不存在或接口路径不对")
            if response.status_code >= 400:
                last_error = TranslationError(f"翻译接口返回 {response.status_code}")
                continue
            payload = response.json()
            try:
                content = payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                last_error = TranslationError("翻译接口没有返回文本")
                continue
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            tokens = int(usage.get("total_tokens") or 0)
            try:
                parsed = _parse_lines(str(content), len(lines))
            except TranslationError as exc:
                last_error = exc
                continue
            return Translation(lines=parsed, token_usage=tokens)
        raise last_error

    async def test_connection(self, base_url: str, model: str, api_key: str) -> ConnectionTest:
        root = base_url.rstrip("/")
        timeout = httpx.Timeout(15.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    root + "/models",
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
                )
        except httpx.HTTPError as exc:
            return ConnectionTest(False, "base_url", f"地址不可达：{exc.__class__.__name__}")
        if response.status_code in {401, 403}:
            return ConnectionTest(False, "api_key", "密钥被拒绝")
        if response.status_code == 404:
            return await self._probe_model(root, model, api_key)
        if response.status_code >= 400:
            return ConnectionTest(False, "base_url", f"模型列表返回 {response.status_code}")
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return ConnectionTest(False, "base_url", "模型列表不是 JSON")
        names: set[str] = set()
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id"):
                    names.add(str(item["id"]))
        if names and model not in names:
            return ConnectionTest(False, "model", f"模型列表里没有 {model}")
        if not names:
            return await self._probe_model(root, model, api_key)
        return ConnectionTest(True, "", f"已确认模型 {model}")

    async def _probe_model(self, root: str, model: str, api_key: str) -> ConnectionTest:
        if not api_key:
            return ConnectionTest(False, "api_key", "还没有填写密钥")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
                response = await client.post(
                    root + "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
        except httpx.HTTPError as exc:
            return ConnectionTest(False, "base_url", f"对话接口不可达：{exc.__class__.__name__}")
        if response.status_code in {401, 403}:
            return ConnectionTest(False, "api_key", "密钥被拒绝")
        if response.status_code == 404:
            return ConnectionTest(False, "model", f"模型名不存在：{model}")
        if response.status_code >= 400:
            body = response.text[:180]
            if "model" in body.lower():
                return ConnectionTest(False, "model", body)
            return ConnectionTest(False, "base_url", f"对话接口返回 {response.status_code}")
        return ConnectionTest(True, "", f"模型 {model} 可以对话")
