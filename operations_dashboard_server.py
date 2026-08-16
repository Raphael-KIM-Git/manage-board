#!/usr/bin/env python3
from __future__ import annotations

import json
import ipaddress
import os
import re
import shlex
import shutil
import subprocess
import time
from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote as url_quote, unquote, urlparse

from operations_dashboard_projection import build_dashboard_summary, project_operations_evidence, project_task
from operations_dashboard_console import project_console_snapshot
from dashboard_instructions import InstructionError, capabilities as instruction_capabilities, list_instructions, submit_instruction
from operations_followup_requests import (
    FollowUpError,
    capabilities as followup_capabilities,
    list_requests as list_followup_requests,
    submit_request as submit_followup_request,
)

BASE_DIR = Path(__file__).resolve().parent
OPERATIONS_DIR = BASE_DIR / 'operations'
BRIEFS_DIR = OPERATIONS_DIR / 'briefs'
RESULTS_DIR = OPERATIONS_DIR / 'results'
VERIFICATIONS_DIR = OPERATIONS_DIR / 'verifications'
DIGESTS_DIR = OPERATIONS_DIR / 'digests'
DISPATCHES_DIR = OPERATIONS_DIR / 'dispatches'
INPUTS_DIR = OPERATIONS_DIR / 'inputs'
INTERVIEWS_DIR = OPERATIONS_DIR / 'interviews'
SEEDS_DIR = OPERATIONS_DIR / 'seeds'
FOLLOWUP_REQUESTS_DIR = OPERATIONS_DIR / 'follow-up-requests'
INSTRUCTIONS_DIR = OPERATIONS_DIR / 'instructions'
CONFIG_DIR = OPERATIONS_DIR / 'config'
WORKERS_CONFIG_PATH = CONFIG_DIR / 'workers.json'
UI_DIR = BASE_DIR / 'operations_dashboard'
PROFILES_DIR = Path('/home/raphael/.hermes/profiles')
HOST = os.environ.get('OPS_DASHBOARD_HOST', '127.0.0.1')
PORT = int(os.environ.get('OPS_DASHBOARD_PORT', '8765'))

