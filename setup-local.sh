#!/usr/bin/env bash
#
# setup-local.sh — clone/checkout this repo, install yt-dlp, and pull a YouTube
# transcript using THIS machine's IP (works on a Mac/home connection where the
# cloud sandbox's IP is blocked by YouTube).
#
# Usage:
#   bash setup-local.sh                      # default video (gTr3J33kQLA)
#   bash setup-local.sh https://youtu.be/ID  # any video URL or 11-char ID
#
# Safe to run from inside an existing clone OR from an empty directory.
set -euo pipefail

REPO_URL="https://github.com/DaRadicalBanana/Daradicalbanana.git"
BRANCH="claude/video-transcript-extraction-jlAit"
VIDEO="${1:-https://youtu.be/gTr3J33kQLA}"

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!!  %s\033[0m\n" "$*"; }

command -v git >/dev/null 2>&1 || { warn "git not found. Install Xcode Command Line Tools: xcode-select --install"; exit 1; }

# 1. Make sure we're inside the repo (clone if we aren't).
if git rev-parse --show-toplevel >/dev/null 2>&1 \
   && git remote get-url origin 2>/dev/null | grep -qi "Daradicalbanana"; then
  cd "$(git rev-parse --show-toplevel)"
  say "Using existing repo at $(pwd)"
else
  say "Cloning $REPO_URL"
  git clone "$REPO_URL"
  cd Daradicalbanana
fi

say "Checking out $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH" || true

# 2. Confirm this machine isn't IP-blocked (expect 200, not 403).
say "Testing network reachability to YouTube"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 https://www.youtube.com || echo 000)
echo "    youtube.com -> HTTP $code"
[ "$code" = "403" ] && warn "Got 403 — this IP looks blocked (cloud/VPN?). Extraction may fail; use a home connection."

# 3. Ensure yt-dlp is available (prefer pipx, then pip3, then brew).
if command -v yt-dlp >/dev/null 2>&1; then
  YTDLP="yt-dlp"
elif command -v pipx >/dev/null 2>&1; then
  say "Installing yt-dlp via pipx"; pipx install yt-dlp; YTDLP="yt-dlp"
elif command -v pip3 >/dev/null 2>&1; then
  say "Installing yt-dlp via pip3 (--user)"; pip3 install --user -U yt-dlp; YTDLP="python3 -m yt_dlp"
elif command -v brew >/dev/null 2>&1; then
  say "Installing yt-dlp via Homebrew"; brew install yt-dlp; YTDLP="yt-dlp"
else
  warn "Need yt-dlp. Install Python 3 (python.org) or Homebrew (brew.sh), then re-run."
  exit 1
fi

# 4. Pull subtitles for the requested video.
say "Fetching transcript for: $VIDEO"
mkdir -p transcripts
$YTDLP --skip-download --write-auto-subs --write-subs \
  --sub-langs "en.*" --sub-format "vtt/srv1/json3" --convert-subs srt \
  -o "transcripts/%(id)s.%(ext)s" "$VIDEO"

# 5. Normalize any .srt to timestamped plain text via the repo's helper.
if ls transcripts/*.srt >/dev/null 2>&1; then
  say "Converting .srt -> timestamped .txt"
  python3 scripts/srt_to_txt.py transcripts || warn "srt_to_txt.py failed; the .srt files are still in ./transcripts"
fi

say "Done. Output in ./transcripts:"
ls -la transcripts
