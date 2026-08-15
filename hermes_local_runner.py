#!/usr/bin/env python3
"""Hermes local worker runner (PC WSL side).

허브 대시보드가 local-inbox 모드로 복사한 brief(JSON)를 감지해
네이티브 claude CLI(headless)로 실행하고, 맥북 worker_runner.py와 동일한 규칙으로
result envelope(json) + 보고서(md)를 operations/results/에 남긴다.

- operations/local-inbox/HermesResearcher/*.json → claude -p --agent HermesResearcher
- 결과: operations/results/<task_id>__<worker_key>.{json,md}
- HTML 산출물은 results/<task_id>__<worker_key>__<파일명>.html로 복사
- 처리한 brief는 local-inbox/<worker>/processed/ 로 이동
- 같은 task_id+worker 결과가 이미 있으면 재처리하지 않음 (멱등성)
- API 일시 오류(429/5xx/529/timeout)는 brief를 남겨 다음 주기에 재시도

실행 주체: Windows 작업 스케줄러 AgentHubLocalRunner (2분 주기, flock 중복 방지)
"""

import fcntl
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from artifact_contract import emit_artifact_manifest

BASE_DIR = Path('/home/raphael/myproject')
OPERATIONS_DIR = BASE_DIR / 'operations'
LOCAL_INBOX_DIR = OPERATIONS_DIR / 'local-inbox'
RESULTS_DIR = OPERATIONS_DIR / 'results'
WORKSPACE_DIR = OPERATIONS_DIR / 'local-workspace'
LOGS_DIR = BASE_DIR / 'logs'
LOCK_FILE = BASE_DIR / '.hermes_local_runner.lock'
AGENTS_DIR = Path.home() / '.claude' / 'agents'

CLAUDE_BIN = os.environ.get('CLAUDE_BIN', '/home/raphael/.local/bin/claude')
TASK_TIMEOUT_SECONDS = int(os.environ.get('WORKER_TASK_TIMEOUT', '900'))

WORKER_SPECS = {
    'HermesResearcher': {'name': 'HermesResearcher', 'agent': 'HermesResearcher'},
}

TRANSIENT_MARKERS = ('429', '500', '502', '503', '504', '529', 'overloaded', 'timeout', 'rate limit')

logger = logging.getLogger('hermes-local-runner')


def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOGS_DIR / 'hermes-local-runner.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.setLevel(logging.INFO)


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def agent_model(agent):
    if not agent:
        return None
    path = AGENTS_DIR / (agent + '.md')
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('model:'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return None


def build_prompt(brief):
    sections = [
        '당신은 멀티에이전트 허브의 worker입니다. 아래 업무 지시(brief)를 수행하고,',
        '최종 산출물을 markdown 보고서 형식의 텍스트로만 답하세요.',
        '파일 생성/수정 등 부수 효과는 제약사항에서 명시적으로 허용된 경우에만 수행하세요.',
        '파일 산출물로 HTML 문서를 생성하는 경우, 동일 내용의 마크다운(.md) 원본도 같은 디렉터리에 쌍으로 저장하세요.',
        '',
        '## Task ID\n' + str(brief.get('task_id', 'unknown')),
        '## 제목\n' + str(brief.get('title', '')),
        '## 목표\n' + str(brief.get('objective', '')),
    ]
    for key, label in (
        ('context', '배경/맥락'),
        ('constraints', '제약사항'),
        ('deliverable', '원하는 산출물'),
    ):
        value = brief.get(key)
        if value:
            sections.append('## ' + label + '\n' + str(value))
    return '\n\n'.join(sections)


def is_transient(text):
    lowered = (text or '').lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def run_claude(brief, task_workspace, agent):
    prompt = build_prompt(brief)
    cmd = [CLAUDE_BIN, '-p', prompt, '--output-format', 'json',
           '--agent', agent, '--permission-mode', 'acceptEdits']
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(task_workspace),
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'transient': True,
                'error': 'timeout after %ss' % TASK_TIMEOUT_SECONDS,
                'report': None, 'raw': None, 'exit_code': None}
    except OSError as exc:
        return {'ok': False, 'transient': False,
                'error': 'failed to launch claude: %s' % exc,
                'report': None, 'raw': None, 'exit_code': None}

    try:
        payload = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = None

    if proc.returncode != 0:
        err_text = (proc.stderr or '') + (proc.stdout or '')
        return {'ok': False, 'transient': is_transient(err_text),
                'error': 'claude exited %s: %s' % (proc.returncode, proc.stderr.strip()[:500]),
                'report': proc.stdout or None, 'raw': payload, 'exit_code': proc.returncode}

    report = None
    if isinstance(payload, dict):
        report = payload.get('result')
    return {'ok': True, 'transient': False, 'error': None,
            'report': report or proc.stdout, 'raw': payload, 'exit_code': proc.returncode}


