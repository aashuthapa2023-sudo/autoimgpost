"""Small public rejection history containing reasons, never tokens or request URLs."""
import json
import os
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path


def profile_signature(channel):
    fields=('channel_id','source_pages','language','content_topic','editorial_style','poster_style','source_layouts','source_cleanup_profiles','highlight_color','preserve_readable_source_cards')
    policy={'revision':10 if channel.get('channel_id') in ('daily_netflix','nepal_speaks') else 9,
            **{key:channel.get(key) for key in fields}}
    return hashlib.sha256(json.dumps(policy,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


def ready_candidates(channel,posts,path='quality_report.json',bypass=False):
    if bypass:
        return posts
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return posts
    signature=profile_signature(channel)
    current=[item for item in data.get('rejections',[])
             if item.get('channel_id')==channel.get('channel_id') and item.get('policy_signature')==signature]
    now=time.time()
    blocked={item.get('post_id') for item in current if item.get('retry_after',0)>now}
    expired_retries={item.get('post_id') for item in current
                     if item.get('retry_after',0)<=now}
    ready=[post for post in posts if str(post.get('post_id','')) not in blocked]
    # Retrying a slow/failed candidate is allowed, but it must not repeatedly
    # consume every attempt slot before previously untried sources are checked.
    return ([post for post in ready if str(post.get('post_id','')) not in expired_retries]
            +[post for post in ready if str(post.get('post_id','')) in expired_retries])


def record_rejection(channel_id,post_id,stage,reason,path='quality_report.json',policy_signature=''):
    target=Path(path)
    try:
        data=json.loads(target.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        data={'rejections':[]}
    retry_delay={'source_image':2700,'transient_processing':900}.get(stage,43200)
    entry={'channel_id':str(channel_id),'post_id':str(post_id),'stage':stage,
           'reason':str(reason)[:240],'checked_at':datetime.now(timezone.utc).isoformat(),
           'policy_signature':policy_signature,
           'retry_after':time.time()+retry_delay}
    previous=[item for item in data.get('rejections',[]) if not (
        item.get('channel_id')==entry['channel_id'] and item.get('post_id')==entry['post_id'])]
    data={'updated_at':entry['checked_at'],'rejections':(previous+[entry])[-2000:]}
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,target)
