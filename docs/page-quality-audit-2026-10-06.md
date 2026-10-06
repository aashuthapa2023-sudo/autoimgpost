# Six-page quality audit — 6 October 2026

## Evidence and limits

Read-only Facebook Graph API requests returned the latest seven published posts, captions, and images for Daily Netflix, Music Store, Daily Hollywood, and Nepal Speaks: 28 published posts inspected. The requests used authorization headers; this audit stores no access tokens or API paging links. Contact sheets and original images are beside this report.

Anisha's configured token returned HTTP 401 / Graph code 190: its session is invalidated. Its seven latest local output files were inspected, but these files do not establish what is currently published. Ocean's Secret uses a GitHub Actions secret reference that is unavailable locally; its seven latest local output files were inspected with the same limitation. Original source Facebook posts were not independently fetched; source-card content is observable inside the published/local images, and source URLs/settings were read from the configured channels.

The Facebook posts observed here predate the new work in the current task. These observations describe defects requiring correction, not confirmation that any new change works.

## Daily Netflix

Published IDs (suffixes), newest first: 1661589979310553, 1661517949317756, 1661462535989964, 1661405349329016, 1661331576003060, 1661260486010169, 1661189609350590.

- **Incomplete key information:** newest poster reads only “GERHARD ZEILER, WARNER BROS.” Its caption actually describes a possible studio departure and his stated intention to enter Austrian politics. The image overlay does not state an event.
- **Unreadable type and unused space:** WME anniversary, darkest films, Overacting, and ITV formats posters include multiple article sentences in very small type, separated from their photos by large black areas. The font must never shrink to accept an article.
- **Subjects obscured:** the WME portrait fades to black over the person's eyes/upper face. The Unabomber image contains obvious abstract patches and rays rather than a clear scene.
- **Repetition and metadata:** WME/Zeiler/ITV captions repeat title facts in the following sentence. Overacting's caption contains the web author's name, handle, date and time as content.
- **Source scope:** all three configured sources are Netflix fan pages, yet fallback outputs include unrelated studio/corporate trade stories. Decide and enforce an explicit Netflix/streaming scope rather than accepting anything labeled entertainment.

Recommended tuning: red accent and charcoal panel; crisp full-subject photo; a distinct bottom editorial panel with 2–3 substantial centered lines; concise streaming facts (title, release/event, platform/date when supplied). Example grounded in the existing Overacting caption: “OVERACTING ARRIVES ON NETFLIX / NOVEMBER 2026.” For Zeiler, preserve the caption's uncertainty about leaving; do not turn “likely” into a confirmed exit.

## Music Store

Published IDs: 1565350889117123, 1565299852455560, 1565254962460049, 1565240479128164, 1565210709131141, 1565168665802012, 1565097779142434.

- **Duplicate publication:** posts 1565254962460049 and 1565240479128164 share the same 31,000-songs caption, artwork and headline; they were published 29 minutes apart. Source-ID-only deduplication misses this.
- **Link debris in overlay:** Taylor Swift's overlay begins “: BIT.LY4HZWHQN…” while the saved Facebook caption is clean. Caption sanitation must also run before headline selection.
- **Source-designed chart card:** the Swift artwork retains Billboard branding, a separate chart title/number/date, and the new overlay above it. Do not blur or inpaint the singer to erase chart graphics; either extract the intact photograph when safe, use another clean source image, or skip.
- **Cleanup scars:** Dolly Parton's image retains a source callout and an indistinct smear below it. The stage-performance image retains white play-triangle shapes and a blurred rectangle. The Game's portrait includes large circular blur/removal scars across the face and hand.
- **Specificity:** “These are the acts…” omits the names that would give a ranked-list image meaning. If the source caption supplies no names, don't fabricate names or treat the teaser as a strong headline.
- **Source scope:** Billboard, Rolling Stone and MTV are topical sources; the configured Netflix fan-page source needs a music relevance test for each candidate.

Recommended tuning: magenta accent, dark plum/charcoal panel, consistently large centered artist/event typography; retain performances and facial detail. Short source-grounded example: “DOLLY PARTON'S 25 BEST SONGS / BILLBOARD'S PICKS.” The source caption says “Boozey”; this audit does not independently establish whether that is a typo or a source nickname, so name changes require actual source evidence.

## Anisha

