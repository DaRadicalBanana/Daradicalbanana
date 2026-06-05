#!/usr/bin/env python3
"""Extract a YouTube transcript using several fallback strategies.

Usage: python extract_transcript.py <video_url_or_id>

Writes results to transcripts/<video_id>.txt (plain text) and, when a
timed source is available, transcripts/<video_id>.srt as well.
"""
import os
import re
import sys
import json
import subprocess

OUT_DIR = "transcripts"


def video_id(url: str) -> str:
    for pat in (r"v=([0-9A-Za-z_-]{11})", r"youtu\.be/([0-9A-Za-z_-]{11})",
                r"shorts/([0-9A-Za-z_-]{11})", r"embed/([0-9A-Za-z_-]{11})"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url):
        return url
    raise SystemExit(f"Could not parse video id from: {url}")


def write_text(vid: str, lines):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{vid}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    print(f"[ok] wrote {path} ({len(lines)} lines)")
    return path


def ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


# --- Strategy 1: youtube-transcript-api -------------------------------------
def via_transcript_api(vid: str) -> bool:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception as e:  # not installed
        print(f"[skip] transcript-api import: {e}")
        return False
    try:
        # Newer API (>=1.0) uses instance .fetch(); older uses classmethod.
        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(vid, languages=["en", "en-US", "en-GB"])
            segments = [{"start": s.start, "text": s.text} for s in fetched]
        except TypeError:
            segments = YouTubeTranscriptApi.get_transcript(
                vid, languages=["en", "en-US", "en-GB"])
        if not segments:
            return False
        lines = [f"[{ts(s['start'])}] {s['text'].strip()}" for s in segments if s['text'].strip()]
        write_text(vid, lines)
        return True
    except Exception as e:
        print(f"[fail] transcript-api: {type(e).__name__}: {e}")
        return False


# --- Strategy 2: yt-dlp subtitles -------------------------------------------
def via_ytdlp(vid: str) -> bool:
    url = f"https://www.youtube.com/watch?v={vid}"
    clients = ["default", "web,mweb,android_vr,tv", "android_vr,ios,web"]
    for client in clients:
        cmd = [
            sys.executable, "-m", "yt_dlp", "--skip-download",
            "--write-auto-subs", "--write-subs", "--sub-langs", "en.*",
            "--sub-format", "json3/vtt/srv1", "--convert-subs", "srt",
            "-o", os.path.join(OUT_DIR, "%(id)s.%(ext)s"), url,
        ]
        if client != "default":
            cmd[3:3] = ["--extractor-args", f"youtube:player_client={client}"]
        os.makedirs(OUT_DIR, exist_ok=True)
        print(f"[run] yt-dlp client={client}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout[-1500:])
        if r.returncode != 0:
            print(r.stderr[-1500:])
        srt = _find_srt(vid)
        if srt:
            _srt_to_txt(vid, srt)
            return True
    return False


def _find_srt(vid: str):
    if not os.path.isdir(OUT_DIR):
        return None
    cands = [f for f in os.listdir(OUT_DIR) if f.startswith(vid) and f.endswith(".srt")]
    cands.sort(key=lambda f: ("orig" not in f, len(f)))  # prefer manual over auto
    return os.path.join(OUT_DIR, cands[0]) if cands else None


def _srt_to_txt(vid: str, srt_path: str):
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()
    lines, seen = [], None
    blocks = re.split(r"\n\s*\n", content)
    for b in blocks:
        rows = [r for r in b.splitlines() if r.strip()]
        if len(rows) < 2:
            continue
        tm = re.match(r"(\d+):(\d+):(\d+)", rows[1])
        stamp = ""
        if tm:
            h, m, s = map(int, tm.groups())
            stamp = ts(h * 3600 + m * 60 + s)
        text = " ".join(rows[2:]).strip()
        text = re.sub(r"<[^>]+>", "", text)
        if text and text != seen:
            lines.append(f"[{stamp}] {text}")
            seen = text
    write_text(vid, lines)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_transcript.py <url|id>")
    vid = video_id(sys.argv[1])
    print(f"[info] video id: {vid}")
    for strat in (via_transcript_api, via_ytdlp):
        if strat(vid):
            print("[done] transcript extracted")
            return
    raise SystemExit("[error] all strategies failed")


if __name__ == "__main__":
    main()
