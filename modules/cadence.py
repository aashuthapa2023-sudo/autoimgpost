"""Publication slots based on confirmed receipts, never on successful scans."""
def publication_wait(channel,last_published,now):
    interval=max(0,float(channel.get('post_interval_hours',1))*3600)
    if not last_published:return 0
    if channel.get('cadence_mode')=='hourly_slots' and interval==3600:
        # Workflow setup and per-page processing vary between runs. A rolling
        # 58-minute gate could miss the next scan by seconds and wait 30 minutes.
        # Use one receipt per clock hour, with a 45-minute burst guard.
        next_slot=(int(last_published)//3600+1)*3600
        return max(0,next_slot-now,last_published+45*60-now)
    return max(0,last_published+max(0,interval-120)-now)