Live access failed with invalidated credentials. Local samples: Anisha_122242799186298966.jpg plus web_cb7a1d4e9a07bbca, web_b40cc52959c05833, web_758fa4c40a8a39a8, web_7500320727c42df0, web_4a036f998d56fbe4, web_0f8e8a0797cba699.

- **Two headline systems:** newest local Bridgerton poster retains the original image text identifying Eloise as Season 6's lead and adds another large headline saying she is next in line for a love story. This reintroduces the same designed-card failure seen in the user's example.
- **Extreme font reduction:** Gwen Stefani's local poster squeezes a very long headline into nearly illegible type. Anime, John Oliver, Overacting, Taylor Swift and Mark Rober posters retain multiple article sentences as headlines.
- **Mask placement:** several local photos are blacked out below the eye line or lose most of their frame to empty black areas.
- **Source scope:** two Netflix fan pages are configured; entertainment fallback stories broaden the channel without an explicit editorial choice.

Recommended tuning: lilac/rose accent and deep charcoal; full actor/character framing; stable bottom panel; 2–3 large lines naming the series/character and actual development. The source card visibly provides “ELOISE BRIDGERTON / SEASON 6 LEAD,” which is more useful than a generic “love story” tease. Reconnect the page credential before claiming successful live publication.

## Daily Hollywood

Published IDs: 1554308293377318, 1554245316716949, 1554087050066109, 1554000123408135, 1553988596742621, 1553949103413237, 1553901713417976.

- **Repeated story:** consecutive Zaslav posters use two sources/headlines for the same farewell event about 90 minutes apart. Deduplicate stories using normalized content, not only source IDs.
- **Source panel remains:** Surviving Hurricane Otis retains a source title, release details and source branding directly above the new headline panel. The new overlay only says a devastating storm is coming to the screen, omitting the film name/date available in the caption.
- **Tiny text:** Hercule and the Syrian Oscar entry both squeeze article-length text into a tiny block.
- **Web-page chrome:** Hercule's caption includes Directors, Writers, Cast, “Attachment(s)” and community guideline text. Those are page scaffolding, not the story.
- **Off-topic/unbranded post:** one of the latest seven posts is a vertical cliff-jumping “Dola AI” image with an extreme-sports caption and no page overlay. It is visibly on the page, but the audit cannot attribute it to this pipeline without a publication record.

Recommended tuning: warm gold/copper accent, cinema charcoal, strong actor/film frame, bottom headline panel. Short source-grounded example: “SURVIVING HURRICANE OTIS / NETFLIX • OCTOBER 23.” Preserve the caption's 2026 year in the post text. Add a film/TV relevance policy and useful rejection logs.

## Nepal Speaks

Published IDs: 122121931389285356, 122121888525285356, 122121868401285356, 122121855915285356, 122121852129285356, 122121846711285356, 122121843219285356.

- **Vague headlines lose the facts:** the coin poster reads “नेपाल राष्ट्र बैंकको ठूलो तयारी…” but the caption actually identifies 30 crore new Rs 2 coins. Prefer that main fact.
- **Truncation:** almost every current overlay ends in an ellipsis; several are sentence fragments. Flydubai, green-card, political-comment and Kohalpur overlays are too long for the current panel, then reduced to small type.
- **Duplicated branding/cleanup scars:** the Miraj Dhungana image retains a Nepal Speaks source logo in the image and a broad blurred white bar near the source panel; a second tiny badge is added below. The coin photo contains a visibly altered patch around the coin's edge and face.
- **Unhelpful empty space:** the political-comment poster has a large black gap between the photograph and a small headline block.
- **Nepali shaping and allegation accuracy:** Devanagari needs measured full glyph bounds and enough line height; incident captions must preserve allegations and attribution rather than imply guilt.
- **Source settings:** Himali Media and Smart Media are configured; the old Smart Media header-fraction setting is a source-specific crop hint and must not be applied blindly to every source image/aspect ratio.

Recommended tuning: deep navy, warm yellow and white; intact news photograph above a compact, distinct news panel; 2–3 balanced centered Nepali lines. Example from the caption: “३० करोड नयाँ २ रुपैयाँका / सिक्का छाप्ने तयारी.” Use a single intentional page masthead with safe glyph margins; don't add extra labels already baked into retained source artwork.

## Ocean's Secret

Live posts could not be read with the locally unavailable Actions secret. Local samples: oceans_secret_122139751209240703.jpg, web_43f0f40b96b1d8ae, web_9e5e049ad70a9216, web_515d170a53097f75, web_327aae21978c5971, 122139656049240703, 122139622851240703.

