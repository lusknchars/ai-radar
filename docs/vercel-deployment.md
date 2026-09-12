# Deploying AI Radar to Vercel

The Vercel build renders the saved publication database into `dist/` using the
same renderer as GitHub Pages. It serves the archive at `/`, including paper
pages, JSON, RSS, the sitemap, fonts, and social sharing images. Only `dist/`
is public. There are no server functions in this deployment.

The build uses a temporary SQLite snapshot. It does not change the committed
database, collect papers, call an LLM, send notifications, or rent GPUs. The
collection status in the database remains visible, including sample mode.

## Import the repository

1. Import `lusknchars/ai-radar` into the intended Vercel team.
2. Use the repository root and the `main` production branch. Framework is
   **Other**. The checked-in `vercel.json` sets installation, build, and output.
3. Add the domain under **Project settings → Domains** and follow Vercel's DNS
   instructions for that hostname.
4. Set `RADAR_SITE_URL` to the full preferred URL, such as
   `https://radar.example.com`, for production and preview. Use a root domain or
   subdomain, without a path. Redeploy after changing it.

If `RADAR_SITE_URL` is absent, the build uses
`VERCEL_PROJECT_PRODUCTION_URL`, then `VERCEL_URL`. Keep Vercel's system
environment variables enabled. An explicit URL avoids canonical links changing
if another custom domain is added. Preview builds include `noindex` metadata
and a robots file that disallows crawling.

Do not set LLM, Telegram, GPU, or newsletter delivery credentials for this
static project. `RADAR_SUBSCRIBE_URL` is optional and must point to an already
working HTTPS signup service. The private newsletter service needs separate
hosting and persistence; this deployment does not enable it.

## Verify locally

With Python 3.12+ and the project installed:

```bash
RADAR_SITE_URL=https://radar.example.com python scripts/build_vercel.py
python -m http.server 8767 --bind 127.0.0.1 --directory dist
```

Open `http://127.0.0.1:8767/`. Check a paper link, its JSON link, the methodology
page, RSS, search, and the mobile layout. For the current 20-paper sample, the
existing Playwright check can run against this URL:

```bash
python scripts/verify_newsletter_browser.py --url http://127.0.0.1:8767/
```

From a Vercel-linked checkout, `vercel` creates a preview; `vercel --prod`
publishes to the production project. The CLI reads `.vercelignore` to omit local
credentials, evaluations, and databases other than the publication snapshot.
The local `.vercel/` project link is ignored by Git.

## Updating the archive

The existing collection workflow remains in GitHub Actions. Vercel rebuilds
from `data/radar-state.db` and committed `reports/` when the connected production
branch changes. If the Git integration does not trigger for an automated digest
commit, redeploy the latest commit from Vercel. A deployment alone does not
refresh the source data. Builds fail if the publication database is missing.

Configuration references: [Vercel build settings](https://vercel.com/docs/project-configuration/vercel-json),
[system environment variables](https://vercel.com/docs/environment-variables/system-environment-variables),
and [build image runtimes](https://vercel.com/docs/builds/build-image).
