"""Strict rolling publication intervals based on confirmed receipts."""
def publication_wait(channel, last_published, now):
    """Seconds until the configured minimum gap has elapsed.

    The first post has no prior receipt and is immediately eligible. Later
    posts become eligible at the exact receipt timestamp plus the configured
    interval; scheduler slots and early-publication tolerances are not used.
    """
    interval = max(0.0, float(channel.get('post_interval_hours', 1)) * 3600)
    if not last_published:
        return 0
    return max(0, last_published + interval - now)
