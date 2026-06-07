# Session Handoff (Claude Code **Desktop**) — YouTube Transcript Extraction

> **Purpose:** hand this work to a *new session in the Claude Code Desktop app* (not the
> terminal) with zero prior context. Read this top-to-bottom, pick Path A or B, then paste
> the opener at the bottom into the new session.
>
> The repo carries everything (transcript, scripts, docs) — nothing from the old chat needs
> re-uploading; the new session just needs the repo open.

## TL;DR — where we are
The original goal is **DONE**: the full transcript is committed at
`transcripts/gTr3J33kQLA.txt` (1,580 lines, 00:09→59:30) on branch
`claude/video-transcript-extraction-jlAit`. A reusable extraction pipeline + helper scripts
+ a one-shot `setup-local.sh` are also committed. Remaining work is **optional** (clean up /
summarize / split the transcript, or pull *new* videos). The next action is just: open the
repo in a new Desktop session (Path A or B below) and tell it what you want.

## The one decision that matters in Desktop: cloud session vs local session
The Desktop app can run a session in **two** places. They behave very differently here
because **YouTube blocks cloud/datacenter IPs** (the whole reason this task was hard):

| | **Path A — Cloud session** (☁ badge) | **Path B — Local session** (your Mac) |
|---|---|---|
| Where code runs | Anthropic cloud sandbox `vm` | Your Mac (`/Users/...`) |
| Network to YouTube | **Blocked (HTTP 403)** | **Works (HTTP 200)** |
| Prior chat context | The *existing* cloud session keeps it | Fresh — paste this handoff |
| Good for | Editing the repo, CI pipeline, PRs, summarizing the existing transcript | Pulling *new* transcripts directly (`yt-dlp` just works) |

**Rule of thumb:** anything that must talk to YouTube → **Path B (local)**. Anything that's
just editing files / running the GitHub Actions pipeline / making a PR → either path.

## Path A — continue in a Cloud session (full context, but IP-blocked)
1. In the Desktop left sidebar, open **Recents → "Video transcript extraction"** (the ☁ one).
   That *is* the original session with all context.
2. Or **New session** and attach the same GitHub repo as a cloud environment.
3. Note: commands run in the sandbox, so `curl youtube.com` returns **403** here. To fetch a
   transcript from a cloud session you must use the committed GitHub Actions pipeline (push a
   commit → it extracts and commits `transcripts/<id>.txt` back). See "Pipeline" below.

## Path B — start a Local session (recommended for any new extraction)
1. **New session** in the Desktop app → when prompted for a location, pick the **local
   folder** option (the one *without* the ☁ cloud badge) → choose a folder on your Mac.
   - If you don't have the repo yet, first clone it (one line in any Terminal):
     `git clone https://github.com/DaRadicalBanana/Daradicalbanana.git`
   - Then point the new session at that `Daradicalbanana` folder and
     `git checkout claude/video-transcript-extraction-jlAit`.
2. Confirm it's truly local: ask it to run `pwd` (should be `/Users/...`) and
   `curl -s -o /dev/null -w "%{http_code}\n" https://www.youtube.com` (should be **200**).
3. Fastest start: have it run **`bash setup-local.sh`** — that installs `yt-dlp` and pulls the
   transcript in one shot. (For another video: `bash setup-local.sh "https://youtu.be/ID"`.)

## Key facts
| Item | Value |
|---|---|
| Repo | `DaRadicalBanana/Daradicalbanana` (public) |
| Branch | `claude/video-transcript-extraction-jlAit` |
| Deliverable | `transcripts/gTr3J33kQLA.txt` (1,580 lines, `[MM:SS]` per line) |
| Video | https://youtu.be/gTr3J33kQLA — "Building Agents with Claude Opus 4.8: Live Demos with Letta" |
| One-shot local setup | `setup-local.sh` (clone/checkout → install yt-dlp → fetch → srt→txt) |
| CI pipeline | `.github/workflows/transcript.yml` |
| Artifact recovery CI | `.github/workflows/recover.yml` (artifact id `7450203183`, expires ~2026-09-04) |
| Helper scripts | `scripts/third_party.py`, `proxy_extract.py`, `po_transcript.mjs`, `mint_potoken.mjs`, `extract_transcript.py`, `srt_to_txt.py` |
| Full background doc | `SESSION_HANDOFF_youtube-transcript.md` |
| Mac guide | `CONTINUE_ON_MAC.md` |

## Root finding (don't re-litigate)
- YouTube **hard-blocks cloud IPs** (web sandbox + GitHub Actions). PO tokens were minted
  successfully but are **not sufficient**; cookies are also broken in youtube-transcript-api.
  A **residential IP (your Mac)** or a **third-party service on residential infra** is what
  works. The delivered transcript came from a third-party provider in CI run `27049446864`,
  recovered via its artifact.

## Decisions already made (settled)
1. **Local Mac session = the clean way to extract** (residential IP). Use Path B for new pulls.
2. **GitHub Actions = the cloud fallback** with concurrency guard + rebase-retry push (avoids
   the race that lost an earlier push).
3. **`workflow_dispatch`/run-cancel are blocked** for the integration token — trigger CI by
   pushing a commit; empty commits don't trigger (path filter).
4. Optional reliability: add a free **`SUPADATA_API_KEY`** repo secret; the pipeline auto-uses it.

## What carries over to the new Desktop session
- **Everything committed to git** — transcript, scripts, workflows, all three docs. Re-fetch
  with `git checkout origin/claude/video-transcript-extraction-jlAit -- <path>` if needed.
- **Does NOT carry over:** this chat's memory, and any file shown only in chat. The transcript
  is in the repo, so you never need to re-upload it.

## Start the new Desktop session with
> "Open the `Daradicalbanana` repo, branch `claude/video-transcript-extraction-jlAit`. Read
> `SESSION_HANDOFF_DESKTOP.md`, `SESSION_HANDOFF_youtube-transcript.md`, and
> `CONTINUE_ON_MAC.md`. The transcript task is already done (`transcripts/gTr3J33kQLA.txt`);
> don't re-litigate the cloud-IP findings. This is a **<cloud / local>** session. Now:
> **[if local]** run `bash setup-local.sh` to confirm yt-dlp works on this machine, then
> <pull video X / clean up the existing transcript / summarize it / split by speaker>.
> **[if cloud]** just <clean up / summarize / split / open a PR for this branch> — and use the
> GitHub Actions pipeline (push a commit) for anything that needs YouTube."

---
*Handoff generated 2026-06-07. For the Claude Code Desktop app. Domain: pulling a YouTube
transcript despite cloud-IP blocking; resolved via residential-IP (Mac) or CI + third-party.*
