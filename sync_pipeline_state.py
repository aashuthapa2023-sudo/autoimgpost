"""Persist publisher results without rebasing generated data over newer code."""
import argparse
import copy
import json
import math
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GENERATED_FILES = ('state.json', 'feed_cache.json', 'posters_cache.json', 'quality_report.json', 'source_cache.json')
_MISSING = object()


class StateSyncError(RuntimeError):
    pass


def _union(*sequences):
    result, positions = [], {}
    for sequence in sequences:
        for value in sequence:
            if isinstance(value, dict) and value.get('published_id'):
                key = ('publication', str(value.get('channel_id', '')), str(value['published_id']))
            else:
                key = ('value', json.dumps(value, sort_keys=True, ensure_ascii=False))
            if key not in positions:
                positions[key] = len(result)
                result.append(copy.deepcopy(value))
            elif isinstance(value, dict):
                previous = result[positions[key]]
                if (previous.get('post_id') and value.get('post_id')
                        and previous['post_id'] != value['post_id']):
                    raise StateSyncError('A Meta confirmation has conflicting source history')
                result[positions[key]].update(copy.deepcopy(value))
    return result


def _merge_value(base, run, latest):
    if run is _MISSING:
        return copy.deepcopy(latest if latest is not _MISSING else base)
    if latest is _MISSING:
        return copy.deepcopy(run)
    if isinstance(run, list) and isinstance(latest, list):
        return _union(base if isinstance(base, list) else [], latest, run)
    if isinstance(run, dict) and isinstance(latest, dict):
        base = base if isinstance(base, dict) else {}
        return {key: _merge_value(base.get(key, _MISSING), run.get(key, _MISSING), latest.get(key, _MISSING))
                for key in sorted(set(base) | set(run) | set(latest))}
    return copy.deepcopy(run if latest == base else latest)


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise StateSyncError('A publication timestamp is invalid; recovery evidence was retained') from None


def _timestamps(stats):
    values = stats.get('timestamps', [])
    if not isinstance(values, list):
        raise StateSyncError('Daily publication timestamps must be a list')
    return {_timestamp(value).isoformat(timespec='microseconds') for value in values}


def _day_count(stats, today):
    count = stats.get('count', 0)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise StateSyncError('Daily publication count is invalid')
    return count if stats.get('date') == today else 0


def merge_pipeline_state(baseline, run, latest, *, now=None):
    """Union publication evidence and reconcile each day's count in UTC.

    Existing unlogged counts are retained as baseline deficits. New branch
    increments already represented by timestamps are never counted twice.
    Unknown scalar state fields prefer newer remote data on a true conflict.
    """
    if not all(isinstance(state, dict) for state in (baseline, run, latest)):
        raise StateSyncError('Publication state must contain JSON objects')
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(timezone.utc).date().isoformat()
    result = _merge_value(baseline, run, latest)
    maps = [state.get('daily_stats', {}) for state in (baseline, run, latest)]
    if not all(isinstance(mapping, dict) for mapping in maps):
        raise StateSyncError('Daily statistics must contain channel objects')
    merged_stats = {}
    for channel in sorted(set().union(*(mapping.keys() for mapping in maps))):
        stats = [mapping.get(channel, {}) for mapping in maps]
        if not all(isinstance(item, dict) for item in stats):
            raise StateSyncError('Daily channel statistics must be objects')
        times = [_timestamps(item) for item in stats]
        day_times = [{value for value in values if _timestamp(value).date().isoformat() == today}
                     for values in times]
        base_count, run_count, latest_count = [_day_count(item, today) for item in stats]
        base_deficit = max(0, base_count - len(day_times[0]))
        run_unlogged = max(0, run_count - base_count - len(day_times[1] - day_times[0]))
        latest_unlogged = max(0, latest_count - base_count - len(day_times[2] - day_times[0]))
        all_times = set.union(*times)
        all_day_times = set.union(*day_times)
        merged = _merge_value(*stats)
        merged.update(date=today, timestamps=sorted(all_times), count=max(
            base_count, run_count, latest_count,
            len(all_day_times) + base_deficit + max(run_unlogged, latest_unlogged)))
        last_times = [item.get('last_published_time', 0) for item in stats]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                   for value in last_times):
            raise StateSyncError('Last publication time is invalid')
        merged['last_published_time'] = max(last_times + [int(_timestamp(value).timestamp()) for value in all_times])
        merged_stats[channel] = merged
    result['daily_stats'] = merged_stats
    return result


