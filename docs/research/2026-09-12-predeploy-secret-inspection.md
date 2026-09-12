# Paperraft pre-deployment inspection

Inspection performed on 2026-09-12 before deploying the action transitions.

## Findings

- GitHub repository `lusknchars/ai-radar` is public. Secret scanning and push
  protection are enabled. The secret-scanning alerts API returned no alerts.
- No Actions secrets were listed at the repository level or in the `kimi`
  environment. This is not a check of local or Vercel secret values.
- Only `.env.example` is tracked among `.env*` files. Local environment files,
  private directories, and Vercel credentials are excluded by ignore rules.
- Gitleaks v8.30.1 scanned all locally available Git refs with `--log-opts=--all`:
  143 commits examined, approximately 11 MB, zero detections. The repository has
  154 reachable commits including merges; scanner counts differ from Git totals.
- Gitleaks scanned the generated `dist/` tree with archive inspection enabled,
  including the skill ZIPs: approximately 1.71 MB, zero detections.
- The Vercel build generates a static archive. It does not call the report model
  or copy local environment files into the public output.
- The reviewed GitHub workflows reference Actions secrets for model calls; the
  test workflow does not inject API keys. No `pull_request_target` trigger was
  found. The report workflow requires the repository owner's request or approval.

These checks detect known secret patterns and inspect configuration. They do not
prove that every credential format is covered, validate credential liveness, or
inspect deleted remote history, private local files, or hosted environment values.
No secret values were printed, transmitted to a model endpoint, rotated, or removed.

No tool named Ripple or skill named transition was found in the installed skill
catalog. The requested Ripple tool name remains unconfirmed. Gitleaks and the
GitHub API were used for this inspection; native CSS supplies the transitions.

## Repeat before deployment

With Gitleaks v8.30.1 available locally, run from the repository:

```bash
gitleaks git --redact --no-banner --log-opts=--all .
RADAR_SITE_URL=https://paperaft.vercel.app .venv/bin/python scripts/build_vercel.py
gitleaks dir --redact --no-banner --max-archive-depth 2 dist
```

The UI changes are prepared for deployment after this inspection. This task did
not trigger a production deployment.
