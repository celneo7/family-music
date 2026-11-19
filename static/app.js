// Family Music frontend — plain JS, no build step.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  token: localStorage.getItem("token"),
  username: localStorage.getItem("username"),
  playlists: [],
  route: { name: "home" },
  queue: [],       // songs in play order
  qIndex: -1,      // index of current song in queue
};

// ---------- icons ----------

const ICON_PATHS = {
  home: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
  search: "M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
  plus: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  play: "M8 5v14l11-7z",
  pause: "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
  next: "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
  prev: "M6 6h2v12H6zm3.5 6l8.5 6V6z",
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
  external: "M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z",
  logout: "M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z",
  more: "M12 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm0 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  close: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  note: "M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z",
  lock: "M18 8h-1V6A5 5 0 0 0 7 6v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2zm-6 9a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm3.1-9H8.9V6a3.1 3.1 0 0 1 6.2 0v2z",
  globe: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 17.93A8 8 0 0 1 4.21 10.21L9 15v1a2 2 0 0 0 2 2v1.93zm6.9-2.54A2 2 0 0 0 16 16h-1v-3a1 1 0 0 0-1-1H8v-2h2a1 1 0 0 0 1-1V7h2a2 2 0 0 0 2-2v-.41a8 8 0 0 1 2.9 12.8z",
  shuffle: "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
  edit: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
  trash: "M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${ICON_PATHS[name]}"/></svg>`;
function paintIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
}

// ---------- helpers ----------

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("show"), 2400);
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && state.token) { logout(); throw new Error("Session expired, please log in"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => e.msg).join(", ") : d || "Something went wrong");
  }
  return data;
}

// Cover art: 4-image mosaic, single image, or a coloured placeholder.
function coverHtml(covers = [], seed = 0, cls = "cover") {
  if (covers.length >= 4) {
    return `<div class="${cls} mosaic">${covers.slice(0, 4).map((c) => `<img src="${esc(c)}" alt="" loading="lazy">`).join("")}</div>`;
  }
  if (covers.length) return `<div class="${cls}"><img src="${esc(covers[0])}" alt="" loading="lazy"></div>`;
  const hue = (seed * 67) % 360;
  return `<div class="${cls} placeholder" style="background:linear-gradient(135deg,hsl(${hue} 70% 55%),hsl(${(hue + 50) % 360} 75% 45%))">${icon("note")}</div>`;
}

const fmt = (sec) => {
  sec = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

// ---------- routing (#/home, #/search/<q>, #/playlist/<id>) ----------

function parseHash() {
  const [, name, arg] = location.hash.split("/");
  if (name === "playlist" && arg) return { name, id: Number(arg) };
  if (name === "search") return { name, q: decodeURIComponent(arg || "") };
  return { name: "home" };
}
const go = (hash) => { if (location.hash === hash) render(); else location.hash = hash; };
window.addEventListener("hashchange", () => state.token && render());

async function render() {
  closeMenu();
  state.route = parseHash();
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.nav === state.route.name));
  renderSidebar();
  $(".main").scrollTop = 0;
  $("#view").onclick = null;
  if (state.route.name === "playlist") return renderPlaylist(state.route.id);
  if (state.route.name === "search") return renderSearch(state.route.q);
  return renderHome();
}

// ---------- auth ----------

let authMode = "login";
$$(".seg-btn").forEach((btn) =>
  btn.addEventListener("click", () => {
    authMode = btn.dataset.mode;
    $$(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
    $("#invite-field").classList.toggle("hidden", authMode !== "register");
    $("#auth-form").invite_code.required = authMode === "register";
    $("#auth-submit").textContent = authMode === "login" ? "Log in" : "Create account";
    $("#auth-error").textContent = "";
  }));

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = { username: f.username.value, password: f.password.value };
  if (authMode === "register") body.invite_code = f.invite_code.value;
  try {
    const data = await api(`/auth/${authMode}`, { method: "POST", body });
    state.token = data.token;
    state.username = data.username;
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
    f.reset();
    showApp();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

function logout() {
  state.token = null;
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  audio.pause();
  state.queue = [];
  $("#player").classList.add("hidden");
  $("#app-view").classList.add("hidden");
  $("#auth-view").classList.remove("hidden");
}
$("#logout").addEventListener("click", logout);

async function showApp() {
  $("#auth-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#whoami").textContent = state.username;
  $("#avatar").textContent = (state.username || "?")[0].toUpperCase();
  await loadPlaylists();
  render();
}

// ---------- data ----------

async function loadPlaylists() {
  state.playlists = await api("/playlists");
}
const myPlaylists = () => state.playlists.filter((p) => p.is_mine);
const familyPlaylists = () => state.playlists.filter((p) => !p.is_mine);

// ---------- sidebar ----------

function renderSidebar() {
  const current = state.route.name === "playlist" ? state.route.id : null;
  const row = (p, sub) => `
    <li data-id="${p.id}" class="${p.id === current ? "active" : ""}">
      ${coverHtml(p.covers, p.id, "cover mini")}
      <div style="min-width:0">
        <div class="pl-name">${esc(p.name)}</div>
        <div class="pl-sub">${sub}</div>
      </div>
    </li>`;
  $("#my-playlists").innerHTML = myPlaylists()
    .map((p) => row(p, `${p.visibility === "private" ? "Private" : "Public"} · ${p.song_count} songs`)).join("")
    || `<li class="empty">No playlists yet</li>`;
  $("#family-playlists").innerHTML = familyPlaylists()
    .map((p) => row(p, `by ${esc(p.owner)}`)).join("")
    || `<li class="empty">Nothing shared yet</li>`;
}

$$(".pl-list").forEach((ul) =>
  ul.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-id]");
    if (li) go(`#/playlist/${li.dataset.id}`);
  }));
