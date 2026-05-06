# Personal News & Interest Dashboard

A self-updating personal dashboard. GitHub Actions runs twice a day, fetches RSS
headlines, asks Grok (xAI) for a live freshness briefing, then asks Claude to
write a polished markdown dashboard tailored to your profile. The result is
served by GitHub Pages at your own URL.

A rolling 5-day window is kept — older daily files are deleted automatically.

---

## Setup (≈ 20 minutes, one-time)

### 1. Create a new GitHub repo
Call it whatever you like — e.g. `mynews`. Make it **public** (free GitHub Pages
needs public, unless you have a paid plan).

### 2. Drop these files into the repo
Either upload them through GitHub's web UI ("Add file → Upload files") or
clone the repo locally and copy them in. The structure must look like:

```
mynews/
├── .github/workflows/dashboard.yml
├── config/
│   ├── feeds.txt
│   └── profile.md
├── dashboards/         (will be auto-populated)
├── scripts/build_dashboard.py
├── requirements.txt
└── README.md
```

### 3. Add your API keys as repo secrets
In GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

Add two secrets:

| Name                | Value                                       |
|---------------------|---------------------------------------------|
| `ANTHROPIC_API_KEY` | from https://console.anthropic.com (Claude) |
| `XAI_API_KEY`       | from https://console.x.ai (Grok) — optional |

If you skip `XAI_API_KEY`, the dashboard still runs — Claude alone uses the RSS
feeds. Adding Grok just gives you a live web/X freshness layer on top.

### 4. Allow Actions to push commits back
**Settings → Actions → General → Workflow permissions** → select
**"Read and write permissions"** → Save.

(Without this, the workflow can build the dashboard but can't commit it back.)

### 5. Enable GitHub Pages
**Settings → Pages → Build and deployment → Source: "Deploy from a branch"**
→ Branch: `main`, folder: `/ (root)` → Save.

After 1–2 minutes your site will be live at:
`https://<your-github-username>.github.io/mynews/`

(Optional: point a custom domain like `mynews.com` at it via Cloudflare —
GitHub's docs cover this under "Configuring a custom domain for your Pages site".)

### 6. Trigger the first run manually
**Actions tab → "Daily Dashboard Refresh" → Run workflow → Run workflow.**
Watch it run (≈ 30 seconds). When it goes green, refresh your Pages URL.

From then on it runs automatically at **07:30 and 17:30 UK time** (BST/GMT
auto-handled). You can edit the cron schedule in `.github/workflows/dashboard.yml`.

---

## How to update your interests

Just edit `config/profile.md` (right in GitHub's web UI is fine — pencil icon →
edit → commit). The next run picks up the changes. Same for `config/feeds.txt`
to add or remove RSS sources.

## How to force a refresh anytime

Actions tab → "Run workflow" button. Useful if a big story breaks and you want
the dashboard updated now.

## How the rolling window works

Each run writes `dashboards/YYYY-MM-DD.md`. Multiple runs on the same day
overwrite that one file. Files older than 5 days are deleted automatically.
The landing page (`index.md`) always shows today's dashboard inline with small
links to the previous 4 days at the top.

## Costs

Roughly £2–5 per month total at twice-daily runs (most of it Claude; Grok pricing
varies by tier). GitHub Actions and Pages are free for public repos.

## Troubleshooting

- **Workflow runs but no commit appears** → Step 4 not done (workflow permissions).
- **Workflow fails on the Claude step** → check the secret name is exactly
  `ANTHROPIC_API_KEY` and the key is valid.
- **Pages URL shows 404** → wait 2 minutes after first successful run; check
  Settings → Pages says "Your site is live at...".
- **Want different times?** Edit the two `cron` lines in the workflow file. The
  format is `minute hour day month weekday` in **UTC**.
