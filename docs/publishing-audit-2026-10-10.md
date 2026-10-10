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

The currently rejected Army source has an unrecognized detector mark in its photograph. The Taylor Swift source has a large publisher seal overlapping the portrait area. These were not excused by the headline repairs. Regular slots still depend on enough new, usable configured source photos; a schedule cannot make an unusable source acceptable.
