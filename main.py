"""Family Music — FastAPI app.

Run:  uvicorn main:app --reload   then open http://localhost:8000
"""
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import itunes
from db import get_db, init_db

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Family Music", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

Db = sqlite3.Connection


# ---------- request bodies ----------

class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=6, max_length=100)


class Register(Credentials):
    invite_code: str


class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    visibility: Literal["public", "private"] = "private"


class PlaylistPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    visibility: Literal["public", "private"] | None = None


class SongIn(BaseModel):
    itunes_id: int
    title: str = Field(max_length=300)
    artist: str = Field(max_length=300)
    album: str | None = Field(default=None, max_length=300)
    artwork_url: str | None = None
    preview_url: str | None = None
    track_url: str | None = None


# ---------- helpers ----------

APPLE_HOSTS = ("apple.com", "mzstatic.com")


def _apple_url(url: str | None) -> str | None:
    """Only keep https URLs that point at Apple, so nobody can inject other links."""
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in APPLE_HOSTS):
        return url
    return None


def _get_playlist(db: Db, playlist_id: int) -> sqlite3.Row:
    row = db.execute(
        """SELECT p.*, u.username AS owner
           FROM playlists p JOIN users u ON u.id = p.owner_id
           WHERE p.id = ?""",
        (playlist_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    return row


def _readable_playlist(db: Db, playlist_id: int, user) -> sqlite3.Row:
    pl = _get_playlist(db, playlist_id)
    if pl["visibility"] == "private" and pl["owner_id"] != user["id"]:
        # 404 rather than 403 so private playlists don't reveal they exist
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    return pl


def _owned_playlist(db: Db, playlist_id: int, user) -> sqlite3.Row:
    pl = _readable_playlist(db, playlist_id, user)
    if pl["owner_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can change this playlist")
    return pl


def _playlist_out(pl: sqlite3.Row, user, songs=None, song_count=None) -> dict:
    out = {
        "id": pl["id"],
        "name": pl["name"],
        "visibility": pl["visibility"],
        "owner": pl["owner"],
        "is_mine": pl["owner_id"] == user["id"],
        "created_at": pl["created_at"],
    }
    if songs is not None:
        out["songs"] = songs
    if song_count is not None:
        out["song_count"] = song_count
    return out


# ---------- pages ----------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------- auth ----------

@app.post("/auth/register", status_code=201)
def register(body: Register, db: Db = Depends(get_db)):
    if body.invite_code != auth.INVITE_CODE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wrong invite code")
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (body.username.strip(), auth.hash_password(body.password)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    return {"token": auth.create_token(cur.lastrowid), "username": body.username.strip()}


@app.post("/auth/login")
def login(body: Credentials, db: Db = Depends(get_db)):
    user = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if user is None or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    return {"token": auth.create_token(user["id"]), "username": user["username"]}


@app.get("/me")
def me(user=Depends(auth.current_user)):
    return {"id": user["id"], "username": user["username"]}


# ---------- search ----------

@app.get("/search")
def search(q: str = Query(min_length=1, max_length=100), user=Depends(auth.current_user)):
    try:
        return itunes.search_songs(q)
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "iTunes search failed, try again")


# ---------- playlists ----------

@app.get("/playlists")
def list_playlists(user=Depends(auth.current_user), db: Db = Depends(get_db)):
    rows = db.execute(
        """SELECT p.*, u.username AS owner,
                  (SELECT COUNT(*) FROM playlist_songs ps WHERE ps.playlist_id = p.id) AS n
           FROM playlists p JOIN users u ON u.id = p.owner_id
           WHERE p.owner_id = ? OR p.visibility = 'public'
           ORDER BY p.created_at DESC, p.id DESC""",
        (user["id"],),
    ).fetchall()
    out = []
    for r in rows:
        pl = _playlist_out(r, user, song_count=r["n"])
        # first 4 artworks → mosaic cover on the frontend
        pl["covers"] = [
            c["artwork_url"]
            for c in db.execute(
                """SELECT s.artwork_url FROM playlist_songs ps JOIN songs s ON s.id = ps.song_id
                   WHERE ps.playlist_id = ? AND s.artwork_url IS NOT NULL
                   ORDER BY ps.position LIMIT 4""",
                (r["id"],),
            )
        ]
        out.append(pl)
    return out


@app.post("/playlists", status_code=201)
def create_playlist(body: PlaylistIn, user=Depends(auth.current_user), db: Db = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO playlists (name, owner_id, visibility) VALUES (?, ?, ?)",
        (body.name.strip(), user["id"], body.visibility),
    )
    return _playlist_out(_get_playlist(db, cur.lastrowid), user, songs=[])


@app.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, user=Depends(auth.current_user), db: Db = Depends(get_db)):
    pl = _readable_playlist(db, playlist_id, user)
    songs = db.execute(
        """SELECT s.* FROM playlist_songs ps JOIN songs s ON s.id = ps.song_id
           WHERE ps.playlist_id = ? ORDER BY ps.position""",
        (playlist_id,),
    ).fetchall()
    return _playlist_out(pl, user, songs=[dict(s) for s in songs])


@app.patch("/playlists/{playlist_id}")
def update_playlist(
    playlist_id: int, body: PlaylistPatch, user=Depends(auth.current_user), db: Db = Depends(get_db)
):
    _owned_playlist(db, playlist_id, user)
    if body.name is not None:
        db.execute("UPDATE playlists SET name = ? WHERE id = ?", (body.name.strip(), playlist_id))
    if body.visibility is not None:
        db.execute("UPDATE playlists SET visibility = ? WHERE id = ?", (body.visibility, playlist_id))
    return _playlist_out(_get_playlist(db, playlist_id), user)


@app.delete("/playlists/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, user=Depends(auth.current_user), db: Db = Depends(get_db)):
    _owned_playlist(db, playlist_id, user)
    db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))


@app.post("/playlists/{playlist_id}/songs", status_code=201)
def add_song(
    playlist_id: int, body: SongIn, user=Depends(auth.current_user), db: Db = Depends(get_db)
):
    _owned_playlist(db, playlist_id, user)
    # Save the song locally the first time anyone adds it (cache of iTunes data).
    db.execute(
        """INSERT INTO songs (itunes_id, title, artist, album, artwork_url, preview_url, track_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(itunes_id) DO NOTHING""",
        (
            body.itunes_id, body.title, body.artist, body.album,
            _apple_url(body.artwork_url), _apple_url(body.preview_url), _apple_url(body.track_url),
        ),
    )
    song_id = db.execute("SELECT id FROM songs WHERE itunes_id = ?", (body.itunes_id,)).fetchone()["id"]
    next_pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_songs WHERE playlist_id = ?",
        (playlist_id,),
    ).fetchone()[0]
    try:
        db.execute(
            "INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)",
            (playlist_id, song_id, next_pos),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Song is already in this playlist")
    return {"song_id": song_id}


@app.delete("/playlists/{playlist_id}/songs/{song_id}", status_code=204)
def remove_song(
    playlist_id: int, song_id: int, user=Depends(auth.current_user), db: Db = Depends(get_db)
):
    _owned_playlist(db, playlist_id, user)
    cur = db.execute(
        "DELETE FROM playlist_songs WHERE playlist_id = ? AND song_id = ?", (playlist_id, song_id)
    )
    if cur.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Song not in this playlist")
