"""Record the Family Music demo video with Playwright.

Two browsers are recorded at the same time (one per family member), then
stitched with ffmpeg:
  Part 1 (full screen): jiwoo signs up, builds playlists, plays music.
  Part 2 (split screen): jiwoo starts "Listen together", minho joins, and
                         both screens stay in sync.

Usage (server must already be running, ideally on a throwaway DB):
    python demo/record_demo.py http://localhost:8078

Needs:  pip install playwright imageio-ffmpeg   (uses the installed Microsoft Edge)
        python -m playwright install ffmpeg      (small helper Playwright uses to save video)
Output: demo/family-music-demo.mp4  (silent)
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8078"
DEMO_DIR = Path(__file__).parent
RAW = DEMO_DIR / "_raw"
OUT = DEMO_DIR / "family-music-demo.mp4"
INVITE = "family2026"
SIZE = {"width": 1280, "height": 960}
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"

# Demo accounts (made-up usernames)
MAIN_USER = ("jiwoo", "demo-pass-1")
OTHER_USER = ("minho", "demo-pass-2")

# Fake cursor + click ripple + caption (headless recordings show no mouse).
OVERLAY_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style');
  s.textContent = `
    #demo-cursor{position:fixed;z-index:99999;width:20px;height:20px;border-radius:50%;
      background:rgba(255,255,255,.9);border:2px solid #ff5577;pointer-events:none;
      transform:translate(-50%,-50%);left:-50px;top:-50px;box-shadow:0 2px 10px rgba(0,0,0,.5)}
    .demo-ripple{position:fixed;z-index:99998;width:16px;height:16px;border-radius:50%;
      border:3px solid #ff5577;pointer-events:none;transform:translate(-50%,-50%);
      animation:demo-r .45s ease-out forwards}
    @keyframes demo-r{to{width:60px;height:60px;opacity:0}}
    #demo-caption{position:fixed;z-index:99997;left:50%;bottom:112px;transform:translateX(-50%);
      background:rgba(15,13,18,.9);color:#fff;font:600 19px 'Plus Jakarta Sans',system-ui,sans-serif;
      padding:11px 22px;border-radius:999px;border:1px solid rgba(255,85,119,.6);white-space:nowrap;
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

def api(path: str, body=None, token=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


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


def both(a: Page, b: Page, ms: int) -> None:
    """Let time pass (both pages keep running in the background)."""
    a.wait_for_timeout(ms)


# ---------- the demo ----------

def record() -> dict:
    """Run the demo in two browsers. Returns timing marks (seconds since jiwoo's video began)."""
    t = register(*OTHER_USER)
    seed_playlist(t, "Gym", "public", [("TXT", "Blue Hour"), ("Red Velvet", "Ice Cream Cake")])

    RAW.mkdir(exist_ok=True)
    for f in RAW.glob("*.webm"):
        f.unlink()

    marks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        def context():
            ctx = browser.new_context(viewport=SIZE, color_scheme="dark",
                                      record_video_dir=str(RAW), record_video_size=SIZE)
            ctx.add_init_script(OVERLAY_JS)
            return ctx

        ctx_a, ctx_b = context(), context()
        A = ctx_a.new_page(); t_a0 = time.time()
        B = ctx_b.new_page(); t_b0 = time.time()
        mark = lambda name: marks.__setitem__(name, time.time() - t_a0)
        marks["b_offset"] = t_b0 - t_a0

        # minho is already logged in on his own laptop (off to the side for now)
        B.goto(BASE)
        B.evaluate("([t,u]) => { localStorage.setItem('token', t); localStorage.setItem('username', u); }",
                   [t, OTHER_USER[0]])
        B.reload()
        B.wait_for_selector(".greet")

        A.goto(BASE)
        A.wait_for_selector("#auth-view:not(.hidden)")
        A.wait_for_timeout(300)

        # ===== Part 1: jiwoo, full screen =====
        mark("start")
        caption(A, "Sign up with the family invite code", hold=500)
        click(A, ".seg-btn[data-mode=register]", pause=150)
        type_into(A, "#auth-form input[name=username]", MAIN_USER[0])
        type_into(A, "#auth-form input[name=password]", MAIN_USER[1])
        type_into(A, "#auth-form input[name=invite_code]", INVITE)
        click(A, "#auth-submit", pause=0)
        A.wait_for_selector(".greet")
        caption(A, "Make playlists: public for the family, or private", hold=500)
        new_playlist(A, "#card-new", "Road Trip", "public")
        new_playlist(A, "#side-new", "Late Night", "private")

        caption(A, "Search an artist, add songs", hold=300)
        search(A, "TXT")
        add(A, "Sugar Rush Ride", "Road Trip")
        add(A, "Deja Vu", "Late Night")
        search(A, "IOI")
        add(A, "Very Very Very", "Road Trip")
        search(A, "Red Velvet")
        add(A, "Psycho", "Road Trip")
        add(A, "Bad Boy", "Late Night")
        caption(A, "", hold=100)

        click(A, '#my-playlists li:has-text("Road Trip")', pause=500)
        caption(A, "Play 30-second previews from Apple", hold=200)
        click(A, "#play-all", pause=2600)
        click(A, "#p-next", pause=2000)
        click(A, "#p-play", pause=300)  # pause
        caption(A, "", hold=200)

        # ===== Part 2: split screen =====
        mark("split")
        both(A, B, 900)
        mark("cap_start")
        click(A, "#together", pause=1800)
        mark("cap_join")
        click(B, ".nav-item[data-nav=home]", pause=700)
        B.wait_for_selector(".live-card")
        B.wait_for_timeout(500)
        click(B, "[data-join]", pause=600)
        mark("cap_sync")
        both(A, B, 3800)
        mark("cap_skip")
        click(B, "#p-next", pause=3000)
        mark("cap_pause")
        click(A, "#p-play", pause=2200)
        mark("cap_resume")
        click(B, "#p-play", pause=2800)
        mark("end")

        va, vb = A.video, B.video
        ctx_a.close(); ctx_b.close()
        marks["a_path"], marks["b_path"] = str(va.path()), str(vb.path())
        browser.close()
    return marks


def stitch(m: dict) -> None:
    """Part 1 = jiwoo full screen. Part 2 = jiwoo | minho side by side with labels and captions."""
    W, H = 1920, 1080
    pw, ph = 920, 690                      # each pane in part 2 (from 1280x960)
    gap = W - 2 * pw - 2 * 30              # space between panes
    x_left, x_right, y_pane = 30, 30 + pw + gap, 170
    s, sp, e, ob = m["start"] - 0.2, m["split"], m["end"], m["b_offset"]

    def text(t, x, y, size, color="white", enable=None):
        t = t.replace("'", "’").replace(":", "\\:").replace(",", "\\,")
        en = f":enable='between(t\\,{enable[0]:.2f}\\,{enable[1]:.2f})'" if enable else ""
        return f"drawtext=fontfile='{FONT}':text='{t}':fontsize={size}:fontcolor={color}:x={x}:y={y}{en}"

    caps = [
        ("Listen together", "cap_start", "cap_join"),
        ("minho sees the party on Home and joins", "cap_join", "cap_sync"),
        ("Same song, same second, on both screens", "cap_sync", "cap_skip"),
        ("minho skips → jiwoo follows", "cap_skip", "cap_pause"),
        ("jiwoo pauses → minho pauses too", "cap_pause", "cap_resume"),
        ("Anyone can control the music", "cap_resume", "end"),
    ]
    cap_filters = ",".join(
        text(t, "(w-text_w)/2", 930, 44, enable=(m[a] - sp, m[b] - sp + (0.6 if b == "end" else 0)))
        for t, a, b in caps
    )
    labels = ",".join([
        text("jiwoo", f"{x_left}+({pw}-text_w)/2", y_pane - 62, 38, "0xff7a8f"),
        text("minho", f"{x_right}+({pw}-text_w)/2", y_pane - 62, 38, "0xff9a5a"),
    ])
    bg = "0x0e0d10"
    graph = (
        f"[0:v]trim={s:.2f}:{sp:.2f},setpts=PTS-STARTPTS,fps=25,"
        f"scale=1440:1080:flags=lanczos,pad={W}:{H}:240:0:color={bg},setpts=PTS/1.45[p1];"
        f"[0:v]trim={sp:.2f}:{e + 0.6:.2f},setpts=PTS-STARTPTS,fps=25,scale={pw}:{ph}:flags=lanczos[a2];"
        f"[1:v]trim={sp - ob:.2f}:{e + 0.6 - ob:.2f},setpts=PTS-STARTPTS,fps=25,scale={pw}:{ph}:flags=lanczos[b2];"
        f"[b2]pad={pw + gap}:{ph}:{gap}:0:color={bg}[b2p];"
        f"[a2][b2p]hstack=inputs=2,pad={W}:{H}:{x_left}:{y_pane}:color={bg},"
        f"drawbox=x={x_left - 3}:y={y_pane - 3}:w={pw + 6}:h={ph + 6}:color=0xff5577@0.5:t=3,"
        f"drawbox=x={x_right - 3}:y={y_pane - 3}:w={pw + 6}:h={ph + 6}:color=0xff9a5a@0.5:t=3,"
        f"{labels},{cap_filters},setpts=PTS/1.2[p2];"
        f"[p1][p2]concat=n=2:v=1:a=0,format=yuv420p[out]"
    )
    script = RAW / "filter.txt"
    script.write_text(graph, encoding="utf-8")
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", m["a_path"], "-i", m["b_path"], "-/filter_complex", str(script),
         "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "22",
         "-movflags", "+faststart", str(OUT)],
        check=True,
    )


if __name__ == "__main__":
    marks = record()
    (RAW / "marks.json").write_text(json.dumps(marks, indent=2))
    stitch(marks)
    print(f"Saved {OUT}")