$$(".nav-item").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.nav === "search") { $("#top-search input").focus(); go(`#/search/${encodeURIComponent($("#top-search").q.value.trim())}`); }
  else go("#/home");
}));
$("#side-new").addEventListener("click", () => createPlaylist());

$("#top-search").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = e.target.q.value.trim();
  if (q) go(`#/search/${encodeURIComponent(q)}`);
});

// ---------- playlist dialog ----------

function playlistDialog({ title, name = "", visibility = "private" }) {
  const dlg = $("#pl-dialog");
  const form = $("#pl-form");
  $("#pl-dialog-title").textContent = title;
  form.name.value = name;
  form.visibility.value = visibility;
  dlg.showModal();
  form.name.focus();
  return new Promise((resolve) => {
    const done = (val) => {
      form.removeEventListener("submit", onSubmit);
      $("#pl-cancel").removeEventListener("click", onCancel);
      dlg.removeEventListener("cancel", onCancel);
      dlg.close();
      resolve(val);
    };
    const onSubmit = (e) => { e.preventDefault(); done({ name: form.name.value.trim(), visibility: form.visibility.value }); };
    const onCancel = (e) => { e.preventDefault(); done(null); };
    form.addEventListener("submit", onSubmit);
    $("#pl-cancel").addEventListener("click", onCancel);
    dlg.addEventListener("cancel", onCancel);
  });
}

async function createPlaylist({ openAfter = true } = {}) {
  const vals = await playlistDialog({ title: "New playlist" });
  if (!vals || !vals.name) return null;
  try {
    const pl = await api("/playlists", { method: "POST", body: vals });
    await loadPlaylists();
    toast(`Created “${pl.name}”`);
    if (openAfter) go(`#/playlist/${pl.id}`); else renderSidebar();
    return pl;
  } catch (err) { toast(err.message); return null; }
}

// ---------- popover menu ----------

