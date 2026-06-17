const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
let current = { year: null, week: null };

async function load(year, week) {
  const qs = year && week ? `?year=${year}&week=${week}` : "";
  const res = await fetch(`/api/schedule${qs}`);
  const data = await res.json();
  render(data);
}

function fmtTime(iso, tz) {
  if (!iso) return "TBA";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    timeZone: tz,
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function badge(conf) {
  if (conf === "jp_fallback")
    return `<span class="badge jp" title="AnimeSchedule fell back to the Japanese broadcast time">JP broadcast time</span>`;
  if (conf === "projected")
    return `<span class="badge proj">projection</span>`;
  return "";
}

function epCard(ep, tz) {
  const num = ep.subtracted_episode_number
    ? `${ep.subtracted_episode_number}–${ep.episode_number}`
    : ep.episode_number ?? "?";
  const link = ep.streams?.crunchyroll
    ? `<a href="${ep.streams.crunchyroll}" target="_blank" rel="noopener">watch ↗</a>`
    : "";
  return `<div class="ep">
    <div class="meta">
      <div class="title">${escapeHtml(ep.title)}</div>
      <div>Ep ${num} · <span class="time">${fmtTime(ep.air_at, tz)}</span></div>
      <div>${badge(ep.confidence)} ${link}</div>
    </div>
  </div>`;
}

function render(data) {
  current = { year: data.iso_year, week: data.iso_week };
  document.getElementById("weeklabel").textContent =
    `${data.iso_year} · ISO week ${data.iso_week}`;
  document.getElementById("tz").textContent = data.timezone;

  const isSample = (data.freshness || []).some((f) => f.source === "sample");
  document.getElementById("samplebanner").hidden = !isSample;

  const fresh = (data.freshness || [])
    .map((f) => {
      const when = f.fetched_at ? new Date(f.fetched_at).toLocaleString("en-US", { timeZone: data.timezone }) : "never";
      return `${f.source}: ${when}${f.stale ? " (stale)" : ""}`;
    })
    .join(" · ");
  document.getElementById("freshness").textContent = `Data freshness — ${fresh}`;
  document.getElementById("warnings").innerHTML = (data.warnings || [])
    .map((w) => `⚠ ${escapeHtml(w)}`)
    .join("<br>");

  const cal = document.getElementById("calendar");
  cal.innerHTML = "";
  for (let wd = 0; wd < 7; wd++) {
    const eps = (data.days && data.days[wd]) || [];
    const col = document.createElement("div");
    col.className = "day";
    const body = eps.length
      ? eps.map((e) => epCard(e, data.timezone)).join("")
      : `<div class="empty">No releases</div>`;
    col.innerHTML = `<h2>${DAYS[wd]}</h2>` + body;
    cal.appendChild(col);
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function shiftWeek(delta) {
  // Naive ISO week stepping; server normalizes anything out of range.
  let { year, week } = current;
  week += delta;
  if (week < 1) { year -= 1; week = 52; }
  if (week > 53) { year += 1; week = 1; }
  load(year, week);
}

document.getElementById("prev").addEventListener("click", () => shiftWeek(-1));
document.getElementById("next").addEventListener("click", () => shiftWeek(1));
load();
