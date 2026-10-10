"""Conservative caption-based topic gates; uncertain sources are skipped."""

import re

OCEAN_TERMS = r"\b(?:oceans?|marine|maritime|seabed|seafloor|seawater|underwater|coral|reefs?|whales?|belugas?|narwhals?|porpoises?|manatees?|dugongs?|dolphins?|sharks?|orcas?|octopus|octopuses|squid|jellyfish|seaweed|seagrass|plankton|mangroves?|coastal|coastlines?|deep[- ]sea|oceanography|seals?|walrus|turtles?|seahorses?|manta rays?|stingrays?)\b"
MUSIC_TERMS = r"\b(?:music|musicians?|singers?|songs?|albums?|concerts?|billboard|grammys?|bands?|rappers?|rap|hip[- ]hop|guitars?|soundtracks?|vocalists?|drummers?|composers?|symphony|orchestra|lyrics|singles?|duets?|vocals?|VMA|VMAs|EP|LP|headliners?|record label|record deal|music video|listening party|video of the year|stage mishap|stage performance)\b"
SCREEN_TERMS = r"\b(?:netflix|streaming|series|seasons?|episodes?|films?|movies?|cinema|hollywood|actors?|actresses?|directors?|cast|casting|screenplay|box[- ]office|trailers?|oscars?|emmys?|hbo|disney|paramount|sitcom|documentary|television|tv show)\b"


MILITARY_TERMS = r"\b(?:army|military|marines?|navy|USS|aircraft carriers?|strike group|air force|soldiers?|veterans?|rangers?|medal of honor|regiment|battalion|infantry|fighter jets?|F-16V?|SR-71|Blackbird|NMESIS|missiles?|armed forces)\b"


def channel_topic(channel):
    topic = str(channel.get('content_topic') or '').strip().lower()
    if topic:
        return {'marine': 'ocean', 'cinema': 'film', 'streaming': 'entertainment', 'screen': 'entertainment'}.get(topic, topic)
    return {
        'oceans_secret': 'ocean', 'Music Store': 'music',
        'daily_netflix': 'entertainment', 'Anisha': 'entertainment',
        'Daily Hollywood': 'film', 'nepal_speaks': 'news',
    }.get(channel.get('channel_id'), '')


def channel_accepts_post(channel, post):
    caption = str(post.get('caption') or '').strip()
    caption = re.sub(r'\[[^\]]*\]\(https?://[^)]*\)', '', caption)
    # A named award attached to a winning/nomination fact is source content,
    # unlike a trailing generic category hashtag.
    if re.search(r'\b(?:wins?|winning|won|nominat(?:ed|ion|ions))\b', caption, re.IGNORECASE):
        caption = re.sub(r'#(VMA|VMAs)\b', r'\1', caption, flags=re.IGNORECASE)
    caption = re.sub(r'(?:https?://|www\.)\S+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?|[#@][\w]+', '', caption, flags=re.IGNORECASE)
    if not caption.strip() or re.match(r"^we asked .* (?:what|how|why)\b", caption, re.IGNORECASE):
        return False
    if re.fullmatch(r'(?:read more|link in (?:bio|comments)|breaking news|latest update)[.! ]*', caption, re.IGNORECASE):
        return False
    topic = channel_topic(channel)
    if topic == 'military':
        return bool(re.search(MILITARY_TERMS, caption, re.IGNORECASE))
    if topic == 'music':
        return bool(re.search(MUSIC_TERMS, caption, re.IGNORECASE))
    if topic in ('film', 'entertainment'):
        return bool(re.search(SCREEN_TERMS, caption, re.IGNORECASE))
    if topic != 'ocean':
        return True
    caption = re.sub(r"ocean['’]s (?:eleven|twelve|thirteen)|sea of (?:fans|people|faces|stars)|shark tank|baby shark", '', caption, flags=re.IGNORECASE)
    if re.search(r'\b(?:bitcoin|cryptocurrency|crypto|ethereum|wallets?|stock market)\b', caption, re.IGNORECASE):
        return False
    direct = bool(re.search(OCEAN_TERMS, caption, re.IGNORECASE))
    maritime_archaeology = bool(re.search(r'\bshipwrecks?\b', caption, re.IGNORECASE) or (
        re.search(r'\b(?:ships?|wrecks?|archaeologists?|cargo|merchant vessel)\b', caption, re.IGNORECASE) and
        re.search(r'\b(?:oceans?|seas?|marine|maritime|underwater|coast(?:al)?|Mediterranean|Pacific|Atlantic|seafloor|seabed)\b', caption, re.IGNORECASE)))
    contextual_sea = bool(re.search(r'\bsea\b', caption, re.IGNORECASE) and re.search(
        r'\b(?:waters?|ecosystem|wildlife|fish|creatures?|habitat|pollution|currents?|surface|depth|bed|floor|life)\b', caption, re.IGNORECASE))
    return direct or contextual_sea or maritime_archaeology
