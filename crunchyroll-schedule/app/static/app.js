const REFRESH_MS = 5 * 60 * 1000; // auto-refresh every 5 minutes

// migrate old 'view' values (week/shows) -> schedule/shows
let view = localStorage.getItem("view");
if (view !== "schedule" && view !== "shows") view = "schedule";
let range = localStorage.getItem("range") || "daily";
if (!["daily", "weekly", "monthly"].includes(range)) range = "daily";
let anchor = null; // YYYY-MM-DD; null = today (server decides)
let airType = localStorage.getItem("airType") === "dub" ? "dub" : "sub";

let lastSchedule = null;
let lastShows = null;

// ---- favorites (persisted) ----
let favorites = new Set(JSON.parse(localStorage.getItem("favorites") || "[]"));
let search = "";
let favOnly = localStorage.getItem("favonly") === "1";
const isFav = (route) => favorites.has(route);
function toggleFav(route) {
  if (favorites.has(route)) favorites.delete(route); else favorites.add(route);
  localStorage.setItem("favorites", JSON.stringify([...favorites]));
  if (lastShows) renderShows(lastShows);
}
function calendarHref() {
  const p = new URLSearchParams({ air_type: airType });
  const favs = [...favorites];
  if (favs.length) p.set("routes", favs.join(","));
  return `/api/calendar.ics?${p.toString()}`;
}

// ---- loading ----
async function load() {
  applyView();
  return view === "shows" ? loadShows() : loadSchedule();
}

async function fetchWithTimeout(url, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { cache: "no-store", signal: ctrl.signal });
  } finally {
    clearTimeout(t);
  }
}

function errMessage(err) {
  return err && err.name === "AbortError"
    ? "timed out — the server may be waking up (free tier). Tap Retry."
    : err.message;
}

async function loadSchedule() {
  const p = new URLSearchParams({ range, air_type: airType });
  if (anchor) p.set("anchor", anchor);
  setStatus("Loading…");
  if (!lastSchedule) showOverlay("Loading the schedule… (first load can take ~30–50s while the server wakes up)");
  try {
    const res = await fetchWithTimeout(`/api/releases?${p}`, 40000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    lastSchedule = data;
    anchor = data.anchor;
    setStatus("");
    renderSchedule(data);
  } catch (err) {
    setStatus(`Couldn't load schedule (${errMessage(err)})`, true);
    showOverlay(`Couldn't load the schedule (${escapeHtml(errMessage(err))})`, true);
  }
}

async function loadShows() {
  const p = new URLSearchParams({ air_type: airType });
  setStatus("Loading…");
  try {
    const res = await fetchWithTimeout(`/api/schedule?${p}`, 40000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    lastShows = data;
    setStatus("");
    renderShows(data);
  } catch (err) {
    setStatus(`Couldn't load shows (${errMessage(err)})`, true);
    showOverlay(`Couldn't load shows (${escapeHtml(errMessage(err))})`, true);
  }
}

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
  el.hidden = !msg;
}

function showOverlay(msg, withRetry) {
  const retry = withRetry ? ` <button id="retry" class="today-btn">Retry</button>` : "";
  const html = `<div class="empty wide">${escapeHtml(msg)}${retry}</div>`;
  document.getElementById("calendar").innerHTML = html;
  document.getElementById("showlist").innerHTML = html;
  const btn = document.getElementById("retry");
  if (btn) btn.addEventListener("click", () => load());
}

// ---- time helpers ----
function fmtClock(iso, tz) {
  if (!iso) return "TBA";
  return new Date(iso).toLocaleString("en-US", { timeZone: tz, hour: "numeric", minute: "2-digit" });
}
function relative(iso) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const past = diff < 0, s = Math.abs(diff) / 1000;
  const mins = Math.round(s / 60), hrs = Math.round(s / 3600), days = Math.round(s / 86400);
  let txt;
  if (s < 90) return "just now";
  else if (mins < 90) txt = `${mins} min`;
  else if (hrs < 36) txt = `${hrs} hr`;
  else txt = `${days} day${days === 1 ? "" : "s"}`;
  return past ? `${txt} ago` : `in ${txt}`;
}

