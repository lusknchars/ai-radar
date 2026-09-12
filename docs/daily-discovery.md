# Daily paper discovery

## Expanded research round

Manual runs can select the `expanded` profile. Scheduled runs keep the daily profile.

| Limit | Daily | Expanded |
| --- | --- | --- |
| Exa searches | 2 | Up to 6, splitting each scope's terms into distinct queries |
| Results per search | 10 by default | 15 |
| Exa publication window | 30 days | 90 days |
| New briefs attempted | Up to 40 | Up to 60 |
| Full-paper reports | 0 | Up to 3 |
| Workflow time limit | 45 minutes | 120 minutes |

These are maximum attempts, not promised publication counts or dollar-spending limits. Existing arXiv, relevance and evidence requirements still apply. One failed Exa query does not prevent the remaining queries from running.

After collection, the expanded round selects recent actionable briefs from different research areas. It reads the original full texts through the existing source-grounded report generator and preserves source hashes, excerpts, limitations and unanswered checks. It does not reproduce the experiments. Reports already on disk are skipped before the limit is applied. Failed reports return a nonzero status; the workflow records incomplete analysis and preserves successfully generated reports.

Queued runs resolve the branch when the job starts, so they see state saved by the previous collection. They share the existing serialization group.

```sh
gh workflow run radar.yml --repo lusknchars/ai-radar -f profile=expanded -f exa_mode=daily
```

Preview the report shortlist locally without model calls:

```sh
.venv/bin/python scripts/deepen_shortlist.py --db data/radar-state.db --plan
```

The radar workflow requests a run daily at 09:17 UTC, 06:17 in Brasilia. GitHub scheduled jobs can start later than the requested time. Manual runs use the same concurrency group, so two collectors cannot write the publication database simultaneously.

## Discovery and publication

1. Query arXiv for the existing inference and agent research scopes. Retry transient transport errors, rate limits and selected server errors up to three attempts, with increasing waits.
2. When EXA_API_KEY is configured, run one Exa search per scope. Default: two searches per daily collection, ten results each, with a 30-day publication window. No content extraction or synthesized answer requests are sent to Exa.
3. Accept only arxiv.org paper URLs, normalize versioned IDs and deduplicate against arXiv discovery. Resolve every new ID through the official arXiv feed. Exa titles and summaries never become paper metadata or scientific evidence. Recheck categories and publication dates against that feed.
4. Apply the existing relevance, repository-signal and judgment pipeline. The new-paper limit remains 20 per scope. Search results are candidates, not automatically published briefs. Exa errors preserve the arXiv results and mark the collection partial.
5. Generate previews for newly published papers, regenerate the site and skill downloads, and commit the resulting state. Missing thumbnails retain original-paper links.
6. Publish GitHub Pages through the existing job. Publish Vercel too when its credentials are configured.

The homepage banner has been removed. `/collection.json` records actual collection status and the last successful run separately from the page publication date. Removing the banner does not change sample data into fresh research.

## Activation

In GitHub repository settings, add Actions secrets via the secure form or interactive CLI prompts:

```sh
gh secret set KIMI_API_KEY --repo lusknchars/ai-radar
gh secret set EXA_API_KEY --repo lusknchars/ai-radar
```

Never commit keys or send them in chat. Repository secrets are available to the `kimi` job environment unless overridden there. Exa alone cannot produce the current structured briefs; the selected LLM provider also needs its key.

Default `RADAR_COLLECTION_MODE=auto` collects live when the LLM key exists and otherwise republishes stored data without network requests. Explicit `live` mode now fails without that key instead of silently publishing samples. An existing repository variable set to `sample` still overrides the default; change it to `auto` or `live` when activating.

The default `RADAR_EXA_MODE=daily` can be overridden with `weekly` for Mondays only or `off`. `RADAR_EXA_RESULTS` accepts 1–25 results per search. The request count is bounded, but it is not a dollar-spending cap; check the Exa account's plan and billing controls.

For automatic Vercel publication, add the `VERCEL_TOKEN` Actions secret and `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` repository variables from the Vercel project. Without them the workflow records that automatic Vercel deployment is unconfigured; it does not claim the Vercel site was refreshed.

After configuring credentials, start a run:

```sh
gh workflow run radar.yml --repo lusknchars/ai-radar -f exa_mode=daily
```

Inspect the run outcome and `/collection.json` before claiming freshness. The CLI's `--dry-run` is not a no-cost network simulation: with live credentials it can still query providers. Offline tests use injected transports.

API contract checked against [Exa Search reference](https://exa.ai/docs/reference/search) and [Exa's coding-agent API guide](https://exa.ai/docs/reference/search-api-guide-for-coding-agents).

## Validation on 2026-09-12

The offline suite passed, including injected Exa responses, canonical source validation, deduplication, missing metadata, stale results and fallback behavior. Retry behavior was checked separately with transient and permanent HTTP failures. A live arXiv metadata probe exhausted its retry budget with HTTP 429; no new corpus was published from that probe. Exa and model calls were not made because activation credentials were not configured. These checks validate the implementation, not end-to-end live discovery quality.
