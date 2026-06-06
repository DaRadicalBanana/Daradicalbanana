#!/usr/bin/env python3
"""Try to fetch a YouTube transcript through free public proxies.

YouTube blocks cloud IPs, but free-proxy pools contain some residential/mobile
IPs that aren't flagged. We pull several public proxy lists and hammer them in
parallel via youtube-transcript-api, taking the first that succeeds. No account
or key required. Writes transcripts/<id>.txt.
"""
import os
import re
import sys
import time
import socket
import random
import urllib.request
import concurrent.futures as cf

OUT = "transcripts"
DEADLINE_SECS = 300
MAX_PROXIES = 400
WORKERS = 50

PROXY_SOURCES = [
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
]


def video_id(u):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([0-9A-Za-z_-]{11})", u)
    return m.group(1) if m else u


def ts(sec):
    sec = int(float(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def write_out(vid, lines):
    lines = [l for l in lines if l and l.strip()]
    if len(lines) < 2:
        return False
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{vid}.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    print(f"[ok] wrote {p} ({len(lines)} lines)")
    return True


def fetch_proxies():
    proxies = set()
    for src in PROXY_SOURCES:
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
            for m in re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})", raw):
                proxies.add(m)
            print(f"[proxies] {src.split('/')[2]}: total now {len(proxies)}")
        except Exception as e:
            print(f"[proxies] {src.split('/')[2]} fail: {type(e).__name__}")
    proxies = list(proxies)
    random.shuffle(proxies)
    return proxies[:MAX_PROXIES]


def attempt(vid, proxy):
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig
    try:
        api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(
            http_url=f"http://{proxy}", https_url=f"http://{proxy}"))
        fetched = api.fetch(vid, languages=["en", "en-US", "en-GB", "en-CA"])
        segs = [(s.start, s.text) for s in fetched]
        if segs:
            return proxy, segs
    except Exception:
        pass
    return proxy, None


def main():
    socket.setdefaulttimeout(12)
    url = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/gTr3J33kQLA"
    vid = video_id(url)
    print(f"[info] video id: {vid}")
    proxies = fetch_proxies()
    print(f"[info] trying {len(proxies)} proxies, deadline {DEADLINE_SECS}s")
    if not proxies:
        sys.exit("[error] no proxies fetched")

    start = time.time()
    tried = 0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(attempt, vid, p): p for p in proxies}
        for fut in cf.as_completed(futures):
            tried += 1
            proxy, segs = fut.result()
            if segs:
                lines = [f"[{ts(s)}] {t.strip()}" for s, t in segs if t.strip()]
                if write_out(vid, lines):
                    print(f"[proxy] SUCCESS via {proxy} after {tried} tries, "
                          f"{int(time.time() - start)}s")
                    for f2 in futures:
                        f2.cancel()
                    return
            if time.time() - start > DEADLINE_SECS:
                print(f"[proxy] deadline reached after {tried} tries")
                for f2 in futures:
                    f2.cancel()
                break
            if tried % 50 == 0:
                print(f"[proxy] {tried} tried, {int(time.time() - start)}s elapsed")
    sys.exit("[error] no working proxy found")


if __name__ == "__main__":
    main()
