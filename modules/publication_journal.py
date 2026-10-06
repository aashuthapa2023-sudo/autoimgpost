"""Durable receipts for confirmed Meta publications and idempotent recovery."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile

_FIELDS = {'channel_id', 'post_id', 'published_id', 'published_at',
           'processed_ids', 'story_fingerprint', 'source_caption',
           'image_hash', 'clean_image_hash'}
_SOURCE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,511}\Z')
_CHANNEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z')
_META_ID = re.compile(r'[0-9]{1,30}(?:_[0-9]{1,30})?\Z')
_HASH = re.compile(r'[0-9a-fA-F]{16,64}\Z')


def _publication_datetime(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)):
            result = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if result.tzinfo is None:
                raise ValueError
            result = result.astimezone(timezone.utc)
        else:
            raise ValueError
        if not datetime(2004, 1, 1, tzinfo=timezone.utc) <= result <= datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError
        return result
    except (ValueError, OverflowError, OSError):
        raise ValueError('Publication receipt has an invalid confirmed UTC timestamp') from None


def _validate_receipt(receipt):
    if not isinstance(receipt, dict) or set(receipt) != _FIELDS:
        raise ValueError('Publication receipt has an invalid field schema')
    result = dict(receipt)
    for field, pattern in (('channel_id', _CHANNEL), ('post_id', _SOURCE_ID), ('published_id', _META_ID)):
        value = result[field]
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ValueError(f'Publication receipt has an invalid {field}')
    processed = result['processed_ids']
    if (not isinstance(processed, list) or not 1 <= len(processed) <= 3
            or any(not isinstance(value, str) or not _SOURCE_ID.fullmatch(value) for value in processed)
            or result['post_id'] not in processed or len(set(processed)) != len(processed)):
        raise ValueError('Publication receipt has invalid source identifiers')
    for field in ('image_hash', 'clean_image_hash'):
        value = result[field]
        if not isinstance(value, str) or (value and not _HASH.fullmatch(value)):
            raise ValueError(f'Publication receipt has an invalid {field}')
    story = result['story_fingerprint']
    if not isinstance(story, str) or len(story) > 1024 or '://' in story:
        raise ValueError('Publication receipt has an invalid story fingerprint')
    caption = result['source_caption']
    if not isinstance(caption, str) or len(caption) > 4000:
        raise ValueError('Publication receipt has an invalid source caption')
    result['published_at'] = _publication_datetime(result['published_at']).isoformat()
    return result


def _read_journal(path):
    if not path.exists():
        return {'publications': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError):
        raise ValueError('Publication journal is malformed; repair it before publishing') from None
    if not isinstance(data, dict) or set(data) != {'publications'} or not isinstance(data['publications'], list):
        raise ValueError('Publication journal has an invalid schema; repair it before publishing')
    return {'publications': [_validate_receipt(receipt) for receipt in data['publications']]}


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def record_publication(channel_id, post, published_id, *, published_at,
                       image_hash, clean_image_hash, story_fingerprint,
                       path='publication_journal.json'):
    """Append only after Meta returns a confirmed publication identifier."""
    if not isinstance(post, dict):
        raise ValueError('Publication receipt requires the source post')
    if channel_id is None or post.get('post_id') is None:
        raise ValueError('Publication receipt requires a channel and source post identifier')
    processed = []
    for value in (post.get('post_id', ''), post.get('photo_id', ''), post.get('caption_fingerprint', '')):
        if value is not None and str(value) and str(value) not in processed:
            processed.append(str(value))
    receipt = _validate_receipt({
        'channel_id': str(channel_id), 'post_id': str(post.get('post_id', '')),
        'published_id': str(published_id), 'published_at': published_at,
        'processed_ids': processed, 'story_fingerprint': str(story_fingerprint or ''),
        'source_caption': str(post.get('caption') or '')[:4000],
        'image_hash': str(image_hash or ''), 'clean_image_hash': str(clean_image_hash or ''),
    })
    target = Path(path)
    journal = _read_journal(target)
    for old in journal['publications']:
        if old['channel_id'] == receipt['channel_id'] and old['published_id'] == receipt['published_id']:
            if old['post_id'] != receipt['post_id']:
                raise ValueError('Confirmed publication identifier is assigned to another source post')
            return old
    journal['publications'].append(receipt)
    _atomic_write(target, journal)
    return receipt


def _mapping(state, field):
    result = state.setdefault(field, {})
    if not isinstance(result, dict):
        raise ValueError(f'Publication recovery requires a valid {field} ledger')
    return result


def _union(ledger, values):
    if not isinstance(ledger, list):
        raise ValueError('Publication recovery requires list-based dedup ledgers')
    for value in values:
        if value and value not in ledger:
            ledger.append(value)


def apply_publication_receipts(state, path='publication_journal.json'):
    """Recover receipts into state without counting a processed source twice."""
    receipts = _read_journal(Path(path))['publications']
    if not isinstance(state, dict):
        raise ValueError('Publication recovery requires a state object')
    # Validate the complete file before mutating anything. A malformed later
    # receipt cannot partially mark earlier sources as published.
    recovered = copy.deepcopy(state)
    today = datetime.now(timezone.utc).date().isoformat()
    for receipt in receipts:
        confirmed = recovered.setdefault('confirmed_publications', [])
        if not isinstance(confirmed, list) or any(not isinstance(entry, dict) for entry in confirmed):
            raise ValueError('Publication recovery requires a confirmed publication ledger')
        prior = next((entry for entry in confirmed
                      if (entry.get('channel_id'), entry.get('published_id')) ==
                         (receipt['channel_id'], receipt['published_id'])), None)
        if prior is not None and prior.get('post_id') != receipt['post_id']:
            raise ValueError('Confirmed publication identifier is assigned to another source post')
        if prior is None:
            confirmed.append(copy.deepcopy(receipt))
        channel = receipt['channel_id']
        ids = _mapping(recovered, 'processed_ids').setdefault(channel, [])
        if not isinstance(ids, list):
            raise ValueError('Publication recovery requires a source ID ledger')
        new_source = receipt['post_id'] not in ids
        _union(ids, receipt['processed_ids'])
        _union(recovered.setdefault('global_processed_ids', []), receipt['processed_ids'])
        for field, value in (('channel_image_hashes', receipt['image_hash']),
                             ('channel_clean_image_hashes', receipt['clean_image_hash']),
                             ('channel_story_fingerprints', receipt['story_fingerprint'])):
            _union(_mapping(recovered, field).setdefault(channel, []), [value])
        _union(recovered.setdefault('global_image_hashes', []), [receipt['image_hash']])
        _union(recovered.setdefault('global_story_fingerprints', []), [receipt['story_fingerprint']])
        captions = _mapping(recovered, 'channel_recent_source_captions').setdefault(channel, [])
        _union(captions, [receipt['source_caption']])
        _mapping(recovered, 'channel_recent_source_captions')[channel] = captions[-80:]
        published = _publication_datetime(receipt['published_at'])
        stats = _mapping(recovered, 'daily_stats').setdefault(channel,
                    {'date': today, 'count': 0, 'timestamps': [], 'last_published_time': 0})
        if not isinstance(stats, dict):
            raise ValueError('Publication recovery requires daily publication statistics')
        last = stats.get('last_published_time', 0)
        if not isinstance(last, (int, float)) or isinstance(last, bool):
            raise ValueError('Publication recovery found invalid last publication time')
        stats['last_published_time'] = max(last, int(published.timestamp()))
        if new_source and published.date().isoformat() == today:
            if stats.get('date') != today:
                stats.update(date=today, count=0, timestamps=[])
            count = stats.get('count', 0)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError('Publication recovery found invalid daily publication count')
            stats['count'] = count + 1
            _union(stats.setdefault('timestamps', []), [receipt['published_at']])
    state.clear()
    state.update(recovered)
    return state
