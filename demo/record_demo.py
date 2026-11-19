"""Record a short demo video of Family Music with Playwright.

Usage (server must already be running, ideally on a throwaway DB):
    python demo/record_demo.py http://localhost:8078

Needs:  pip install playwright imageio-ffmpeg   (uses the installed Microsoft Edge)
        python -m playwright install ffmpeg      (small helper Playwright uses to save video)
Output: demo/family-music-demo.mp4  (silent, ~42s)
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8078"
OUT = Path(__file__).parent / "family-music-demo.webm"
INVITE = "family2026"
SIZE = {"width": 1280, "height": 720}

# Demo accounts (made-up usernames)
MAIN_USER = ("jiwoo", "demo-pass-1")
OTHER_USER = ("minho", "demo-pass-2")

# Fake cursor + click ripple + caption (headless recordings show no mouse).
OVERLAY_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style');
  s.textContent = `
    #demo-cursor{position:fixed;z-index:99999;width:18px;height:18px;border-radius:50%;
      background:rgba(255,255,255,.9);border:2px solid #ff5577;pointer-events:none;
      transform:translate(-50%,-50%);left:-50px;top:-50px;box-shadow:0 2px 10px rgba(0,0,0,.5)}
    .demo-ripple{position:fixed;z-index:99998;width:16px;height:16px;border-radius:50%;
      border:3px solid #ff5577;pointer-events:none;transform:translate(-50%,-50%);
      animation:demo-r .45s ease-out forwards}
    @keyframes demo-r{to{width:56px;height:56px;opacity:0}}
    #demo-caption{position:fixed;z-index:99997;left:50%;bottom:112px;transform:translateX(-50%);
      background:rgba(15,13,18,.9);color:#fff;font:600 17px 'Plus Jakarta Sans',system-ui,sans-serif;
      padding:10px 20px;border-radius:999px;border:1px solid rgba(255,85,119,.6);white-space:nowrap;
      box-shadow:0 8px 30px rgba(0,0,0,.4);pointer-events:none;transition:opacity .25s;opacity:0}`;
  document.head.append(s);
  const c = document.createElement('div'); c.id = 'demo-cursor'; document.body.append(c);
  const cap = document.createElement('div'); cap.id = 'demo-caption'; document.body.append(cap);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = 'demo-ripple';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.body.append(r); setTimeout(() => r.remove(), 500);
  }, true);
});
"""


# ---------- API helpers (off-camera setup) ----------

def api(path: str, body=None, token=None, method=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method or ("POST" if body is not None else "GET"),
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r) if r.status != 204 else None


def register(username: str, password: str) -> str:
    try:
        return api("/auth/register", {"username": username, "password": password, "invite_code": INVITE})["token"]
    except urllib.error.HTTPError:
        return api("/auth/login", {"username": username, "password": password})["token"]


def seed_playlist(token: str, name: str, visibility: str, picks: list[tuple[str, str]]) -> None:
    pl = api("/playlists", {"name": name, "visibility": visibility}, token)
    for query, title in picks:
        results = api(f"/search?q={urllib.parse.quote(query)}", token=token)
        song = next(s for s in results if title.lower() in s["title"].lower())
        api(f"/playlists/{pl['id']}/songs", song, token)


# ---------- on-camera helpers ----------

def caption(page: Page, text: str, hold: int = 1100) -> None:
    page.evaluate(
        "t => { const c = document.getElementById('demo-caption'); if (!c) return;"
        " c.textContent = t; c.style.opacity = t ? 1 : 0; }",
        text,
    )
    page.wait_for_timeout(hold)


def click(page: Page, selector: str, pause: int = 350) -> None:
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=8)
    page.wait_for_timeout(120)
    loc.click()
    page.wait_for_timeout(pause)


def type_into(page: Page, selector: str, text: str) -> None:
    click(page, selector, pause=80)
    page.locator(selector).first.press_sequentially(text, delay=40)


def search(page: Page, query: str) -> None:
    page.locator("#top-search input").fill("")
    type_into(page, "#top-search input", query)
    page.keyboard.press("Enter")
    page.wait_for_selector(".tracks .track")
    page.wait_for_timeout(600)


def add(page: Page, title: str, playlist: str) -> None:
    """Add the search result whose title contains `title` to `playlist`."""
    rows = page.locator(".tracks .track")
    for i in range(rows.count()):
        if title.lower() in rows.nth(i).locator(".t-title").inner_text().lower():
            rows.nth(i).scroll_into_view_if_needed()
            click(page, f".tracks .track >> nth={i} >> .add-btn", pause=300)
            click(page, f'#menu button:has-text("{playlist}")', pause=550)
            return
    raise RuntimeError(f"'{title}' not in results")


