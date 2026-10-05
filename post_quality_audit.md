# Post quality audit

Reviewed all seven latest Music Store posts through the configured Facebook page connection, plus recent generated Ocean’s Secret posters.

| Music Store post | Findings | Correction |
| --- | --- | --- |
| 1564943682491177 — Slayyyter | Emoji appears as missing glyphs in overlay; long caption reused as headline | Remove overlay emoji; concise specific hook; rewrap readable type |
| 1564898379162374 — Fuerza Regida | Small type; dark backing hides heads | Larger type; separate headline panel and full subject framing |
| 1564836762501869 — Primavera | Long artist list in tiny type; performer cropped | Key artists plus event/year; full image framing |
| 1564793159172896 — Outkast | Caption only says “We asked a Harvard Law professor…” | Reject context-free teasers rather than fabricate an explanation |
| 1564691362516409 — Avengers | Movie box-office post on music page | Music relevance gate |
| 1564756422509903 — Auction | Artwork heavily smeared by cleanup | Require recognized text; reject destructive removal areas |
| 1564721052513440 — John Oliver | Long headline and non-music topic | Readability gate and music relevance filter |

Ocean’s Secret’s unrelated entertainment posts came from its generic web fallback. That fallback is disabled for restricted-topic pages, and ocean relevance is checked before rendering. Caption deduplication now compares individual sentences, including near duplicates within one paragraph. Overlays use a 54-pixel minimum, wrap to at most three balanced lines, and center visible glyphs. Cleanup does not run the old unverified edge/colour remover. Large removal areas are rejected, leaving the source unchanged. Headline panels no longer cover photo subjects.

Existing Facebook posts were not edited or deleted. No prediction or guarantee of viral reach is made.
