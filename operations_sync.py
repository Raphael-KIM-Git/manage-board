#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import re
import subprocess
import sys
import stat
from datetime import datetime
from pathlib import Path

from artifact_contract import validate_artifact_manifest

# 모듈 해석 루트: 활성 체크아웃 기준 (worktree 격리용)
MODULE_ROOT = Path(__file__).resolve().parent
# 데이터 루트: 정규 저장소 고정 (운영 산출물 위치 유지)
BASE = Path('/home/raphael/myproject')
OPERATIONS = BASE / 'operations'
BRIEFS = OPERATIONS / 'briefs'
RESULTS = OPERATIONS / 'results'
VERIFICATIONS = OPERATIONS / 'verifications'
DISPATCHES = OPERATIONS / 'dispatches'
STAGE_BRIEFS = OPERATIONS / 'stage-briefs'
RESEARCH_EVIDENCE_POLICY_PATH = OPERATIONS / 'config' / 'research-evidence-policy.v1.json'
WORKER_STATUS = OPERATIONS / 'worker-status.json'
KEY = '/home/raphael/.ssh/id_ed25519'
REMOTE = 'raphael@100.120.123.120:~/agent-hub/results/*'
GATE_ENABLED = os.environ.get('OPS_GATE_ENABLED', '1') != '0'
GATE_MAX_REVISE = int(os.environ.get('OPS_GATE_MAX_REVISE', '1'))
SYNC_LOCK = OPERATIONS / '.sync.lock'
SYNC_EVIDENCE = OPERATIONS / 'sync' / 'latest.json'
ENTRY_RESEARCH_WORKERS = ['HermesResearcher', 'researcher-co', 'researcher_agent', 'analyst-co']

STAGE_BRIEFS.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location('ops_dashboard_server', MODULE_ROOT / 'operations_dashboard_server.py')
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(server)


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def research_evidence_policy() -> dict:
    return load_json(RESEARCH_EVIDENCE_POLICY_PATH)


def research_evidence_policy_text() -> str:
    policy = research_evidence_policy()
    rules = '\n'.join(f"- {rule}" for rule in policy.get('acceptance_rules', []))
    classes = ', '.join(policy.get('observation_classes', []))
    fields = ', '.join(policy.get('direct_observation_fields', []))
    return (f"{policy['policy_id']} v{policy['version']}\n"
            f"관찰 분류: {classes}\n직접 확인 기록 필드: {fields}\n"
            f"정책 규칙:\n{rules}")


def worker_key(name: str) -> str:
    return name.lower().replace(' worker', '').replace(' ', '-')


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r'[^a-z0-9가-힣]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'task'


def base_task_id(task_id: str) -> str:
    for suffix in ('-writing', '-verify', '-final'):
        if task_id.endswith(suffix):
            return task_id[:-len(suffix)]
    return task_id


def stage_task_id(task_id: str, stage_id: str) -> str:
    suffix_map = {
        'writing': '-writing',
        'verification': '-verify',
        'final_write': '-final',
    }
    return f'{task_id}{suffix_map[stage_id]}'


