# Publishing audit — October 13, 2026

## Why publication had gaps

At 06:57 UTC (12:42 Nepal time), GitHub recorded 51 successful executions in
24 hours and 106 in 48 hours. The largest trigger gap was 30.3 minutes. The
external cronjob and GitHub schedule were reaching the cloud runner. They do
not require the PC to remain on.

Actual page publications in the preceding 24 hours were Netflix 1, Music Store
3, Hollywood 3, Nepal Speaks 22, Ocean's Secret 5, and Army 0. Source/caption
rejections exhausted several pages' queues. A successful workflow is not proof
that every page published.

## Shared repairs

- Measure exactly the uppercase/highlight display tokens used by the final
  renderer. Previously lowercase previews could accept a headline that later
  failed at readable type size. Both standard and ocean replacement layouts
  now use the same display tokenization for preview and rendering.
- Honor up to four configured headline lines within the existing height and
  font limits. Music Store now permits four lines; Army's existing four-line
  setting is honored. Text is never shrunk below the readability threshold.
- Extract complete named event clauses from source captions, retaining names,
  species, dates, numbers, attribution, and uncertainty. Remove optional comma
  tails only when they contain no qualification or negation. Keep the full
  supporting source sentence once in the caption, rather than padding it with
  repeated prose. Anonymous sequels and question teasers cannot become hooks.
- Recognize inline Billboard 200/Hot 100 chart facts, R&B tour news, and military
  aviation context. Category hashtags alone still cannot establish a topic.
- For Billboard's reviewed top-left publisher corner, use a small opaque owned
  wordmark cover instead of a full-height edge crop. Protect frontal face
  features; leave native photo pixels untouched until after clarity and dedup
  checks. Verify the reviewed image hash, full logo coverage, face separation,
  and safe wordmark bounds before publishing.
- For Hollywood's configured source, preserve complete released film-poster
  artwork only when its recognized title matches its exact caption and all
  other detected lettering is conventional artwork text. Unknown publisher
  watermarks, clipped titles, and unrelated artwork remain rejected. Fit the
  intact artwork in 1080×1350 with one owned masthead and no second headline.
  Remove stale relative trailer teasers from its caption.
- Advance the quality policy to revision 17 so prior false rejections are
  reconsidered by the cloud without changing posted IDs or duplicate hashes.

The user chose source-based rewriting. No new AI service/key is required.
Anisha remains paused. Music Store and Netflix retain Facebook-source-only
images. Existing page intervals and daily caps are preserved.

## Validation

345 Python regression tests and the GitHub UI save tests pass. Fifteen new
tests cover complete clauses, qualification/negation, source context,
attribution, species, actual display width, four-line fitting, localized logo
coverage, face protection, image-hash changes, and safe poster preservation.

The current 27 downloaded source pairs were rechecked against native clarity,
source extraction, topic gates, caption generation, exact final typography,
and publication manifests. Ten previously rejected, unpublished candidates
now pass across Netflix, Music Store, Hollywood, Ocean, and Army. A further
renderable music photo was already published and remains excluded by dedup.
Representative final images were visually inspected.

Genuine low-detail source photos, lettering over the main subject, central
watermarks, missing caption context, unrelated topics, and duplicates still
fail. Source availability can limit an individual page's hourly/2-hourly
cadence even when the cloud timer is healthy.

Live cloud verification is recorded below after deployment.