function openMenu(anchor, html, onPick) {
  const menu = $("#menu");
  menu.innerHTML = html;
  menu.classList.remove("hidden");
  const r = anchor.getBoundingClientRect();
  const mw = menu.offsetWidth, mh = menu.offsetHeight;
  menu.style.left = `${Math.max(8, Math.min(r.right - mw, innerWidth - mw - 8))}px`;
  menu.style.top = `${r.bottom + mh + 8 > innerHeight ? r.top - mh - 6 : r.bottom + 6}px`;
  menu.onclick = (e) => {
    const b = e.target.closest("button[data-pick]");
    if (!b) return;
    closeMenu();
    onPick(b.dataset.pick);
  };
}
function closeMenu() { $("#menu").classList.add("hidden"); }
document.addEventListener("click", (e) => {
  if (!e.target.closest("#menu") && !e.target.closest("[data-menu]")) closeMenu();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

function addToPlaylistMenu(anchor, song) {
  const items = myPlaylists().map((p) =>
    `<button type="button" data-pick="${p.id}">${coverHtml(p.covers, p.id, "cover mini")}<span>${esc(p.name)}</span></button>`).join("");
  openMenu(anchor,
    `<div class="menu-label">Add to playlist</div>${items}
     <button type="button" data-pick="new">${icon("plus")}<span>New playlist…</span></button>`,
    async (pick) => {
      let id = pick;
      if (pick === "new") {
        const pl = await createPlaylist({ openAfter: false });
        if (!pl) return;
        id = pl.id;
      }
      try {
        await api(`/playlists/${id}/songs`, { method: "POST", body: song });
        await loadPlaylists();
        renderSidebar();
        const pl = state.playlists.find((p) => p.id === Number(id));
        toast(`Added to ${pl ? pl.name : "playlist"}`);
      } catch (err) { toast(err.message); }
    });
}

// ---------- track rows ----------

function trackRow(song, i, actions) {
  const playing = isCurrent(song);
  return `
    <li class="track ${song.preview_url ? "" : "no-preview"} ${playing ? "playing" : ""}" data-idx="${i}" data-itunes="${song.itunes_id}">
      <div class="num">
        <span class="n">${i + 1}</span>
        <span class="eq"><i></i><i></i><i></i></span>
        ${song.preview_url ? `<span class="play-ico"><button type="button" data-act="play" title="Play">${icon("play")}</button></span>` : ""}
      </div>
      <img class="art" src="${esc(song.artwork_url || "")}" alt="" loading="lazy">
      <div style="min-width:0">
        <div class="t-title">${esc(song.title)}</div>
        <div class="t-artist">${esc(song.artist)}</div>
      </div>
      <div class="t-album">${esc(song.album || "")}</div>
      <div class="t-actions">${actions}</div>
    </li>`;
}

// ---------- home ----------

function playlistCard(p) {
  return `
    <div class="card" data-id="${p.id}">
      <div class="cover-wrap">
        ${coverHtml(p.covers, p.id)}
        ${p.song_count ? `<button type="button" class="play-btn sm hover-play" data-play="${p.id}" title="Play">${icon("play")}</button>` : ""}
      </div>
      <div class="card-title">${esc(p.name)}</div>
      <div class="card-sub">${p.is_mine ? (p.visibility === "private" ? "Private" : "Public") : `by ${esc(p.owner)}`} · ${p.song_count} song${p.song_count === 1 ? "" : "s"}</div>
    </div>`;
}

function renderHome() {
  const fam = familyPlaylists();
  $("#view").innerHTML = `
    <div class="greet">${greeting()}, ${esc(state.username)}</div>
    <div class="muted">Here's what the family is listening to.</div>

    <div class="section-title">Your playlists</div>
    <div class="grid">
      ${myPlaylists().map(playlistCard).join("")}
      <div class="card new" id="card-new">
        <div class="cover">${icon("plus")}</div>
        <div class="card-title">New playlist</div>
        <div class="card-sub">Start a new mix</div>
      </div>
    </div>

    <div class="section-title">From the family</div>
    ${fam.length ? `<div class="grid">${fam.map(playlistCard).join("")}</div>`
      : `<div class="empty-note">No public playlists from the family yet. Make one of yours public to share it!</div>`}`;

  $("#card-new").addEventListener("click", () => createPlaylist());
  $("#view").onclick = async (e) => {
    const playBtn = e.target.closest("[data-play]");
    if (playBtn) {
      e.stopPropagation();
      const pl = await api(`/playlists/${playBtn.dataset.play}`).catch((err) => toast(err.message));
      if (pl) playSongs(pl.songs, 0);
      return;
    }
    const card = e.target.closest(".card[data-id]");
    if (card) go(`#/playlist/${card.dataset.id}`);
  };
}

// ---------- search ----------

async function renderSearch(q) {
  $("#top-search").q.value = q;
  if (!q) {
    $("#view").innerHTML = `<div class="search-head"><h2>Search</h2></div>
      <div class="empty-note">Search for any song or artist. You'll get 30-second previews from Apple, and full songs are one click away on Apple Music.</div>`;
    $("#top-search input").focus();
    return;
  }
  $("#view").innerHTML = `<div class="search-head"><h2>Results for “${esc(q)}”</h2></div>
    ${'<div class="skel"></div>'.repeat(6)}`;

  let results;
  try { results = await api(`/search?q=${encodeURIComponent(q)}`); }
  catch (err) {
    $("#view").innerHTML = `<div class="search-head"><h2>Search</h2></div><div class="empty-note">${esc(err.message)}</div>`;
    return;
  }
  if (state.route.name !== "search" || state.route.q !== q) return; // user moved on

  $("#view").innerHTML = `
    <div class="search-head"><h2>Results for “${esc(q)}”</h2><span class="muted small">${results.length} songs</span></div>
    ${results.length ? `<ul class="tracks">${results.map((s, i) => trackRow(s, i,
      `<button type="button" class="add-btn" data-act="add" data-menu>${icon("plus")}Add</button>`)).join("")}</ul>`
      : `<div class="empty-note">No songs found. Try a different spelling?</div>`}`;

  $(".tracks")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const idx = Number(btn.closest(".track").dataset.idx);
    if (btn.dataset.act === "play") playSongs(results, idx);
    if (btn.dataset.act === "add") addToPlaylistMenu(btn, results[idx]);
  });
}