- **Off-topic candidates:** four of these seven local outputs are entertainment/corporate stories (a director, a documentary production, Sam Altman/Andrew Garfield and a Syrian film). This is actual local generation evidence, not confirmation these exact files were published.
- **Source subtitles remain:** latest marine image still includes “IN TOTAL DARKNESS?” inside the photo beneath the new oxygen question. Avoid treating transcript subtitle cards as clean photos.
- **Small text/missing glyphs:** several non-ocean samples carry tiny article text; the chains/ruins sample has missing emoji boxes and a long trailing narrative in its overlay.
- **Question-only hooks:** the oxygen poster asks a general question without supplying the key finding/location that would make it informative. Its original caption is unavailable in this audit, so adding scientific specifics would be invention.
- **Potentially fictional imagery:** the underwater-chains picture looks illustrative; the audit cannot establish its origin. If the source is a fiction/AI tale, retain that distinction in the caption and do not present it as verified discovery.

Recommended tuning: ocean cyan, deep navy, white; preserve underwater detail/animal subjects; no image-reconstruction cleanup; compact centered bottom panel. Require a positive marine topic match and enough source information for a complete hook. Unknown captions, unclear science claims and unseparable subtitle cards should enter the skipped/review queue rather than forced publication.

## Shared release criteria

1. Caption and photo are paired from the same source post. Reject missing or context-free text rather than invent a long caption.
2. Remove URLs, tracking fragments, bylines and web-page chrome before both caption rewriting and overlay selection. No minimum-length padding.
3. Overlay states a subject and meaningful event/finding with the key supplied detail. No ellipses, arbitrary word cuts, trailing conjunctions, unsupported claims, missing glyphs or article paragraphs.
4. Headline fits as large centered type with visible glyph margins at the final output scale. Fitting failure skips rendering or chooses another complete source headline; it never makes type microscopic.
5. Photographic content is intact. Use panel crops only when the panel is separable. Never apply broad inpainting to a main subject or blur large regions as a text-removal substitute.
6. One intentional page headline/masthead. Retained source card text must not compete with it. Small source provenance is distinct from a second source headline.
7. Deduplicate normalized captions/headlines and image similarity per destination across sources/runs. Persist skipped reasons without labeling the candidate successfully posted.
8. Enforce page-specific topic checks and show credential failures separately from content rejections. A scheduled slot may legitimately remain empty if no safe candidate passes.

No audit or algorithm can promise that every possible future input is error-free. The practical target is to block known unsafe/low-confidence cases and make those skips visible before publication.

## Implemented tuning

| Page | Scope | Accent / panel | Headline size | Branding |
| --- | --- | --- | --- | --- |
| Daily Netflix | Streaming / film / television | Red #FF5964 / #150E14 | 68–94px | One red wordmark |
| Music Store | Music only | Gold #FFD166 / #121018 | 68–94px | One gold wordmark |
| Anisha | Streaming / film / television | Rose #F4A6C7 / #1B101B | 68–90px | One rose wordmark |
| Daily Hollywood | Film and industry | Gold #D9BB78 / #141720 | 68–92px | One cinema wordmark |
| Nepal Speaks | Nepali news | Yellow #FFC83B / #101C2D | 66–90px | Owned logo plus wordmark, once |
| Ocean's Secret | Marine science and ocean life | Cyan #4DD6E8 / #081E28 | 68–92px | One cyan wordmark |

All six have a bottom panel, a maximum of three centered headline lines, and 64px safety margins. The full retained photograph is fitted inside its own photo area. No broad inpainting, face-covering gradients, blur fills, arbitrary source crop fractions, microscopic fit-to-page text, or artificial thumbnail enlargement remains in the active rendering path. English uses bundled Barlow Condensed; Nepali uses Akshar with actual shaping. Unsupported shaping or a headline that cannot fit at the minimum readable size skips the candidate.

Source-specific top/bottom headline and branding controls remain available. Branding uses a reserved masthead or a reserved opposite-edge band, preserving the photograph and safe margins. Re-adding a configured page preserves its editorial and source settings.

Generic web fallback is disabled on all six pages. Music's Netflix source was removed. Source caption gates require positive topic evidence; model outputs must preserve observable names, numbers, species, negations and uncertainty. Invalid provider output retries another provider, falls back only to a complete source fact, or skips. Caption padding, arbitrary truncation and forced ellipses were removed. This is conservative lexical validation and cannot establish scientific or news truth on its own.

