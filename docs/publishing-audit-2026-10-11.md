# Regular publication repair, October 11, 2026

At 15:13 UTC the preceding 24 hours contained 55 successful cloud runs (50 dispatches and five native scheduled runs). The largest trigger gap was 30.2 minutes. Publication counts were Netflix 3, Music Store 4, Hollywood 2, Nepal Speaks 4, Ocean's Secret 7 and Army 1. Anisha was paused. Green workflow status concealed empty or rejected per-page queues; it did not confirm a publication.

## Changes

Discovery now targets four available recent pairs per configured source, combining the landing feed, both public posts routes and a bounded mobile feed scan. Candidates waiting on quality checks are excluded from discovery selection without being marked as published. Mobile scanning stops after four scrolls or two unchanged snapshots. New DOM discoveries require a same-source Facebook permalink; hydration still verifies source actors and exact same-story caption/photo attachments. Freshness, duplicate checks, source restrictions and the publication journal remain in place.

Headline selection measures the actual renderer's glyphs and limits before choosing a candidate. The local fallback supplies complete supported hooks for the blocked chart, marine, relief and missile-contract stories. Vague introductory prose is excluded. Optional rewrite providers receive a shorter-word budget and the same fit check; no provider keys were configured in this audited runner. Unsupported or unfitting text still fails closed. Source review promotion is excluded from our captions.

Billboard's reviewed template may trim a corner strip up to 16% when a full-width header crop would cut a face. All detected faces must remain inside the retained native photograph, and at least 80% of its width must remain. Ordinary edge crops remain limited to 8%. No inpainting, invented backgrounds or subject wiping is introduced.

A near-threshold extracted portrait can qualify through native face detail when its background is intentionally soft. Its overall sharpness must be at least 75% of the normal threshold; every detected face must be at least 120 native pixels across, have sufficient contrast and exceed 140% of the normal sharpness threshold. The raw-image check is unchanged. This recovers the reviewed Animals frame (overall 32.3, native face 52.2) without accepting the heavily blurred Netflix or Nepal sources.

Policy revision 15 permits review under these actual repairs without clearing publication history. Anisha remains paused. Music Store and Netflix still use only configured Facebook sources; Ocean still requires marine content. The existing cloud schedules remain independent of the user's PC.

## Actual-source validation

Eight previously rejected pairs rendered at 1080×1350 and passed native-photo, source extraction, caption and poster checks: Netflix `1121260296927098`, Music `1472449894755584`, Hollywood `1568035602004427`, Nepal `1541167231368850`, and Ocean `122140579323240703`, `122119907253320544`, `122123324925298539`, `122119651407320544`. Their measured type ranges from 72 to 94px. The fresh FrontlineDiary source `1573142061513585` also passed with 94px type and its intact missile photograph. Representative outputs were visually inspected.

The source with a large cancellation stamp across the actors, full text-only announcement cards, centrally watermarked images, repeated photos and genuinely blurred images remain unsuitable. Regular hourly slots depend on new usable photos from the configured sources; the engine does not manufacture filler to meet a slot.

Validation: 329 Python regression tests and the GitHub UI save tests.

## Live verification

Deployed code `465e622`; cloud run [38152586222](https://github.com/aashuthapa2023-sudo/autoimgpost/actions/runs/38152586222) completed successfully with all 329 tests. Facebook confirmed:

| Page | Source | Meta photo | UTC |
| --- | --- | --- | --- |
| Daily Netflix | 1121260296927098 | 1667972115339006 | 15:48:34 |
| Music Store | 1472449894755584 | 1570382151947330 | 15:49:05 |
| Daily Hollywood | 1568035602004427 | 1560020622806085 | 15:49:18 |
| Ocean's Secret | 122140579323240703 | 122110119183493170 | 15:50:01 |

Nepal Speaks last published at 15:34:21 and correctly waited for its configured interval. Anisha stayed paused. Publication state was saved to latest main, and the live website served the new Billboard cleanup settings.

FrontlineDiary's public feed remained unavailable to this cloud run, although the exact fresh pair `1573142061513585` was accessible and independently verified locally. The official source API also returned an unavailable-object response (100/33) using the existing destination connection. The verified pair was saved to the configured-source cache for the cloud publisher; it retains the exact source caption, photo ID, URL and publication timestamp. This recovery does not grant new Facebook source-read permissions or guarantee a new photo every two hours from one source.
