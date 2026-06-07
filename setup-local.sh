#!/usr/bin/env bash
#
# setup-local.sh — clone/checkout this repo and pull a YouTube transcript using
# THIS machine's IP. Designed for a Mac / home connection.
#
# Why it works where the cloud sandbox / GitHub Actions don't:
#   * YouTube blocks cloud/datacenter IPs; a home IP is fine.
#   * It pulls captions via the timedtext / watch-page route (youtube-transcript-api),
#     NOT YouTube's player API. The player API is PO-token / client-gated for some
#     videos (you'll see yt-dlp say "This video is not available" via android_vr),
#     but the timedtext route serves public captions regardless and just needs a
#     non-blocked (residential) IP.
#
# Usage:
#   bash setup-local.sh                      # default video (gTr3J33kQLA)
#   bash setup-local.sh https://youtu.be/ID  # any video URL or 11-char ID
set -euo pipefail

REPO_URL="https://github.com/DaRadicalBanana/Daradicalbanana.git"
BRANCH="claude/video-transcript-extraction-jlAit"
VIDEO="${1:-https://youtu.be/gTr3J33kQLA}"

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!!  %s\033[0m\n" "$*"; }

command -v git >/dev/null 2>&1 || { warn "git not found. Run: xcode-select --install"; exit 1; }
command -v python3 >/dev/null 2>&1 || { warn "python3 not found. Install from python.org or 'brew install python'."; exit 1; }

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

# 3. Python tools in an isolated venv (avoids macOS PEP 668 'externally-managed' errors).
say "Setting up Python venv + tools (yt-dlp, youtube-transcript-api)"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q --upgrade yt-dlp youtube-transcript-api
if ! command -v deno >/dev/null 2>&1 && ! command -v node >/dev/null 2>&1; then
  warn "No JS runtime (deno/node) found — fine, the primary method doesn't need it; only the yt-dlp fallback is limited without one."
fi

# 4. Extract. extract_transcript.py tries the timedtext route (youtube-transcript-api)
#    FIRST, then yt-dlp; third_party.py is a final fallback (transcript services).
say "Extracting transcript for: $VIDEO"
if python scripts/extract_transcript.py "$VIDEO"; then
  :
elif python scripts/third_party.py "$VIDEO"; then
  :
else
  warn "All extraction methods failed. If this is a private/members-only video, add browser auth:"
  warn "  yt-dlp --cookies-from-browser chrome --skip-download --write-auto-subs --sub-langs en.* --convert-subs srt -o 'transcripts/%(id)s.%(ext)s' '$VIDEO'"
  exit 1
fi

say "Done. Output in ./transcripts:"
ls -la transcripts
