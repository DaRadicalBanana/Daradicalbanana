# YouTube transcript extractor

A GitHub Actions workflow (`.github/workflows/transcript.yml`) that extracts the
transcript/captions of a YouTube video and commits it to `transcripts/<id>.txt`.

## Usage

Push to the working branch, or set the `video_url` input. The default video is
`https://youtu.be/gTr3J33kQLA`.

## How it works

It tries several strategies in order until one yields a transcript:

1. **yt-dlp + cookies** — uses the `YT_COOKIES` repository secret (Netscape
   cookie file contents). Required for videos that demand a signed-in session
   from datacenter IPs.
2. **InnerTube + PO token** — mints a BotGuard Proof-of-Origin token via
   `bgutils-js` (`scripts/mint_potoken.mjs`) and calls YouTube's `get_transcript`
   / `player` endpoints (`scripts/po_transcript.mjs`).
3. **yt-dlp + PO token** — feeds the minted token to yt-dlp.
4. **yt-dlp / youtube-transcript-api** — last-resort plain extraction.

The result is normalized to timestamped plain text.

## Providing cookies

YouTube blocks caption/playback requests from cloud IPs (GitHub Actions) unless
authenticated. Export `youtube.com` cookies in Netscape format (e.g. with the
"Get cookies.txt LOCALLY" browser extension, from an incognito session) and add
them as the repository secret **`YT_COOKIES`**.
