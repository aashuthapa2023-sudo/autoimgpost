"""Channel relevance gates applied before rendering or publishing."""
import re

OCEAN_TERMS = r"\b(?:oceans?|marine|maritime|seas?|seabed|seafloor|seawater|underwater|coral|reefs?|whales?|dolphins?|sharks?|orcas?|octopus|octopuses|squid|jellyfish|seaweed|seagrass|plankton|mangroves?|coastal|coastlines?|deep[- ]sea|tides?|tsunami|oceanography)\b"

def channel_accepts_post(channel, post):
    caption = str(post.get('caption', ''))
    if not caption.strip() or re.match(r"^we asked .* (?:what|how|why)\b", caption, re.IGNORECASE):
        return False
    if channel.get('channel_id') == 'Music Store' or channel.get('content_topic') == 'music':
        return bool(re.search(r"\b(?:music|musicians?|singers?|songs?|albums?|concerts?|tours?|billboard|grammy|band|bands|rapper|rappers|rap|hip.hop|guitar|festival|soundtrack|headliners?|perform(?:ed|ance)?|slayyyter|outkast|fuerza regida|byrne|baez|ringo|def leppard)\b", caption, re.IGNORECASE))
    if channel.get('content_topic') != 'ocean' and channel.get('channel_id') != 'oceans_secret':
        return True
    caption = str(post.get('caption', ''))
    caption = re.sub(r'https?://\S+|#[\w]+', '', caption)
    caption = re.sub(r"ocean['’]s (?:eleven|twelve|thirteen)|sea of (?:fans|people|faces)|sea of stars", '', caption, flags=re.IGNORECASE)
    return bool(re.search(OCEAN_TERMS, caption, re.IGNORECASE))
