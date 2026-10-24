"""Apple Music 链接解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["song", "album", "playlist"]

_HOST = r"https?://(?:beta\.|classical\.)?music\.apple\.com"
_ALBUM = re.compile(
    _HOST + r"/(\w{2})/album/(?:[^/?#]+/)?(\d+)(?:\?([^#]*))?",
    re.IGNORECASE,
)
_SONG = re.compile(
    _HOST + r"/(\w{2})/song/(?:[^/?#]+/)?(\d+)",
    re.IGNORECASE,
)
_PLAYLIST = re.compile(
    _HOST + r"/(\w{2})/playlist/(?:[^/?#]+/)?(pl\.[\w-]+)",
    re.IGNORECASE,
)
_TRACK_QUERY = re.compile(r"(?:^|&)i=(\d+)(?:&|$)")


@dataclass(frozen=True)
class AppleRef:
    kind: Kind
    storefront: str
    url: str
    album_id: str | None = None
    track_id: str | None = None
    playlist_id: str | None = None


def parse_apple_url(url: str) -> AppleRef | None:
    text = url.strip()
    playlist = _PLAYLIST.search(text)
    if playlist:
        return AppleRef(
            kind="playlist",
            storefront=playlist.group(1).lower(),
            playlist_id=playlist.group(2),
            url=text,
        )
    song = _SONG.search(text)
    if song:
        return AppleRef(
            kind="song",
            storefront=song.group(1).lower(),
            track_id=song.group(2),
            url=text,
        )
    album = _ALBUM.search(text)
    if album:
        storefront, album_id, query = album.group(1).lower(), album.group(2), album.group(3) or ""
        track = _TRACK_QUERY.search(query)
        if track:
            return AppleRef(
                kind="song",
                storefront=storefront,
                album_id=album_id,
                track_id=track.group(1),
                url=text,
            )
        return AppleRef(kind="album", storefront=storefront, album_id=album_id, url=text)
    return None


def song_url(storefront: str, album_id: str, track_id: str) -> str:
    return f"https://music.apple.com/{storefront}/album/{album_id}?i={track_id}"
