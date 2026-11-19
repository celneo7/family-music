"""Listen-together rooms: everyone in a room hears the same song at the same moment.

The server holds the single source of truth for each room (which song, playing or
paused, and where in the song). Playback position is stored as `position` seconds
at server time `anchor`; while playing, the live position is
position + (now - anchor). Clients use that to line their own <audio> up.

Rooms live in memory (fine for a family-sized app) and vanish when the last
listener leaves or the server restarts.
"""
import time
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class Room:
    playlist_id: int
    name: str
    visibility: str
    owner_id: int
    started_by: str
    songs: list[dict]
    index: int = 0
    playing: bool = False
    position: float = 0.0
    anchor: float = field(default_factory=time.time)
    members: dict[WebSocket, str] = field(default_factory=dict)

    # ----- playback state -----

    def live_position(self) -> float:
        return self.position + (time.time() - self.anchor if self.playing else 0.0)

    def update(self, *, index: int | None = None, playing: bool | None = None,
               position: float | None = None) -> None:
        pos = self.live_position() if position is None else position
        if index is not None and index != self.index:
            self.index = index
            pos = 0.0 if position is None else position
        if playing is not None:
            self.playing = playing
        self.position = max(0.0, pos)
        self.anchor = time.time()

    def next(self) -> None:
        if self.index + 1 < len(self.songs):
            self.update(index=self.index + 1, position=0.0)
        else:  # end of playlist: back to the top, paused
            self.update(index=0, position=0.0, playing=False)

    def prev(self) -> None:
        if self.live_position() > 3:
            self.update(position=0.0)
        else:
            self.update(index=max(0, self.index - 1), position=0.0)

    # ----- messaging -----

    def listeners(self) -> list[str]:
        return sorted(set(self.members.values()), key=str.lower)

    def state(self, **extra) -> dict:
        return {
            "type": "state",
            "index": self.index,
            "playing": self.playing,
            "position": self.position,
            "server_time": self.anchor,
            "listeners": self.listeners(),
            "started_by": self.started_by,
            **extra,
        }

    def summary(self) -> dict:
        song = self.songs[self.index]
        return {
            "playlist_id": self.playlist_id,
            "name": self.name,
            "started_by": self.started_by,
            "listeners": self.listeners(),
            "now_playing": {"title": song["title"], "artist": song["artist"], "artwork_url": song["artwork_url"]},
            "playing": self.playing,
        }

    def visible_to(self, user_id: int) -> bool:
        return self.visibility == "public" or self.owner_id == user_id

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.members):
            try:
                await ws.send_json(msg)
            except Exception:
                self.members.pop(ws, None)


rooms: dict[int, Room] = {}  # playlist_id -> Room
