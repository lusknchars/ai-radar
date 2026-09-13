# Newsletter foundation

AI Radar serves engineers deciding which inference and agent papers deserve a
closer look. The first publication is a weekly English email containing up to
five relevant papers published during the previous Monday-to-Sunday window.
The site continues to publish the complete archive daily.

For local reading, run `python -m radar.preview` and open
`http://127.0.0.1:8766/`. The server redirects to the configured publication
path and serves article pages and assets there. A plain `http.server` rooted
at `site/` does not provide the `/ai-radar/` mount used by generated links.

The application collects and judges each paper centrally. The newsletter uses
the stored brief, so adding readers does not add model calls. The website has
separate recent-paper and independent-implementation selections. Recent papers
need no independent implementation to qualify. Out-of-scope recommendations
are excluded from both selections and from the newsletter, while remaining
visible in the complete archive.

The current architecture is:

```text
arXiv / GitHub / OpenAlex -> Python collection -> public research SQLite
                                                    |
                              +---------------------+------------------+
                              |                                        |
                        static website                         weekly email draft
                              |                                        |
                        signup service                         Resend Broadcasts
                              |                                        |
                   private confirmation SQLite -> confirmed contacts --+
```

Collection runs now have their own status. Page publication never creates a
successful collection. Sample mode is labelled, and an unsuccessful attempt
preserves the last successful collection date. Collection failures and partial
upstream coverage produce a nonzero exit status; an intentionally configured
sample publication can succeed. The public-research evaluation remains separate:
it still requires deep reports and reader-study results before its release gate
can pass.

Telegram messages go through a persistent outbox. The pipeline records local
publication, and the CLI records external delivery only after Telegram accepts
the message. Pending messages survive ordinary failed runs and are retried even
when their papers are already known. An API timeout after remote acceptance can
still lead to duplicate delivery, because Telegram has no application-provided
idempotency key. GitHub runners must commit the state after the run; a runner
lost before that commit can also lose its latest checkpoint. This remains a
single-writer deployment, not a distributed delivery system.

The 20 sample briefs have reviewed English translations in the corpus
checkpoint. Their classifications and numeric fields are preserved. The
`editorial_translation` metadata identifies the text edit separately from the
original Kimi judgment. Apply these translations to existing state without
calling a model:

```bash
python scripts/english_briefs.py --db data/radar-state.db --apply-checkpoint --publish
```

To enable live collection after deploying this branch:

1. Keep `KIMI_API_KEY` in the existing `kimi` GitHub environment. The daily job
   now uses that environment. Confirm any environment deployment rules permit
   the intended schedule.
2. Set the repository variable `RADAR_COLLECTION_MODE=live`. Its Actions
   default remains `sample`. A requested live run without a usable key fails
   and publishes an honest collection-status notice.
3. Use `RADAR_DB=data/radar-state.db`, the current-schema archive, rather than
   the historical `data/radar.db`.
4. Start with `RADAR_MAX_NEW_PER_SCOPE=20` and
   `RADAR_MAX_EQUATIONS_PER_RUN=5`. That bounds a daily run to at most 40 new
   brief judgments across the two scopes and five equation selections, before
   adapter retries. These are call-count limits, not a currency budget. The
   recheck path reuses judgments. Deferred new papers are counted and remain
   eligible for later discovery within arXiv's search window.
5. Run the workflow manually, then inspect its collection status, output,
   provider usage, and pending delivery state before relying on the schedule.

Weekly drafts are deliberately reviewable. On Mondays the newsletter workflow
builds the previous week's issue, preserves its HTML, plain text, and JSON, and
makes them available as a GitHub artifact. It does not send an email. Production
drafts reject sample or incomplete collection state and untranslated briefs.
No qualifying papers means no draft; a short week is not padded with old papers.
An existing issue cannot silently change under the same filename.