// ---------- playlist ----------

async function renderPlaylist(id) {
  let pl;
  try { pl = await api(`/playlists/${id}`); }
  catch (err) {
    $("#view").innerHTML = `<div class="empty-note" style="margin-top:24px">${esc(err.message)}</div>`;
    return;
  }
  if (state.route.name !== "playlist" || state.route.id !== id) return;

  const covers = pl.songs.map((s) => s.artwork_url).filter(Boolean).slice(0, 4);
  const playable = pl.songs.filter((s) => s.preview_url).length;

  $("#view").innerHTML = `
    <section class="hero">
      <div class="hero-bg" style="${covers[0] ? `background-image:url('${esc(covers[0])}')` : `background:hsl(${(id * 67) % 360} 70% 50%)`}"></div>
      ${coverHtml(covers, id)}
      <div style="min-width:0">
        <div class="hero-kicker">${pl.visibility === "public" ? "Public playlist" : "Private playlist"}</div>
        <h1>${esc(pl.name)}</h1>
        <div class="hero-meta">
          <span class="avatar">${esc(pl.owner[0].toUpperCase())}</span>
          <b>${pl.is_mine ? "You" : esc(pl.owner)}</b> · ${pl.songs.length} song${pl.songs.length === 1 ? "" : "s"}
          ${playable ? `· about ${Math.ceil(playable * 0.5)} min of previews` : ""}
        </div>
      </div>
    </section>

    <div class="actions-bar">
      <button type="button" class="play-btn" id="play-all" title="Play" ${playable ? "" : "disabled"}>${icon("play")}</button>
      <button type="button" class="icon-btn" id="shuffle" title="Shuffle" ${playable ? "" : "disabled"}>${icon("shuffle")}</button>
      ${pl.is_mine ? `
        <button type="button" class="btn" id="toggle-vis">${icon(pl.visibility === "public" ? "lock" : "globe")}
          Make ${pl.visibility === "public" ? "private" : "public"}</button>
        <button type="button" class="icon-btn" id="pl-more" title="More" data-menu>${icon("more")}</button>` : ""}
    </div>

    ${pl.songs.length ? `<ul class="tracks">${pl.songs.map((s, i) => trackRow(s, i,
      pl.is_mine ? `<button type="button" class="icon-btn sm" data-act="remove" title="Remove from playlist">${icon("close")}</button>` : "")).join("")}</ul>`
      : `<div class="empty-note">${pl.is_mine ? "This playlist is empty. Use the search bar above to find songs and hit “Add”." : "No songs here yet."}</div>`}`;

  $("#play-all").addEventListener("click", () => playSongs(pl.songs, 0));
  $("#shuffle").addEventListener("click", () => {
    const s = [...pl.songs].sort(() => Math.random() - 0.5);
    playSongs(s, 0);
  });

  $(".tracks")?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const idx = Number(btn.closest(".track").dataset.idx);
    if (btn.dataset.act === "play") return playSongs(pl.songs, idx);
    if (btn.dataset.act === "remove") {
      try {
        await api(`/playlists/${id}/songs/${pl.songs[idx].id}`, { method: "DELETE" });
        await loadPlaylists();
        toast(`Removed “${pl.songs[idx].title}”`);
        render();
      } catch (err) { toast(err.message); }
    }
  });

  if (!pl.is_mine) return;

  $("#toggle-vis").addEventListener("click", async () => {
    const visibility = pl.visibility === "public" ? "private" : "public";
    try {
      await api(`/playlists/${id}`, { method: "PATCH", body: { visibility } });
      await loadPlaylists();
      toast(visibility === "public" ? "Now visible to the family" : "Now private to you");
      render();
    } catch (err) { toast(err.message); }
  });

  $("#pl-more").addEventListener("click", (e) => {
    openMenu(e.currentTarget,
      `<button type="button" data-pick="edit">${icon("edit")}<span>Edit details</span></button>
       <button type="button" data-pick="delete">${icon("trash")}<span>Delete playlist</span></button>`,
      async (pick) => {
        if (pick === "edit") {
          const vals = await playlistDialog({ title: "Edit playlist", name: pl.name, visibility: pl.visibility });
          if (!vals || !vals.name) return;
          try {
            await api(`/playlists/${id}`, { method: "PATCH", body: vals });
            await loadPlaylists();
            render();
          } catch (err) { toast(err.message); }
        }
        if (pick === "delete") {
          if (!confirm(`Delete “${pl.name}”? This can't be undone.`)) return;
          try {
            await api(`/playlists/${id}`, { method: "DELETE" });
            await loadPlaylists();
            toast("Playlist deleted");
            go("#/home");
          } catch (err) { toast(err.message); }
        }
      });
  });
}

