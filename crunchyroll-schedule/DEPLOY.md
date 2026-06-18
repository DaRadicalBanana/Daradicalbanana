# Put the app online (open it on your phone, anytime)

This deploys the app to **Render** on its **free** plan. You get a permanent link
like `https://crunchyroll-schedule.onrender.com` that you can open on your phone —
no computer left running. It starts in **demo mode** (sample data) and switches to
live Crunchyroll timing the moment you add a token (last section).

You can do all of this from your phone's browser.

## One-time setup (~3 minutes)

1. Go to **https://render.com** and click **Get Started** — sign in with your
   **GitHub** account (the same one that owns this repo). It's free; no card.
2. In the Render dashboard, click **New +** → **Blueprint**.
3. Connect/authorize GitHub if asked, then pick the **`Daradicalbanana`** repo.
4. Render finds the `render.yaml` in this repo and shows a service called
   **crunchyroll-schedule**. Click **Apply** (or **Create**).
5. Wait ~2–3 minutes for the first build. When it's done, the service page shows a
   URL at the top: **`https://crunchyroll-schedule.onrender.com`** (the exact name
   may differ).
6. Open that URL on your phone. Tap the browser's **Share → Add to Home Screen**
   to get an app icon.

That's it. Every time you (or I) push to the branch, Render redeploys automatically.

## Notes

- **Free plan sleeps when idle.** The first open after a while takes ~30–50
  seconds to wake up, then it's fast. That's normal for the free tier.
- It shows a **SAMPLE DATA** banner until you add a token (next section).

## Switch to real Crunchyroll data (later)

1. Mint a token: sign up at **animeschedule.net**, then go to
   `animeschedule.net/users/<your-username>/settings/api` → **Create Application**
   → copy the token.
2. In Render: open the **crunchyroll-schedule** service → **Environment** →
   **Add Environment Variable** → key `ANIMESCHEDULE_TOKEN`, value = your token →
   **Save Changes**.
3. Render redeploys; the app auto-switches to live timing (the banner disappears).
   No code change needed.
