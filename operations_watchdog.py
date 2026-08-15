#!/usr/bin/env python3
"""Detect stalled or blocked Dashboard work and emit only new exception events.

The script is intentionally deterministic and side-effect limited: it reads the
file-backed Operations state, persists its own snapshot, and writes alerts.
The HermesPM cron owns user delivery by forwarding non-empty stdout to Discord.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = Path('/home/raphael/myproject')
OPERATIONS = BASE / 'operations'
TERMINAL_STATUSES = {'completed', 'cancelled'}
BLOCKED_STATUSES = {
    'blocked', 'dispatch_blocked', 'dispatch_failed', 'worker_missing',
    'worker_disabled', 'needs_pm_review', 'gate_hold', 'entry_hold',
}
ACTIVE_STATUSES = {
    'queued', 'dispatched', 'partially_dispatched', 'in_progress', 'watching',
    'results_received', 'partial_results', 'waiting_verification',
}
STALL_AFTER = timedelta(minutes=15)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def stage_for_task(task: dict[str, Any]) -> str:
    for stage in task.get('stages') or []:
        if stage.get('status') in {'in_progress', 'blocked', 'gate_hold', 'entry_hold'}:
            return str(stage.get('id') or 'unknown')
    return str(task.get('status') or 'unknown')


def latest_progress(task: dict[str, Any], task_path: Path) -> datetime:
    candidates = [
        parse_time(task.get('updated_at')),
        parse_time(task.get('created_at')),
        datetime.fromtimestamp(task_path.stat().st_mtime, tz=timezone.utc),
    ]
    for stage in task.get('stages') or []:
        gate = stage.get('gate') or {}
        candidates.extend([parse_time(stage.get('updated_at')), parse_time(gate.get('at'))])
    return max(value for value in candidates if value is not None)


def active_tasks(operations: Path) -> list[tuple[dict[str, Any], Path]]:
    tasks: list[tuple[dict[str, Any], Path]] = []
    for path in sorted((operations / 'briefs').glob('T-*.json')):
        task = read_json(path, {})
        if not task.get('task_id') or task.get('status') in TERMINAL_STATUSES:
            continue
        tasks.append((task, path))
    return tasks


def detect_issues(operations: Path, now: datetime) -> dict[str, dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    worker_status = read_json(operations / 'worker-status.json', {})
    workers = worker_status.get('workers') or {}
    for task, path in active_tasks(operations):
        task_id = str(task['task_id'])
        status = str(task.get('status') or 'unknown')
        stage = stage_for_task(task)
        assigned_workers = set(str(worker) for worker in (task.get('assigned_workers') or []))
        for stage_data in task.get('stages') or []:
            assigned_workers.update(str(worker) for worker in (stage_data.get('agents') or []))
        for worker in sorted(assigned_workers):
            runtime = workers.get(worker) or {}
            runtime_status = str(runtime.get('status') or '')
            if runtime_status not in {'rate_limited', 'blocked', 'unavailable', 'failed'}:
                continue
            detail = str(runtime.get('message') or f'{worker} 상태가 {runtime_status}입니다.')[:500]
            key = f'{task_id}:worker_unavailable:{worker}:{runtime_status}:{detail}'
            issues[key] = {
                'fingerprint': key, 'task_id': task_id, 'title': task.get('title', ''),
                'kind': 'worker_unavailable', 'severity': 'critical', 'stage': stage,
                'status': runtime_status, 'detail': f'{worker}: {detail}',
                'recommended_action': 'PM이 해당 worker를 재시도하지 말고 reset 시각을 확인하거나 대체 worker를 배정해야 합니다.',
            }
        detail = str(task.get('last_error') or '').strip()
        if status in BLOCKED_STATUSES:
            key = f'{task_id}:blocked:{stage}:{status}:{detail}'
            issues[key] = {
                'fingerprint': key, 'task_id': task_id, 'title': task.get('title', ''),
                'kind': 'blocked', 'severity': 'critical', 'stage': stage, 'status': status,
                'detail': detail or f'작업 상태가 {status}입니다.',
                'recommended_action': 'PM이 dispatch/worker/gate 증적을 점검하고 재시도 또는 대체 worker를 결정해야 합니다.',
            }
            continue
        if status not in ACTIVE_STATUSES:
            continue
        progress_at = latest_progress(task, path)
        age = now - progress_at
        if age >= STALL_AFTER:
            minutes = int(age.total_seconds() // 60)
            key = f'{task_id}:stalled:{stage}:{status}'
            issues[key] = {
                'fingerprint': key, 'task_id': task_id, 'title': task.get('title', ''),
                'kind': 'stalled', 'severity': 'warning', 'stage': stage, 'status': status,
                'detail': f'{minutes}분 동안 task/stage/결과 갱신이 없습니다. 마지막 갱신: {iso(progress_at)}',
                'recommended_action': 'PM이 worker heartbeat, dispatch 기록, 결과 inbox를 확인하고 다음 조치를 기록해야 합니다.',
            }
    return issues


def format_event(event: dict[str, Any]) -> str:
    icon = {'critical': '🚨', 'warning': '⚠️', 'info': '✅'}.get(event.get('severity'), '•')
    if event['kind'] == 'resolved':
        return f"{icon} 재개/해소: {event['task_id']} · {event['title']} — 이전 예외가 해소되었습니다."
    return (
        f"{icon} {event['kind']}: {event['task_id']} · {event['title']}\n"
        f"  단계/상태: {event['stage']} / {event['status']}\n"
        f"  증거: {event['detail']}\n"
        f"  권고: {event['recommended_action']}"
    )


def run_watchdog(operations: Path = OPERATIONS, *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or now_utc()).astimezone(timezone.utc)
    watchdog_dir = operations / 'watchdog'
    alerts_dir = operations / 'alerts'
    state_path = watchdog_dir / 'state.json'
    previous = read_json(state_path, {'issues': {}})
    previous_issues = previous.get('issues') or {}
    current_issues = detect_issues(operations, now)
    events: list[dict[str, Any]] = []

    for key, issue in current_issues.items():
        if key not in previous_issues:
            events.append(issue)
    for key, old_issue in previous_issues.items():
        if key not in current_issues:
            events.append({
                'fingerprint': key, 'task_id': old_issue.get('task_id', 'unknown'),
                'title': old_issue.get('title', ''), 'kind': 'resolved', 'severity': 'info',
                'stage': old_issue.get('stage', ''), 'status': 'resolved',
                'detail': '현재 감시 기준에서 예외가 더 이상 감지되지 않았습니다.',
                'recommended_action': 'PM이 실제 결과/상태 전이를 확인한 뒤 작업을 계속 진행합니다.',
            })

    active = active_tasks(operations)
    snapshot = {
        'observed_at': iso(now),
        'active_task_count': len(active),
        'active_tasks': [
            {
                'task_id': task['task_id'],
                'title': task.get('title', ''),
                'status': task.get('status', ''),
                'stage': stage_for_task(task),
                'updated_at': task.get('updated_at'),
            }
            for task, _ in active
        ],
        'issues': current_issues,
    }
    write_json(state_path, snapshot)
    write_json(watchdog_dir / 'latest.json', snapshot)
    if events:
        alert = {'observed_at': iso(now), 'events': events}
        stamp = now.strftime('%Y%m%dT%H%M%SZ')
        write_json(alerts_dir / f'watchdog-{stamp}.json', alert)
        (alerts_dir / f'watchdog-{stamp}.md').write_text(
            '# Agent watchdog alert\n\n' + '\n\n'.join(format_event(event) for event in events) + '\n',
            encoding='utf-8',
        )
    return {'observed_at': iso(now), 'event_count': len(events), 'events': events, 'snapshot': snapshot}


def main() -> int:
    outcome = run_watchdog()
    if outcome['events']:
        print('[Operations 5분 예외 모니터]')
        print('\n'.join(format_event(event) for event in outcome['events']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
