# Cloud publication audit, October 10, 2026

Snapshot: October 10 at 15:16 UTC / 21:01 Nepal time. Read-only GitHub API audit of the preceding 24 hours and the confirmed publication ledger.

The workflow was active. All 55 observed pipeline runs completed successfully: 50 workflow dispatches and 5 native scheduled runs. The largest gap between run start times was 30.2 minutes. The origin of the recurring dispatches was not established by this audit; native GitHub scheduling remains independent of the user's PC.

| Active page | Confirmed publications in the preceding 24 hours |
| --- | ---: |
| Nepal Speaks | 10 |
| Ocean's Secret | 10 |
| Daily Hollywood | 3 |
| Music Store | 2 |
| Daily Netflix | 2 |
| US Army Fans | 1 |

Anisha remained paused as requested. A green workflow means the runner completed its checks, not that each page published a post. Latest audited run: [38061907465](https://github.com/aashuthapa2023-sudo/autoimgpost/actions/runs/38061907465). Ocean's Secret published in that run; other active pages encountered quality waits or exhausted eligible sources.

## Repairs verified against rejected sources

- Daily Netflix source `1118640433855751`: select the full named renewal event before the comparison with another season's premiere. Previously it selected an overlong secondary sentence beginning “Season 3” and failed layout. The repaired headline includes THE HUNTING WIVES, Season 3 and Netflix, at 94px type.
- Daily Hollywood source `1567985788676075`: keep the complete release-date clause, including November 12, 2026 and Never Surrender. Keep the cast/synopsis detail in the caption. Repaired poster uses 86px type.
- Music Store source `1471081868225720`: a complete hook for a sourced critics' ranked list is available even when the associated photograph contains no text. Fact validation previously split the plural acronym VMAs into a nonexistent VM token and rejected the original caption itself. Whole-word name checks preserve invented-name rejection. Repaired poster uses 94px type.
- Caption generation uses original full source sentences once, with the selected fact's sentence first when available. It does not prepend a shorter version of the same sentence to create redundant padding.

All three previews passed the existing resolution/sharpness, source extraction, caption approval and 1080×1350 poster gates. Photos were inspected visually. The unchanged safety gates still reject uncertain lettering over a subject, graphics that would require cropping a face, and stale/duplicate sources. Policy revision 12 allows previously rejected candidates to be reconsidered under the repaired caption rules without clearing publication history.

At that snapshot, the Army source still had an unrecognized detector mark in its photograph. The Taylor Swift source has a large publisher seal overlapping the portrait area. These were not excused by the initial headline repairs. Regular slots still depend on enough new, usable configured source photos; a schedule cannot make an unusable source acceptable.

## Quality recovery follow-up

Eight additional rejected Facebook caption/photo pairs were replayed with their actual OCR evidence. All passed retained-photo quality, caption, source coverage and poster approval at 1080×1350. Their previews were inspected visually; type ranges from 72 to 94px. Resolution and sharpness thresholds remain unchanged.

| Page | Source post | Repair |
| --- | --- | --- |
| US Army Fans | 1571452095015915 | Trim a 63px left edge detector hit and the original footer; keep the people and carrier. Hook names USS Abraham Lincoln and its 322-day absence. |
| Daily Hollywood | 1568994228575231 | Trim a 77px edge containing a partial photographed sign; preserve the characters. Hook keeps Ray Gunn, Brad Bird, Netflix and December 18, 2026. |
| Daily Netflix | 1119440090442452 | Use the exact caption's complete Bridgerton romance fact when footer OCR is uncertain. |
| Daily Netflix | 1119614170425044 | Keep Gene Simmons's opinion attributed to him; remove excess commentary from the hook. |
| Music Store | 1471481508185756 | Keep the repeated physical TIFF sponsor wall intact; use a complete tour hook and one distinct caption fact. |
| Ocean's Secret | 122119506615320544 | Crop the detected header, retain the whale photo and add the owned bottom panel and circular transparent logo. Preserve the source's event date and approximate weight. |
| Ocean's Secret | 122119559067320544 | Crop the detected header; use the caption's complete reported beluga death/location fact. |
| Ocean's Secret | 122123046069298539 | Recognize beluga as a marine species and keep the approximate two-month timeline and named aquarium. |

Side crops are opt-in for reviewed sources, limited to 8% per edge and 12% total, and cannot cut a detected face. The TIFF exception requires at least eight small recognized physical labels, three brands, four TIFF labels and multiple vertical bands. Unknown recognized words, unexplained central detector rows and a lone publisher logo still fail review. Ocean header extraction requires every source text region to lie outside the retained crop; that proof is checked before publication.

Replacement quality now measures the visible native photograph rather than the sharp source footer that will be covered. Caption fallbacks preserve complete supporting sentences without repeating a source title or padding the caption with promotional review text. Proper-name possessives no longer produce false fact-validation failures; invented names and new numeric facts still fail. Policy revision 13 reconsiders prior false rejections without clearing duplicate/publication history.

The full-page Bridgerton announcement letter, the Taylor Swift portrait with a large overlapping seal, and genuinely blurry or centrally watermarked sources remain unsuitable for a clean photo poster. The engine continues checking other candidates and pages when a source fails. Anisha remains paused.

Validation: 309 Python tests, the GitHub UI save/pending-page tests, and the eight real-source poster replays.
