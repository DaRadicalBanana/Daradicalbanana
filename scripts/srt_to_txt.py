#!/usr/bin/env python3
"""Convert any .srt files in a directory to timestamped plain-text .txt."""
import os
import re
import sys


def ts(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def convert(srt_path, txt_path):
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()
    lines, seen = [], None
    for block in re.split(r"\n\s*\n", content):
        rows = [r for r in block.splitlines() if r.strip()]
        if len(rows) < 2:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)", rows[1])
        stamp = ""
        if m:
            h, mn, s = map(int, m.groups())
            stamp = ts(h * 3600 + mn * 60 + s)
        text = re.sub(r"<[^>]+>", "", " ".join(rows[2:])).strip()
        if text and text != seen:
            lines.append(f"[{stamp}] {text}")
            seen = text
    if lines:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")
        print(f"[ok] wrote {txt_path} ({len(lines)} lines)")
        return True
    return False


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "transcripts"
    if not os.path.isdir(d):
        return
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".srt"):
            vid = fn.split(".")[0]
            convert(os.path.join(d, fn), os.path.join(d, f"{vid}.txt"))


if __name__ == "__main__":
    main()