function badge(conf) {
  if (conf === "jp_fallback")
    return `<span class="badge jp" title="AnimeSchedule fell back to the Japanese broadcast time">JP broadcast time</span>`;
  if (conf === "projected") return `<span class="badge proj">projection</span>`;
  return "";
}
function epNum(ep) {
  return ep.subtracted_episode_number
    ? `${ep.subtracted_episode_number}–${ep.episode_number}`
    : ep.episode_number ?? "?";
}
function watchLink(ep) {
  const url = ep && ep.streams && ep.streams.crunchyroll;
  return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Watch ↗</a>` : "";
}
function coverImg(url, cls) {
  return url
    ? `<img class="${cls}" src="${escapeHtml(url)}" alt="" loading="lazy" />`
    : (cls === "noart" ? `<div class="noart"></div>` : "");
}

// Attach image error fallbacks in JS (no inline handlers, so a strict CSP holds).
function wireImages(container) {
  container.querySelectorAll("img").forEach((img) => {
    img.addEventListener("error", () => {
      if (img.classList.contains("ep-thumb")) { img.remove(); return; }
      const d = document.createElement("div");
      d.className = "noart";
      img.replaceWith(d);
    });
  });
}
function englishLine(ep) {
  return ep.english_title ? `<div class="english">${escapeHtml(ep.english_title)}</div>` : "";
}

// ---- schedule (range) view ----
function epCard(ep, tz) {
  const past = ep.air_at && new Date(ep.air_at).getTime() < Date.now();
  return `<div class="ep ${past ? "past" : "upcoming"}">
    ${coverImg(ep.cover_image_url, "ep-thumb")}
    <div class="meta">
      <div class="title">${escapeHtml(ep.title)}</div>
      ${englishLine(ep)}
      <div>Ep ${epNum(ep)} · <span class="time">${fmtClock(ep.air_at, tz)}</span>
        <span class="rel">(${relative(ep.air_at)})</span></div>
      <div>${badge(ep.confidence)} ${watchLink(ep)}</div>
    </div>
  </div>`;
}

function renderSchedule(data) {
  document.getElementById("range").value = data.range;
  document.getElementById("rangelabel").textContent = data.title;
  document.getElementById("tz").textContent = data.timezone;
  setMeta(data);
  const cal = document.getElementById("calendar");
  const groups = data.groups || [];
  const total = groups.reduce((n, g) => n + g.releases.length, 0);
  if (total === 0) {
    cal.innerHTML = `<div class="empty wide">No Crunchyroll releases for ${escapeHtml(data.title)}.</div>`;
    return;
  }
  cal.innerHTML = groups
    .map((g) => {
      const body = g.releases.length
        ? g.releases.map((e) => epCard(e, data.timezone)).join("")
        : `<div class="empty">No releases</div>`;
      return `<section class="daygroup${g.is_today ? " today" : ""}">
        <h2 class="dayhdr">${escapeHtml(g.label)}</h2>${body}</section>`;
    })
    .join("");
  wireImages(cal);
}

// ---- shows view ----
function showRow(show, tz) {
  const fav = isFav(show.route);
  const star = `<button class="fav ${fav ? "on" : ""}" data-route="${escapeHtml(show.route)}"
    aria-pressed="${fav}" aria-label="${fav ? "Unfavorite" : "Favorite"}" title="${fav ? "Unfavorite" : "Favorite"}">${fav ? "★" : "☆"}</button>`;
  const cover = coverImg(show.cover_image_url, "noart-or-img") || `<div class="noart"></div>`;
  const eng = show.english_title ? `<div class="english">${escapeHtml(show.english_title)}</div>` : "";
  const last = show.last_released
    ? `<div class="slot"><span class="lbl">Last</span> Ep ${epNum(show.last_released)} ·
        <span class="time">${fmtClock(show.last_released.air_at, tz)}</span>
        <span class="rel">(${relative(show.last_released.air_at)})</span></div>`
    : `<div class="slot muted">No released episode this week</div>`;
  const next = show.next_scheduled
    ? `<div class="slot next"><span class="lbl">Next</span> Ep ${epNum(show.next_scheduled)} ·
        <span class="time">${fmtClock(show.next_scheduled.air_at, tz)}</span>
        <span class="rel">(${relative(show.next_scheduled.air_at)})</span> ${badge(show.next_scheduled.confidence)}</div>`
    : `<div class="slot muted">No upcoming episode this week</div>`;
  return `<div class="show">
    ${show.cover_image_url ? coverImg(show.cover_image_url, "") : `<div class="noart"></div>`}
    <div class="info">
      <div class="title">${star} ${escapeHtml(show.title)} ${watchLink(show.next_scheduled || show.last_released || {})}</div>
      ${eng}${last}${next}
    </div>
  </div>`;
}

function renderShows(data) {
  document.getElementById("rangelabel").textContent = "All current shows";
  document.getElementById("tz").textContent = data.timezone;
  setMeta(data);
  let shows = (data.shows || []).slice();
  if (favOnly) shows = shows.filter((s) => isFav(s.route));
  if (search) { const q = search.toLowerCase(); shows = shows.filter((s) =>
    s.title.toLowerCase().includes(q) || (s.english_title || "").toLowerCase().includes(q)); }
  shows.sort((a, b) => {
    const an = a.next_scheduled?.air_at, bn = b.next_scheduled?.air_at;
    if (an && bn) return new Date(an) - new Date(bn);
    if (an) return -1; if (bn) return 1;
    return a.title.localeCompare(b.title);
  });
  const el = document.getElementById("showlist");
  el.innerHTML = shows.length
    ? shows.map((s) => showRow(s, data.timezone)).join("")
    : `<div class="empty wide">No Crunchyroll shows match.</div>`;
  wireImages(el);
}

// shared header meta (banner, freshness, warnings, calendar link)
function setMeta(data) {
  const isSample = (data.freshness || []).some((f) => f.source === "sample");
  document.getElementById("samplebanner").hidden = !isSample;
  const fresh = (data.freshness || [])
    .map((f) => `${f.source} ${f.fetched_at ? relative(f.fetched_at) : "never"}${f.stale ? " (stale)" : ""}`)
    .join(" · ");
  document.getElementById("freshness").textContent = fresh ? `Updated ${fresh}` : "";
  document.getElementById("warnings").innerHTML = (data.warnings || [])
    .map((w) => `⚠ ${escapeHtml(w)}`).join("<br>");
  document.getElementById("callink").href = calendarHref();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- view / control wiring ----
function setTab(id, active) {
  const el = document.getElementById(id);
  el.classList.toggle("active", active);
  el.setAttribute("aria-selected", active ? "true" : "false");
}
function applyView() {
  const sched = view === "schedule";
  document.getElementById("calendar").hidden = !sched;
  document.getElementById("showlist").hidden = sched;
  document.getElementById("showcontrols").hidden = sched;
  // range + week nav only apply to the schedule view
  document.getElementById("range").hidden = !sched;
  document.getElementById("prev").hidden = !sched;
  document.getElementById("next").hidden = !sched;
  setTab("view-schedule", sched);
  setTab("view-shows", !sched);
  setTab("at-sub", airType === "sub");
  setTab("at-dub", airType === "dub");
}

function setView(v) {
  view = v; localStorage.setItem("view", v);
  if (v === "shows" && !lastShows) { load(); return; }
  if (v === "schedule" && !lastSchedule) { load(); return; }
  applyView();
  if (v === "shows") renderShows(lastShows); else renderSchedule(lastSchedule);
}
function setAirType(t) { airType = t; localStorage.setItem("airType", t); anchor = anchor; load(); }

document.getElementById("range").addEventListener("change", (e) => {
  range = e.target.value; localStorage.setItem("range", range);
  anchor = null; // reset to today when changing range
  loadSchedule();
});
document.getElementById("prev").addEventListener("click", () => {
  if (lastSchedule) { anchor = lastSchedule.prev_anchor; loadSchedule(); }
});
document.getElementById("next").addEventListener("click", () => {
  if (lastSchedule) { anchor = lastSchedule.next_anchor; loadSchedule(); }
});
document.getElementById("view-schedule").addEventListener("click", () => setView("schedule"));
document.getElementById("view-shows").addEventListener("click", () => setView("shows"));
document.getElementById("at-sub").addEventListener("click", () => setAirType("sub"));
document.getElementById("at-dub").addEventListener("click", () => setAirType("dub"));

document.getElementById("search").addEventListener("input", (e) => {
  search = e.target.value.trim(); if (lastShows) renderShows(lastShows);
});
const favOnlyEl = document.getElementById("favonly");
favOnlyEl.checked = favOnly;
favOnlyEl.addEventListener("change", (e) => {
  favOnly = e.target.checked; localStorage.setItem("favonly", favOnly ? "1" : "0");
  if (lastShows) renderShows(lastShows);
});
document.getElementById("showlist").addEventListener("click", (e) => {
  const btn = e.target.closest(".fav"); if (btn) toggleFav(btn.dataset.route);
});

// re-render relative times each minute (no refetch); auto-refresh + on focus
setInterval(() => {
  if (view === "schedule" && lastSchedule) renderSchedule(lastSchedule);
  else if (view === "shows" && lastShows) renderShows(lastShows);
}, 60 * 1000);
setInterval(() => load(), REFRESH_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });

document.getElementById("range").value = range;
load();