def pull_results() -> tuple[int, str]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    before = {p.name: p.stat().st_mtime for p in RESULTS.glob('*') if p.is_file()}
    cmd = [
        'scp', '-i', KEY,
        '-o', 'BatchMode=yes',
        '-o', 'IdentitiesOnly=yes',
        '-P', '22',
        REMOTE,
        str(RESULTS) + '/',
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    after = {p.name: p.stat().st_mtime for p in RESULTS.glob('*') if p.is_file()}
    changed = sorted(name for name, m in after.items() if before.get(name) != m)
    summary = f'pull_exit={proc.returncode} changed={len(changed)} files=' + ','.join(changed)
    if proc.returncode != 0:
        summary += '\nstderr=' + (proc.stderr.strip() or '')
    return proc.returncode, summary


def sync_remote_worker_status() -> str:
    """Collect bounded runtime status from the MacBook runner log."""
    remote_script = """python3 - <<'PY'
from pathlib import Path
import json
p = Path.home() / 'agent-hub/logs/worker-runner.log'
lines = p.read_text(errors='replace').splitlines() if p.exists() else []
print(json.dumps({'lines': lines[-250:]}, ensure_ascii=False))
PY"""
    cmd = [
        'ssh', '-i', KEY,
        '-o', 'BatchMode=yes',
        '-o', 'IdentitiesOnly=yes',
        '-o', 'ConnectTimeout=8',
        'raphael@100.120.123.120',
        remote_script,
    ]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
    except Exception as exc:
        return f'remote_status=unavailable error={exc}'
    if proc.returncode != 0:
        return f'remote_status=unavailable error={proc.stderr.strip()[:160]}'
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return f'remote_status=parse_failed error={exc}'

    statuses = {}
    for line in payload.get('lines', []):
        lower = line.lower()
        if 'session limit' in lower or 'api error 429' in lower or '세션 제한' in line:
            worker = 'verify-co' if '(verify-co)' in line else None
            if worker:
                reset_match = re.search(r'resets?\\s+([^—]+)', line, re.IGNORECASE)
                statuses[worker] = {
                    'status': 'rate_limited',
                    'message': line[-300:],
                    'reset_at': reset_match.group(1).strip() if reset_match else None,
                    'updated_at': now_iso(),
                }
        elif '처리 완료:' in line:
            match = re.search(r'\\(([^)]+)\\).*→\\s*completed', line)
            if match:
                statuses.pop(match.group(1), None)

    save_json(WORKER_STATUS, {'updated_at': now_iso(), 'workers': statuses})
    return f'remote_status=ok workers={list(statuses)}'


def exact_result_map() -> dict[str, list[dict]]:
    result_files = list(RESULTS.glob('*.json'))
    out: dict[str, list[dict]] = {}
    for path in result_files:
        try:
            data = load_json(path)
        except Exception:
            continue
        tid = data.get('task_id', '')
        if not tid:
            continue
        out.setdefault(tid, []).append(data)
    return out


def exact_result_markdowns(task_id: str) -> list[Path]:
    return sorted(RESULTS.glob(f'{task_id}__*.md'))


def aggregate_markdown(paths: list[Path], header: str, limit: int = 12000) -> str:
    blocks = []
    for path in paths:
        body = read_text(path).strip()
        if not body:
            continue
        blocks.append(f'## {path.name}\n\n{body}')
    if not blocks:
        return f'{header}\n\n(아직 수집된 본문이 없습니다.)'
    text = f'{header}\n\n' + '\n\n---\n\n'.join(blocks)
    return text[:limit]


def find_stage(task: dict, stage_id: str) -> dict | None:
    for stage in task.get('stages', []):
        if stage.get('id') == stage_id:
            return stage
    return None


def set_stage_status(task: dict, stage_id: str, status: str):
    stage = find_stage(task, stage_id)
    if stage is not None:
        stage['status'] = status


def create_stage_brief(task: dict, stage_id: str, context_text: str, derived_id: str | None = None) -> dict:
    base_id = task['task_id']
    derived_id = derived_id or stage_task_id(base_id, stage_id)
    slug = slugify(task.get('title', 'task'))
    md_path = STAGE_BRIEFS / f'{derived_id}-{slug}.md'
    json_path = STAGE_BRIEFS / f'{derived_id}-{slug}.json'

    if stage_id == 'research':
        title = f"{task['title']} — research"
        objective = '외부 근거를 조사하고 관찰별 증거 수준과 미확인 항목을 기록'
        assigned_workers = task.get('assigned_workers') or ENTRY_RESEARCH_WORKERS
        deliverable = 'research evidence report with source-level verification metadata'
    elif stage_id == 'writing':
        title = f"{task['title']} — writing"
        objective = 'research 결과를 종합해 초안 문서를 작성'
        assigned_workers = ['writer-co']
        deliverable = task.get('deliverable') or 'first draft synthesized from research artifacts'
    elif stage_id == 'verification':
        title = f"{task['title']} — verification"
        objective = 'draft 문서를 검토하고 사실성/누락/위험 요소를 지적'
        assigned_workers = ['verify-co']
        deliverable = 'verification report with factual/risk/completeness checks'
    elif stage_id == 'final_write':
        title = f"{task['title']} — final_write"
        objective = 'verification 피드백을 반영해 최종 결과물을 정리'
        assigned_workers = ['writer-co']
        deliverable = task.get('deliverable') or 'final polished deliverable'
    else:
        raise ValueError(f'unsupported stage_id: {stage_id}')

    data = {
        'task_id': derived_id,
        'parent_task_id': base_id,
        'stage_id': stage_id,
        'created_at': now_iso(),
        'updated_at': now_iso(),
        'title': title,
        'objective': objective,
        'priority': task.get('priority', 'medium'),
        'execution_mode': 'single',
        'assigned_workers': assigned_workers,
        'reviewer': task.get('reviewer', 'HermesVerifier'),
        'context': context_text,
        'constraints': task.get('constraints', ''),
        'deliverable': deliverable,
        'status': 'queued',
        'source': 'operations-sync-stage-auto-dispatch',
        'dispatch_ready': True,
        'artifacts': {
            'markdown_brief': str(md_path),
            'json_brief': str(json_path),
        },
    }

    if stage_id == 'research':
        data['research_evidence_policy'] = research_evidence_policy()
    policy_block = f"\n\n## Research Evidence Policy\n{research_evidence_policy_text()}" if stage_id == 'research' else ''
    md = f'''# Stage Brief\n\n- Parent Task ID: {base_id}\n- Stage Task ID: {derived_id}\n- Stage: {stage_id}\n- Assigned Workers: {", ".join(assigned_workers)}\n\n## Objective\n{objective}\n\n## Context\n{context_text}\n\n## Constraints\n{task.get('constraints') or '(none provided)'}{policy_block}\n\n## Deliverable\n{deliverable}\n'''
    md_path.write_text(md, encoding='utf-8')
    save_json(json_path, data)
    return data


def dispatch_stage_brief(stage_task: dict) -> dict:
    workers = server.load_workers()
    selected = stage_task.get('assigned_workers') or []
    records = []
    statuses = []
    for worker in selected:
        record = server.dispatch_to_worker(stage_task, worker, workers)
        save_json(server.dispatch_record_path(stage_task['task_id'], worker), record)
        records.append(record)
        statuses.append(record['status'])

    new_status = 'queued'
    if statuses and all(s == 'dispatched' for s in statuses):
        new_status = 'dispatched'
    elif any(s == 'dispatched' for s in statuses):
        new_status = 'partially_dispatched'
    elif any(s in {'needs_config', 'worker_missing', 'worker_disabled'} for s in statuses):
        new_status = 'dispatch_blocked'
    elif any(s == 'dispatch_failed' for s in statuses):
        new_status = 'dispatch_failed'

    return {'task_id': stage_task['task_id'], 'status': new_status, 'records': records}


def stage_completed_by_results(result_map: dict[str, list[dict]], task_id: str) -> bool:
    results = result_map.get(task_id, [])
    return any(r.get('status') == 'completed' for r in results)


def stage_result_envelopes(task: dict, stage_id: str,
                           result_map: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[str]]:
    """Return only result envelopes that safely prove a derived stage completed.

    A parent stage must never be advanced from a similarly named sidecar.  The
    envelope task id, derived stage id, worker identity, completion status, and
    report file are all required evidence.  Invalid/malformed envelopes are
    returned as reasons for the sync runner's raw evidence output.
    """
    if result_map is None:
        result_map = exact_result_map()
    stage = find_stage(task, stage_id) or {}
    expected_id = stage.get('derived_task_id') or stage_task_id(task['task_id'], stage_id)
    expected_workers = (stage.get('dispatched_workers') or stage.get('agents')
                        or stage.get('assigned_workers') or [])
    expected_keys = {worker_key(str(worker)) for worker in expected_workers if worker}
    accepted: list[dict] = []
    rejected: list[str] = []
    envelopes = result_map.get(expected_id, [])
    completed_worker_counts: dict[str, int] = {}
    for envelope in envelopes:
        if isinstance(envelope, dict) and envelope.get('status') == 'completed':
            worker = envelope.get('worker_key') or envelope.get('worker') or envelope.get('worker_name')
            if worker:
                key = worker_key(str(worker))
                completed_worker_counts[key] = completed_worker_counts.get(key, 0) + 1
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            rejected.append(f'{expected_id}:unparseable')
            continue
        worker = envelope.get('worker_key') or envelope.get('worker') or envelope.get('worker_name')
        actual_worker = worker_key(str(worker)) if worker else ''
        report_file = envelope.get('report_file')
        report_path = RESULTS / str(report_file) if isinstance(report_file, str) else None
        expected_report = f'{expected_id}__{actual_worker}.md' if actual_worker else None
        reason = None
        if envelope.get('task_id') != expected_id:
            reason = 'task_id_mismatch'
        elif envelope.get('status') != 'completed':
            reason = f"status_{envelope.get('status') or 'missing'}"
        elif expected_keys and actual_worker not in expected_keys:
            reason = 'worker_mismatch'
        elif (not isinstance(report_file, str) or not report_file.strip()
              or report_path is None or report_path.name != report_file
              or report_file != expected_report
              or report_path.is_symlink()
              or not report_path.is_file()
              or not stat.S_ISREG(report_path.stat().st_mode)):
            reason = 'report_identity_mismatch' if isinstance(report_file, str) and report_file != expected_report else 'report_missing'
        if reason is None and envelope.get('artifact_schema_version') == 2:
            manifest_check = validate_artifact_manifest(envelope, RESULTS)
            if not manifest_check.get('valid'):
                reason = 'artifact_manifest_' + str(manifest_check.get('reason', 'invalid'))
        if reason:
            rejected.append(f'{expected_id}:{actual_worker or "unknown"}:{reason}')
        else:
            accepted.append(envelope)
    if completed_worker_counts.get(next(iter(expected_keys), ''), 0) > 1:
        rejected.extend(
            f'{expected_id}:{worker_key(str(item.get("worker_key") or item.get("worker") or "unknown"))}:duplicate_or_ambiguous'
            for item in envelopes if isinstance(item, dict) and item.get('status') == 'completed'
        )
        accepted = []
    elif len(accepted) > 1:
        rejected.extend(
            f'{expected_id}:{worker_key(str(item.get("worker_key") or item.get("worker") or "unknown"))}:duplicate_or_ambiguous'
            for item in accepted
        )
        accepted = []
    return accepted, rejected


def research_stage_complete(task: dict, result_map: dict[str, list[dict]]) -> tuple[bool, str]:
    research = find_stage(task, 'research') or {}
    expected_workers = (
        research.get('dispatched_workers')
        or task.get('assigned_workers')
        or research.get('agents')
        or []
    )
    expected_keys = {worker_key(w) for w in expected_workers if w}
    results = result_map.get(task['task_id'], [])
    result_keys = {
        worker_key(r.get('worker_key'))
        for r in results
        if r.get('worker_key')
    }
    completed_keys = {
        worker_key(r.get('worker_key'))
        for r in results
        if r.get('status') == 'completed' and r.get('worker_key')
    }

    if expected_keys and expected_keys.issubset(completed_keys):
        return True, 'waiting_verification'
    if completed_keys:
        return False, 'partial_results'
    if result_keys:
        return False, 'results_received'
    return False, task.get('status', 'queued')


def maybe_dispatch_writing(task: dict, notes: list[str], pm_feedback: str = '', derived_id: str | None = None) -> bool:
    writing = find_stage(task, 'writing')
    if not writing or writing.get('status') not in {'planned', 'queued'}:
        return False
    research_md = exact_result_markdowns(task['task_id'])
    context = aggregate_markdown(research_md, 'Research 결과 본문')
    live = live_notes_block(task)
    if live:
        context = '[PM 실시간 지시 — 최우선 반영]\n' + live + '\n\n---\n\n' + context
    if pm_feedback:
        context = '[PM 게이트 피드백 — 반드시 반영]\n' + pm_feedback + '\n\n---\n\n' + context
    stage_task = create_stage_brief(task, 'writing', context, derived_id=derived_id)
    result = dispatch_stage_brief(stage_task)
    writing['derived_task_id'] = stage_task['task_id']
    writing['status'] = 'in_progress' if result['status'] in {'dispatched', 'partially_dispatched'} else 'blocked'
    if writing['status'] == 'in_progress':
        consume_live_notes(task)
    task['status'] = result['status']
    task['updated_at'] = now_iso()
    task['last_error'] = next((r.get('message') for r in result['records'] if r['status'] != 'dispatched'), None)
    notes.append(f"{task['task_id']}:writing->{result['status']}")
    return True


def maybe_dispatch_verification(task: dict, notes: list[str], pm_feedback: str = '') -> bool:
    stage = find_stage(task, 'verification')
    if not stage or stage.get('status') not in {'planned', 'queued'}:
        return False
    writing_stage = find_stage(task, 'writing')
    if writing_stage and writing_stage.get('status') == 'skipped':
        source_md = exact_result_markdowns(task['task_id'])
        header = f"원본 목표\n\n{task.get('objective', '')}\n\n---\n\nResearch 결과 본문 (문서 작성 단계 없음 — 조사 리포트 자체를 검증할 것)"
    else:
        source_md = exact_result_markdowns(active_writing_id(task))
        header = f"원본 목표\n\n{task.get('objective', '')}\n\n---\n\nWriting draft 본문"
    context = aggregate_markdown(source_md, header)
    live = live_notes_block(task)
    if live:
        context = '[PM 실시간 지시 — 최우선 반영]\n' + live + '\n\n---\n\n' + context
    if pm_feedback:
        context = '[PM 게이트 피드백]\n' + pm_feedback + '\n\n---\n\n' + context
    stage_task = create_stage_brief(task, 'verification', context)
    result = dispatch_stage_brief(stage_task)
    stage['derived_task_id'] = stage_task['task_id']
    stage['status'] = 'in_progress' if result['status'] in {'dispatched', 'partially_dispatched'} else 'blocked'
    if stage['status'] == 'in_progress':
        consume_live_notes(task)
    task['status'] = 'waiting_verification' if stage['status'] == 'in_progress' else result['status']
    task['updated_at'] = now_iso()
    task['last_error'] = next((r.get('message') for r in result['records'] if r['status'] != 'dispatched'), None)
    notes.append(f"{task['task_id']}:verification->{result['status']}")
    return True


def maybe_dispatch_final(task: dict, notes: list[str], pm_feedback: str = '') -> bool:
    stage = find_stage(task, 'final_write')
    if not stage or stage.get('status') not in {'planned', 'queued'}:
        return False
    writing_id = active_writing_id(task)
    verify_id = stage_task_id(task['task_id'], 'verification')
    writing_md = exact_result_markdowns(writing_id)
    verify_md = exact_result_markdowns(verify_id)
    verify_local_md = sorted(VERIFICATIONS.glob(f'{task["task_id"]}*.md'))
    context = aggregate_markdown(writing_md + verify_md + verify_local_md, 'Writing draft + verification feedback')
    live = live_notes_block(task)
    if live:
        context = '[PM 실시간 지시 — 최우선 반영]\n' + live + '\n\n---\n\n' + context
    if pm_feedback:
        context = '[PM 게이트 피드백]\n' + pm_feedback + '\n\n---\n\n' + context
    stage_task = create_stage_brief(task, 'final_write', context)
    result = dispatch_stage_brief(stage_task)
    stage['derived_task_id'] = stage_task['task_id']
    stage['status'] = 'in_progress' if result['status'] in {'dispatched', 'partially_dispatched'} else 'blocked'
    if stage['status'] == 'in_progress':
        consume_live_notes(task)
    task['status'] = result['status']
    task['updated_at'] = now_iso()
    task['last_error'] = next((r.get('message') for r in result['records'] if r['status'] != 'dispatched'), None)
    notes.append(f"{task['task_id']}:final_write->{result['status']}")
    return True


def active_writing_id(task: dict) -> str:
    w = find_stage(task, 'writing')
    if w and w.get('derived_task_id'):
        return w['derived_task_id']
    return stage_task_id(task['task_id'], 'writing')


def pending_live_notes(task: dict) -> list[dict]:
    return [n for n in (task.get('pm_live_notes') or [])
            if isinstance(n, dict) and not n.get('consumed') and str(n.get('note') or '').strip()]


def live_notes_block(task: dict) -> str:
    notes = pending_live_notes(task)
    return '\n'.join(f"- ({n.get('at', '')}) {str(n.get('note'))[:500]}" for n in notes[-5:])


def consume_live_notes(task: dict):
    ts = now_iso()
    for n in pending_live_notes(task):
        n['consumed'] = ts


def _fresh_note_after(task: dict, gate: dict) -> bool:
    gate_at = str((gate or {}).get('at') or '')
    return any(str(n.get('at') or '') > gate_at for n in pending_live_notes(task))


def hermes_gate(task: dict, from_id: str, to_id: str, output_context: str) -> dict:
    """HermesPM에게 완료된 단계 산출물을 검토시켜 다음 단계 진행 여부를 판정받는다."""
    schema = ('{"decision": "proceed|revise|hold", '
              '"severity": "none|minor|major", '
              '"reason": "1-2문장 한국어 판단 근거", '
              '"feedback": "다음 단계 또는 재작업에 전달할 구체 지시(없으면 빈 문자열)"}')
    prompt = (
        "당신은 HermesPM. 파이프라인 '" + from_id + "' 단계가 방금 낸 결과물을 검토해, "
        "다음 단계 '" + to_id + "'로 넘어가도 되는지 게이트 심사한다.\n\n"
        "## 원 업무 목표\n" + str(task.get('objective', '')) + "\n\n"
        "## 제약\n" + str(task.get('constraints') or '(없음)') + "\n\n"
        "## 기대 산출물 형태\n" + str(task.get('deliverable') or '(지정 없음)') + "\n\n"
        + (("## PM 실시간 지시 (심사와 feedback에 반드시 반영)\n" + live_notes_block(task) + "\n\n") if pending_live_notes(task) else "")
        + "## '" + from_id + "' 단계 결과물 본문\n" + output_context + "\n\n"
        "## 판단 기준\n"
        "- 목표/제약을 충족하고 다음 단계 진행이 가능하면 decision=proceed.\n"
        "- 경미한 보완만 필요하면 decision=revise, severity=minor, feedback에 수정 지시.\n"
        "- 사실오류/핵심 누락/방향 이탈 등 중대한 결함이면 decision=hold, severity=major, reason에 사유.\n\n"
        "## 출력 형식 (CRITICAL)\n"
        "아래 스키마의 JSON 객체 하나만 출력. 코드펜스/설명/기타 텍스트 금지.\n"
        + schema
    )
    try:
        code, out, err = server.run_command(
            [server.PM_CLAUDE_BIN, '-p', '--agent', server.PM_AGENT_NAME, prompt],
            timeout=server.PM_LLM_TIMEOUT,
            cwd='/home/raphael',
        )
    except Exception as exc:
        return {'decision': 'pending', 'severity': 'none', 'reason': f'gate 예외: {exc}', 'feedback': ''}
    if code != 0:
        return {'decision': 'pending', 'severity': 'none',
                'reason': f'gate claude exit {code}: {(err or out).strip()[:160]}', 'feedback': ''}
    try:
        parsed = server.pm_llm_extract_json(out)
    except Exception as exc:
        return {'decision': 'pending', 'severity': 'none', 'reason': f'gate 파싱 실패: {exc}', 'feedback': ''}
    decision = str(parsed.get('decision') or '').strip().lower()
    if decision not in {'proceed', 'revise', 'hold'}:
        decision = 'pending'
    return {
        'decision': decision,
        'severity': str(parsed.get('severity') or 'none').strip().lower(),
        'reason': str(parsed.get('reason') or '').strip(),
        'feedback': str(parsed.get('feedback') or '').strip(),
        'at': now_iso(),
    }


def _apply_gate(task, source_stage, from_id, to_id, source_context, notes, allow_revise=False):
    """반환: (action, feedback, mutated). action in {proceed, revise, hold, wait}."""
    task_id = task['task_id']

    # 1) 대시보드 수동 오버라이드 우선
    override = source_stage.pop('gate_override', None)
    if override == 'approve':
        fb = (source_stage.get('gate') or {}).get('feedback', '')
        source_stage['status'] = 'completed'
        source_stage['gate'] = {'decision': 'proceed', 'severity': 'none',
                                'reason': '사용자 승인', 'feedback': fb, 'override': True, 'at': now_iso()}
        notes.append(f'{task_id}:OVERRIDE[{from_id}]=approve')
        return 'proceed', fb, True
    if override == 'revise':
        fb = (source_stage.get('gate') or {}).get('feedback', '')
        source_stage['gate'] = None
        source_stage['gate_revise_count'] = 0
        source_stage['status'] = 'completed'
        notes.append(f'{task_id}:OVERRIDE[{from_id}]=revise')
        return ('revise' if allow_revise else 'proceed'), fb, True

    # 2) 게이트 판정 (없거나 직전이 transient pending이면 재호출)
    gate = source_stage.get('gate')
    if gate and source_stage.get('status') == 'gate_hold' and _fresh_note_after(task, gate):
        source_stage['gate'] = None
        gate = None
        notes.append(f'{task_id}:gate[{from_id}] PM 실시간 지시로 재심사')
    mutated = False
    if not gate or gate.get('decision') == 'pending':
        if not GATE_ENABLED:
            return 'proceed', '', False
        gate = hermes_gate(task, from_id, to_id, source_context)
        if gate.get('decision') == 'pending':
            source_stage['gate'] = None
            notes.append(f'{task_id}:gate[{from_id}]=pending(retry)')
            return 'wait', '', False
        source_stage['gate'] = gate
        mutated = True
        notes.append(f"{task_id}:gate[{from_id}]={gate.get('decision')}/{gate.get('severity')}")

    decision = gate.get('decision')
    severity = gate.get('severity', 'none')
    fb = gate.get('feedback', '')
    if decision == 'proceed':
        return 'proceed', fb, mutated
    if decision == 'revise' and severity != 'major':
        if allow_revise and source_stage.get('gate_revise_count', 0) < GATE_MAX_REVISE:
            return 'revise', fb, mutated
        if not allow_revise:
            return 'proceed', fb, mutated  # 경미 + 재작업 미지원 게이트 -> 피드백 주입 후 진행

    # 3) hold: 중대 결함 또는 재작업 예산 소진
    if source_stage.get('status') != 'gate_hold':
        source_stage['status'] = 'gate_hold'
        source_stage['gate_hold_reason'] = gate.get('reason', '')
        task['status'] = 'needs_pm_review'
        task['last_error'] = f"[게이트 보류:{from_id}] " + gate.get('reason', '')
        notes.append(f"{task_id}:HOLD[{from_id}] " + gate.get('reason', '')[:80])
        mutated = True
    return 'hold', '', mutated


def hermes_entry_gate(task: dict) -> dict:
    """파이프라인 시작 전, HermesPM이 브리프만 보고 research 진입을 판단."""
    worker_descs = {
        'HermesResearcher': '웹 조사 (PC 로컬 실행)',
        'researcher-co': '웹 조사 (공식 출처 중심)',
        'researcher_agent': '웹 조사 (병렬 대안 관점)',
        'analyst-co': '입력 파일 분석 전용 — RFP/계약서/데이터. 첨부 입력 파일이 있는 분석 업무에만 선택',
    }
    workers_line = ', '.join(f"{w}({worker_descs.get(w, '')})" for w in ENTRY_RESEARCH_WORKERS)
    input_names = [Path(p).name for p in (task.get('input_files') or [])]
    inputs_line = '\n'.join('- ' + n for n in input_names) or '(없음)'
    conv_lines = []
    for t in (task.get('pm_conversation') or [])[-16:]:
        speaker = 'Raphael' if t.get('role') == 'user' else 'HermesPM'
        txt = str(t.get('text') or '').strip()
        if txt:
            conv_lines.append(f'{speaker}: {txt[:400]}')
    conv_text = '\n'.join(conv_lines) or '(기록 없음)'
    interp = str(task.get('pm_interpretation') or '').strip() or '(기록 없음)'
    pipeline_keys = '|'.join(PIPELINE_CATALOG)
    pipeline_lines = ''.join(f"  * {k} — {v['desc']}\n" for k, v in PIPELINE_CATALOG.items())
    schema = ('{"decision": "proceed|skip_research|hold", '
              '"pipeline": "' + pipeline_keys + '", '
              '"workers": ["proceed일 때 쓸 research 워커(위 목록에서만)"], '
              '"reason": "1-2문장 한국어 판단 근거", '
              '"feedback": "research 워커/writing에 전달할 지시(없으면 빈 문자열)"}')
    prompt = (
        "당신은 HermesPM. 아래 업무 브리프를 보고 파이프라인 진입을 판단한다. 아직 어떤 단계도 실행되지 않았다.\n\n"
        "## 제목\n" + str(task.get('title', '')) + "\n\n"
        "## 업무 목표\n" + str(task.get('objective', '')) + "\n\n"
        "## 배경/맥락\n" + str(task.get('context') or '(없음)') + "\n\n"
        "## 제약\n" + str(task.get('constraints') or '(없음)') + "\n\n"
        "## 기대 산출물\n" + str(task.get('deliverable') or '(지정 없음)') + "\n\n"
        "## 첨부된 입력 파일\n" + inputs_line + "\n\n"
        "## 브리프 작성 대화 원문 (사용자 실제 발화 — 브리프와 대조할 것)\n" + conv_text + "\n\n"
        "## PM의 해석 요약\n" + interp + "\n\n"
        + (("## PM 실시간 지시 (판단에 반드시 반영)\n" + live_notes_block(task) + "\n\n") if pending_live_notes(task) else "")
        + "## 사용 가능한 research 워커\n" + workers_line + "\n\n"
        "## 판단 기준\n"
        "- 웹/외부 조사가 필요하면 decision=proceed, workers에 적합한 워커 선택(간단하면 1곳, 교차검증 중요하면 여러 곳).\n"
        "- pipeline으로 업무 프로세스를 선택한다 (proceed와 skip_research 모두 적용):\n"
        + pipeline_lines +
        "  기대 산출물(deliverable)과 사용자 발화를 근거로 고르고, 애매하면 full을 쓴다. skip_research일 때는 full 또는 write_verify만 의미가 있다.\n"
        "- 첨부된 입력 파일을 분석하는 업무(RFP/계약서/기획서 검토, 데이터 분석)는 pipeline=analyze_verify + workers=[analyst-co]를 기본으로 한다. 웹 조사 병행이 필요하면 조사 워커를 추가한다. 입력 파일이 없으면 analyze_verify와 analyst-co를 선택하지 않는다.\n"
        "- 이미 브리프에 자료가 충분하거나 순수 작성 작업이면 decision=skip_research(research 생략, 바로 writing).\n"
        "- 목표/범위가 불분명해 그대로 진행하면 안 되면 decision=hold, reason에 확인 필요사항.\n"
        "- 브리프의 objective/context에 사용자 발화에 없는 용어 재정의·해석·가정이 들어 있고, 그 해석에 따라 조사 방향이 크게 달라질 수 있으면 decision=hold로 사용자 확인을 요청한다. 대화 원문과 브리프가 일치하면 해당 없음.\n"
        "- '테스트', '간단한 업무'라는 표현만을 근거로 교차검증(복수 워커)을 생략하지 않는다. 워커 축소는 조사 범위가 좁고 사실검증 부담이 낮은 경우에만 한다.\n\n"
        "## 출력 형식 (CRITICAL)\n아래 스키마의 JSON 객체 하나만 출력. 코드펜스/설명 금지.\n"
        + schema
    )
    try:
        code, out, err = server.run_command(
            [server.PM_CLAUDE_BIN, '-p', '--agent', server.PM_AGENT_NAME, prompt],
            timeout=server.PM_LLM_TIMEOUT, cwd='/home/raphael',
        )
    except Exception as exc:
        return {'decision': 'pending', 'reason': f'entry gate 예외: {exc}', 'workers': [], 'feedback': ''}
    if code != 0:
        return {'decision': 'pending', 'reason': f'entry gate claude exit {code}: {(err or out).strip()[:160]}', 'workers': [], 'feedback': ''}
    try:
        parsed = server.pm_llm_extract_json(out)
    except Exception as exc:
        return {'decision': 'pending', 'reason': f'entry gate 파싱 실패: {exc}', 'workers': [], 'feedback': ''}
    decision = str(parsed.get('decision') or '').strip().lower()
    if decision not in {'proceed', 'skip_research', 'hold'}:
        decision = 'pending'
    workers = parsed.get('workers') or []
    if isinstance(workers, str):
        workers = [w.strip() for w in workers.split(',') if w.strip()]
    workers = [w for w in workers if w in ENTRY_RESEARCH_WORKERS]
    pipeline = str(parsed.get('pipeline') or '').strip().lower()
    if pipeline not in PIPELINE_CATALOG:
        pipeline = 'full'
    return {
        'decision': decision,
        'pipeline': pipeline,
        'workers': workers,
        'reason': str(parsed.get('reason') or '').strip(),
        'feedback': str(parsed.get('feedback') or '').strip(),
        'at': now_iso(),
    }


PIPELINE_CATALOG = {
    'full': {
        'skip': [],
        'desc': '제안서/보고서 등 조사 결과를 바탕으로 새 문서를 작성하고 최종본까지 다듬어야 하는 격식 문서 업무 (조사→작성→검증→최종본)',
    },
    'write_verify': {
        'skip': ['final_write'],
        'desc': '초안+검증으로 충분하고 별도 최종본 재작성은 불필요한 일반 문서 업무 (조사→작성→검증)',
    },
    'research_verify': {
        'skip': ['writing', 'final_write'],
        'desc': '조사 리포트 자체가 최종 산출물인 업무 — 현황 조사, 요약 정리, 팩트 확인 (조사→검증)',
    },
    'analyze_verify': {
        'skip': ['writing', 'final_write'],
        'desc': '첨부된 입력 파일(RFP·계약서·기획서·CSV/XLSX 데이터)을 분석한 리포트가 최종 산출물인 업무 (분석→검증). 입력 파일이 있을 때만 선택',
    },
    'research_only': {
        'skip': ['writing', 'verification', 'final_write'],
        'desc': '빠른 내부 참고용 단순 조사로 검증까지 불필요한 저위험 업무 (조사만)',
    },
}
PIPELINE_SKIP_STAGES = {k: v['skip'] for k, v in PIPELINE_CATALOG.items() if v['skip']}


def apply_pipeline_shape(task: dict, pipeline: str, notes: list[str]):
    shape = pipeline if pipeline in PIPELINE_SKIP_STAGES else 'full'
    task['pipeline_shape'] = shape
    for sid in PIPELINE_SKIP_STAGES.get(shape, []):
        st = find_stage(task, sid)
        if st and st.get('status') in {'planned', 'queued'}:
            st['status'] = 'skipped'
            st['skipped'] = True
    if shape == 'analyze_verify':
        st = find_stage(task, 'research')
        if st:
            st['label'] = 'Analysis'
    if shape != 'full':
        notes.append(f"{task['task_id']}:pipeline={shape}")


def dispatch_research(task: dict, workers, feedback: str, notes: list[str]):
    research = find_stage(task, 'research')
    live = live_notes_block(task)
    if live:
        feedback = ((feedback + '\n\n') if feedback else '') + '[PM 실시간 지시]\n' + live
    avail = server.load_workers()
    valid = [w for w in (workers or []) if w in avail and avail[w].get('mode') != 'local' and avail[w].get('enabled', True)]
    if not valid:
        valid = [w for w in (task.get('assigned_workers') or ENTRY_RESEARCH_WORKERS)
                 if w in avail and avail[w].get('mode') != 'local']
    if feedback:
        try:
            task['context'] = (task.get('context') or '') + f"\n\n[PM 진입 지시]\n{feedback}"
            save_json(Path(task['artifacts']['json_brief']), task)
        except Exception:
            pass
    task['research_evidence_policy'] = research_evidence_policy()
    policy_marker = '[Research Evidence Policy]'
    constraints = str(task.get('constraints') or '')
    if policy_marker not in constraints:
        task['constraints'] = (constraints.rstrip() + '\n\n' + policy_marker + '\n' + research_evidence_policy_text()).strip()
    save_json(Path(task['artifacts']['json_brief']), task)
    stage_task = create_stage_brief(
        {**task, 'assigned_workers': valid}, 'research',
        feedback or task.get('context', ''), derived_id=task['task_id'],
    )
    stage_task['research_evidence_policy'] = task['research_evidence_policy']
    save_json(Path(stage_task['artifacts']['json_brief']), stage_task)
    result = dispatch_stage_brief(stage_task)
    research['status'] = 'in_progress' if result['status'] in {'dispatched', 'partially_dispatched'} else 'blocked'
    if research['status'] == 'in_progress':
        consume_live_notes(task)
    research['dispatched_workers'] = valid
    task['status'] = result['status']
    task['updated_at'] = now_iso()
    task['last_error'] = next((r.get('message') for r in result['records'] if r['status'] != 'dispatched'), None)
    notes.append(f"{task['task_id']}:ENTRY->research({','.join(valid)})[{result['status']}]")


def _apply_entry_gate(task, research, notes):
    """반환: (action, workers, feedback). action in {proceed, skip, hold, wait}."""
    task_id = task['task_id']
    override = research.pop('gate_override', None)
    if override in {'approve', 'proceed', 'revise'}:
        research['entry_gate'] = {'decision': 'proceed', 'reason': '사용자 승인', 'workers': [], 'feedback': '', 'override': True, 'at': now_iso()}
        notes.append(f'{task_id}:ENTRY-OVERRIDE=proceed')
        return 'proceed', [], ''
    if override == 'skip':
        research['entry_gate'] = {'decision': 'skip_research', 'reason': '사용자 생략', 'feedback': '', 'override': True, 'at': now_iso()}
        notes.append(f'{task_id}:ENTRY-OVERRIDE=skip')
        return 'skip', [], ''

    eg = research.get('entry_gate')
    if eg and research.get('status') == 'entry_hold' and _fresh_note_after(task, eg):
        research['entry_gate'] = None
        eg = None
        notes.append(f'{task_id}:entry_gate PM 실시간 지시로 재심사')
    if not eg or eg.get('decision') == 'pending':
        if not GATE_ENABLED:
            return 'proceed', [], ''
        eg = hermes_entry_gate(task)
        if eg.get('decision') == 'pending':
            research['entry_gate'] = None
            notes.append(f'{task_id}:entry_gate=pending(retry)')
            return 'wait', [], ''
        research['entry_gate'] = eg
        notes.append(f"{task_id}:entry_gate={eg.get('decision')}")

    d = eg.get('decision')
    if d == 'proceed':
        apply_pipeline_shape(task, eg.get('pipeline') or 'full', notes)
        return 'proceed', eg.get('workers') or [], eg.get('feedback', '')
    if d == 'skip_research':
        pl = eg.get('pipeline') or 'full'
        if pl not in {'full', 'write_verify'}:
            pl = 'full'
        apply_pipeline_shape(task, pl, notes)
        return 'skip', [], eg.get('feedback', '')
    if research.get('status') != 'entry_hold':
        research['status'] = 'entry_hold'
        research['entry_hold_reason'] = eg.get('reason', '')
        task['status'] = 'needs_pm_review'
        task['last_error'] = '[진입 게이트 보류] ' + eg.get('reason', '')
        notes.append(f'{task_id}:ENTRY-HOLD ' + eg.get('reason', '')[:80])
    return 'hold', [], ''


def deliverable_stage_id(task: dict) -> str:
    """최종 산출물을 낸 단계 id (검증 제외, 완료·비생략 우선순위 final_write>writing>research)."""
    for sid in ('final_write', 'writing', 'research'):
        st = find_stage(task, sid)
        if st and st.get('status') == 'completed' and not st.get('skipped'):
            return sid
    return 'research'


def final_deliverable_markdowns(task: dict) -> list:
    sid = deliverable_stage_id(task)
    tid = task['task_id']
    if sid == 'final_write':
        return exact_result_markdowns(stage_task_id(tid, 'final_write'))
    if sid == 'writing':
        return exact_result_markdowns(active_writing_id(task))
    return exact_result_markdowns(tid)


def hermes_final_review(task: dict, deliverable_context: str) -> dict:
    """파이프라인 종료 후, 사용자 원 요청 대비 최종 산출물을 마감 총평한다."""
    conv_lines = []
    for t in (task.get('pm_conversation') or [])[-16:]:
        speaker = 'Raphael' if t.get('role') == 'user' else 'HermesPM'
        txt = str(t.get('text') or '').strip()
        if txt:
            conv_lines.append(f'{speaker}: {txt[:400]}')
    conv_text = '\n'.join(conv_lines) or '(기록 없음)'
    interp = str(task.get('pm_interpretation') or '').strip() or '(기록 없음)'
    live = live_notes_block(task) or '(없음)'
    schema = ('{"verdict": "meets|partial|not_meets", '
              '"comment": "1-2문장 한국어 총평(사용자 원 요청 대비 결과 평가)", '
              '"gaps": "미충족·보완 필요 사항, 없으면 빈 문자열"}')
    prompt = (
        "당신은 HermesPM. 파이프라인이 끝났다. 최종 산출물이 '사용자가 처음 요청한 것'을 실제로 충족하는지 마감 총평한다.\n\n"
        "## 사용자 원 발화 (가장 중요 — 이 요청에 답했는지 본다)\n" + conv_text + "\n\n"
        "## PM의 해석\n" + interp + "\n\n"
        "## 업무 목표\n" + str(task.get('objective', '')) + "\n\n"
        "## 기대 산출물\n" + str(task.get('deliverable') or '(지정 없음)') + "\n\n"
        "## 진행 중 PM 실시간 지시\n" + live + "\n\n"
        "## 최종 산출물 본문\n" + deliverable_context + "\n\n"
        "## 판단 기준\n"
        "- 사용자 원 요청·목표를 충실히 충족하면 verdict=meets.\n"
        "- 큰 방향은 맞으나 일부 보완이 필요하면 verdict=partial, gaps에 보완점(완료하되 총평에 남김).\n"
        "- 요청과 결과가 어긋나거나 핵심이 빠졌으면 verdict=not_meets, gaps에 무엇이 왜 안 맞는지.\n\n"
        "## 출력 형식 (CRITICAL)\n아래 스키마의 JSON 객체 하나만 출력. 코드펜스/설명 금지.\n" + schema
    )
    try:
        code, out, err = server.run_command(
            [server.PM_CLAUDE_BIN, '-p', '--agent', server.PM_AGENT_NAME, prompt],
            timeout=server.PM_LLM_TIMEOUT, cwd='/home/raphael',
        )
    except Exception as exc:
        return {'verdict': 'pending', 'comment': f'총평 예외: {exc}', 'gaps': ''}
    if code != 0:
        return {'verdict': 'pending', 'comment': f'총평 claude exit {code}: {(err or out).strip()[:120]}', 'gaps': ''}
    try:
        parsed = server.pm_llm_extract_json(out)
    except Exception as exc:
        return {'verdict': 'pending', 'comment': f'총평 파싱 실패: {exc}', 'gaps': ''}
    verdict = str(parsed.get('verdict') or '').strip().lower()
    if verdict not in {'meets', 'partial', 'not_meets'}:
        verdict = 'pending'
    return {
        'verdict': verdict,
        'comment': str(parsed.get('comment') or '').strip(),
        'gaps': str(parsed.get('gaps') or '').strip(),
        'at': now_iso(),
    }


def _reopen_deliverable(task: dict, notes: list):
    """최종 총평 재작업: 산출물 단계와 그 이후 완료단계를 재개, 총평 gaps를 재작업 지시로 주입."""
    task_id = task['task_id']
    sid = deliverable_stage_id(task)
    order = ['research', 'writing', 'verification', 'final_write']
    review = task.get('pm_final_review') or {}
    gaps = (review.get('gaps') or review.get('comment') or '').strip()
    if gaps:
        live = task.get('pm_live_notes') or []
        live.append({'note': '[최종 총평 재작업 지시] ' + gaps, 'at': now_iso(), 'consumed': None})
        task['pm_live_notes'] = live[-20:]
    reopen_from = order.index(sid) if sid in order else 0
    for s in task.get('stages', []):
        if s.get('id') in order and order.index(s['id']) >= reopen_from and s.get('status') == 'completed' and not s.get('skipped'):
            s['status'] = 'queued' if s['id'] == sid else 'planned'
            s['gate'] = None
            s.pop('gate_revise_count', None)
            s.pop('derived_task_id', None)
    task.pop('pm_final_review', None)
    task['status'] = 'results_received'
    task['last_error'] = None
    notes.append(f'{task_id}:FINAL-REWORK reopen from {sid}')


def _apply_final_review(task: dict, notes: list):
    """반환: (action, mutated). action in {complete, hold, wait, rework}."""
    task_id = task['task_id']
    override = task.pop('final_review_override', None)
    if override == 'accept':
        prev = task.get('pm_final_review') or {}
        task['pm_final_review'] = {
            'verdict': prev.get('verdict') or 'meets',
            'comment': prev.get('comment') or '사용자 승인으로 완료 처리',
            'gaps': prev.get('gaps', ''), 'override': True, 'at': now_iso(),
        }
        notes.append(f'{task_id}:FINAL-OVERRIDE=accept')
        return 'complete', True
    if override == 'rework':
        _reopen_deliverable(task, notes)
        return 'rework', True

    fr = task.get('pm_final_review')
    if fr and fr.get('verdict') in {'meets', 'partial', 'not_meets'}:
        return ('complete' if fr.get('verdict') in {'meets', 'partial'} else 'hold'), False

    if not GATE_ENABLED:
        task['pm_final_review'] = {'verdict': 'meets', 'comment': '(게이트 비활성)', 'gaps': '', 'at': now_iso()}
        return 'complete', True

    ctx = aggregate_markdown(final_deliverable_markdowns(task), '최종 산출물 본문')
    review = hermes_final_review(task, ctx)
    if review.get('verdict') == 'pending':
        notes.append(f'{task_id}:final_review=pending(retry)')
        return 'wait', False
    task['pm_final_review'] = review
    v = review.get('verdict')
    notes.append(f'{task_id}:final_review={v}')
    if v in {'meets', 'partial'}:
        return 'complete', True
    task['status'] = 'needs_pm_review'
    task['last_error'] = '[최종 총평: 미충족] ' + (review.get('comment') or '')
    return 'hold', True


def sync_task_statuses() -> list[str]:
    notes = []
    result_map = exact_result_map()

    for path in sorted(BRIEFS.glob('T-*.json')):
        task = load_json(path)
        if task.get('status') == 'cancelled':
            continue
        if task.get('pipeline_name') != 'research-write-verify-finalize':
            continue
        task_id = task.get('task_id')
        if not task_id:
            continue
        changed = False
        stages = task.get('stages') or server.default_pipeline_stages(task_id, task.get('deliverable', ''), task.get('reviewer', 'HermesVerifier'))
        task['stages'] = stages

        research = find_stage(task, 'research')
        writing = find_stage(task, 'writing')
        verification = find_stage(task, 'verification')
        final_write = find_stage(task, 'final_write')
        if verification is not None and verification.get('completion_policy') != 'any':
            verification['completion_policy'] = 'any'
            changed = True

        # GATE 0: 파이프라인 진입 판단 (PM이 research 진행/생략/보류 결정)
        if research and research.get('status') in {'queued', 'planned', 'entry_hold'} and not stage_completed_by_results(result_map, task_id):
            e_action, e_workers, e_feedback = _apply_entry_gate(task, research, notes)
            if e_action == 'proceed':
                dispatch_research(task, e_workers, e_feedback, notes)
                changed = True
            elif e_action == 'skip':
                research['status'] = 'completed'
                research['skipped'] = True
                research['gate'] = {'decision': 'proceed', 'severity': 'none',
                                    'reason': 'PM 판단: research 생략', 'at': now_iso(),
                                    'feedback': (e_feedback or '') + ' (research 생략됨: 브리프 기반 작성)'}
                task['status'] = 'results_received'
                changed = True
            elif e_action == 'hold':
                changed = True

        research_done, research_status = research_stage_complete(task, result_map)
        if research and research.get('status') not in {'completed', 'gate_hold', 'entry_hold'}:
            if research_done:
                research['status'] = 'completed'
                changed = True
            elif research_status in {'results_received', 'partial_results'} and research.get('status') != 'in_progress':
                research['status'] = 'in_progress'
                task['status'] = research_status
                changed = True

        # GATE 1: research -> writing
        if research and research.get('status') in {'completed', 'gate_hold'} and writing and writing.get('status') in {'planned', 'queued'}:
            ctx = aggregate_markdown(exact_result_markdowns(task_id), 'Research 결과 본문')
            action, feedback, mutated = _apply_gate(task, research, 'research', 'writing', ctx, notes, allow_revise=False)
            if mutated:
                changed = True
            if action == 'proceed':
                if research.get('status') != 'completed':
                    research['status'] = 'completed'
                if maybe_dispatch_writing(task, notes, pm_feedback=feedback):
                    changed = True

        writing_active = active_writing_id(task)
        writing_envelopes, writing_rejections = stage_result_envelopes(task, 'writing', result_map)
        writing_done = bool(writing_envelopes)
        if writing_rejections:
            notes.append(f'{task_id}:writing evidence rejected=' + '|'.join(writing_rejections))
        if writing and writing_done and writing.get('status') in {'planned', 'queued', 'in_progress'}:
            writing['status'] = 'completed'
            task['status'] = 'results_received'
            changed = True
            notes.append(f'{task_id}:writing envelope correlated task={writing_active} worker={writing_envelopes[0].get("worker_key")} report={writing_envelopes[0].get("report_file")}')
            if verification and verification.get('status') in {'planned', 'queued'}:
                verification['status'] = 'queued'

        # GATE 1.5: writing 생략 파이프라인 — research -> verification 직결
        if research and research.get('status') in {'completed', 'gate_hold'} and writing and writing.get('status') == 'skipped' and verification and verification.get('status') in {'planned', 'queued'}:
            ctx = aggregate_markdown(exact_result_markdowns(task_id), 'Research 결과 본문 (조사 리포트 자체가 최종 산출물 — 이 내용을 검증 대상으로 삼을 것)')
            action, feedback, mutated = _apply_gate(task, research, 'research', 'verification', ctx, notes, allow_revise=False)
            if mutated:
                changed = True
            if action == 'proceed':
                if research.get('status') != 'completed':
                    research['status'] = 'completed'
                if maybe_dispatch_verification(task, notes, pm_feedback=feedback):
                    changed = True

        # GATE 2: writing -> verification (auto-revise 허용)
        if writing and writing.get('status') in {'completed', 'gate_hold'} and verification and verification.get('status') in {'planned', 'queued'}:
            ctx = aggregate_markdown(exact_result_markdowns(writing_active), "원본 목표\n\n" + str(task.get('objective', '')) + "\n\n---\n\nWriting draft 본문")
            action, feedback, mutated = _apply_gate(task, writing, 'writing', 'verification', ctx, notes, allow_revise=True)
            if mutated:
                changed = True
            if action == 'proceed':
                if writing.get('status') != 'completed':
                    writing['status'] = 'completed'
                if maybe_dispatch_verification(task, notes, pm_feedback=feedback):
                    changed = True
            elif action == 'revise':
                n = writing.get('gate_revise_count', 0) + 1
                writing['gate'] = None
                writing['gate_revise_count'] = n
                writing['status'] = 'queued'
                new_id = stage_task_id(task_id, 'writing') + '-r' + str(n)
                if maybe_dispatch_writing(task, notes, pm_feedback=feedback, derived_id=new_id):
                    notes.append(f'{task_id}:writing REVISE r{n}')
                changed = True

        verification_envelopes, verification_rejections = stage_result_envelopes(task, 'verification', result_map)
        verification_done = bool(verification_envelopes)
        if verification_rejections:
            notes.append(f'{task_id}:verification evidence rejected=' + '|'.join(verification_rejections))
        if verification and verification_done and verification.get('status') in {'planned', 'queued', 'in_progress'}:
            verification['status'] = 'completed'
            task['status'] = 'results_received'
            changed = True
            if final_write and final_write.get('status') in {'planned', 'queued'}:
                final_write['status'] = 'queued'

        # GATE 3: verification -> final_write
        if verification and verification.get('status') in {'completed', 'gate_hold'} and final_write and final_write.get('status') in {'planned', 'queued'}:
            verify_md_ctx = exact_result_markdowns(stage_task_id(task_id, 'verification')) + sorted(VERIFICATIONS.glob(f'{task_id}*.md'))
            ctx = aggregate_markdown(verify_md_ctx, 'Verification 리포트 본문')
            action, feedback, mutated = _apply_gate(task, verification, 'verification', 'final_write', ctx, notes, allow_revise=False)
            if mutated:
                changed = True
            if action == 'proceed':
                if verification.get('status') != 'completed':
                    verification['status'] = 'completed'
                if maybe_dispatch_final(task, notes, pm_feedback=feedback):
                    changed = True

        final_envelopes, final_rejections = stage_result_envelopes(task, 'final_write', result_map)
        final_done = bool(final_envelopes)
        if final_rejections:
            notes.append(f'{task_id}:final_write evidence rejected=' + '|'.join(final_rejections))
        if final_write and final_done and final_write.get('status') in {'planned', 'queued', 'in_progress'}:
            final_write['status'] = 'completed'
            task['status'] = 'completed'
            changed = True

        stage_states = [s.get('status') for s in stages if s]
        if stage_states and all(st in {'completed', 'skipped'} for st in stage_states) and task.get('status') != 'completed':
            fr_action, fr_mutated = _apply_final_review(task, notes)
            if fr_action == 'complete':
                task['status'] = 'completed'
                changed = True
            elif fr_mutated:
                changed = True

        if changed:
            task['updated_at'] = now_iso()
            save_json(path, task)
            notes.append(f'{task_id}:{task.get("status", "updated")}')
    return notes


if __name__ == '__main__':
    SYNC_LOCK.parent.mkdir(parents=True, exist_ok=True)
    _lock_fp = open(SYNC_LOCK, 'w')
    try:
        fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('skip: previous sync still running')
        sys.exit(0)
    rc, pull_summary = pull_results()
    remote_status_summary = sync_remote_worker_status()
    notes = sync_task_statuses()
    SYNC_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    save_json(SYNC_EVIDENCE, {
        'observed_at': now_iso(),
        'pull_exit': rc,
        'pull_summary': pull_summary,
        'remote_status_summary': remote_status_summary,
        'status_updates': notes,
        'last_result': 'success' if rc == 0 else 'error',
    })
    print(pull_summary)
    print(remote_status_summary)
    print('status_updates=' + (','.join(notes) if notes else 'none'))
    print('sync_evidence=' + (','.join(n for n in notes if 'envelope correlated' in n or 'evidence rejected' in n) or 'none'))
