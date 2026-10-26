# Automated Facebook Content Pipeline

A multi-page publisher with a GitHub Pages control panel. Each destination uses its own sources, editorial topic, palette, language and source-specific text/branding placement.

## How a post is accepted

1. Fetch a source post with its own full caption and associated photo. Topic and language checks run before image processing. Generic web fallback is disabled on the six configured pages.
2. Check native resolution, sharpness and contrast. Thumbnails are not artificially enlarged to pass this check.
3. Detect English/Nepali text across the source. Reviewed publisher frames can be cropped only when the photograph remains usable and faces stay intact. Small corner source credits remain intact; photo headlines and body paragraphs cannot be treated as logos. No broad text/logo inpainting is used. Ocean's Secret uses its configured replacement layout and transparent circular destination logo; an approved source seal must fit entirely behind its opaque circle.
4. Rewrite from the exact paired caption. Reject repetition, page metadata, incomplete hooks and observable changes to names, numbers, species, negation or uncertainty. An invalid AI response moves to another provider; fallback must still be a complete source fact.
5. Render a 1080×1350 editorial card with the full photograph, at most three centered headline lines, readable minimum font sizes and 64px safe margins. Source-specific branding positions reserve space instead of covering the subject.
6. Verify the approved image/caption hashes and layout before upload. Only Meta-confirmed publication updates state and deduplication history.

Ambiguous sources are skipped rather than forced into a scheduled slot. Checks reduce known failures; they cannot guarantee interpretation of every possible image or guarantee viral reach.

## Page settings

`config.json` contains nine destination pages. Each page needs a numeric Facebook destination ID, at least one source page, a `content_topic`, and a page-specific `dest_access_token_env`. Anisha is intentionally paused.

Use the control panel's page/source settings to choose headline and branding positions. **Push pages to GitHub** saves the current configuration to `main`; the GitHub token must have permission to update repository contents. Updating an existing page preserves its detailed styling settings.

The [six-page audit and tuning report](docs/page-quality-audit-2026-10-06.md) documents observed failures, selected styles, verification and live-access limits. In particular, Anisha's configured Facebook session was invalidated and needs reconnection.

## Publishing and diagnostics

- `pipeline_active` controls automated publishing.
- Per-page daily caps default to 15 posts per UTC calendar day.
- Per-page intervals have a minimum of one hour.
- `state.json` stores confirmed posts, cadence and per-page image/story deduplication. `publication_journal.json` records Meta confirmations before the broader state save and replays them idempotently after interruption.
- `quality_report.json` records recent rejected candidates and reasons without tokens.
- Runner logs distinguish unavailable sources, topic rejections, quality retry waits and actual published duplicates. A successful Actions run can still have no eligible post; look for Meta's confirmed publication ID.
- Each current poster has a matching `.quality.json` approval manifest. Older designs are labeled for regeneration in the gallery.
- `queue_worker.py` uses the same checked pipeline for every page. Older queued posters are retained for review and are not uploaded directly.

GitHub Actions runs regression checks before generation/publishing, checks out current `main` when queued work starts, and backs up confirmed receipts and state before pushing. Generated results merge into the latest repository history with normal push retries, preserving publication history when another update lands during the run. Normal posting runs retain the latest scanned feed; manual ingestion honors the selected source and preserves an existing usable feed when that source is unavailable.

The cloud workflow schedules a check every five minutes. Your PC and browser may be off: GitHub-hosted runners perform source ingestion, image generation and publishing using repository configuration and credentials. The local `daemon` and `run_scheduler.bat` modes require the PC to remain on. The cloud workflow does not depend on them.

A check publishes at most one post per page once the full configured rolling interval has elapsed since that page's last confirmed Meta receipt (one hour on most pages, two hours for Army); the cadence gate never permits an early post. New valid Facebook sources, working page credentials and passing image/caption checks are also required. The five-minute schedule checks eligibility frequently, but GitHub can delay or drop scheduled events under load and each run takes time to start and process pages, so actual publication can be later than the exact interval. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). The [October 10 publication audit](docs/publishing-audit-2026-10-10.md) distinguishes runner activity from actual page publications.

## Local use

Install `requirements.txt` in a Python environment. Devanagari rendering requires Windows GDI or Pillow with RAQM; OCR needs its EasyOCR models. Optional provider credentials are `GROQ_API_KEY`, `GEMINI_API_KEY` and `OPENROUTER_API_KEY`.

Store page access tokens only as GitHub Actions repository secrets or local environment variables; never put token values in `config.json`. The workflow maps the nine configured pages to `FB_TOKEN_DAILY_NETFLIX`, `FB_TOKEN_MUSIC_STORE`, `FB_TOKEN_ANISHA`, `FB_TOKEN_DAILY_HOLLYWOOD`, `FB_TOKEN_NEPAL_SPEAKS`, `FB_TOKEN_OCEANS_SECRET`, `FB_TOKEN_US_ARMY_FANS_AI`, `FB_TOKEN_LIFE_IN_ARMY_BOOTS`, and `FB_TOKEN_GUARDIANS_OF_LIBERTY`. Each secret must be added in the repository settings. New pages can use `FB_TOKEN_DEFAULT` (also add that repository secret), or a page-specific name that is explicitly mapped in `.github/workflows/pipeline.yml`. A page saved only in browser storage does not reach scheduled runs: use **Push pages to GitHub** and confirm the save succeeds. Missing credentials never fall back to another page's token.

```sh
python -m unittest discover -s tests
node tests/test_github_save.js
python main.py dry_run all
python server.py
```

A dry run creates accepted previews without Facebook uploads or published-state changes. Design-only proofs do not have source approval and cannot pass the upload gate.
