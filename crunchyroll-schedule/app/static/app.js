const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const REFRESH_MS = 5 * 60 * 1000; // auto-refresh every 5 minutes
let current = { year: null, week: null };
let view = localStorage.getItem("view") || "week";
let airType = localStorage.getItem("airType") === "dub" ? "dub" : "sub";
let lastData = null;
let refreshTimer = null;

// ---- favorites (persisted) ----
let favorites = new Set(JSON.parse(localStorage.getItem("favorites") || "[]"));
let search = "";
let favOnly = localStorage.getItem("favonly") === "1";

function isFav(route) { return favorites.has(route); }
function toggleFav(route) {
  if (favorites.has(route)) favorites.delete(route); else favorites.add(route);
  localStorage.setItem("favorites", JSON.stringify([...favorites]));
  if (lastData) render(lastData);
}
function calendarHref() {
  const params = new URLSearchParams({ air_type: airType });
  const favs = [...favorites];
  if (favs.length) params.set("routes", favs.join(","));
  return `/api/calendar.ics?${params.toString()}`;
}

async function load(year, week) {
  const params = new URLSearchParams({ air_type: airType });
  if (year && week) { params.set("year", year); params.set("week", week); }
  const qs = `?${params.toString()}`;
  setStatus("Loading…");
  if (!lastData) showOverlay("Loading the schedule… (first load can take ~30–50s while the server wakes up)");
  try {
    const res = await fetch(`/api/schedule${qs}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    lastData = data;
    setStatus("");
    render(data);
  } catch (err) {
    setStatus(`Couldn't load schedule (${err.message}).`, true);
    showOverlay(
      `Couldn't load the schedule (${escapeHtml(err.message)}).`,
      true
    );
  }
}

// Show a message (with optional Retry button) in the visible content area.
function showOverlay(msg, withRetry) {
  const retry = withRetry
    ? ` <button id="retry" class="today-btn">Retry</button>`
    : "";
  const html = `<div class="empty wide">${escapeHtml(msg)}${retry}</div>`;
  document.getElementById("calendar").innerHTML = html;
  document.getElementById("showlist").innerHTML = html;
  const btn = document.getElementById("retry");
  if (btn) btn.addEventListener("click", () => load(current.year, current.week));
}

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
  el.hidden = !msg;
}

// ---- time helpers ----
function fmtTime(iso, tz) {
  if (!iso) return "TBA";
  return new Date(iso).toLocaleString("en-US", {
    timeZone: tz, weekday: "short", hour: "numeric", minute: "2-digit",
  });
}

function relative(iso) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const past = diff < 0;
  const s = Math.abs(diff) / 1000;
  const mins = Math.round(s / 60), hrs = Math.round(s / 3600), days = Math.round(s / 86400);
  let txt;
  if (s < 90) txt = "just now";
  else if (mins < 90) txt = `${mins} min`;
  else if (hrs < 36) txt = `${hrs} hr`;
  else txt = `${days} day${days === 1 ? "" : "s"}`;
  if (txt === "just now") return txt;
  return past ? `${txt} ago` : `in ${txt}`;
}

// today (in the data's tz) as {iso_week_year, week, weekday}
function localTodayParts(tz) {
  const now = new Date();
  const wd = (new Date(now.toLocaleString("en-US", { timeZone: tz })).getDay() + 6) % 7; // Mon=0
  return { weekday: wd };
}

function badge(conf) {
  if (conf === "jp_fallback")
    return `<span class="badge jp" title="AnimeSchedule fell back to the Japanese broadcast time">JP broadcast time</span>`;
  if (conf === "projected")
    return `<span class="badge proj">projection</span>`;
  return "";
}

function epNum(ep) {
  return ep.subtracted_episode_number
    ? `${ep.subtracted_episode_number}–${ep.episode_number}`
    : ep.episode_number ?? "?";
}

function watchLink(ep) {
  return ep.streams?.crunchyroll
    ? `<a href="${ep.streams.crunchyroll}" target="_blank" rel="noopener">watch ↗</a>`
    : "";
}

