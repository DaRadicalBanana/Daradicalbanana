# Security review & hardening

Personal, read-only web app. No accounts, no user data stored, no write
endpoints. Threat surface is small but it is internet-exposed (Render), so this
documents the review and the hardening applied.

## Assets & trust boundaries
- **Secret:** `ANIMESCHEDULE_TOKEN` (env only). Used solely as an outbound
  `Authorization: Bearer` header to AnimeSchedule. Never logged, never returned
  by any endpoint (`/api/health` exposes only a `token_present` boolean), never
  committed (`.gitignore` excludes `.env`; `.env.example` is blank).
- **Untrusted input:** the AnimeSchedule/AniList API responses (titles, stream
  URLs, image paths) and query params (`range`, `air_type`, `anchor`,
  `year`/`week`, `routes`).
- **No PII** is collected or stored. Favorites/preferences live only in the
  browser's `localStorage`.

## Findings & mitigations (this review)
| # | Finding | Severity | Mitigation |
|---|---------|----------|------------|
| 1 | `/api/debug` exposed raw upstream payload + internals publicly | Medium | Gated behind `APP_DEBUG` (default off → 404) |
| 2 | No security response headers | Medium | Added CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` |
| 3 | Inline `onerror` handler blocked a strict CSP | Low | Removed; image fallbacks wired via JS so CSP needs no `unsafe-inline` |
| 4 | XSS via untrusted titles/URLs | Low (already ok) | All dynamic values pass through `escapeHtml`; verified |
| 5 | `javascript:`/scheme-less stream URLs | Low | `normalize_streams` forces an `https://` scheme; links use `rel="noopener"` |

## Already-sound controls (verified)
- Token confined to the request header; error messages include only upstream
  status/body (`resp.text[:200]`), not the token.
- No CORS middleware → API is same-origin only.
- Aggressive caching + token-bucket rate limiter bound outbound calls; failures
  degrade to cache/sample rather than erroring.
- Server-side `asyncio.wait_for` + client fetch timeout prevent hangs.

## Backlog for upcoming security runs
- Input hardening: clamp/validate `year`/`week`/`anchor` to a sane window so odd
  values can't trigger 500s or amplification; bound monthly fan-out.
- Abuse/DoS: per-IP request throttling on the API; cap how far prev/next can page.
- Supply chain: pin dependency versions and add a `pip-audit`/Dependabot check.
- Repo hygiene: secret-scanning in CI on every push.
- Tighten CSP `img-src` from `https:` to the specific image hosts.

## Enabling debug safely
`/api/debug` is off by default. To diagnose live data temporarily, set
`APP_DEBUG=1` in the environment, inspect, then unset it.
