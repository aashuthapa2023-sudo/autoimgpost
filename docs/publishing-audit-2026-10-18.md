# Publishing regularity audit — 18 October 2026

At 16:38 UTC, GitHub had completed 56 successful publisher runs in 24 hours
(48 external cron dispatches and 8 GitHub scheduled runs). The longest trigger
gap was 30.3 minutes. The cloud schedule was operating while Music Store had
published no images in that window; its last receipt was 17 October at 02:05 UTC.
Daily Netflix and Daily Hollywood each had one publication, Nepal Speaks 14,
Ocean's Secret 7, and Army 1. A green scan was not evidence of publication.

## Repairs

- Hourly pages now use confirmed receipts and clock-hour slots, with a 45-minute
  spacing guard and at most one publication per run. This avoids missing a rolling
  58-minute gate because setup or processing finishes a few seconds later.
  Existing daily caps, workflow concurrency, receipt journaling, duplicate checks,
  and Army's two-hour interval remain in force. Anisha remains paused.
- Music Store explicitly covers US entertainment: music, film, television and
  celebrity culture. Artist-name stories no longer require the literal word
  "music". Unrelated crime, military, animal, hiring, finance and shopping stories
  do not qualify merely by being carried by a broad entertainment publisher.
- Added verified Facebook feeds from Variety, People, E! News and Entertainment
  Weekly for Music Store; Variety and Entertainment Weekly for Hollywood;
  Netflix Life for Daily Netflix; and the official US Army
  feed for Army. Deeper discovery checks past rejected/consumed feed entries.
  Music Store and Daily Netflix retain Facebook-only imagery.
- Music Store captions can retain up to 160 words of distinct source detail,
  with a separate lead paragraph. Short sources stay short. Duplicate title/body
  facts, incomplete quoted passages, source promotions, link teasers and camera
  credits are removed. No AI key is required and no supporting facts are invented.
- New Music Store treatment: sentence-case headlines, large centered type, a dark
  navy panel, restrained gold accent and a US entertainment edition label. Preview
  measurement uses the same casing as the final renderer. Output remains 1080×1350.
- Anonymous quoted fragments and vague teaser hooks are blocked. Concrete named
  source events take priority. A named Netflix season can resolve its immediately
  following nominal reference without implying a subsequent renewal. Ocean hooks
  prioritize the actual marine event rather than geographic background.
- Native photo selection chooses the largest declared image variant from the
  same Facebook Photo object, retaining its exact photo ID. It never substitutes
  a link preview or an unrelated album photograph.
- Corrected overescaped source-credit expressions. Reviewed Ocean header crop
  increased from 34% to 36% for a source whose lettering ends at 35%, preserving
  the rescue photograph and rejecting any remaining subject lettering.

## Validation before deployment

377 Python tests pass, including 20 new checks for cadence jitter, same-hour
deduplication, spacing, detailed captions, anonymous hooks, quoted movie titles,
source topic filtering, native photo identity and measured image layout.
The Git UI save/permission/pending-page tests pass, and the diff has no whitespace errors.

Reviewed 87 real source pairs with OCR, native photo checks, headline generation,
rendering and final image manifests. Thirteen rendered successfully: nine Music
Store, one Netflix, one Hollywood, one Ocean and one Army. These are rendering
proofs, not publication promises: one music example was already published, and
live freshness, duplicate, topic and receipt checks still apply. Rejected blurred
images and unexplained watermarks were not forced through.

## Operational limits

The engine and backup cron dispatch run in the cloud; the PC is not needed.
One intended slot per hour does not guarantee a publishable new Facebook photo
every hour. Source outages, short teasers, native blur, duplicate stories, daily
caps or a Facebook API rejection can still leave a slot empty. US English and
entertainment coverage shape the content; organic geographic reach is determined
by Facebook, not guaranteed by a caption or page setting.

Live deployment verification will be recorded after the all-page cloud run.
