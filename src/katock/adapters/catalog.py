"""Apple Music 目录、封面与歌词。"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import zhconv

from katock.domain.apple_url import song_url
from katock.domain.failures import AUTH, UNAVAILABLE, UNKNOWN, suggestion

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_INDEX = re.compile(r"/assets/index[^\"']+\.js")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class CatalogError(Exception):
    def __init__(self, kind: str, summary: str) -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary
        self.suggestion = suggestion(kind)


@dataclass(frozen=True)
class CatalogTrack:
    track_id: str
    title: str
    artist: str
    album: str
    album_artist: str
    year: int | None
    duration_s: float
    track_number: int
    disc_number: int
    artwork_url: str
    storefront: str
    url: str
    audio_locale: str
    has_lyrics: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "trackId": self.track_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "albumArtist": self.album_artist,
            "year": self.year,
            "durationS": self.duration_s,
            "trackNumber": self.track_number,
            "discNumber": self.disc_number,
            "artworkUrl": self.artwork_url,
            "storefront": self.storefront,
            "url": self.url,
            "audioLocale": self.audio_locale,
            "hasLyrics": self.has_lyrics,
        }


def artwork_at(template: str, size: int) -> str:
    if not template:
        return ""
    return template.replace("{w}", str(size)).replace("{h}", str(size)).replace("{f}", "jpg")


def _year(release: str) -> int | None:
    if len(release) >= 4 and release[:4].isdigit():
        return int(release[:4])
    return None


def _jwt_exp(token: str) -> int:
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
        return int(data.get("exp", 0))
    except (IndexError, ValueError, json.JSONDecodeError):
        return 0


class Catalog:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._token = ""
        self._exp = 0

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )

    async def developer_token(self, force: bool = False) -> str:
        now = int(time.time())
        if not force and self._token and self._exp - now > 300:
            return self._token
        cache = self.cache_dir / "devtoken.json"
        if not force and cache.is_file():
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if int(saved.get("exp", 0)) - now > 300:
                self._token = str(saved["token"])
                self._exp = int(saved["exp"])
                return self._token
        async with await self._client() as client:
            page = await client.get("https://music.apple.com")
            page.raise_for_status()
            match = _INDEX.search(page.text)
            token = ""
            if match:
                script = await client.get("https://music.apple.com" + match.group(0))
                script.raise_for_status()
                found = _JWT.search(script.text)
                token = found.group(0) if found else ""
            if not token:
                found = _JWT.search(page.text)
                token = found.group(0) if found else ""
        if not token:
            raise CatalogError(UNKNOWN, "没有从 Apple Music 网页拿到开发者令牌")
        self._token = token
        self._exp = _jwt_exp(token)
        cache.write_text(
            json.dumps({"token": token, "exp": self._exp}),
            encoding="utf-8",
        )
        return token

    def _headers(self, token: str, media_token: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Origin": "https://music.apple.com",
            "Referer": "https://music.apple.com/",
            "User-Agent": _USER_AGENT,
        }
        if media_token:
            headers["Cookie"] = f"media-user-token={media_token}"
        return headers

    async def _get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        media_token: str | None = None,
    ) -> dict[str, object]:
        token = await self.developer_token()
        async with await self._client() as client:
            response = await client.get(
                url, params=params, headers=self._headers(token, media_token)
            )
            if response.status_code == 401:
                token = await self.developer_token(force=True)
                response = await client.get(
                    url, params=params, headers=self._headers(token, media_token)
                )
        if response.status_code in {401, 403}:
            raise CatalogError(AUTH, "Apple 目录接口拒绝访问，登录态或开发者令牌无效")
        if response.status_code == 404:
            raise CatalogError(UNAVAILABLE, "该曲目在当前店面不可获取")
        if response.status_code >= 400:
            raise CatalogError(UNKNOWN, f"Apple 目录接口返回 {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise CatalogError(UNKNOWN, "Apple 目录接口返回了无法识别的内容")
        return payload

    def _track(
        self, item: dict[str, object], storefront: str, album_hint: str = ""
    ) -> CatalogTrack | None:
        attributes = item.get("attributes")
        if not isinstance(attributes, dict):
            return None
        track_id = str(item.get("id", ""))
        if not track_id:
            return None
        album = str(attributes.get("albumName") or album_hint or "")
        relationships = item.get("relationships")
        album_id = ""
        album_artist = str(attributes.get("artistName") or "")
        if isinstance(relationships, dict):
            albums = relationships.get("albums")
            if isinstance(albums, dict):
                data = albums.get("data")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    album_id = str(data[0].get("id") or "")
                    album_attrs = data[0].get("attributes")
                    if isinstance(album_attrs, dict):
                        album = album or str(album_attrs.get("name") or "")
                        album_artist = str(album_attrs.get("artistName") or album_artist)
        artwork = attributes.get("artwork")
        artwork_url = ""
        if isinstance(artwork, dict):
            artwork_url = str(artwork.get("url") or "")
        url = str(attributes.get("url") or "")
        if not url and album_id:
            url = song_url(storefront, album_id, track_id)
        duration_ms = attributes.get("durationInMillis") or 0
        return CatalogTrack(
            track_id=track_id,
            title=str(attributes.get("name") or ""),
            artist=str(attributes.get("artistName") or ""),
            album=album,
            album_artist=album_artist,
            year=_year(str(attributes.get("releaseDate") or "")),
            duration_s=float(duration_ms) / 1000 if isinstance(duration_ms, int | float) else 0,
            track_number=int(attributes.get("trackNumber") or 1),
            disc_number=int(attributes.get("discNumber") or 1),
            artwork_url=artwork_url,
            storefront=storefront,
            url=url,
            audio_locale=str(attributes.get("audioLocale") or ""),
            has_lyrics=bool(attributes.get("hasLyrics")),
        )

    async def search(
        self, storefront: str, term: str, limit: int = 10, offset: int = 0
    ) -> list[CatalogTrack]:
        variants: list[str] = []
        for text in (term, zhconv.convert(term, "zh-cn"), zhconv.convert(term, "zh-tw")):
            if text and text not in variants:
                variants.append(text)
        merged: dict[str, CatalogTrack] = {}
        for text in variants:
            payload = await self._get(
                f"https://amp-api.music.apple.com/v1/catalog/{storefront}/search",
                {
                    "term": text,
                    "types": "songs",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
            results = payload.get("results")
            songs: list[object] = []
            if isinstance(results, dict):
                bucket = results.get("songs")
                if isinstance(bucket, dict) and isinstance(bucket.get("data"), list):
                    songs = bucket["data"]
            for item in songs:
                if isinstance(item, dict):
                    track = self._track(item, storefront)
                    if track and track.track_id not in merged:
                        merged[track.track_id] = track
        tracks = list(merged.values())
        folded = term.casefold()
        order = {id(track): index for index, track in enumerate(tracks)}

        def rank(track: CatalogTrack) -> tuple[int, int]:
            title = track.title.casefold()
            if title == folded:
                exact = 0
            elif folded in title:
                exact = 1
            else:
                exact = 2
            return (exact, order[id(track)])

        tracks.sort(key=rank)
        return tracks[:limit]

    async def song(self, storefront: str, track_id: str) -> CatalogTrack:
        payload = await self._get(
            f"https://amp-api.music.apple.com/v1/catalog/{storefront}/songs/{track_id}",
            {"include": "albums,artists"},
        )
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CatalogError(UNAVAILABLE, "没有找到这首曲目")
        track = self._track(data[0], storefront)
        if track is None:
            raise CatalogError(UNAVAILABLE, "曲目信息缺少必要字段")
        return track

    async def collection(
        self, storefront: str, kind: str, collection_id: str
    ) -> list[CatalogTrack]:
        resource = "albums" if kind == "album" else "playlists"
        payload = await self._get(
            f"https://amp-api.music.apple.com/v1/catalog/{storefront}/{resource}/{collection_id}",
            {"include": "tracks"},
        )
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CatalogError(UNAVAILABLE, "没有找到这个专辑或歌单")
        root = data[0]
        attributes = root.get("attributes") if isinstance(root.get("attributes"), dict) else {}
        album_name = str(attributes.get("name") or "") if isinstance(attributes, dict) else ""
        relationships = root.get("relationships")
        tracks_blob: dict[str, object] = {}
        if isinstance(relationships, dict) and isinstance(relationships.get("tracks"), dict):
            tracks_blob = relationships["tracks"]
        raw_items = tracks_blob.get("data")
        items: list[dict[str, object]] = []
        if isinstance(raw_items, list):
            items = [item for item in raw_items if isinstance(item, dict)]
        next_url = str(tracks_blob.get("next") or "")
        while next_url:
            page = await self._get("https://amp-api.music.apple.com" + next_url)
            extra = page.get("data")
            if isinstance(extra, list):
                items.extend(item for item in extra if isinstance(item, dict))
            next_url = str(page.get("next") or "")
        tracks: list[CatalogTrack] = []
        for item in items:
            if isinstance(item, dict):
                track = self._track(item, storefront, album_name)
                if track:
                    tracks.append(track)
        return tracks

    async def lyrics_ttml(self, storefront: str, track_id: str, media_token: str) -> str:
        if len(media_token) < 20:
            raise CatalogError(LYRICS_KIND, "还没有填写 media-user-token")
        payload = await self._get(
            f"https://amp-api.music.apple.com/v1/catalog/{storefront}/songs/{track_id}/lyrics",
            {"extend": "ttmlLocalizations"},
            media_token=media_token,
        )
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise CatalogError(LYRICS_KIND, "这首歌没有歌词")
        attributes = data[0].get("attributes")
        if not isinstance(attributes, dict):
            raise CatalogError(LYRICS_KIND, "这首歌没有歌词")
        ttml = str(attributes.get("ttml") or attributes.get("ttmlLocalizations") or "")
        if not ttml:
            raise CatalogError(LYRICS_KIND, "这首歌没有歌词")
        return ttml

    async def cover_bytes(self, template: str) -> tuple[bytes, int, int]:
        last_error = "封面地址为空"
        async with await self._client() as client:
            for size in (3000, 2000, 1400, 1000, 600):
                url = artwork_at(template, size)
                if not url:
                    break
                response = await client.get(url)
                if response.status_code != 200 or not response.content:
                    last_error = f"封面下载返回 {response.status_code}（{size}）"
                    continue
                width, height = _jpeg_size(response.content) or (size, size)
                return response.content, width, height
        raise CatalogError(COVER_KIND, last_error)


LYRICS_KIND = "lyrics"
COVER_KIND = "cover"


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in {0xC0, 0xC1, 0xC2}:
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD9:
            index += 2
            continue
        if index + 4 > len(data):
            break
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        if length < 2:
            break
        index += 2 + length
    return None
