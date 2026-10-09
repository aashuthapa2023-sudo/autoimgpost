"""Keep exact configured Facebook caption/photo pairs through temporary feed failures."""
import json
import time
from pathlib import Path


def merge_source_candidates(channel, live_posts, processed_ids=(), path='source_cache.json', now=None):
    now=time.time() if now is None else now
    sources=set(channel.get('source_pages',[]))
    processed=set(map(str,processed_ids))
    file=Path(path)
    try:
        stored=json.loads(file.read_text(encoding='utf-8'))
        if not isinstance(stored,dict):stored={}
    except (OSError,ValueError):stored={}
    cid=channel['channel_id']
    rows={}
    for post in stored.get(cid,[])+list(live_posts):
        if not isinstance(post,dict):continue
        stamp=post.get('created_time')
        if (post.get('source_page_url') not in sources or not str(post.get('post_id','')).isdigit()
                or not str(post.get('photo_id','')).isdigit() or not str(post.get('caption','')).strip()
                or not str(post.get('image_url','')).startswith('https://')
                or not isinstance(stamp,(int,float)) or isinstance(stamp,bool)
                or not now-72*3600<=stamp<=now+300):continue
        if any(str(post.get(key,'')) in processed for key in ('post_id','photo_id','caption_fingerprint')):continue
        rows[str(post['post_id'])]=post
    selected=sorted(rows.values(),key=lambda post:post['created_time'],reverse=True)[:120]
    stored[cid]=selected
    temporary=file.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(stored,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(file)
    recovered=sum(post['post_id'] not in {p.get('post_id') for p in live_posts} for post in selected)
    if recovered:print(f' [SOURCE RECOVERY] {channel.get("channel_name",cid)}: {recovered} previously verified Facebook pair(s) retained within 72 hours')
    # Live ingestion remains authoritative and keeps its existing validation
    # path. Only recovered records must meet the stricter cache requirements.
    result={post['post_id']:post for post in selected}
    result.update({str(post.get('post_id','')):post for post in live_posts})
    return sorted(result.values(),key=lambda post:post.get('created_time',0),reverse=True)
