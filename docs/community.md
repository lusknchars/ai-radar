# Paperraft community

The reading room at `/community/` links every published paper to its discussion section. Readers use GitHub accounts. Paperraft does not collect passwords, email addresses or profile records. GitHub stores comments, replies and reactions, and repository moderators manage the forum. Public comments remain separate from the paper's editorial and evidence status.

This fits the existing static Vercel and GitHub Pages publication. Discussion data is not written to the research SQLite database and survives site deployments.

## Current configuration

`content/community.json` contains public repository and category IDs. GitHub Discussions is enabled for `lusknchars/ai-radar`. Until the Giscus app is installed, `embedded` remains false and the UI opens the working GitHub forum. It does not show an inactive comment composer.

To activate embedded comments:

1. Install [the Giscus GitHub app](https://github.com/apps/giscus) for only `lusknchars/ai-radar`. It needs access to that repository's discussions.
2. Check the repository configuration at [giscus.app](https://giscus.app/). Confirm the repository and General category match `content/community.json`.
3. Set `embedded` to true, rebuild and deploy. Check one paper while signed out, then sign in with a GitHub test account and verify posting, replying and deleting. Do not post test comments as another person's account.

Readers load the widget explicitly. The local loader requests `https://giscus.app/client.js` only after that action. If the script fails or times out, the forum links remain usable. Giscus handles authentication and comment validation. Its strict mapping uses `arXiv <canonical ID>` so domains, titles and refreshed briefs share the same thread. A thread is created by Giscus when a reader first comments; generating a research page never creates a public post.

If a paper thread was created directly in GitHub before embedded comments were enabled, migrate it using Giscus's documented strict-title hash before activation. Otherwise Giscus cannot recognize it as the same thread. Canonical backlinks point to the production research page even when a reader loads a preview deployment.

`giscus.json` limits embeds to the production domains, this project's Vercel preview URLs and local development. Update the origins when changing domains. Forks do not inherit the community unless their configured repository matches the community file.

## Scope

This version provides public discussions with GitHub identities, replies, reactions and GitHub moderation. The reading-room onboarding explains the three-step path: open GitHub, choose a paper, and share a reproducible observation. It does not provide separate Paperraft passwords, private messages or saved-paper lists. Those features would need a private transactional database and an account service.

The scaling boundary is intentional. Static pages and GitHub Discussions absorb public reading and conversation traffic, while the optional signup service handles only short-lived confirmation records. Its SQLite store enables WAL and a busy timeout for small concurrent bursts. Before a larger subscriber base or multiple service instances, move the confirmation store to managed Postgres, keep the same double-opt-in contract, and add provider delivery metrics. Do not put discussion messages or GitHub access tokens in the research database.

Validation covers stable paper mapping, HTML escaping, configuration isolation, no widget before activation, and browser search and loading failures. An embedded widget cannot be considered live until the GitHub app installation and a real sign-in test succeed.

Provider references: [Giscus setup](https://giscus.app/), [advanced configuration](https://github.com/giscus/giscus/blob/main/ADVANCED-USAGE.md), [GitHub Discussions](https://docs.github.com/en/discussions).
