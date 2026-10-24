"""搜索排序不能在排序过程中再查列表。"""

from __future__ import annotations

import asyncio

from katock.adapters.catalog import Catalog


def test_search_orders_exact_title_without_crashing(tmp_path) -> None:
    def song(track_id: str, title: str) -> dict[str, object]:
        return {
            "id": track_id,
            "attributes": {
                "name": title,
                "artistName": "Queen",
                "albumName": "Album",
                "durationInMillis": 1000,
                "trackNumber": 1,
                "discNumber": 1,
                "releaseDate": "1975-01-01",
                "audioLocale": "en-US",
                "hasLyrics": True,
            },
        }

    payload = {
        "results": {
            "songs": {
                "data": [
                    song("2", "Bohemian Rhapsody (Live)"),
                    song("1", "Bohemian Rhapsody"),
                ]
            }
        }
    }

    async def fake_get(
        self: Catalog,
        url: str,
        params: dict[str, str] | None = None,
        media_token: str | None = None,
    ) -> dict[str, object]:
        return payload

    catalog = Catalog(tmp_path / "cache")
    catalog._get = fake_get.__get__(catalog, Catalog)  # type: ignore[method-assign]
    tracks = asyncio.run(catalog.search("cn", "Bohemian Rhapsody Queen"))
    assert [item.track_id for item in tracks] == ["2", "1"]
    exact = asyncio.run(catalog.search("cn", "Bohemian Rhapsody"))
    assert exact[0].track_id == "1"
