#!/usr/bin/env python3
"""Fetch a YouTube transcript via third-party transcript services.

These services fetch YouTube from their own infrastructure, so they work from
cloud IPs (GitHub Actions) that YouTube itself blocks. Tries several endpoints
in order. Writes transcripts/<id>.txt.
"""
import os
import re
import sys
import json
import time
import html
import urllib.request
import urllib.error

OUT = "transcripts"
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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
    lines = [l for l in lines if l and l.strip() and l.strip() not in ("[00:00]",)]
    if len(lines) < 2:
        return False
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{vid}.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    print(f"[ok] wrote {p} ({len(lines)} lines)")
    return True


def _req(url, data=None, headers=None, method=None, timeout=60):
    h = dict(BROWSER)
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
    if isinstance(data, (dict, list)):
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(t):
    return html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\n", " ").strip()


# --- youtubetranscript.com (no auth, XML) ----------------------------------
def via_youtubetranscript(vid):
    try:
        raw = _req(f"https://youtubetranscript.com/?server_vid2={vid}").decode("utf-8", "replace")
        segs = re.findall(r'<text[^>]*start="([\d.]+)"[^>]*>(.*?)</text>', raw, re.S)
        lines = [f"[{ts(s)}] {clean(t)}" for s, t in segs if clean(t)]
        if write_out(vid, lines):
            print("[youtubetranscript] success")
            return True
        print(f"[youtubetranscript] no segments (body {raw[:120]!r})")
    except Exception as e:
        print(f"[youtubetranscript] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


# --- kome.ai (JSON, retry on 5xx) ------------------------------------------
def via_kome(vid):
    for attempt in range(3):
        try:
            raw = _req("https://api.kome.ai/api/tools/youtube-transcripts",
                       data={"video_id": vid, "format": True},
                       headers={"Origin": "https://kome.ai", "Referer": "https://kome.ai/"})
            d = json.loads(raw)
            t = d.get("transcript")
            if isinstance(t, list):
                lines = [f"[{ts(x.get('start', 0))}] {clean(x.get('text', ''))}" for x in t]
            elif isinstance(t, str):
                lines = [l.strip() for l in t.splitlines() if l.strip()]
            else:
                lines = []
            if write_out(vid, lines):
                print("[kome] success")
                return True
        except urllib.error.HTTPError as e:
            print(f"[kome] HTTP {e.code} (attempt {attempt + 1})")
            if e.code in (522, 502, 503, 429):
                time.sleep(3 * (attempt + 1)); continue
            break
        except Exception as e:
            print(f"[kome] fail: {type(e).__name__}: {str(e)[:200]}")
            break
    return False


# --- tactiq (JSON) ----------------------------------------------------------
def via_tactiq(vid):
    try:
        raw = _req("https://tactiq-apps-prod.tactiq.io/transcript",
                   data={"videoUrl": f"https://www.youtube.com/watch?v={vid}", "langCode": "en"},
                   headers={"Origin": "https://tactiq.io", "Referer": "https://tactiq.io/"})
        d = json.loads(raw)
        caps = d.get("captions") or []
        lines = [f"[{ts(c.get('start', 0))}] {clean(c.get('text', ''))}" for c in caps]
        if write_out(vid, lines):
            print("[tactiq] success")
            return True
    except Exception as e:
        print(f"[tactiq] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


# --- notegpt.io (JSON) ------------------------------------------------------
def via_notegpt(vid):
    try:
        raw = _req(f"https://notegpt.io/api/v2/video-transcript?platform=youtube&video_id={vid}",
                   headers={"Referer": "https://notegpt.io/"})
        d = json.loads(raw)
        trans = (((d.get("data") or {}).get("transcripts") or {}))
        # transcripts keyed by lang -> {custom:[{start,text}]}
        items = None
        for k, v in trans.items():
            if isinstance(v, dict) and (v.get("custom") or v.get("auto")):
                items = v.get("custom") or v.get("auto"); break
        lines = [f"[{ts(x.get('start', 0))}] {clean(x.get('text', ''))}" for x in (items or [])]
        if write_out(vid, lines):
            print("[notegpt] success")
            return True
    except Exception as e:
        print(f"[notegpt] fail: {type(e).__name__}: {str(e)[:200]}")
    return False


# --- youtubetotranscript.com (HTML scrape with priming) --------------------
def via_yttotranscript(vid):
    try:
        # prime cookies
        try:
            _req("https://youtubetotranscript.com/", headers={"Referer": "https://youtubetotranscript.com/"})
        except Exception:
            pass
        raw = _req(f"https://youtubetotranscript.com/transcript?v={vid}",
                   headers={"Referer": "https://youtubetotranscript.com/"}).decode("utf-8", "replace")
        segs = re.findall(r'data-start="([\d.]+)"[^>]*>(.*?)</span>', raw, re.S)
        lines = [f"[{ts(s)}] {clean(t)}" for s, t in segs if clean(t)]
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
    for fn in (via_youtubetranscript, via_kome, via_notegpt, via_tactiq, via_yttotranscript):
        try:
            if fn(vid):
                return
        except Exception as e:
            print(f"[{fn.__name__}] unexpected: {e}")
    sys.exit("[error] all third-party services failed")


if __name__ == "__main__":
    main()