def _read_json(path, default=None):
    if not path.exists() and default is not None:
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise StateSyncError('A state or recovery snapshot is unreadable') from None


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _git(directory, *arguments, check=True):
    result = subprocess.run(['git', '-C', str(directory), *arguments],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        # Git errors can contain authenticated remote URLs. Keep those out of
        # logs/artifacts; the named operation is enough to locate the failure.
        raise StateSyncError('Git ' + arguments[0] + ' failed; saved publisher evidence remains recoverable')
    return result


def capture_baseline(repository, directory):
    repository, directory = Path(repository).resolve(), Path(directory).resolve()
    baseline = _read_json(repository/'state.json', {})
    head = _git(repository, 'rev-parse', 'HEAD').stdout.strip()
    _write_json(directory/'baseline.json', {'head': head, 'state': baseline})
    journal = repository/'publication_journal.json'
    if journal.exists():
        from modules.publication_journal import apply_publication_receipts
        shutil.copy2(journal, directory/'prior_publication_journal.json')
        recovered = copy.deepcopy(baseline)
        apply_publication_receipts(recovered, str(journal))
        _write_json(repository/'state.json', recovered)
    # Only clear the current-run evidence after every prior receipt has been
    # preserved in state (and backed up locally for artifact recovery).
    _write_json(journal, {'publications': []})
    print('[STATE BASELINE] Latest checkout publication ledger captured.')


def _snapshot_generated(repository, directory):
    snapshot = directory/'run-results'
    snapshot.mkdir(parents=True, exist_ok=True)
    paths = [repository/name for name in GENERATED_FILES if (repository/name).is_file()]
    output = repository/'output'
    if output.is_dir():
        paths += [path for path in output.rglob('*') if path.is_file() and not path.is_symlink()
                  and (path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp') or path.name.endswith('.quality.json'))]
    relative_paths = []
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(repository):
            raise StateSyncError('Generated output path leaves the publisher checkout')
        relative = path.relative_to(repository)
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        relative_paths.append(relative)
    journal = repository/'publication_journal.json'
    if journal.exists():
        shutil.copy2(journal, snapshot/journal.name)
    return snapshot, relative_paths


def _remote_head(repository):
    output = _git(repository, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').stdout.split()
    if not output:
        raise StateSyncError('Remote main could not be verified')
    return output[0]


def sync_results(repository, directory, *, retries=4):
    """Normal-push results on latest main; never rebase or replace remote code."""
    repository, directory = Path(repository).resolve(), Path(directory).resolve()
    baseline = _read_json(directory/'baseline.json')['state']
    snapshot, paths = _snapshot_generated(repository, directory)
    run_state = _read_json(snapshot/'state.json', baseline)
    journal = snapshot/'publication_journal.json'
    if journal.exists():
        from modules.publication_journal import apply_publication_receipts
        apply_publication_receipts(run_state, str(journal))
    for attempt in range(1, retries + 1):
        _git(repository, 'fetch', '--no-tags', '--depth=1', 'origin', 'main')
        parent = _git(repository, 'rev-parse', 'FETCH_HEAD').stdout.strip()
        with tempfile.TemporaryDirectory(prefix='publisher-state-sync-') as temporary:
            checkout = Path(temporary)/'checkout'
            attached = False
            try:
                _git(repository, 'worktree', 'add', '--detach', str(checkout), parent)
                attached = True
                latest_state = _read_json(checkout/'state.json', {})
                merged = merge_pipeline_state(baseline, run_state, latest_state)
                for relative in paths:
                    if relative.as_posix() == 'state.json':
                        continue
                    target = checkout/relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot/relative, target)
                _write_json(checkout/'state.json', merged)
                stage = sorted({str(path) for path in paths} | {'state.json'})
                _git(checkout, 'add', '--', *stage)
                difference = _git(checkout, 'diff', '--cached', '--quiet', check=False)
                if difference.returncode not in (0, 1):
                    raise StateSyncError('Generated publication results could not be compared')
                if _remote_head(repository) != parent:
                    print(f'[STATE SYNC RETRY] Main advanced before save (attempt {attempt}/{retries}).')
                    continue
                if difference.returncode == 0:
                    print('[STATE SYNC] Publication evidence already exists on latest main.')
                    return {'status': 'already_saved', 'parent': parent}
                _git(checkout, '-c', 'user.name=github-actions[bot]', '-c',
                     'user.email=github-actions[bot]@users.noreply.github.com',
                     'commit', '-m', 'chore: persist publisher state and confirmed results [skip ci]')
                pushed = _git(checkout, 'push', 'origin', 'HEAD:main', check=False)
                if pushed.returncode == 0:
                    print('[STATE SYNC] Confirmed publication state saved on latest main.')
                    return {'status': 'saved', 'parent': parent}
                print(f'[STATE SYNC RETRY] Normal push was rejected (attempt {attempt}/{retries}); recovery artifact is retained.')
            finally:
                if attached:
                    _git(repository, 'worktree', 'remove', '--force', str(checkout))
    raise StateSyncError('State push failed after retries; restore the uploaded publisher-state artifact before another live run')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture-baseline', 'push'))
    parser.add_argument('--directory', default='.pipeline-sync')
    arguments = parser.parse_args()
    repository = Path.cwd()
    if arguments.action == 'capture-baseline':
        capture_baseline(repository, repository/arguments.directory)
    else:
        sync_results(repository, repository/arguments.directory)


if __name__ == '__main__':
    main()