def deliver_html_artifacts(task_id, worker_key, artifact_paths):
    delivered = []
    for raw in artifact_paths:
        p = Path(raw)
        if p.suffix.lower() != '.html' or not p.is_file():
            continue
        dest = RESULTS_DIR / ('%s__%s__%s' % (task_id, worker_key, p.name))
        try:
            shutil.copy2(p, dest)
            delivered.append(str(dest))
        except OSError as exc:
            logger.warning('HTML 산출물 복사 실패 %s: %s', p, exc)
    return delivered


def write_result(worker_key, brief, brief_file, outcome, started_at):
    task_id = brief.get('task_id') or brief_file.stem
    base = '%s__%s' % (task_id, worker_key)
    md_path = RESULTS_DIR / (base + '.md')
    json_path = RESULTS_DIR / (base + '.json')

    report_text = outcome.get('report') or ('(no output)\n\nerror: %s' % outcome.get('error'))
    md_path.write_text(report_text, encoding='utf-8')

    spec = WORKER_SPECS.get(worker_key, {})
    finished_at = now_iso()
    envelope = {
        'task_id': task_id,
        'worker': spec.get('name', worker_key),
        'worker_name': spec.get('name', worker_key),
        'worker_key': worker_key.lower(),
        'status': 'completed' if outcome['ok'] else 'failed',
        'started_at': started_at,
        'finished_at': finished_at,
        'completed_at': finished_at,
        'summary': ' '.join(report_text.split())[:200],
        'artifacts': outcome.get('artifacts') or [],
        'model': agent_model(spec.get('agent')),
        'exit_code': outcome.get('exit_code'),
        'error': outcome.get('error'),
        'brief_file': brief_file.name,
        'report_file': md_path.name,
        'usage': (outcome.get('raw') or {}).get('usage') if outcome.get('raw') else None,
        'source': 'hermes-local-runner',
    }
    envelope.update(emit_artifact_manifest(md_path, f'{task_id}:{worker_key}:primary'))
    json_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding='utf-8')
    return envelope


def process_brief(worker_key, brief_file):
    try:
        brief = json.loads(brief_file.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error('brief 파싱 실패 %s: %s', brief_file.name, exc)
        return None

    task_id = brief.get('task_id') or brief_file.stem
    result_json = RESULTS_DIR / ('%s__%s.json' % (task_id, worker_key))
    if result_json.exists():
        logger.info('이미 처리됨, 건너뜀: %s (%s)', task_id, worker_key)
        return 'already'

    logger.info('처리 시작: %s (%s)', task_id, worker_key)
    started_at = now_iso()

    spec = WORKER_SPECS[worker_key]
    task_workspace = WORKSPACE_DIR / ('%s__%s' % (task_id, worker_key))
    task_workspace.mkdir(parents=True, exist_ok=True)
    outcome = run_claude(brief, task_workspace, spec['agent'])
    outcome['artifacts'] = sorted(
        str(p) for p in task_workspace.rglob('*')
        if p.is_file() and p.name != 'prompt.md')
    if outcome.get('transient'):
        logger.warning('일시적 오류, 다음 주기에 재시도: %s (%s) — %s',
                       task_id, worker_key, outcome.get('error'))
        return 'retry'
    delivered = deliver_html_artifacts(task_id, worker_key, outcome['artifacts'])
    if delivered:
        outcome['artifacts'] = sorted(set(outcome['artifacts']) | set(delivered))
    envelope = write_result(worker_key, brief, brief_file, outcome, started_at)

    logger.info('처리 완료: %s (%s) → %s', task_id, worker_key, envelope['status'])
    return envelope['status']


def archive_brief(worker_key, brief_file):
    processed_dir = LOCAL_INBOX_DIR / worker_key / 'processed'
    processed_dir.mkdir(parents=True, exist_ok=True)
    brief_file.rename(processed_dir / brief_file.name)


def main():
    setup_logging()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    lock_handle = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.info('다른 러너 인스턴스 실행 중 — 종료')
        return 0

    handled = 0
    for worker_key in WORKER_SPECS:
        worker_inbox = LOCAL_INBOX_DIR / worker_key
        if not worker_inbox.is_dir():
            continue
        for brief_file in sorted(worker_inbox.glob('*.json')):
            status = process_brief(worker_key, brief_file)
            if status is not None and status != 'retry':
                archive_brief(worker_key, brief_file)
                handled += 1

    logger.info('이번 실행에서 처리한 brief: %d건', handled)
    return 0


if __name__ == '__main__':
    sys.exit(main())
