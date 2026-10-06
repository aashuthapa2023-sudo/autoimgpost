"""Compare source stories across feeds without collapsing changed numbered facts."""
import re
import unicodedata


def _words(text):
    text=unicodedata.normalize('NFKC',str(text)).casefold()
    text=re.sub(r'https?://\S+|www\.\S+|[#@]\w+', ' ', text)
    return re.findall(r'[^\W_]+',text,flags=re.UNICODE)


def is_repeated_story(caption, recent_captions):
    words=_words(caption)
    candidate=set(words)
    if len(candidate)<6:
        return False
    numbers=sorted(word for word in words if word.isdecimal())
    for old in recent_captions:
        old_words=_words(old)
        if sorted(word for word in old_words if word.isdecimal())!=numbers:
            continue
        previous=set(old_words)
        union=candidate|previous
        if union and len(candidate&previous)/len(union)>=.84:
            return True
    return False
