"""iTunes Search API wrapper (free, no key, ~20 requests/minute).

Apple's terms: stream previews from Apple's URLs only (never download/re-host),
and link back to the track on Apple Music / iTunes.
"""
import json
import urllib.parse
import urllib.request

SEARCH_URL = "https://itunes.apple.com/search"


def search_songs(term: str, limit: int = 20) -> list[dict]:
    query = urllib.parse.urlencode(
        {"term": term, "media": "music", "entity": "song", "limit": limit}
    )
    req = urllib.request.Request(f"{SEARCH_URL}?{query}", headers={"User-Agent": "family-music/0.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)

    results = []
    for r in data.get("results", []):
        if "trackId" not in r:
            continue
        artwork = r.get("artworkUrl100") or ""
        results.append(
            {
                "itunes_id": r["trackId"],
                "title": r.get("trackName", "Unknown"),
                "artist": r.get("artistName", "Unknown"),
                "album": r.get("collectionName"),
                # bump artwork from 100px to 300px
                "artwork_url": artwork.replace("100x100bb", "300x300bb") or None,
                "preview_url": r.get("previewUrl"),
                "track_url": r.get("trackViewUrl"),
            }
        )
    return results