function epCard(ep, tz, cover) {
  const past = ep.air_at && new Date(ep.air_at).getTime() < Date.now();
  const thumb = cover
    ? `<img class="ep-thumb" src="${escapeHtml(cover)}" alt="" loading="lazy" onerror="this.remove()" />`
    : "";
  return `<div class="ep ${past ? "past" : "upcoming"}">
    ${thumb}
    <div class="meta">
      <div class="title">${escapeHtml(ep.title)}</div>
      <div>Ep ${epNum(ep)} · <span class="time">${fmtTime(ep.air_at, tz)}</span></div>
      <div class="rel">${relative(ep.air_at)}</div>
      <div>${badge(ep.confidence)} ${watchLink(ep)}</div>
    </div>
  </div>`;
}

// ---- views ----
function renderWeek(data) {
  const cal = document.getElementById("calendar");
  cal.innerHTML = "";
  const total = Object.values(data.days || {}).reduce((n, a) => n + a.length, 0);
  if (total === 0) {
    cal.innerHTML = `<div class="empty wide">No Crunchyroll releases found for ${data.iso_year} · week ${data.iso_week}.</div>`;
    return;
  }
  const isCurrentWeek = data.is_current_week;
  const today = localTodayParts(data.timezone).weekday;
  const coverByRoute = Object.fromEntries(
    (data.shows || []).map((s) => [s.route, s.cover_image_url])
  );
  for (let wd = 0; wd < 7; wd++) {
    const eps = (data.days && data.days[wd]) || [];
    const col = document.createElement("div");
    col.className = "day" + (isCurrentWeek && wd === today ? " today" : "");
    const body = eps.length
      ? eps.map((e) => epCard(e, data.timezone, coverByRoute[e.route])).join("")
      : `<div class="empty">No releases</div>`;
    col.innerHTML = `<h2>${DAYS[wd]}${isCurrentWeek && wd === today ? " · Today" : ""}</h2>` + body;
    cal.appendChild(col);
  }
}

function showRow(show, tz) {
  const fav = isFav(show.route);
  const star = `<button class="fav ${fav ? "on" : ""}" data-route="${escapeHtml(show.route)}"
    aria-pressed="${fav}" title="${fav ? "Unfavorite" : "Favorite"}">${fav ? "★" : "☆"}</button>`;
  const cover = show.cover_image_url
    ? `<img src="${escapeHtml(show.cover_image_url)}" alt="" loading="lazy"
         onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'noart'}))" />`
    : `<div class="noart"></div>`;
  const last = show.last_released
    ? `<div class="slot"><span class="lbl">Last</span> Ep ${epNum(show.last_released)} ·
        <span class="time">${fmtTime(show.last_released.air_at, tz)}</span>
        <span class="rel">(${relative(show.last_released.air_at)})</span></div>`
    : `<div class="slot muted">No released episode this week</div>`;
  const next = show.next_scheduled
    ? `<div class="slot next"><span class="lbl">Next</span> Ep ${epNum(show.next_scheduled)} ·
        <span class="time">${fmtTime(show.next_scheduled.air_at, tz)}</span>
        <span class="rel">(${relative(show.next_scheduled.air_at)})</span>
        ${badge(show.next_scheduled.confidence)}</div>`
    : `<div class="slot muted">No upcoming episode this week</div>`;
  return `<div class="show">
    ${cover}
    <div class="info">
      <div class="title">${star} ${escapeHtml(show.title)} ${watchLink(show.next_scheduled || show.last_released || {})}</div>
      ${last}${next}
    </div>
  </div>`;
}

