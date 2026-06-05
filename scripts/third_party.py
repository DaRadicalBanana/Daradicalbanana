#!/usr/bin/env python3
"""Fetch a YouTube transcript via third-party transcript services.

These services fetch YouTube from their own infrastructure, so they work from
cloud IPs (GitHub Actions) that YouTube itself blocks. Tries several free
endpoints in order. Writes transcripts/<id>.txt.
"""
import os
import re
import sys
import json
import html
import urllib.request
import urllib.error

OUT = "transcripts"


def video_id(u):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([0-9A-Za-z_-]{11})", u)
    return m.group(1) if m else u


def ts(sec):
    try:
        sec = int(float(sec))
    except Exception:
        sec = 0
    return f"{sec // 60:02d}:{sec % 60:02d}"


def write_out(vid, lines):
    lines = [l for l in lines if l and l.strip()]
    if not lines:
        return False
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{vid}.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    print(f"[ok] wrote {p} ({len(lines)} lines)")
    return True


def _req(url, data=None, headers=None, method=None):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# --- 1. Tactiq -------------------------------------------------------------
def via_tactiq(vid):
    try:
        raw = _req(
            "https://tactiq-apps-prod.tactiq.io/transcript",
            data={"videoUrl": f"https://www.youtube.com/watch?v={vid}", "langCode": "en"},
            headers={"Origin": "https://tactiq.io", "Referer": "https://tactiq.io/"},
        )
        d = json.loads(raw)
        caps = d.get("captions") or d.get("transcript") or []
        lines = []
        for c in caps:
            t = (c.get("text") or "").strip()
            if t:
                lines.append(f"[{ts(c.get('start', 0))}] {t}")
        if write_out(vid, lines):
            print("[tactiq] success")
            return True
    except Exception as e:
        print(f"[tactiq] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


# --- 2. kome.ai ------------------------------------------------------------
def via_kome(vid):
    try:
        raw = _req(
            "https://api.kome.ai/api/tools/youtube-transcripts",
            data={"video_id": vid, "format": True},
            headers={"Origin": "https://kome.ai"},
        )
        d = json.loads(raw)
        t = d.get("transcript")
        if isinstance(t, list):
            lines = [f"[{ts(x.get('start', 0))}] {(x.get('text') or '').strip()}" for x in t]
        elif isinstance(t, str):
            lines = [l.strip() for l in t.splitlines() if l.strip()]
        else:
            lines = []
        if write_out(vid, lines):
            print("[kome] success")
            return True
    except Exception as e:
        print(f"[kome] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


# --- 3. youtubetotranscript.com (HTML scrape) ------------------------------
def via_yttotranscript(vid):
    try:
        raw = _req(f"https://youtubetotranscript.com/transcript?v={vid}",
                   headers={"Referer": "https://youtubetotranscript.com/"})
        page = raw.decode("utf-8", "replace")
        # spans carry data-start and the caption text
        segs = re.findall(r'data-start="([\d.]+)"[^>]*>(.*?)</span>', page, re.S)
        if not segs:
            segs = re.findall(r'<span[^>]*class="[^"]*transcript[^"]*"[^>]*>(.*?)</span>', page, re.S)
            segs = [("0", s) for s in segs]
        lines = []
        for start, txt in segs:
            txt = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
            if txt:
                lines.append(f"[{ts(start)}] {txt}")
        if write_out(vid, lines):
            print("[yttotranscript] success")
            return True
    except Exception as e:
        print(f"[yttotranscript] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/gTr3J33kQLA"
    vid = video_id(url)
    print(f"[info] video id: {vid}")
    for fn in (via_tactiq, via_kome, via_yttotranscript):
        if fn(vid):
            return
    sys.exit("[error] all third-party services failed")


if __name__ == "__main__":
    main()