```bash
python scripts/prepare_newsletter.py --db data/radar-state.db
# Offline, visibly labelled sample for reviewing the email layout:
python scripts/prepare_newsletter.py --db data/radar-state.db \
  --week-ending 2026-08-30 --preview --out /tmp/radar-newsletter-preview
# With Resend configured, upload a production issue as a draft, without sending:
python scripts/prepare_newsletter.py \
  --upload-draft newsletter/ai-radar-week-2026-09-13.json
```

The Resend adapter uses the current Contacts, Segments, and Broadcasts APIs.
The first newsletter uses one dedicated segment. A stable issue name allows a
retry to recover an existing provider draft. Serialize draft uploads; the
provider lookup is not a lock against simultaneous independent clients. The
email includes Resend's unsubscribe link. Review and send the first editions
from the Resend dashboard, using its delivery and click reporting.

The signup service is a separate optional Python process. It presents an email
form, requires affirmative consent and a server-validated Turnstile challenge,
sends a confirmation email, and only adds a contact after an explicit
confirmation POST. A GET from an email scanner changes nothing. Confirmed-token
replays cannot restore a later unsubscribe. Confirmation requests expire after
24 hours; subsequent signup requests clean up expired rows. A confirmed
request immediately loses its stored email address. Resend owns the ongoing
subscriber list and unsubscribe status.

Configure these server values:

| Setting | Value |
| --- | --- |
| `RADAR_SIGNUP_ORIGIN` | HTTPS origin of the signup service, without a path |
| `RADAR_EMAIL_FROM` | Sender at a domain verified in Resend |
| `RESEND_API_KEY` | Private key with contact and broadcast access |
| `RESEND_SEGMENT_ID` | Dedicated AI Radar weekly-reader segment |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Widget configured for the signup hostname |
| `RADAR_SUBSCRIBER_DB` | Absolute private SQLite path outside the repository, on a persistent volume |

```bash
pip install -e '.[newsletter]'
uvicorn radar.subscriptions:create_app --factory --env-file .env \
  --host 127.0.0.1 --port 8000 --no-access-log
```

`Dockerfile.signup` packages the same service as a non-root process. Mount a
private persistent volume at `/var/lib/ai-radar`, supply the settings through
the host's secret configuration, and terminate HTTPS at the hosting proxy.
Use one service instance for this SQLite deployment. Configure
`FORWARDED_ALLOW_IPS` for the actual trusted proxy addresses so rate limits see
the originating client; do not trust arbitrary public forwarded headers.
Proxy access logs must also omit confirmation query tokens.

After verifying signup, confirmation, and unsubscribe against the real domain,
set `RADAR_SUBSCRIBE_URL=https://YOUR-SIGNUP-HOST/subscribe` for the static-site
publisher. Until then, the site explicitly says email signup is not open and
offers RSS. No API key or subscriber data is embedded in the static pages.

The first reader test should cover four weekly editions with a small group of
engineers. Record useful-paper feedback, repeat clicks, and actual attempts to
try a technique. The existing five-reader research-page study is still needed
to validate the deeper report format. Reader recruitment, production signup
hosting, DNS verification, and live email delivery are not completed by the
local implementation.

The [community](community.md) now uses GitHub accounts for public paper discussions.
Separate Paperraft email accounts, saved papers, topic-specific editions, automatic bulk sending, and
paper-version-aware regeneration remain later work. Existing deep reports are
still reused by canonical arXiv ID; this change does not claim to detect and
regenerate analyses when arXiv publishes a new version. Move operational state
to a private transactional database when interactive or concurrent writers
are introduced. Reader traffic alone does not query the current SQLite store.

Provider references checked during implementation:
[Resend Broadcasts](https://resend.com/docs/api-reference/broadcasts/create-broadcast),
[Contacts](https://resend.com/docs/api-reference/contacts/create-contact),
[segment membership](https://resend.com/docs/api-reference/contacts/add-contact-to-segment),
[Turnstile verification](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).
