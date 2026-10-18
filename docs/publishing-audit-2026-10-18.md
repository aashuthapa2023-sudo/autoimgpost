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

## Live deployment verification

Run [39148940557](https://github.com/aashuthapa2023-sudo/autoimgpost/actions/runs/39148940557)
passed its 375 tests at revision 05889ac and confirmed four new publications:

| Page | Facebook photo receipt | UTC time |
| --- | --- | --- |
| Daily Netflix | 1675517351251149 | 17:23:15 |
| Music Store | 1577356797916532 | 17:25:00 |
| Daily Hollywood | 1567261375415343 | 17:25:33 |
| Ocean's Secret | 122113140789493170 | 17:26:26 |

Facebook's page feed independently confirmed Music Store's post with a 140-word
caption. Its Facebook-served image was visually checked at 720×900 (4:5); the
stored original is 1080×1350. Publication state was saved on latest main at
17:27:11 UTC. Nepal respected its interval; Anisha remained paused.

Army's public Facebook feeds were unavailable from this GitHub runner. Its two
older cached photos were correctly rejected for severe native blur. Four exact
official-source photo/caption pairs captured during this audit were therefore
retained in the existing 72-hour source cache, including the tested fast-roping
photograph. This is a bounded source recovery, not permission to publish blurred
images or a guarantee of future Facebook feed availability.

Final source/teaser refinements at 594f32f pass 377 local tests. A subsequent cloud
check will verify those refinements and the recovered Army source queue.