def new_playlist(page: Page, opener: str, name: str, visibility: str) -> None:
    click(page, opener, pause=300)
    type_into(page, "#pl-form input[name=name]", name)
    click(page, f".vis-pick label:has(input[value={visibility}])", pause=250)
    click(page, "#pl-form button[type=submit]", pause=700)


def login(page: Page, user: tuple[str, str]) -> None:
    click(page, ".seg-btn[data-mode=login]", pause=150)
    type_into(page, "#auth-form input[name=username]", user[0])
    type_into(page, "#auth-form input[name=password]", user[1])
    click(page, "#auth-submit", pause=600)


# ---------- the demo ----------

def main() -> None:
    # Off camera: another family member with one public and one private playlist.
    t = register(*OTHER_USER)
    seed_playlist(t, "Gym", "public", [("TXT", "Sugar Rush Ride"), ("Red Velvet", "Bad Boy"), ("IOI", "Whatta Man")])
    seed_playlist(t, "Sleep", "private", [("IOI", "Downpour")])

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(
            viewport=SIZE, color_scheme="dark",
            record_video_dir=str(OUT.parent / "_raw"), record_video_size=SIZE,
        )
        ctx.add_init_script(OVERLAY_JS)
        page = ctx.new_page()
        page.goto(BASE)
        page.wait_for_selector("#auth-view:not(.hidden)")
        page.wait_for_timeout(500)

        # 1. Sign up
        caption(page, "Sign up with the family invite code", hold=700)
        click(page, ".seg-btn[data-mode=register]", pause=150)
        type_into(page, "#auth-form input[name=username]", MAIN_USER[0])
        type_into(page, "#auth-form input[name=password]", MAIN_USER[1])
        type_into(page, "#auth-form input[name=invite_code]", INVITE)
        click(page, "#auth-submit", pause=0)
        page.wait_for_selector(".greet")
        caption(page, "Family members' public playlists show up on Home", hold=1300)

        # 2. Three playlists
        caption(page, "Make some playlists: public or private", hold=500)
        new_playlist(page, "#card-new", "Road Trip", "public")
        new_playlist(page, "#side-new", "Study", "public")
        new_playlist(page, "#side-new", "Late Night", "private")

        # 3. Search artists and add songs
        caption(page, "Search an artist and add songs", hold=400)
        search(page, "TXT")
        add(page, "Sugar Rush Ride", "Road Trip")
        add(page, "Deja Vu", "Road Trip")
        add(page, "Blue Hour", "Study")
        add(page, "Love Language", "Late Night")

        search(page, "IOI")
        add(page, "Very Very Very", "Road Trip")
        add(page, "Downpour", "Study")

        search(page, "Red Velvet")
        add(page, "Psycho", "Late Night")
        add(page, "Ice Cream Cake", "Study")
        caption(page, "", hold=100)

        # 4. Home grid + playback
        click(page, ".nav-item[data-nav=home]", pause=1000)
        click(page, '.card:has-text("Road Trip")', pause=500)
        caption(page, "Play 30-second previews from Apple", hold=200)
        click(page, "#play-all", pause=2500)
        click(page, "#p-next", pause=1800)
        click(page, '#my-playlists li:has-text("Late Night")', pause=300)
        caption(page, "Private playlists are only visible to you", hold=1500)
        click(page, "#p-play", pause=100)  # pause audio

        # 5. Another family member's view
        caption(page, "Log in as another family member…", hold=300)
        click(page, "#logout", pause=400)
        login(page, OTHER_USER)
        page.wait_for_selector(".greet")
        page.mouse.move(640, 600, steps=8)
        caption(page, "minho sees Road Trip and Study, but not Late Night", hold=2400)

        video = page.video
        ctx.close()
        video.save_as(OUT)
        video.delete()
        browser.close()

    # Skip the idle page-load lead-in (~6s raw), speed up 1.25x, and convert to a
    # silent H.264 MP4 (needs: pip install imageio-ffmpeg).
    import subprocess

    import imageio_ffmpeg

    mp4 = OUT.with_suffix(".mp4")
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", "6", "-i", str(OUT),
         "-vf", "setpts=PTS/1.25", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
        check=True,
    )
    OUT.unlink()
    print(f"Saved {mp4}")


if __name__ == "__main__":
    main()