// ---------- player ----------

const audio = $("#audio");
const seek = $("#seek");
audio.volume = Number(localStorage.getItem("volume") ?? 0.8);
$("#volume").value = audio.volume;

const currentSong = () => state.queue[state.qIndex];
const isCurrent = (song) => currentSong() && currentSong().itunes_id === song.itunes_id;

function playSongs(songs, startIdx = 0) {
  const start = songs[startIdx];
  state.queue = songs.filter((s) => s.preview_url);
  if (!state.queue.length) { toast("No previews available"); return; }
  state.qIndex = Math.max(0, state.queue.indexOf(start));
  loadCurrent();
}

function loadCurrent() {
  const song = currentSong();
  if (!song) return;
  $("#player").classList.remove("hidden");
  $("#app-view").classList.add("playing");
  $("#np-art").src = song.artwork_url || "";
  $("#np-title").textContent = song.title;
  $("#np-artist").textContent = song.artist;
  $("#np-apple").href = song.track_url || "https://music.apple.com";
  audio.src = song.preview_url;
  audio.play().catch(() => {});
  markPlayingRows();
}

function markPlayingRows() {
  const song = currentSong();
  $$(".track").forEach((li) => {
    li.classList.toggle("playing", !!song && Number(li.dataset.itunes) === song.itunes_id);
  });
  document.body.classList.toggle("paused", audio.paused);
}

function step(dir) {
  if (dir < 0 && audio.currentTime > 3) { audio.currentTime = 0; return; }
  const next = state.qIndex + dir;
  if (next < 0 || next >= state.queue.length) { if (dir > 0) audio.pause(); return; }
  state.qIndex = next;
  loadCurrent();
}

$("#p-play").addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
$("#p-next").addEventListener("click", () => step(1));
$("#p-prev").addEventListener("click", () => step(-1));
audio.addEventListener("ended", () => step(1));
audio.addEventListener("play", () => { $("#p-play").innerHTML = icon("pause"); markPlayingRows(); });
audio.addEventListener("pause", () => { $("#p-play").innerHTML = icon("play"); markPlayingRows(); });
audio.addEventListener("loadedmetadata", () => { seek.max = audio.duration || 30; });
audio.addEventListener("timeupdate", () => {
  if (seek.dataset.dragging) return;
  seek.value = audio.currentTime;
  seek.style.setProperty("--pct", `${(audio.currentTime / (audio.duration || 30)) * 100}%`);
  $("#p-time").textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration || 30)}`;
});
seek.addEventListener("input", () => {
  seek.dataset.dragging = "1";
  seek.style.setProperty("--pct", `${(seek.value / seek.max) * 100}%`);
});
seek.addEventListener("change", () => { audio.currentTime = Number(seek.value); delete seek.dataset.dragging; });
$("#volume").addEventListener("input", (e) => {
  audio.volume = Number(e.target.value);
  try { localStorage.setItem("volume", e.target.value); } catch {}
});
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || e.target.closest("input, textarea, button, dialog") || !currentSong()) return;
  e.preventDefault();
  audio.paused ? audio.play() : audio.pause();
});

// ---------- start ----------

paintIcons();
if (state.token) {
  api("/me").then(showApp).catch(logout);
} else {
  $("#auth-view").classList.remove("hidden");
}
