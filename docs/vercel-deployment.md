# Deploying AI Radar to Vercel

The production archive is [paperaft.vercel.app](https://paperaft.vercel.app),
in the `floater/paperaft` Vercel project. The local checkout is linked for CLI
deployments. GitHub Actions can deploy through the CLI using a Vercel access
token; this does not require Vercel's Git integration. The optional Git integration
requires connecting the GitHub account and repository in Vercel.

The Vercel build renders the saved publication database into `dist/` using the
same renderer as GitHub Pages. It serves the archive at `/`, including paper
pages, JSON, RSS, the sitemap, fonts, and social sharing images. Only `dist/`
is public. There are no server functions in this deployment.

Dependencies install into a project virtual environment because Vercel's
system Python is externally managed. The build uses that same environment.

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
page, RSS, search, and the mobile layout. The browser layout check can run
against this URL:

```bash
python scripts/verify_paper_layout.py --origin http://127.0.0.1:8767
```

From a Vercel-linked checkout, `vercel` creates a preview; `vercel --prod`
publishes to the production project. The CLI reads `.vercelignore` to omit local
credentials, evaluations, and databases other than the publication snapshot.
The local `.vercel/` project link is ignored by Git.

## Updating the archive

The collection workflow saves its database and reports before deploying to
Vercel. `scripts/deploy_vercel.py` first checks access to the exact configured
project and team. A rejected credential fails with an explicit error; publication
failures are not silently treated as successful runs. GitHub Pages can still
publish a usable archive after the Vercel step fails.

Store `VERCEL_TOKEN` in GitHub Actions secrets, with access to the `floater`
team and `paperaft` project. Set `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` as
repository variables. Tokens belong in the secret form, never in a command
committed to Git. Vercel documents [team-scoped access tokens](https://vercel.com/kb/guide/how-do-i-use-a-vercel-api-access-token).

To recover a failed deployment, run **Publish Vercel** from the Actions page on
`main`. Its default mode only checks credentials. After that passes, turn off
**Check project access without deploying** to publish the latest saved archive.
Both modes skip discovery, model calls, and notifications. They share the
collector's concurrency group so they wait for an in-progress collection to
finish. A deployment alone does not refresh source data, and builds fail when
the publication database is missing.

Configuration references: [Vercel build settings](https://vercel.com/docs/project-configuration/vercel-json),
[system environment variables](https://vercel.com/docs/environment-variables/system-environment-variables),
and [build image runtimes](https://vercel.com/docs/builds/build-image).