function renderShows(data) {
  const el = document.getElementById("showlist");
  let shows = (data.shows || []).slice();
  if (favOnly) shows = shows.filter((s) => isFav(s.route));
  if (search) {
    const q = search.toLowerCase();
    shows = shows.filter((s) => s.title.toLowerCase().includes(q));
  }
  shows.sort((a, b) => {
    const an = a.next_scheduled?.air_at, bn = b.next_scheduled?.air_at;
    if (an && bn) return new Date(an) - new Date(bn);
    if (an) return -1;
    if (bn) return 1;
    return a.title.localeCompare(b.title);
  });
  el.innerHTML = shows.length
    ? shows.map((s) => showRow(s, data.timezone)).join("")
    : `<div class="empty">No Crunchyroll shows this week.</div>`;
}

function applyView() {
  document.getElementById("calendar").hidden = view !== "week";
  document.getElementById("showlist").hidden = view !== "shows";
  document.getElementById("showcontrols").hidden = view !== "shows";
  setTab("view-week", view === "week");
  setTab("view-shows", view === "shows");
  setTab("at-sub", airType === "sub");
  setTab("at-dub", airType === "dub");
}

function setTab(id, active) {
  const el = document.getElementById(id);
  el.classList.toggle("active", active);
  el.setAttribute("aria-selected", active ? "true" : "false");
}

function render(data) {
  current = { year: data.iso_year, week: data.iso_week };
  document.getElementById("weeklabel").textContent =
    `${data.iso_year} · ISO week ${data.iso_week}` + (data.is_current_week ? " · this week" : "");
  document.getElementById("tz").textContent = data.timezone;

  const isSample = (data.freshness || []).some((f) => f.source === "sample");
  document.getElementById("samplebanner").hidden = !isSample;

  const fresh = (data.freshness || [])
    .map((f) => `${f.source} ${f.fetched_at ? relative(f.fetched_at) : "never"}${f.stale ? " (stale)" : ""}`)
    .join(" · ");
  document.getElementById("freshness").textContent = fresh ? `Updated ${fresh}` : "";
  document.getElementById("warnings").innerHTML = (data.warnings || [])
    .map((w) => `⚠ ${escapeHtml(w)}`).join("<br>");

  document.getElementById("callink").href = calendarHref();
  renderWeek(data);
  renderShows(data);
  applyView();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function shiftWeek(delta) {
  let { year, week } = current;
  week += delta;
  if (week < 1) { year -= 1; week = 52; }
  if (week > 53) { year += 1; week = 1; }
  load(year, week);
}

function setView(v) {
  view = v;
  localStorage.setItem("view", v);
  applyView();
  if (lastData) render(lastData); // refresh relative times
}

document.getElementById("prev").addEventListener("click", () => shiftWeek(-1));
document.getElementById("next").addEventListener("click", () => shiftWeek(1));
document.getElementById("today").addEventListener("click", () => load());
document.getElementById("view-week").addEventListener("click", () => setView("week"));
document.getElementById("view-shows").addEventListener("click", () => setView("shows"));

function setAirType(t) {
  airType = t;
  localStorage.setItem("airType", t);
  applyView();
  load(current.year, current.week);
}
document.getElementById("at-sub").addEventListener("click", () => setAirType("sub"));
document.getElementById("at-dub").addEventListener("click", () => setAirType("dub"));

// search + favorites
document.getElementById("search").addEventListener("input", (e) => {
  search = e.target.value.trim();
  if (lastData) renderShows(lastData);
});
const favOnlyEl = document.getElementById("favonly");
favOnlyEl.checked = favOnly;
favOnlyEl.addEventListener("change", (e) => {
  favOnly = e.target.checked;
  localStorage.setItem("favonly", favOnly ? "1" : "0");
  if (lastData) renderShows(lastData);
});
// star toggles (event delegation)
document.getElementById("showlist").addEventListener("click", (e) => {
  const btn = e.target.closest(".fav");
  if (btn) toggleFav(btn.dataset.route);
});

// re-render relative times every minute without refetching
setInterval(() => { if (lastData) render(lastData); }, 60 * 1000);
// auto-refresh data periodically and on tab focus
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => load(current.year, current.week), REFRESH_MS);
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load(current.year, current.week);
});

(async function init() {
  applyView();
  await load();
  setInterval(scheduleRefresh, REFRESH_MS);
})();