for d in [BRIEFS_DIR, RESULTS_DIR, VERIFICATIONS_DIR, DIGESTS_DIR, DISPATCHES_DIR, INPUTS_DIR, INTERVIEWS_DIR, SEEDS_DIR, FOLLOWUP_REQUESTS_DIR, INSTRUCTIONS_DIR, CONFIG_DIR, UI_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_WORKERS = {
    'Claude Code Worker': {
        'enabled': True,
        'mode': 'ssh',
        'host': '',
        'user': '',
        'port': 22,
        'remote_inbox_dir': '~/agent-hub/inbox/claude-code',
        'dispatch_command_template': '',
        'notes': 'Configure MacBook SSH host/user to enable real dispatch.',
    },
    'OpenClaw Worker': {
        'enabled': True,
        'mode': 'ssh',
        'host': '',
        'user': '',
        'port': 22,
        'remote_inbox_dir': '~/agent-hub/inbox/openclaw',
        'dispatch_command_template': '',
        'notes': 'Configure MacBook SSH host/user to enable real dispatch.',
    },
    'HermesVerifier': {
        'enabled': True,
        'mode': 'local',
        'notes': 'Local hub profile; not a remote dispatch target.',
    },
}

if not WORKERS_CONFIG_PATH.exists():
    WORKERS_CONFIG_PATH.write_text(json.dumps(DEFAULT_WORKERS, ensure_ascii=False, indent=2), encoding='utf-8')


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def write_all(stream, body: bytes) -> None:
    """Write a complete HTTP body even when the socket accepts a partial write."""
    remaining = memoryview(body)
    while remaining:
        written = stream.write(remaining)
        if not written:
            raise ConnectionError('HTTP response stream stopped accepting data')
        remaining = remaining[written:]


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r'[^a-z0-9가-힣]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'task'


def next_task_id() -> str:
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'T-{today}-'
    existing = []
    for path in BRIEFS_DIR.glob(f'{prefix}*.md'):
        m = re.match(rf'T-{today}-(\d{{3}})-', path.name)
        if m:
            existing.append(int(m.group(1)))
    n = max(existing, default=0) + 1
    return f'T-{today}-{n:03d}'


def read_preview(path: Path, limit: int = 700) -> str:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return f'[read error] {e}'
    return text[:limit]


def file_item(path: Path) -> dict:
    stat = path.stat()
    return {
        'name': path.name,
        'path': str(path),
        'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
        'size': stat.st_size,
        'preview': read_preview(path),
    }


def list_items(folder: Path) -> list[dict]:
    raw_items = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.')]
    grouped: dict[str, Path] = {}
    for path in raw_items:
        key = path.stem
        chosen = grouped.get(key)
        if chosen is None:
            grouped[key] = path
            continue
        if chosen.suffix != '.md' and path.suffix == '.md':
            grouped[key] = path
            continue
        if path.stat().st_mtime > chosen.stat().st_mtime:
            grouped[key] = path
    items = sorted(grouped.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    return [file_item(p) for p in items]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def read_json_file(path: Path, default: dict) -> dict:
    try:
        value = load_json(path)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, dict) else default


def read_observational_json_file(path: Path) -> dict:
    """Keep malformed sync/watchdog snapshots visible to the read-only projection."""
    try:
        value = load_json(path)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {'_malformed_snapshot': True}
    return value if isinstance(value, dict) else {'_malformed_snapshot': True}


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_workers() -> dict:
    try:
        return load_json(WORKERS_CONFIG_PATH)
    except Exception:
        return DEFAULT_WORKERS


def parse_worker_names(text: str) -> list[str]:
    known = set(load_workers().keys()) | set(profile_agent_map().keys())
    found = []
    for name in sorted(known, key=len, reverse=True):
        if name and name in text:
            found.append(name)
    seen = set()
    out = []
    for name in found:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def extract_field(message: str, labels: list[str]) -> str:
    for label in labels:
        m = re.search(rf'(?:^|\n)\s*{re.escape(label)}\s*[:：]\s*(.+)', message, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ''


def pm_brief_assist_heuristic(payload: dict) -> dict:
    message = (payload.get('message') or '').strip()
    draft = dict(payload.get('draft') or {})

    title = (draft.get('title') or '').strip()
    objective = (draft.get('objective') or '').strip()
    context = (draft.get('context') or '').strip()
    constraints = (draft.get('constraints') or '').strip()
    deliverable = (draft.get('deliverable') or '').strip()
    reviewer = (draft.get('reviewer') or 'HermesVerifier').strip() or 'HermesVerifier'
    execution_mode = (draft.get('execution_mode') or 'research-pipeline').strip() or 'research-pipeline'
    assigned_workers = draft.get('assigned_workers') or []
    if isinstance(assigned_workers, str):
        assigned_workers = [w.strip() for w in assigned_workers.split(',') if w.strip()]

    explicit_title = extract_field(message, ['제목', '작업 제목', 'title'])
    explicit_objective = extract_field(message, ['목표', '결과', '산출물', 'objective'])
    explicit_context = extract_field(message, ['맥락', '배경', 'context'])
    explicit_constraints = extract_field(message, ['제약', '제약사항', 'constraints'])
    explicit_deliverable = extract_field(message, ['산출물 형태', '원하는 산출물', 'deliverable'])

    if explicit_title:
        title = explicit_title
    elif not title and message:
        title = re.split(r'[\n.!?]+', message, maxsplit=1)[0].strip()[:90]

    if explicit_objective:
        objective = explicit_objective
    elif not objective and message:
        lowered = message.lower()
        if any(token in lowered for token in ['정리', '비교', '검증', '작성', '조사', '분석', '요약', '문서']):
            objective = message.strip()

    if explicit_context:
        context = f'{context}\n{explicit_context}'.strip() if context else explicit_context
    elif message and any(token in message for token in ['참고', '기존', '이전', '배경', '맥락', '파일', '결과물']):
        context = f'{context}\n{message}'.strip() if context else message

    if explicit_constraints:
        constraints = f'{constraints}\n{explicit_constraints}'.strip() if constraints else explicit_constraints
    if explicit_deliverable:
        deliverable = explicit_deliverable

    parsed_workers = parse_worker_names(message)
    if parsed_workers:
        research_first = [w for w in parsed_workers if w in {'HermesResearcher', 'researcher-co', 'researcher_agent'}]
        non_local = [
            w for w in (research_first or parsed_workers)
            if w != reviewer and load_workers().get(w, {}).get('mode') != 'local'
        ]
        assigned_workers = non_local or assigned_workers
    if not assigned_workers:
        assigned_workers = ['HermesResearcher', 'researcher-co', 'researcher_agent']

    draft.update({
        'title': title,
        'objective': objective,
        'context': context,
        'constraints': constraints,
        'deliverable': deliverable,
        'reviewer': reviewer,
        'execution_mode': execution_mode,
        'assigned_workers': assigned_workers,
    })

    questions = []
    if not title:
        questions.append('이번 업무의 제목을 한 줄로 어떻게 두면 좋을까요?')
    if not objective:
        questions.append('이번 작업이 끝났을 때 반드시 남아 있어야 할 결과를 한두 문장으로 알려주세요.')
    if title and objective and not deliverable:
        questions.append('원하는 산출물 형태가 있나요? 예: 비교표, 최종 보고서, 검토 메모, 실행 체크리스트')

    ready = bool(title and objective and not questions)
    if ready:
        reply = f'좋아요. 지금 초안이면 바로 진행 가능합니다. 제목은 "{title}"이고, 기본 실행 에이전트는 {", ".join(assigned_workers)} 로 잡겠습니다.'
    elif questions:
        reply = '좋아요. 진행 전에 아래만 더 확인하면 바로 브리프로 넘길 수 있어요.\n- ' + '\n- '.join(questions)
    else:
        reply = '좋아요. 초안은 잡혔고, 필요하면 세부 옵션만 조금 더 보완하면 됩니다.'

    checklist = {
        'title': bool(title),
        'objective': bool(objective),
        'context': bool(context),
        'deliverable': bool(deliverable),
        'assigned_workers': bool(assigned_workers),
    }
    return {
        'draft': draft,
        'ready': ready,
        'questions': questions,
        'reply': reply,
        'checklist': checklist,
    }


PM_AGENT_NAME = 'HermesPM'
PM_HERMES_PYTHON = os.environ.get(
    'OPS_PM_HERMES_PYTHON', '/home/raphael/.hermes/hermes-agent/venv/bin/python3'
)
PM_HERMES_HELPER = Path(__file__).with_name('operations_dashboard_pm_assist.py')
PM_HERMES_MODEL = 'gpt-5.6-terra'
PM_HERMES_PROVIDER = 'openai-codex'
PM_LLM_TIMEOUT = min(int(os.environ.get('OPS_PM_TIMEOUT', '45')), 60)
PM_CIRCUIT_FAILURE_LIMIT = 3
_pm_circuit_failures = 0
_pm_circuit_opened_at = 0.0


def pm_llm_extract_json(text: str) -> dict:
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end <= start:
        raise ValueError('LLM 응답에서 JSON 객체를 찾지 못함')
    return json.loads(text[start:end + 1])


def pm_llm_build_prompt(turns: list[str], draft: dict, remote_workers: list[str], reviewer: str) -> str:
    draft_json = json.dumps(draft, ensure_ascii=False, indent=2)
    conversation = '\n'.join(turns) if turns else '(첫 대화)'
    return f'''지금까지의 브리프 작성 대화를 보고 업무 지시서(브리프) 초안을 갱신하라.

[현재 초안]
{draft_json}

[선택 가능한 원격 실행 에이전트]
{', '.join(remote_workers)}
- reviewer({reviewer})는 assigned_workers에 넣지 않는다.
- pipeline은 고정하지 않는다. 목표·산출물·리스크·데이터 의존성에 따라 PM이 단계와 순서를 선정한다.
- 외부 데이터, 내부 데이터, 저장소/파일, 현재 환경 정보가 필요하면 research agent를 첫 단계로 선택하고, 결과 수집·검증 후에 writing/developer/QA 단계로 진행한다.
- research가 필요하면 기본적으로 HermesResearcher, researcher-co, researcher_agent를 모두 고려하고, 필요성 판단에 따라 1~2개로 줄일 수 있다. 우선순위는 HermesResearcher > researcher-co > researcher_agent다.
- verification은 가능한 경우 verify-co와 HermesVerifier를 모두 고려하되, 필요 없으면 1개 또는 생략할 수 있다. 우선순위는 verify-co > HermesVerifier다.
- 자료가 충분한 순수 작성/변환 업무는 research를 생략할 수 있으며, 그 판단 이유를 context 또는 constraints에 남긴다.
- PM은 실제 조사·작성·개발·QA를 직접 수행하지 않고, agent를 배정하고 단계 전환과 결과물을 검증한다.

[대화]
{conversation}

[출력 규칙]
아래 스키마의 JSON 객체 하나만 출력한다. 코드펜스·설명·인사말 금지.
{{
  "reply": "Raphael에게 보낼 한국어 답변. 부족한 정보가 있으면 여기서 자연스럽게 질문한다 (질문은 최대 2개)",
  "title": "작업 제목 한 줄, 90자 이내 (아직 모르면 빈 문자열)",
  "objective": "작업이 끝났을 때 반드시 남아야 할 결과 1~2문장 (아직 모르면 빈 문자열)",
  "context": "배경/맥락 (없으면 빈 문자열)",
  "constraints": "제약사항 (없으면 빈 문자열)",
  "deliverable": "원하는 산출물 형태 (없으면 빈 문자열)",
  "assigned_workers": ["research 단계 실행 에이전트 이름"],
  "ready": false,
  "questions": ["추가 확인이 필요한 질문 (없으면 빈 배열)"],
  "interpretation": "사용자 발화를 어떻게 이해했는지 1~3문장. 특히 사용자가 직접 말하지 않은 용어 정의·범위 판단·가정을 했다면 반드시 명시 (없으면 빈 문자열)"
}}
- 대화에서 확인된 내용만 채운다. 지어내지 않는다. 기존 초안 값은 사용자가 바꾸라고 하지 않는 한 유지한다.
- ready는 title과 objective가 확정됐을 때만 true.
- interpretation은 매 턴 갱신한다. 모호한 용어를 임의로 해석했다면 reply에서도 사용자에게 그 해석이 맞는지 확인한다.'''


def _pm_safe_environment() -> dict[str, str]:
    allowed = {'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'HERMES_HOME'}
    return {key: value for key, value in os.environ.items() if key in allowed}


def pm_brief_assist_hermes(payload: dict, *, prompt: str) -> dict:
    """Run one isolated Hermes turn in Hermes' own Python runtime."""
    envelope = json.dumps({'prompt': prompt[:24000], 'source': 'dashboard-pm-assist'}, ensure_ascii=False)
    code, output, _ = run_command(
        [PM_HERMES_PYTHON, str(PM_HERMES_HELPER)],
        timeout=PM_LLM_TIMEOUT,
        cwd=str(PM_HERMES_HELPER.parent),
        input_text=envelope,
        env=_pm_safe_environment(),
    )
    if code != 0:
        raise RuntimeError('Hermes helper failed')
    output = output.strip()
    if len(output) > 50000:
        raise RuntimeError('Hermes helper response exceeded limit')
    parsed = pm_llm_extract_json(output)
    return parsed if isinstance(parsed, dict) else {}


def pm_brief_assist_llm(payload: dict) -> dict:
    message = (payload.get('message') or '').strip()
    conversation = payload.get('conversation') or []
    draft = dict(payload.get('draft') or {})
    reviewer = (draft.get('reviewer') or 'HermesVerifier').strip() or 'HermesVerifier'
    workers = load_workers()
    remote_workers = sorted(n for n, cfg in workers.items() if cfg.get('mode') != 'local')

    turns = []
    for turn in conversation[-24:]:
        text = str(turn.get('text') or '').strip()
        if text:
            speaker = 'Raphael' if turn.get('role') == 'user' else 'HermesPM'
            turns.append(f'{speaker}: {text}')
    if not turns and message:
        turns.append(f'Raphael: {message}')

    prompt = pm_llm_build_prompt(turns, draft, remote_workers, reviewer)
    parsed = pm_brief_assist_hermes(payload, prompt=prompt)

    title = str(parsed.get('title') or '').strip() or (draft.get('title') or '').strip()
    objective = str(parsed.get('objective') or '').strip() or (draft.get('objective') or '').strip()

    assigned = parsed.get('assigned_workers') or []
    if isinstance(assigned, str):
        assigned = [w.strip() for w in assigned.split(',') if w.strip()]
    assigned = [w for w in assigned if w in workers and workers[w].get('mode') != 'local' and w != reviewer]
    if not assigned:
        assigned = ['HermesResearcher', 'researcher-co', 'researcher_agent']

    questions = [str(q).strip() for q in (parsed.get('questions') or []) if str(q).strip()]
    ready = bool(parsed.get('ready')) and bool(title and objective)

    draft.update({
        'title': title,
        'objective': objective,
        'context': str(parsed.get('context') or draft.get('context') or '').strip(),
        'constraints': str(parsed.get('constraints') or draft.get('constraints') or '').strip(),
        'deliverable': str(parsed.get('deliverable') or draft.get('deliverable') or '').strip(),
        'reviewer': reviewer,
        'execution_mode': (draft.get('execution_mode') or 'research-pipeline').strip() or 'research-pipeline',
        'assigned_workers': assigned,
    })

    checklist = {
        'title': bool(title),
        'objective': bool(objective),
        'context': bool(draft['context']),
        'deliverable': bool(draft['deliverable']),
        'assigned_workers': bool(assigned),
    }
    return {
        'draft': draft,
        'ready': ready,
        'questions': questions,
        'reply': str(parsed.get('reply') or '초안을 반영했습니다.').strip(),
        'checklist': checklist,
        'interpretation': str(parsed.get('interpretation') or '').strip(),
        'engine': 'hermespm-llm',
    }


def pm_brief_assist(payload: dict) -> dict:
    global _pm_circuit_failures, _pm_circuit_opened_at
    if _pm_circuit_failures >= PM_CIRCUIT_FAILURE_LIMIT and time.monotonic() - _pm_circuit_opened_at < 60:
        result = pm_brief_assist_heuristic(payload)
        result['engine'] = 'heuristic-fallback'
        result['reply'] = '(HermesPM 보조 경로가 잠시 열리지 않아 규칙 기반으로 처리했습니다.)\n' + result['reply']
        return result
    try:
        result = pm_brief_assist_llm(payload)
        _pm_circuit_failures = 0
        return result
    except Exception:
        _pm_circuit_failures += 1
        _pm_circuit_opened_at = time.monotonic()
        result = pm_brief_assist_heuristic(payload)
        result['engine'] = 'heuristic-fallback'
        result['reply'] = '(HermesPM 보조 경로 실패로 규칙 기반 임시 처리)\n' + result['reply']
        return result


def worker_status_map() -> dict:
    workers = load_workers()
    out = {'Hermes Hub': 'configured'}
    for name, cfg in workers.items():
        if cfg.get('mode') == 'local':
            out[name] = 'configured'
            continue
        if cfg.get('mode') == 'local-inbox':
            out[name] = 'configured' if cfg.get('local_inbox_dir') else 'needs_config'
            continue
        if cfg.get('enabled', True) and cfg.get('host') and cfg.get('user') and cfg.get('remote_inbox_dir'):
            out[name] = 'configured'
        else:
            out[name] = 'needs_config'
    runtime_status_path = OPERATIONS_DIR / 'worker-status.json'
    if runtime_status_path.exists():
        try:
            runtime = load_json(runtime_status_path)
            for name, info in (runtime.get('workers') or {}).items():
                if info.get('status'):
                    out[name] = info['status']
        except Exception:
            pass
    return out


def profile_agent_map() -> dict[str, dict]:
    profile_name_map = {
        'pm': 'HermesPM',
        'planner': 'HermesPlanner',
        'researcher': 'HermesResearcher',
        'designer': 'HermesDesigner',
        'verifier': 'HermesVerifier',
        'developer': 'HermesDeveloper',
        'qa': 'HermesQA',
        'default': 'Hermes',
    }
    out: dict[str, dict] = {}
    if not PROFILES_DIR.exists():
        return out
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        if not profile_dir.is_dir():
            continue
        profile_slug = profile_dir.name
        profile_yaml = profile_dir / 'profile.yaml'
        if not profile_yaml.exists():
            continue
        description = ''
        for line in profile_yaml.read_text(encoding='utf-8').splitlines():
            if line.startswith('description:'):
                description = line.split(':', 1)[1].strip()
                break
        display_name = profile_name_map.get(profile_slug, f'Hermes {profile_slug}')
        out[display_name] = {
            'profile_slug': profile_slug,
            'description': description or 'Hermes profile agent',
            **safe_profile_metadata(profile_dir),
        }
    return out


def safe_profile_metadata(profile_dir: Path) -> dict[str, str]:
    """Read only scalar model/provider labels; never expose raw config."""
    path = profile_dir / 'config.yaml'
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*(model|provider)\s*:\s*([^#]+?)\s*$', line)
            if not match:
                continue
            value = match.group(2).strip().strip('"\'')
            if value and re.fullmatch(r'[A-Za-z0-9._/-]{1,80}', value):
                values[match.group(1)] = value
    except (OSError, UnicodeError):
        return {}
    return values


def task_json_paths() -> list[Path]:
    paths = sorted(BRIEFS_DIR.glob('T-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p for p in paths if p.name != 'workers.json']


def load_tasks() -> list[dict]:
    tasks = []
    for path in task_json_paths():
        try:
            data = load_json(path)
        except Exception:
            continue
        data['_json_path'] = str(path)
        tasks.append(data)
    tasks.sort(key=lambda t: t.get('created_at', ''), reverse=True)
    return tasks


def find_task(task_id: str) -> tuple[dict, Path]:
    for path in task_json_paths():
        data = load_json(path)
        if data.get('task_id') == task_id:
            return data, path
    raise FileNotFoundError(task_id)


def normalize_string_list(values: object, limit: int = 20) -> list[str]:
    if isinstance(values, str):
        values = values.splitlines()
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text[:1000])
    return out[:limit]


def simple_yaml(data: dict) -> str:
    """Small dependency-free YAML writer for human-readable Seed artifacts."""
    def quote(value: object) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f'{key}:')
            if value:
                lines.extend(f'  - {quote(item)}' for item in value)
            else:
                lines.append('  []')
        else:
            lines.append(f'{key}: {quote(value)}')
    return '\n'.join(lines) + '\n'


def create_interview_artifact(task: dict, questions: object, answers: object) -> dict:
    task_id = str(task['task_id'])
    questions = normalize_string_list(questions, limit=12)
    answers = normalize_string_list(answers, limit=12)
    status = 'completed' if questions and len(answers) >= len(questions) else 'in_progress'
    created_at = now_iso()
    stem = f'{task_id}-interview-v1'
    json_path = INTERVIEWS_DIR / f'{stem}.json'
    md_path = INTERVIEWS_DIR / f'{stem}.md'
    pairs = [
        {'question': question, 'answer': answers[index] if index < len(answers) else ''}
        for index, question in enumerate(questions)
    ]
    data = {
        'artifact_type': 'ouroboros-interview',
        'task_id': task_id,
        'version': 1,
        'status': status,
        'created_at': created_at,
        'title': task.get('title', ''),
        'pairs': pairs,
        'open_questions': [pair['question'] for pair in pairs if not pair['answer']],
    }
    md_lines = [f'# Interview · {task_id}', '', f'- Status: {status}', f'- Created At: {created_at}', '', '## Questions and Answers']
    for pair in pairs:
        md_lines.extend([f'### Q. {pair["question"]}', pair['answer'] or '(answer pending)', ''])
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text('\n'.join(md_lines).rstrip() + '\n', encoding='utf-8')
    return {'id': stem, 'version': 1, 'status': status, 'json_path': str(json_path), 'markdown_path': str(md_path)}


def create_seed_artifact(task: dict, acceptance_criteria: object, included_scope: object, excluded_scope: object, assumptions: object) -> dict:
    task_id = str(task['task_id'])
    existing = list(SEEDS_DIR.glob(f'{task_id}-seed-v*.json'))
    version = len(existing) + 1
    created_at = now_iso()
    criteria = normalize_string_list(acceptance_criteria, limit=20)
    if not criteria:
        criteria = [task.get('deliverable') or '검증 가능한 산출물과 결과 증적을 남긴다.']
    data = {
        'artifact_type': 'ouroboros-seed',
        'seed_id': f'SEED-{task_id}-v{version}',
        'task_id': task_id,
        'version': version,
        'status': 'awaiting_approval',
        'created_at': created_at,
        'approved_at': '',
        'approved_by': '',
        'title': task.get('title', ''),
        'objective': task.get('objective', ''),
        'context': task.get('context', ''),
        'constraints': task.get('constraints', ''),
        'included_scope': normalize_string_list(included_scope),
        'excluded_scope': normalize_string_list(excluded_scope),
        'acceptance_criteria': criteria,
        'assumptions': normalize_string_list(assumptions),
    }
    stem = f'{task_id}-seed-v{version}'
    json_path = SEEDS_DIR / f'{stem}.json'
    yaml_path = SEEDS_DIR / f'{stem}.yaml'
    md_path = SEEDS_DIR / f'{stem}.md'
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    yaml_path.write_text(simple_yaml(data), encoding='utf-8')
    md = f'''# Seed · {data['seed_id']}

- Status: {data['status']}
- Task: {task_id}
- Created At: {created_at}

## Objective
{data['objective']}

## Included Scope
{chr(10).join(f'- {item}' for item in data['included_scope']) or '- (not specified)'}

## Excluded Scope
{chr(10).join(f'- {item}' for item in data['excluded_scope']) or '- (not specified)'}

## Acceptance Criteria
{chr(10).join(f'- {item}' for item in criteria)}

## Constraints
{data['constraints'] or '(not specified)'}

## Assumptions
{chr(10).join(f'- {item}' for item in data['assumptions']) or '- (not specified)'}
'''
    md_path.write_text(md, encoding='utf-8')
    return {'id': data['seed_id'], 'version': version, 'status': data['status'], 'json_path': str(json_path), 'yaml_path': str(yaml_path), 'markdown_path': str(md_path)}


def approve_seed_artifact(seed_json_path: str, approver: str = 'Raphael') -> dict:
    path = Path(seed_json_path)
    data = load_json(path)
    if data.get('artifact_type') != 'ouroboros-seed':
        raise ValueError('not an ouroboros seed artifact')
    data['status'] = 'approved'
    data['approved_by'] = approver.strip() or 'Raphael'
    data['approved_at'] = now_iso()
    save_json(path, data)
    path.with_suffix('.yaml').write_text(simple_yaml(data), encoding='utf-8')
    return data


def dispatch_record_path(task_id: str, worker_name: str) -> Path:
    worker_slug = slugify(worker_name)
    ts = datetime.now().strftime('%Y%m%dT%H%M%S')
    return DISPATCHES_DIR / f'{task_id}-{worker_slug}-{ts}.json'


def latest_dispatch_status(task_id: str) -> dict[str, str]:
    statuses = {}
    for path in sorted(DISPATCHES_DIR.glob(f'{task_id}-*.json')):
        try:
            data = load_json(path)
            statuses[data.get('worker_name', path.stem)] = data.get('status', 'unknown')
        except Exception:
            continue
    return statuses


def task_related_files(task_id: str, directory: Path) -> list[dict]:
    items = []
    for path in sorted(directory.glob(f'{task_id}*'), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        items.append({
            'name': path.name,
            'path': str(path),
            'modified_at': datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
            'size': path.stat().st_size,
        })
    return items


def result_metadata(task_id: str, files: list[dict]) -> list[dict]:
    """Expose only safe correlation fields from result JSON sidecars."""
    safe = {'task_id', 'worker', 'worker_name', 'worker_key', 'status', 'verdict', 'report_file', 'stage', 'stage_id',
            'artifact_id', 'artifact_version', 'attempt_id', 'result_artifact_id', 'result_version',
            'artifact_schema_version', 'artifact_manifest', 'target_artifact'}
    output = []
    for item in files:
        if not item.get('name', '').lower().endswith('.json'):
            continue
        try:
            data = load_json(Path(item['path']))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        metadata = {key: data[key] for key in safe if key in data}
        if metadata:
            output.append({'name': item['name'], 'metadata': metadata})
    return output


def default_pipeline_stages(task_id: str, deliverable: str, reviewer: str) -> list[dict]:
    return [
        {
            'id': 'research',
            'label': 'Research',
            'status': 'queued',
            'agents': ['HermesResearcher', 'researcher-co', 'researcher_agent'],
            'deliverable': 'source notes, citations, structured findings',
            'artifacts_dir': str(OPERATIONS_DIR / 'research' / task_id),
            'depends_on': [],
        },
        {
            'id': 'writing',
            'label': 'Draft Writing',
            'status': 'planned',
            'agents': ['writer-co'],
            'deliverable': 'first draft synthesized from research artifacts',
            'artifacts_dir': str(OPERATIONS_DIR / 'drafts' / task_id),
            'depends_on': ['research'],
        },
        {
            'id': 'verification',
            'label': 'Verification',
            'status': 'planned',
            'agents': [reviewer, 'verify-co'],
            'deliverable': 'verification report with factual/risk/completeness checks',
            'completion_policy': 'any',
            'artifacts_dir': str(OPERATIONS_DIR / 'verifications' / task_id),
            'depends_on': ['writing'],
        },
        {
            'id': 'final_write',
            'label': 'Final Write',
            'status': 'planned',
            'agents': ['writer-co'],
            'deliverable': deliverable or 'final polished deliverable that incorporates verification feedback',
            'artifacts_dir': str(OPERATIONS_DIR / 'finals' / task_id),
            'depends_on': ['verification'],
        },
    ]


def pipeline_summary(stages: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    current = None
    for stage in stages:
        status = stage.get('status', 'planned')
        status_counts[status] = status_counts.get(status, 0) + 1
        if current is None and status not in {'completed', 'cancelled'}:
            current = stage.get('id')
    return {
        'current_stage': current or (stages[-1].get('id') if stages else None),
        'completed_stages': status_counts.get('completed', 0),
        'stage_count': len(stages),
        'status_counts': status_counts,
    }


def build_task_view(task: dict) -> dict:
    task_id = task['task_id']
    dispatches = latest_dispatch_status(task_id)
    result_files = task_related_files(task_id, RESULTS_DIR)
    verification_files = task_related_files(task_id, VERIFICATIONS_DIR)
    digest_files = task_related_files(task_id, DIGESTS_DIR)
    interview_files = task_related_files(task_id, INTERVIEWS_DIR)
    seed_files = task_related_files(task_id, SEEDS_DIR)
    sync_evidence = read_observational_json_file(OPERATIONS_DIR / 'sync' / 'latest.json')
    watchdog_evidence = read_observational_json_file(OPERATIONS_DIR / 'watchdog' / 'latest.json')
    stages = task.get('stages') or ([] if task.get('pipeline_name') != 'research-write-verify-finalize' else default_pipeline_stages(task_id, task.get('deliverable', ''), task.get('reviewer', 'HermesVerifier')))
    pipeline = pipeline_summary(stages)
    view = {
        'task_id': task_id,
        'title': task.get('title', ''),
        'objective': task.get('objective', ''),
        'priority': task.get('priority', 'medium'),
        'execution_mode': task.get('execution_mode', 'primary+review'),
        'assigned_workers': task.get('assigned_workers', []),
        'reviewer': task.get('reviewer', 'HermesVerifier'),
        'project_ref': deepcopy(task.get('project_ref')) if isinstance(task.get('project_ref'), dict) else None,
        'status': task.get('status', 'queued'),
        'created_at': task.get('created_at'),
        'updated_at': task.get('updated_at', task.get('created_at')),
        'dispatches': dispatches,
        'artifacts': task.get('artifacts', {}),
        'pipeline_name': task.get('pipeline_name', 'research-write-verify-finalize'),
        'pipeline_shape': task.get('pipeline_shape', 'full'),
        'input_files': [Path(p).name for p in (task.get('input_files') or [])],
        'pm_live_notes': (task.get('pm_live_notes') or [])[-5:],
        'pm_final_review': task.get('pm_final_review'),
        'stages': stages,
        'pipeline': pipeline,
        'last_error': task.get('last_error'),
        'result_files': result_files,
        'result_metadata': result_metadata(task_id, result_files),
        'verification_files': verification_files,
        'verification_metadata': result_metadata(task_id, verification_files),
        'digest_files': digest_files,
        'interview': task.get('interview'),
        'seed': task.get('seed'),
        'interview_files': interview_files,
        'seed_files': seed_files,
        'operations_evidence': project_operations_evidence(task, sync_evidence, watchdog_evidence),
        'latest_result': result_files[0]['name'] if result_files else None,
        'latest_verification': verification_files[0]['name'] if verification_files else None,
        'latest_digest': digest_files[0]['name'] if digest_files else None,
    }
    # The legacy field defaults missing pipeline_shape to ``full``.  Feed the
    # projection a raw-presence-preserving copy so data quality is not lost.
    projection_input = dict(view)
    if 'pipeline_shape' not in task:
        projection_input.pop('pipeline_shape', None)
    if 'status' not in task:
        projection_input.pop('status', None)
    view['dashboard_projection'] = project_task(projection_input)
    return view


def build_dashboard_console() -> dict:
    """Build all v2 panes from one task load; pane failures stay isolated."""
    tasks = [build_task_view(t) for t in load_tasks()]
    availability = worker_status_map()
    profile_agents = profile_agent_map()
    registry = {name: 'configured' for name in profile_agents}
    registry.update(availability)
    return project_console_snapshot(tasks, instruction_records=list_instructions(INSTRUCTIONS_DIR),
                                    availability=availability, agent_registry=registry,
                                    agent_metadata={name: {key: value for key, value in data.items() if key in {'model', 'provider'}}
                                                   for name, data in profile_agents.items()})


def build_agent_summary(tasks: list[dict]) -> list[dict]:
    worker_statuses = worker_status_map()
    profile_agents = profile_agent_map()
    always_visible = {'Hermes Hub', *profile_agents.keys(), *worker_statuses.keys()}
    task_visible_agents: set[str] = set()
    base_agents: dict[str, dict] = {
        'Hermes Hub': {
            'name': 'Hermes Hub',
            'kind': 'hub',
            'availability': worker_statuses.get('Hermes Hub', 'configured'),
            'role_label': '브리프 저장과 전송 흐름을 묶는 허브',
            'active_count': 0,
            'review_count': 0,
            'blocked_count': 0,
            'completed_count': 0,
            'latest_task_title': None,
            'latest_status': None,
        },
        'HermesVerifier': {
            'name': 'HermesVerifier',
            'kind': 'reviewer',
            'availability': worker_statuses.get('HermesVerifier', 'configured'),
            'role_label': profile_agents.get('HermesVerifier', {}).get('description') or '결과를 검토하고 판정하는 검증 에이전트',
            'active_count': 0,
            'review_count': 0,
            'blocked_count': 0,
            'completed_count': 0,
            'latest_task_title': None,
            'latest_status': None,
        },
    }

    for profile_name, profile_info in profile_agents.items():
        if profile_name in base_agents:
            continue
        kind = 'profile'
        if profile_name == 'HermesPM':
            kind = 'orchestrator'
        elif profile_name == 'HermesPlanner':
            kind = 'planner'
        elif profile_name == 'HermesResearcher':
            kind = 'researcher'
        elif profile_name == 'HermesDesigner':
            kind = 'designer'
        elif profile_name == 'HermesDeveloper':
            kind = 'developer'
        elif profile_name == 'HermesQA':
            kind = 'reviewer'
        base_agents[profile_name] = {
            'name': profile_name,
            'kind': kind,
            'availability': 'configured',
            'role_label': profile_info.get('description') or 'Hermes profile agent',
            'active_count': 0,
            'review_count': 0,
            'blocked_count': 0,
            'completed_count': 0,
            'latest_task_title': None,
            'latest_status': None,
        }

    for name, status in worker_statuses.items():
        if name in base_agents:
            continue
        kind = 'worker'
        role_label = '브리프를 받아 실행하는 에이전트'
        if name == 'researcher-co':
            role_label = 'MacBook Claude 연구 수집 에이전트'
        elif name == 'writer-co':
            role_label = 'MacBook Claude 문서 작성/최종 정리 에이전트'
        elif name == 'verify-co':
            role_label = 'MacBook Claude 검증 에이전트'
            kind = 'reviewer'
        elif name == 'researcher_agent':
            role_label = 'MacBook OpenClaw 연구 수집 에이전트'
        elif 'Claude' in name:
            role_label = '기획·분석·구현 중심 메인 실행 에이전트'
        elif 'OpenClaw' in name:
            role_label = 'headless 실행과 결과 회수 중심 에이전트'
        base_agents[name] = {
            'name': name,
            'kind': kind,
            'availability': status,
            'role_label': role_label,
            'active_count': 0,
            'review_count': 0,
            'blocked_count': 0,
            'completed_count': 0,
            'latest_task_title': None,
            'latest_status': None,
        }

    ordered_tasks = sorted(tasks, key=lambda t: t.get('updated_at') or t.get('created_at') or '', reverse=True)
    for task in ordered_tasks:
        status = task.get('status', 'queued')
        related_agents = {'Hermes Hub'}
        for worker in task.get('assigned_workers', []):
            related_agents.add(worker)
        for stage in task.get('stages', []):
            for agent_name in stage.get('agents', []):
                related_agents.add(agent_name)
        reviewer = task.get('reviewer')
        if reviewer:
            related_agents.add(reviewer)

        if status not in {'completed', 'cancelled'}:
            task_visible_agents.update(related_agents)

        for agent_name in related_agents:
            if agent_name not in base_agents:
                base_agents[agent_name] = {
                    'name': agent_name,
                    'kind': 'worker',
                    'availability': 'needs_config',
                    'role_label': '아직 구성되지 않았지만 흐름에 언급된 에이전트',
                    'active_count': 0,
                    'review_count': 0,
                    'blocked_count': 0,
                    'completed_count': 0,
                    'latest_task_title': None,
                    'latest_status': None,
                }
            agent = base_agents[agent_name]
            if agent['latest_task_title'] is None:
                agent['latest_task_title'] = task.get('title')
                agent['latest_status'] = status
            if status == 'cancelled':
                continue
            if status in {'dispatch_blocked', 'dispatch_failed', 'blocked'}:
                agent['blocked_count'] += 1
            elif status == 'waiting_verification' or (agent_name == reviewer and status != 'completed'):
                agent['review_count'] += 1
            elif status == 'completed':
                agent['completed_count'] += 1
            else:
                agent['active_count'] += 1

    kind_order = {
        'hub': 0,
        'orchestrator': 1,
        'planner': 2,
        'designer': 3,
        'researcher': 4,
        'worker': 5,
        'reviewer': 6,
        'profile': 7,
    }
    visible_agents = []
    for agent in base_agents.values():
        if agent['name'] in always_visible or agent['name'] in task_visible_agents:
            visible_agents.append(agent)
            continue
        if agent['active_count'] or agent['review_count'] or agent['blocked_count']:
            visible_agents.append(agent)
    return sorted(visible_agents, key=lambda a: (kind_order.get(a['kind'], 99), a['name']))


def build_overview() -> dict:
    tasks = [build_task_view(t) for t in load_tasks()]
    results = list_items(RESULTS_DIR)
    verifications = list_items(VERIFICATIONS_DIR)
    digests = list_items(DIGESTS_DIR)
    status_counts = {}
    for task in tasks:
        status_counts[task['status']] = status_counts.get(task['status'], 0) + 1
    sync_evidence = read_observational_json_file(OPERATIONS_DIR / 'sync' / 'latest.json')
    watchdog_evidence = read_observational_json_file(OPERATIONS_DIR / 'watchdog' / 'latest.json')
    return {
        'hub_status': 'online',
        'task_count': len(tasks),
        'brief_count': len(tasks),
        'result_count': len(results),
        'verification_count': len(verifications),
        'digest_count': len(digests),
        'latest_brief': tasks[0]['artifacts'].get('markdown_brief', '').split('/')[-1] if tasks else None,
        'latest_result': results[0]['name'] if results else None,
        'latest_verification': verifications[0]['name'] if verifications else None,
        'latest_digest': digests[0]['name'] if digests else None,
        'status_counts': status_counts,
        'workers': worker_status_map(),
        'agents': build_agent_summary(tasks),
        'sync_evidence': sync_evidence,
        'watchdog_evidence': watchdog_evidence,
        'operations_evidence': {
            'schema_version': 1,
            'sync': project_operations_evidence({}, sync_evidence, None)['sync'],
            'watchdog': project_operations_evidence({}, None, watchdog_evidence)['watchdog'],
        },
        'dashboard_summary': build_dashboard_summary(tasks),
    }


def write_task_brief(payload: dict) -> dict:
    title = (payload.get('title') or '').strip()
    objective = (payload.get('objective') or '').strip()
    if not title or not objective:
        raise ValueError('title and objective are required')

    task_id = next_task_id()
    created_at = now_iso()
    priority = (payload.get('priority') or 'medium').strip()
    execution_mode = (payload.get('execution_mode') or 'research-pipeline').strip()
    assigned_workers = payload.get('assigned_workers') or []
    if isinstance(assigned_workers, str):
        assigned_workers = [w.strip() for w in assigned_workers.split(',') if w.strip()]
    context = (payload.get('context') or '').strip()
    constraints = (payload.get('constraints') or '').strip()
    deliverable = (payload.get('deliverable') or '').strip()
    reviewer = (payload.get('reviewer') or 'HermesVerifier').strip()
    raw_project_ref = payload.get('project_ref')
    project_ref = None
    if isinstance(raw_project_ref, dict) and str(raw_project_ref.get('project_id') or '').strip():
        project_ref = {'project_id': str(raw_project_ref['project_id']).strip()}
        if str(raw_project_ref.get('name') or '').strip():
            project_ref['name'] = str(raw_project_ref['name']).strip()[:240]
    if not assigned_workers:
        assigned_workers = ['HermesResearcher', 'researcher-co', 'researcher_agent']
    raw_conv = payload.get('pm_conversation') or []
    if not isinstance(raw_conv, list):
        raw_conv = []
    pm_conversation = [
        {'role': str(t.get('role') or ''), 'text': str(t.get('text') or '')[:2000]}
        for t in raw_conv if isinstance(t, dict) and str(t.get('text') or '').strip()
    ][:60]
    pm_interpretation = str(payload.get('pm_interpretation') or '').strip()
    raw_inputs = payload.get('input_files') or []
    if isinstance(raw_inputs, str):
        raw_inputs = [raw_inputs]
    input_files = []
    for p in raw_inputs:
        try:
            fp = Path(str(p)).resolve()
            if fp.is_file() and str(fp).startswith(str(INPUTS_DIR.resolve())):
                input_files.append(str(fp))
        except OSError:
            continue
    input_files = input_files[:10]
    input_files_remote = [f'~/agent-hub/inputs/{task_id}/{Path(p).name}' for p in input_files]
    slug = slugify(title)

    md_path = BRIEFS_DIR / f'{task_id}-{slug}.md'
    json_path = BRIEFS_DIR / f'{task_id}-{slug}.json'
    stages = default_pipeline_stages(task_id, deliverable, reviewer)

    md = f'''# Task Brief\n\n## 1. Task Metadata\n- Task ID: {task_id}\n- Created At: {created_at}\n- Created By: Dashboard UI\n- Priority: {priority}\n- Execution Mode: {execution_mode}\n- Assigned Workers: {", ".join(assigned_workers) if assigned_workers else "TBD"}\n- Reviewer: {reviewer}\n\n---\n\n## 2. Objective\n한 줄 목표:\n{title}\n\n상세 목표:\n{objective}\n\n---\n\n## 3. Background Context\n{context or "(none provided)"}\n\n---\n\n## 4. Constraints\n{constraints or "(none provided)"}\n\n---\n\n## 5. Required Deliverable\n{deliverable or "Structured result envelope + verifiable artifacts + blockers/assumptions/confidence"}\n\n---\n\n## 6. Verification Focus\n- factual correctness\n- completeness\n- contradictions\n- artifact validity\n- risk notes\n'''

    data = {
        'task_id': task_id,
        'created_at': created_at,
        'updated_at': created_at,
        'title': title,
        'objective': objective,
        'priority': priority,
        'execution_mode': execution_mode,
        'assigned_workers': assigned_workers,
        'reviewer': reviewer,
        'project_ref': project_ref,
        'context': context,
        'constraints': constraints,
        'deliverable': deliverable,
        'pipeline_name': 'research-write-verify-finalize',
        'stages': stages,
        'status': 'queued',
        'source': 'operations-dashboard-ui',
        'pm_conversation': pm_conversation,
        'pm_interpretation': pm_interpretation,
        'input_files': input_files,
        'input_files_remote': input_files_remote,
        'dispatch_ready': True,
        'artifacts': {
            'markdown_brief': str(md_path),
            'json_brief': str(json_path),
        },
    }

    md_path.write_text(md, encoding='utf-8')
    save_json(json_path, data)
    return data


def run_command(cmd: list[str], timeout: int = 30, cwd: str | None = None,
                input_text: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, cwd=cwd,
                          input=input_text, env=env, shell=False)
    return proc.returncode, proc.stdout, proc.stderr


def base_task_id_str(task_id: str) -> str:
    parts = str(task_id).split('-')
    return '-'.join(parts[:3]) if len(parts) >= 3 else str(task_id)


def dispatch_to_worker(task: dict, worker_name: str, workers: dict) -> dict:
    cfg = workers.get(worker_name)
    base = {
        'task_id': task['task_id'],
        'worker_name': worker_name,
        'attempted_at': now_iso(),
        'brief_json_path': task['artifacts']['json_brief'],
        'status': 'unknown',
    }
    if not cfg:
        base['status'] = 'worker_missing'
        base['message'] = 'Worker config not found.'
        return base
    if not cfg.get('enabled', True):
        base['status'] = 'worker_disabled'
        base['message'] = 'Worker disabled in config.'
        return base
    mode = cfg.get('mode', 'ssh')
    base['mode'] = mode
    if mode == 'local':
        base['status'] = 'not_dispatch_target'
        base['message'] = 'Local profile; no remote dispatch performed.'
        return base
    if mode == 'local-inbox':
        inbox_dir = cfg.get('local_inbox_dir')
        if not inbox_dir:
            base['status'] = 'needs_config'
            base['message'] = 'Missing worker config: local_inbox_dir'
            return base
        local_brief = Path(task['artifacts']['json_brief'])
        dest_dir = Path(inbox_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / local_brief.name
        base['target'] = str(dest)
        try:
            shutil.copy2(local_brief, dest)
        except OSError as exc:
            base['status'] = 'dispatch_failed'
            base['message'] = f'Failed to copy brief to local inbox: {exc}'
            return base
        base['status'] = 'dispatched'
        base['message'] = 'Brief copied to local inbox successfully.'
        return base
    required = ['host', 'user', 'remote_inbox_dir']
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        base['status'] = 'needs_config'
        base['message'] = f'Missing worker config: {", ".join(missing)}'
        return base

    host = cfg['host']
    user = cfg['user']
    port = str(cfg.get('port', 22))
    remote_inbox_dir = cfg['remote_inbox_dir']
    # scp(SFTP)는 원격 경로의 $HOME/~ 를 확장하지 않으므로 홈 상대 경로를 사용한다
    remote_inbox_dir_shell = remote_inbox_dir[2:] if remote_inbox_dir.startswith('~/') else remote_inbox_dir
    local_brief = Path(task['artifacts']['json_brief'])
    remote_brief = f"{remote_inbox_dir_shell.rstrip('/')}/{local_brief.name}"
    base['target'] = f'{user}@{host}:{remote_brief}'

    mkdir_cmd = ['ssh', '-p', port, f'{user}@{host}', f'mkdir -p {shlex.quote(remote_inbox_dir_shell)}']
    cp_cmd = ['scp', '-P', port, str(local_brief), f'{user}@{host}:{remote_brief}']

    input_files = [p for p in (task.get('input_files') or []) if Path(p).is_file()]
    if input_files:
        remote_inputs_dir = f"agent-hub/inputs/{base_task_id_str(task['task_id'])}"
        rc0, _, err0 = run_command(['ssh', '-p', port, f'{user}@{host}', f'mkdir -p {shlex.quote(remote_inputs_dir)}'])
        if rc0 != 0:
            base['status'] = 'dispatch_failed'
            base['message'] = 'Failed to create remote inputs dir.'
            base['stderr'] = err0.strip()
            return base
        for fp in input_files:
            rci, _, erri = run_command(['scp', '-P', port, str(fp), f'{user}@{host}:{remote_inputs_dir}/'], timeout=180)
            if rci != 0:
                base['status'] = 'dispatch_failed'
                base['message'] = f'Failed to copy input file: {Path(fp).name}'
                base['stderr'] = erri.strip()
                return base
        base['input_files_sent'] = [Path(fp).name for fp in input_files]

    rc1, out1, err1 = run_command(mkdir_cmd)
    base['mkdir_command'] = ' '.join(shlex.quote(x) for x in mkdir_cmd)
    if rc1 != 0:
        base['status'] = 'dispatch_failed'
        base['message'] = 'Failed to create remote inbox dir.'
        base['stderr'] = err1.strip()
        base['stdout'] = out1.strip()
        return base

    rc2, out2, err2 = run_command(cp_cmd)
    base['copy_command'] = ' '.join(shlex.quote(x) for x in cp_cmd)
    if rc2 != 0:
        base['status'] = 'dispatch_failed'
        base['message'] = 'Failed to copy brief to remote worker inbox.'
        base['stderr'] = err2.strip()
        base['stdout'] = out2.strip()
        return base

    template = (cfg.get('dispatch_command_template') or '').strip()
    if template:
        rendered = template.format(remote_brief_path=remote_brief, task_id=task['task_id'])
        cmd3 = ['ssh', '-p', port, f'{user}@{host}', rendered]
        rc3, out3, err3 = run_command(cmd3)
        base['dispatch_command'] = ' '.join(shlex.quote(x) for x in cmd3)
        if rc3 != 0:
            base['status'] = 'dispatch_failed'
            base['message'] = 'Remote dispatch command failed.'
            base['stderr'] = err3.strip()
            base['stdout'] = out3.strip()
            return base
        base['dispatch_stdout'] = out3.strip()

    base['status'] = 'dispatched'
    base['message'] = 'Brief copied to remote inbox successfully.'
    return base


def dispatch_task(task_id: str, worker_names: list[str] | None = None) -> dict:
    task, path = find_task(task_id)
    workers = load_workers()
    selected = worker_names or task.get('assigned_workers') or []
    if not selected:
        raise ValueError('No assigned workers to dispatch.')

    records = []
    statuses = []
    for worker in selected:
        record = dispatch_to_worker(task, worker, workers)
        statuses.append(record['status'])
        save_json(dispatch_record_path(task_id, worker), record)
        records.append(record)

    new_status = 'queued'
    if statuses and all(s == 'dispatched' for s in statuses):
        new_status = 'dispatched'
    elif any(s == 'dispatched' for s in statuses):
        new_status = 'partially_dispatched'
    elif any(s in {'needs_config', 'worker_missing', 'worker_disabled'} for s in statuses):
        new_status = 'dispatch_blocked'
    elif any(s == 'dispatch_failed' for s in statuses):
        new_status = 'dispatch_failed'

    task['status'] = new_status
    task['updated_at'] = now_iso()
    task['last_dispatch_at'] = task['updated_at']
    task['last_dispatch_workers'] = selected
    task['last_error'] = next((r.get('message') for r in records if r['status'] != 'dispatched'), None)
    stages = task.get('stages') or []
    if stages:
        stage0 = stages[0]
        if new_status in {'dispatched', 'partially_dispatched'}:
            stage0['status'] = 'in_progress'
        elif new_status in {'dispatch_blocked', 'dispatch_failed'}:
            stage0['status'] = 'blocked'
        task['stages'] = stages
    save_json(path, task)
    return {'task_id': task_id, 'status': new_status, 'records': records}


def auto_dispatch_queued() -> dict:
    task_views = [build_task_view(t) for t in load_tasks()]
    queued = [t for t in task_views if t.get('status') == 'queued']
    results = []
    for task in queued:
        results.append(dispatch_task(task['task_id']))
    return {
        'queued_count': len(queued),
        'dispatched_count': len(results),
        'results': results,
    }


def add_live_note(task_id: str, note: str) -> dict:
    task, path = find_task(task_id)
    if task.get('status') in {'completed', 'cancelled'}:
        raise ValueError('완료/취소된 업무에는 지시를 추가할 수 없습니다')
    notes = task.get('pm_live_notes') or []
    notes.append({'note': note, 'at': now_iso(), 'consumed': None})
    task['pm_live_notes'] = notes[-20:]
    task['updated_at'] = now_iso()
    save_json(path, task)
    return {'task_id': task_id, 'count': len(task['pm_live_notes'])}


def set_final_review_override(task_id: str, action: str) -> dict:
    """최종 총평 not_meets 태스크에 대한 사용자 결정. sync가 다음 사이클에 반영."""
    if action not in {'accept', 'rework'}:
        raise ValueError('action must be accept or rework')
    task, path = find_task(task_id)
    task['final_review_override'] = action
    task['updated_at'] = now_iso()
    save_json(path, task)
    return {'task_id': task_id, 'final_review_override': action}


def set_gate_override(task_id: str, stage_id: str, action: str) -> dict:
    if action not in {'approve', 'revise', 'skip'}:
        raise ValueError('action must be approve, revise, or skip')
    for path in task_json_paths():
        data = load_json(path)
        if data.get('task_id') != task_id:
            continue
        stage = next((item for item in data.get('stages', []) if item.get('id') == stage_id), None)
        if stage is None:
            raise ValueError(f'stage not found: {stage_id}')
        stage['gate_override'] = action
        data['updated_at'] = now_iso()
        save_json(path, data)
        return {'task_id': task_id, 'stage_id': stage_id, 'override': action}
    raise FileNotFoundError(task_id)


def record_default_interview(task_id: str) -> dict:
    task, path = find_task(task_id)
    questions = [
        '이 작업이 끝났을 때 반드시 남아야 하는 결과는 무엇인가?',
        '이 작업이 필요한 배경과 현재 맥락은 무엇인가?',
        '지켜야 할 제약 또는 금지 범위는 무엇인가?',
        '어떤 형태의 산출물이 완료 기준인가?',
    ]
    answers = [task.get('objective', ''), task.get('context', ''), task.get('constraints', ''), task.get('deliverable', '')]
    artifact = create_interview_artifact(task, questions, answers)
    task['interview'] = artifact
    task['updated_at'] = now_iso()
    save_json(path, task)
    return artifact


def draft_task_seed(task_id: str, payload: dict) -> dict:
    task, path = find_task(task_id)
    artifact = create_seed_artifact(
        task,
        acceptance_criteria=payload.get('acceptance_criteria') or [task.get('deliverable', '')],
        included_scope=payload.get('included_scope') or [task.get('objective', '')],
        excluded_scope=payload.get('excluded_scope') or [],
        assumptions=payload.get('assumptions') or [],
    )
    task['seed'] = artifact
    task['updated_at'] = now_iso()
    save_json(path, task)
    return artifact


def approve_task_seed(task_id: str, approver: str = 'Raphael') -> dict:
    task, path = find_task(task_id)
    seed = task.get('seed') or {}
    seed_path = seed.get('json_path')
    if not seed_path or not Path(seed_path).is_file():
        raise ValueError('draft seed not found; create a seed draft first')
    approved = approve_seed_artifact(seed_path, approver)
    task['seed'] = {
        'id': approved['seed_id'],
        'version': approved['version'],
        'status': approved['status'],
        'json_path': seed_path,
        'yaml_path': str(Path(seed_path).with_suffix('.yaml')),
        'markdown_path': str(Path(seed_path).with_suffix('.md')),
    }
    task['updated_at'] = now_iso()
    save_json(path, task)
    return task['seed']


def _task_exists(task_id: str) -> bool:
    try:
        find_task(task_id)
    except FileNotFoundError:
        return False
    return True


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict | list, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        write_all(self.wfile, body)

    def _send_text(self, text: str, status: int = 200, content_type: str = 'text/plain; charset=utf-8'):
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        write_all(self.wfile, body)

    def _followup_origin_allowed(self) -> bool:
        """Follow-up writes are local-only and require the exact listener origin."""
        address = getattr(self.server, 'server_address', (HOST, PORT))
        listener_host = str(address[0])
        try:
            if not ipaddress.ip_address(listener_host).is_loopback:
                return False
        except ValueError:
            return False
        listener_port = int(address[1])
        canonical_host = f'[{listener_host}]:{listener_port}' if ':' in listener_host else f'{listener_host}:{listener_port}'
        origin = (self.headers.get('Origin') or '').strip()
        host = (self.headers.get('Host') or '').strip()
        if host != canonical_host or not origin:
            return False
        parsed = urlparse(origin)
        return parsed.scheme == 'http' and parsed.netloc == canonical_host and not parsed.path and not parsed.params and not parsed.query and not parsed.fragment

    def _followup_listener_allowed(self) -> bool:
        address = getattr(self.server, 'server_address', (HOST, PORT))
        try:
            return ipaddress.ip_address(str(address[0])).is_loopback
        except (ValueError, IndexError):
            return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/api/overview':
            return self._send_json(build_overview())
        if path == '/api/dashboard-console':
            return self._send_json(build_dashboard_console())
        if path == '/api/dashboard/instruction-capabilities':
            return self._send_json(instruction_capabilities())
        if path == '/api/briefs':
            return self._send_json(list_items(BRIEFS_DIR))
        if path == '/api/results':
            return self._send_json(list_items(RESULTS_DIR))
        if path == '/api/verifications':
            return self._send_json(list_items(VERIFICATIONS_DIR))
        if path == '/api/digests':
            return self._send_json(list_items(DIGESTS_DIR))
        if path == '/api/interviews':
            return self._send_json(list_items(INTERVIEWS_DIR))
        if path == '/api/seeds':
            return self._send_json(list_items(SEEDS_DIR))
        if path == '/api/tasks':
            return self._send_json([build_task_view(t) for t in load_tasks()])
        if path == '/api/agents':
            return self._send_json(build_agent_summary([build_task_view(t) for t in load_tasks()]))
        if path == '/api/workers':
            return self._send_json(load_workers())
        if path == '/api/follow-up-request-capabilities':
            return self._send_json(followup_capabilities())
        match = re.fullmatch(r'/api/tasks/([^/]+)/follow-up-requests', path)
        if match:
            task_id = unquote(match.group(1))
            if not _task_exists(task_id):
                return self._send_json({'ok': False, 'error': f'task not found: {task_id}'}, status=404)
            return self._send_json({'ok': True, 'requests': list_followup_requests(task_id, FOLLOWUP_REQUESTS_DIR)})
        if path == '/api/health':
            return self._send_json({'ok': True, 'host': HOST, 'port': PORT})
        if path == '/detail.html':
            p = UI_DIR / 'detail.html'
            return self._send_text(p.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')
        if path.startswith('/files/'):
            parts = path[len('/files/'):].split('/', 1)
            if len(parts) == 2:
                kind, raw_name = parts
                name = unquote(raw_name)
                folders = {
                    'results': RESULTS_DIR,
                    'verifications': VERIFICATIONS_DIR,
                    'digests': DIGESTS_DIR,
                    'interviews': INTERVIEWS_DIR,
                    'seeds': SEEDS_DIR,
                }
                folder = folders.get(kind)
                if folder and name and '/' not in name and '..' not in name:
                    fp = folder / name
                    if fp.is_file():
                        ctypes = {
                            '.md': 'text/markdown; charset=utf-8',
                            '.json': 'application/json; charset=utf-8',
                            '.html': 'text/html; charset=utf-8',
                        }
                        ctype = ctypes.get(fp.suffix.lower(), 'text/plain; charset=utf-8')
                        body = fp.read_bytes()
                        self.send_response(200)
                        self.send_header('Content-Type', ctype)
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.send_header('Referrer-Policy', 'no-referrer')
                        if fp.suffix.lower() in {'.html', '.htm'}:
                            self.send_header(
                                'Content-Security-Policy',
                                "sandbox; default-src 'none'; script-src 'none'; connect-src 'none'; "
                                "form-action 'none'; object-src 'none'; base-uri 'none'; "
                                "img-src data: https:; style-src 'unsafe-inline' https:"
                            )
                        if parse_qs(parsed.query).get('download'):
                            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + url_quote(name))
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        write_all(self.wfile, body)
                        return
            return self._send_text('Not Found', status=404)
        if path == '/' or path == '/index.html':
            index = UI_DIR / 'index.html'
            return self._send_text(index.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')
        if path == '/app.js':
            p = UI_DIR / 'app.js'
            return self._send_text(p.read_text(encoding='utf-8'), content_type='application/javascript; charset=utf-8')
        if path == '/styles.css':
            p = UI_DIR / 'styles.css'
            return self._send_text(p.read_text(encoding='utf-8'), content_type='text/css; charset=utf-8')
        return self._send_text('Not Found', status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        followup_match = re.fullmatch(r'/api/tasks/([^/]+)/follow-up-requests', parsed.path)
        if followup_match:
            declared_length = self.headers.get('Content-Length')
            try:
                if declared_length is None:
                    raise ValueError
                length = int(declared_length)
            except (TypeError, ValueError):
                return self._send_json({'ok': False, 'error': 'valid Content-Length required'}, status=400)
            if length < 0:
                return self._send_json({'ok': False, 'error': 'valid Content-Length required'}, status=400)
            if length > 64 * 1024:
                return self._send_json({'ok': False, 'error': 'follow-up request payload is too large'}, status=413)
            ctype = self.headers.get('Content-Type', '')
            raw = self.rfile.read(length)
            try:
                return self._handle_followup_post(followup_match, raw, ctype, length)
            except FollowUpError as e:
                return self._send_json({'ok': False, 'error': str(e)}, status=getattr(e, 'status', 400))
            except FileNotFoundError as e:
                return self._send_json({'ok': False, 'error': f'task not found: {e}'}, status=404)
            except ValueError as e:
                return self._send_json({'ok': False, 'error': str(e)}, status=400)
            except Exception as e:
                return self._send_json({'ok': False, 'error': f'unexpected error: {e}'}, status=500)

        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        raw = self.rfile.read(length) if length >= 0 else b''
        ctype = self.headers.get('Content-Type', '')
        try:
            if parsed.path == '/api/upload-input':
                return self._handle_upload_input(parsed, raw)
            if parsed.path == '/api/dashboard/instructions':
                if not self._followup_origin_allowed():
                    return self._send_json({'ok': False, 'error': {'code': 'same_origin_required', 'message': 'same-origin Origin header required', 'retryable': False}}, status=403)
                if 'application/json' not in ctype:
                    return self._send_json({'ok': False, 'error': {'code': 'json_required', 'message': 'application/json content type required', 'retryable': False}}, status=415)
                if length > 64 * 1024:
                    return self._send_json({'ok': False, 'error': {'code': 'payload_too_large', 'message': 'instruction payload is too large', 'retryable': False}}, status=413)
                if not instruction_capabilities().get('write_enabled'):
                    return self._send_json({'ok': False, 'error': {'code': 'write_disabled', 'message': 'instruction write is disabled', 'retryable': False}}, status=403)
                try:
                    payload = json.loads(raw.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return self._send_json({'ok': False, 'error': {'code': 'invalid_json', 'message': 'valid JSON object required', 'retryable': False}}, status=400)
                if not isinstance(payload, dict):
                    return self._send_json({'ok': False, 'error': {'code': 'invalid_json', 'message': 'JSON object required', 'retryable': False}}, status=400)
                record, created = submit_instruction(payload, self.headers.get('Idempotency-Key', ''), root=INSTRUCTIONS_DIR, task_exists=_task_exists)
                return self._send_json({'ok': True, 'instruction': record, 'parent_changed': False}, status=201 if created else 200)
            if 'application/json' in ctype and raw:
                payload = json.loads(raw.decode('utf-8'))
            else:
                payload = {k: v[0] for k, v in parse_qs(raw.decode('utf-8')).items()}

            if parsed.path == '/api/tasks':
                created = write_task_brief(payload)
                return self._send_json({'ok': True, 'task': created}, status=201)
            if parsed.path == '/api/interview':
                task_id = str(payload.get('task_id') or '').strip()
                if not task_id:
                    raise ValueError('task_id is required')
                result = record_default_interview(task_id)
                return self._send_json({'ok': True, 'interview': result}, status=201)
            if parsed.path == '/api/seed':
                task_id = str(payload.get('task_id') or '').strip()
                action = str(payload.get('action') or 'draft').strip()
                if not task_id:
                    raise ValueError('task_id is required')
                if action == 'draft':
                    result = draft_task_seed(task_id, payload)
                    return self._send_json({'ok': True, 'seed': result}, status=201)
                if action == 'approve':
                    result = approve_task_seed(task_id, str(payload.get('approver') or 'Raphael'))
                    return self._send_json({'ok': True, 'seed': result}, status=200)
                raise ValueError('seed action must be draft or approve')
            if parsed.path == '/api/pm-brief-assist':
                result = pm_brief_assist(payload)
                return self._send_json({'ok': True, **result}, status=200)
            if parsed.path == '/api/dispatch':
                task_id = (payload.get('task_id') or '').strip()
                workers = payload.get('workers') or None
                if isinstance(workers, str):
                    workers = [w.strip() for w in workers.split(',') if w.strip()]
                if not task_id:
                    raise ValueError('task_id is required')
                result = dispatch_task(task_id, workers)
                return self._send_json({'ok': True, 'dispatch': result}, status=200)
            if parsed.path == '/api/auto-dispatch':
                result = auto_dispatch_queued()
                return self._send_json({'ok': True, 'auto_dispatch': result}, status=200)
            if parsed.path == '/api/live-note':
                task_id = (payload.get('task_id') or '').strip()
                note = str(payload.get('note') or '').strip()[:1000]
                if not task_id or not note:
                    raise ValueError('task_id and note required')
                result = add_live_note(task_id, note)
                return self._send_json({'ok': True, 'live_note': result}, status=200)
            if parsed.path == '/api/final-review':
                task_id = (payload.get('task_id') or '').strip()
                action = (payload.get('action') or '').strip()
                if not task_id:
                    raise ValueError('task_id required')
                result = set_final_review_override(task_id, action)
                return self._send_json({'ok': True, 'final_review': result}, status=200)
            if parsed.path == '/api/gate-override':
                task_id = (payload.get('task_id') or '').strip()
                stage_id = (payload.get('stage_id') or '').strip()
                action = (payload.get('action') or '').strip()
                if not task_id or not stage_id:
                    raise ValueError('task_id and stage_id required')
                result = set_gate_override(task_id, stage_id, action)
                return self._send_json({'ok': True, 'gate_override': result}, status=200)
            return self._send_json({'error': 'Not Found'}, status=404)
        except FollowUpError as e:
            return self._send_json({'ok': False, 'error': str(e)}, status=getattr(e, 'status', 400))
        except InstructionError as e:
            return self._send_json({'ok': False, 'error': {'code': getattr(e, 'code', 'invalid_instruction'), 'message': str(e), 'retryable': getattr(e, 'retryable', False)}}, status=getattr(e, 'status', 400))
        except FileNotFoundError as e:
            return self._send_json({'ok': False, 'error': f'task not found: {e}'}, status=404)
        except ValueError as e:
            return self._send_json({'ok': False, 'error': str(e)}, status=400)
        except subprocess.TimeoutExpired:
            return self._send_json({'ok': False, 'error': 'dispatch command timed out'}, status=504)
        except Exception as e:
            return self._send_json({'ok': False, 'error': f'unexpected error: {e}'}, status=500)

    def _handle_followup_post(self, match, raw: bytes, ctype: str, length: int):
        if not self._followup_listener_allowed() or not self._followup_origin_allowed():
            return self._send_json({'ok': False, 'error': 'loopback exact-origin required'}, status=403)
        if ctype != 'application/json':
            return self._send_json({'ok': False, 'error': 'application/json content type required'}, status=400)
        if length < 0:
            return self._send_json({'ok': False, 'error': 'valid Content-Length required'}, status=400)
        if length > 64 * 1024:
            return self._send_json({'ok': False, 'error': 'follow-up request payload is too large'}, status=413)
        if not self.headers.get('Idempotency-Key'):
            return self._send_json({'ok': False, 'error': 'Idempotency-Key header required'}, status=400)
        if not followup_capabilities().get('write_enabled'):
            return self._send_json({'ok': False, 'error': 'follow-up request write is disabled'}, status=503)
        try:
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._send_json({'ok': False, 'error': 'valid JSON object required'}, status=400)
        if not isinstance(payload, dict):
            return self._send_json({'ok': False, 'error': 'JSON object required'}, status=400)
        task_id = unquote(match.group(1))
        request, created = submit_followup_request(
            task_id, payload, self.headers['Idempotency-Key'],
            actor_id=followup_capabilities()['actor_id'],
            auth_source=followup_capabilities()['auth_source'],
            requests_dir=FOLLOWUP_REQUESTS_DIR, task_exists=_task_exists,
        )
        return self._send_json({'ok': True, 'request': request, 'parent_task_changed': False}, status=201 if created else 200)

    def _handle_upload_input(self, parsed, raw: bytes):
        params = parse_qs(parsed.query)
        name = os.path.basename(unquote((params.get('name') or [''])[0])).strip()
        if not name or not raw:
            return self._send_json({'ok': False, 'error': 'name 쿼리와 파일 본문이 필요합니다'}, status=400)
        if len(raw) > 30 * 1024 * 1024:
            return self._send_json({'ok': False, 'error': '파일이 너무 큽니다 (최대 30MB)'}, status=413)
        safe = re.sub(r'[^\w.\-가-힣 ()\[\]]', '_', name)[:120] or 'input.bin'
        INPUTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%dT%H%M%S')
        dest = INPUTS_DIR / f'{stamp}__{safe}'
        i = 0
        while dest.exists():
            i += 1
            dest = INPUTS_DIR / f'{stamp}-{i}__{safe}'
        dest.write_bytes(raw)
        return self._send_json({'ok': True, 'path': str(dest), 'name': safe, 'size': len(raw)}, status=201)

    def log_message(self, format: str, *args):
        return


if __name__ == '__main__':
    if not ipaddress.ip_address(HOST).is_loopback:
        raise SystemExit('operations dashboard follow-up listener must bind to loopback')
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'Operations dashboard running on http://{HOST}:{PORT}')
    server.serve_forever()

