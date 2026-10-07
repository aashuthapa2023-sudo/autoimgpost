# Automated Facebook Content Pipeline

A multi-page publisher with a GitHub Pages control panel. Each destination uses its own sources, editorial topic, palette, language and source-specific text/branding placement.

## How a post is accepted

1. Fetch a source post with its own full caption and associated photo. Topic and language checks run before image processing. Generic web fallback is disabled on the six configured pages.
2. Check native resolution, sharpness and contrast. Thumbnails are not artificially enlarged to pass this check.
3. Detect English/Nepali text across the source. Extract a photograph only from a separable solid source panel. Small corner source credits remain intact; photo headlines and body paragraphs cannot be treated as logos. No broad text/logo inpainting is used. Ocean's Secret may preserve a readable original card intact, with one page-brand footer and no additional headline, when its existing lettering matches the exact caption.
4. Rewrite from the exact paired caption. Reject repetition, page metadata, incomplete hooks and observable changes to names, numbers, species, negation or uncertainty. An invalid AI response moves to another provider; fallback must still be a complete source fact.
5. Render a 1080×1350 editorial card with the full photograph, at most three centered headline lines, readable minimum font sizes and 64px safe margins. Source-specific branding positions reserve space instead of covering the subject.
6. Verify the approved image/caption hashes and layout before upload. Only Meta-confirmed publication updates state and deduplication history.

Ambiguous sources are skipped rather than forced into a scheduled slot. Checks reduce known failures; they cannot guarantee interpretation of every possible image or guarantee viral reach.

## Page settings

The six profiles in `config.json` are Daily Netflix, Music Store, Anisha, Daily Hollywood, Nepal Speaks and Ocean's Secret. Each includes `content_topic`, `editorial_style`, `poster_style`, and `source_layouts`.

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

## Local use

Install `requirements.txt` in a Python environment. Devanagari rendering requires Windows GDI or Pillow with RAQM; OCR needs its EasyOCR models. Optional provider credentials are `GROQ_API_KEY`, `GEMINI_API_KEY` and `OPENROUTER_API_KEY`.

Set each destination's `dest_access_token_env` to its own environment/Actions secret name. Ocean's Secret uses `FB_TOKEN_OCEANS_SECRET`. A missing credential never falls back to another page's token.

```sh
python -m unittest discover -s tests
node tests/test_github_save.js
python main.py dry_run all
python server.py
```

A dry run creates accepted previews without Facebook uploads or published-state changes. Design-only proofs do not have source approval and cannot pass the upload gate.
