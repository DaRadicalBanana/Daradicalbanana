# Continuing this project on your Mac

This repo contains a YouTube-transcript extractor. The transcript that was the original
goal is already done: **`transcripts/gTr3J33kQLA.txt`** (1,580 lines, full video).

## Two ways to "continue", and why the difference matters

YouTube blocks **cloud/datacenter IPs** (AWS/GCP/Azure → GitHub Actions, and the Claude
Code *web* sandbox). It does **not** block normal home connections. So *where the code
runs* decides whether YouTube extraction "just works."

| Where you run | Network result | Notes |
|---|---|---|
| Claude Code **web / cloud session** (even if viewed in the desktop app) | YouTube **blocked** (403) | Same restricted sandbox; needs the GitHub Actions pipeline in this repo |
| Claude Code **local session** on your Mac, or your Mac terminal | YouTube **works** | Residential IP — no proxies/PO-tokens/keys needed |

> Tip: opening the cloud session inside the desktop app keeps full chat context, but the
> commands still execute in the cloud sandbox. To get your Mac's IP, start a **local**
> session pointed at a local clone of this repo.

## Pull a transcript locally (the easy path)

```bash
pipx run yt-dlp --skip-download --write-auto-subs --write-subs \
  --sub-langs "en.*" --convert-subs srt \
  -o "%(id)s.%(ext)s" "https://youtu.be/gTr3J33kQLA"
```

That writes `gTr3J33kQLA.en.srt`. To normalize any `.srt` into timestamped text:

```bash
python scripts/srt_to_txt.py .          # converts *.srt in the current dir
```

## The cloud pipeline (already wired, for CI use)

`.github/workflows/transcript.yml` runs on push and tries, in order: third-party transcript
services → free proxy pool → yt-dlp+cookies (`YT_COOKIES` secret) → InnerTube+PO-token →
yt-dlp+PO-token → yt-dlp/transcript-api. First success commits `transcripts/<id>.txt` back
to the branch. Optional reliability boost: add a free **`SUPADATA_API_KEY`** repo secret.

`.github/workflows/recover.yml` re-downloads a transcript that a past run uploaded as an
artifact (set the artifact id inside it) and commits it — used when a run produced the
transcript but its push lost a race.

## Full background

See `SESSION_HANDOFF_youtube-transcript.md` for the complete state, decisions, and IDs.
