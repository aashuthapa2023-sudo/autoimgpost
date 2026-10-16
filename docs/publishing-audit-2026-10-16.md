# Publishing audit — October 16, 2026

At 16:28 UTC (22:13 Nepal time), the preceding 24 hours had 54 successful cloud
executions: 48 cronjob dispatches and 6 GitHub scheduled runs. The largest gap
was 30.3 minutes. The preceding 48 hours had 108 successful executions.
Scheduling and Facebook credentials were not the current bottleneck.

Confirmed publications in the preceding 24 hours: Nepal Speaks 23, Ocean's
Secret 9, Hollywood 2, Music Store 2, Netflix 0, Army 0. The other queues were
being exhausted by source/caption/image rejection. Netflix's four remaining
unpublished cached pairs were already about 66–69 hours old.

## Repairs

- Apply the reviewed editorial photo clarity threshold consistently at source
  and retained-photo stages, instead of rejecting clean film stills against a
  separate higher upload threshold. Near-threshold editorial photos must prove
  clear detail at their actual 1080px display width or in the central 70% of
  native pixels. No sharpening or upsampling can create this approval. Grossly
  blurred subjects, blank images, and small source-logo detail cannot qualify.
- Let a tiny reviewed publisher corner expand just enough for the owned
  wordmark within its bounded cover area. Recheck face separation and safe
  lettering bounds after expansion. Retain a recognized publisher seal as an
  extraction anchor even while its own area is reserved for the later cover.
- Honor configured footer-start positions on square source cards. Hollywood's
  reviewed template can begin at 50% height, with native size, retained area,
  publisher evidence and face protection still required. Native body lettering
  above the reviewed footer remains rejected.
- Extend source-based event selection to production status, character looks,
  observed animals, quoted titles, and paired-title announcements. Preserve
  both titles, platform and release date when reducing descriptive lists.
  Reported funding requests retain the speaker, approximate amount, request
  status and full scope; they cannot become approved funding.
- Reject vague narration, anonymous plot hooks and second-person teasers as
  display headlines. Question bait cannot be added as a topic-context fact.
- Add the existing Hollywood Facebook source, What's on Netflix, to Netflix's
  explicit source list with its already reviewed cleanup profile. Both pages
  allow up to four measured lines at the existing readable font minimum.
- Reuse exact cached caption/photo pairs across destinations only when the
  originating Facebook source is explicitly configured for that destination.
  The same complete-pair, 72-hour age and destination-specific duplicate gates
  apply; unrelated sources are never imported.
- Advance quality policy to revision 18 so fixed failures are reconsidered.

Music Store and Netflix still use Facebook images only. No new AI key is
needed. Anisha stays paused. Page intervals, daily caps, confirmed publication
receipts, and per-page duplicate protections are retained.

## Validation and limits

357 Python regressions and GitHub UI-save checks pass and cover source-event extraction,
request attribution, actual image detail, square footer geometry, tiny logos,
publisher anchors, quoted titles and shared-source isolation. Current rejected
source images were downloaded; 16 of 56 pairs passed the current image/caption
and layout checks. Freshness, story/photo dedup and cadence are still applied
separately by the live publisher. Representative repaired posters were
visually inspected. Main-subject watermarks, severe blur and unsafe crops still
fail intentionally.

An interval is a minimum publication gap, not a guarantee of enough new source
material. A Facebook source that stops supplying usable public photo posts
can still leave a page waiting. More frequent triggers cannot create missing
source material, and stale or duplicate posts are not used to fill slots.

## Live verification

Cloud run [38935231033](https://github.com/aashuthapa2023-sudo/autoimgpost/actions/runs/38935231033)
completed successfully against code revision 17463be. All 357 regression tests
passed on Ubuntu as well as locally. Facebook confirmed these new publications:

| Page | Confirmation ID | UTC publication time |
| --- | --- | --- |
| Netflix | 1673448741458010 | 16:55:21 |
| Music Store | 1575298778122334 | 16:55:56 |
| Hollywood | 1565255218949292 | 16:56:12 |
| Ocean's Secret | 122112401403493170 | 16:57:04 |
| US Army Fans | 122149678221353591 | 16:57:33 |

Nepal Speaks respected its interval after its recent publication. Anisha stayed
paused. At 16:57:49 UTC the workflow confirmed that publication state was saved
on the latest main branch. The cronjob and GitHub schedules continue running
in the cloud independently of the user's PC.