The exact approved poster and caption are bound by hashes. The upload path checks source approval, current manifest version, image dimensions, measured text/branding bounds and the caption/image hashes before contacting Meta. Older queued posters are retained for review and all live publishing goes through the same cadence/topic/duplicate controls. Gallery cards mark older designs for regeneration. New rejection reasons persist to quality_report.json without tokens or request URLs.

Duplicate tracking now compares normalized recent source captions and retained photo hashes per destination, while preserving changed numerical facts. Only confirmed Meta publication updates the posted state. Scheduled runs execute the regression suite before publishing. A page attempts at most six image candidates and checks a four-minute processing budget between candidates. Failed downloads wait 45 minutes before retry; persistent quality/topic/layout failures wait 12 hours. Changed settings and manual previews bypass these cooldowns, so one bad source cannot repeatedly block later candidates.

## Validation and remaining limitations

Real OCR was run on the three supplied bad examples and seven Music Store artifacts. The duplicate-headline and Nepali court artifacts were rejected. A separable Ocean top panel could be extracted, but the already-smeared old artifact cannot be restored and is not a clean source. Four original-looking cache candidates were also checked; all four failed resolution/sharpness or retained source text/logo checks. No rejected artifact was passed to Meta.

The six neutral style proofs verify typography and layout, including Nepali shaping, centered visible glyph bounds, one masthead and at least 64px global safety margins. These are design proofs; they are not source-matched news and all have source_checked=false. They deliberately cannot pass the publisher approval gate.

Anisha still requires a fresh Facebook page token. Ocean's live feed could not be audited locally because its Actions secret is not readable here. Existing Facebook posts have not been modified or deleted by this task. The changes govern future generation and publishing. Skipping an ambiguous source is intentional; no algorithm can promise perfect interpretation of every future image/caption or guarantee virality.

The local validation suite passes 114 Python regressions, plus the GitHub configuration-save JavaScript checks and source syntax/whitespace checks. Ingestion regressions cover atomic photo/ID selection, full-caption pairing, shared wrapper ambiguity, video/link exclusion, unknown dates and direct/numeric profile URLs. Actual live Facebook mobile DOM selectors remain unverified and may yield fewer candidates when full captions/dates are unavailable.

## Posting interruption repair

The scheduler continued running, but the earlier cleanup policy rejected even small corner source credits and put those candidates into a 12-hour retry wait. Empty queues were misleadingly labeled up to date. Current repairs distinguish source outages, topic rejection, quality waits and already published stories; policy revision 4 allows affected candidates to be reviewed again without erasing publication history.

Small peripheral provenance marks now remain untouched. The original frame geometry is retained during any panel crop, so a body paragraph cannot become a permitted corner mark after cropping. Actual OCR verification accepted a Netflix photograph unchanged and extracted a clear 1639×1217 photograph from the latest Himali policy card. Metro and cucumber cards whose headlines overlap the photograph remain blocked, as do the user's damaged examples.

For Ocean's Secret, the owner selected readable original cards rather than skipping every card containing a baked headline. This mode keeps the whole original frame, applies no reconstruction or grading, adds only a small separate brand footer and does not generate another headline. Dedicated English OCR preserves decimals such as 2.4; the existing headline must match its own paired caption, remain readable at the final scale and have unclipped lettering. Small body text, uncertain OCR, incomplete headlines and contradictory source assertions remain blocked. The latest sponge and Pacific expedition sources passed this review and their final image/caption approvals.

Browser hydration now uses the same complete story/photo/date extraction as server-rendered sources. Real source snapshot replay recovered current posts on five source pages; the removed netflixfanatics alias led to an old Portuguese film page with no current posts. Music duets and VMA wins, and marine shipwreck archaeology with explicit sea context, pass the topic rules without accepting unrelated land stories.

Normal posting runs no longer overwrite their scanned source feed with an extra fixed Netflix refresh. Manual source ingestion respects its selected URL and preserves a last usable feed when the requested source returns nothing. Missing optional rewrite-provider keys remain a limitation: those runs use complete source excerpts rather than claim an AI rewrite occurred.

Recovery validation passes 156 Python tests and the GitHub configuration-save JavaScript checks. The real latest Ocean originals pass native quality checks at 768×1376 and their final retained-card headlines measure 45–53px high. They preserve the whole source photograph and contain one separate page-brand footer.
