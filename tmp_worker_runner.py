#!/usr/bin/env python3
"""Agent Hub worker runner (MacBook side).

PC 허브(Raphael Agent Hub)가 SSH로 업로드한 brief(JSON)를 inbox에서 감지해
worker별 headless 실행을 수행하고, result envelope를 results/에 기록한다.

- inbox/claude-code/*.json  → claude -p 실행 → results/<task_id>__claude-code.{json,md}
- inbox/openclaw/*.json     → openclaw agent --local 실행 → results/<task_id>__openclaw.{json,md}
- 처리한 brief는 inbox/<worker>/processed/ 로 이동
- 회신 레그는 PC 허브가 results/ 를 SSH pull 하는 방식 (허브 쪽 설정)
"""

import fcntl
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HUB_DIR = Path.home() / "agent-hub"
INBOX_DIR = HUB_DIR / "inbox"
RESULTS_DIR = HUB_DIR / "results"
LOGS_DIR = HUB_DIR / "logs"
WORKSPACE_DIR = HUB_DIR / "workspace"
LOCK_FILE = HUB_DIR / ".worker_runner.lock"

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/opt/homebrew/bin/claude")
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "/opt/homebrew/bin/openclaw")
OPENCLAW_AGENT = os.environ.get("OPENCLAW_AGENT", "main")
OPENCLAW_PATH = os.environ.get("OPENCLAW_PATH", "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")
WORKER_MODEL = os.environ.get("CLAUDE_WORKER_MODEL", "sonnet")
TASK_TIMEOUT_SECONDS = int(os.environ.get("WORKER_TASK_TIMEOUT", "900"))

WORKER_NAMES = {
    "claude-code": "Claude Code Worker",
    "openclaw": "OpenClaw Worker",
}

logger = logging.getLogger("worker-runner")


def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOGS_DIR / "worker-runner.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(logging.INFO)


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_prompt(brief):
    sections = [
        "당신은 멀티에이전트 허브의 worker입니다. 아래 업무 지시(brief)를 수행하고,",
        "최종 산출물을 markdown 보고서 형식의 텍스트로만 답하세요.",
        "파일 생성/수정 등 부수 효과는 제약사항에서 명시적으로 허용된 경우에만 수행하세요.",
        "",
        "## Task ID\n" + str(brief.get("task_id", "unknown")),
        "## 제목\n" + str(brief.get("title", "")),
        "## 목표\n" + str(brief.get("objective", "")),
    ]
    for key, label in (
        ("context", "배경/맥락"),
        ("constraints", "제약사항"),
        ("deliverable", "원하는 산출물"),
    ):
        value = brief.get(key)
        if value:
            sections.append("## " + label + "\n" + str(value))
    return "\n\n".join(sections)


def run_claude(brief, task_workspace):
    prompt = build_prompt(brief)
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--output-format", "json",
        "--model", WORKER_MODEL,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(task_workspace),
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "transient": True,
                "error": "timeout after %ss" % TASK_TIMEOUT_SECONDS,
                "report": None, "raw": None, "exit_code": None}
    except OSError as exc:
        return {"ok": False, "transient": False,
                "error": "failed to launch claude: %s" % exc,
                "report": None, "raw": None, "exit_code": None}

    try:
        payload = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = None

    if payload is not None and payload.get("is_error"):
        api_status = payload.get("api_error_status")
        result_text = str(payload.get("result", ""))
        transient = api_status in (429, 500, 502, 503, 529) or "Overloaded" in result_text
        return {"ok": False, "transient": transient,
                "error": "api error %s: %s" % (api_status, result_text[:300]),
                "report": result_text, "raw": payload, "exit_code": proc.returncode}

    if proc.returncode != 0:
        return {"ok": False, "transient": False,
                "error": "claude exited %s: %s" % (proc.returncode, proc.stderr.strip()[:500]),
                "report": proc.stdout or None, "raw": payload, "exit_code": proc.returncode}

    report = payload.get("result") if payload else proc.stdout
    return {"ok": True, "transient": False, "error": None,
            "report": report or proc.stdout, "raw": payload, "exit_code": proc.returncode}


def run_openclaw(brief, task_workspace):
    prompt = build_prompt(brief)
    prompt_path = task_workspace / "openclaw_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        OPENCLAW_BIN,
        "agent",
        "--local",
        "--agent", OPENCLAW_AGENT,
        "--message-file", str(prompt_path),
        "--json",
        "--timeout", str(TASK_TIMEOUT_SECONDS),
    ]
    env = dict(os.environ)
    env["PATH"] = OPENCLAW_PATH
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(task_workspace),
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SECONDS + 30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "transient": True,
                "error": "timeout after %ss" % TASK_TIMEOUT_SECONDS,
                "report": None, "raw": None, "exit_code": None}
    except OSError as exc:
        return {"ok": False, "transient": False,
                "error": "failed to launch openclaw: %s" % exc,
                "report": None, "raw": None, "exit_code": None}

    try:
        payload = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = None

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:1200]
        transient = "Overloaded" in err or "timeout" in err.lower()
        return {"ok": False, "transient": transient,
                "error": "openclaw exited %s: %s" % (proc.returncode, err),
                "report": proc.stdout or None, "raw": payload, "exit_code": proc.returncode}

    report = None
    if payload:
        report = "\n\n".join(item.get("text", "") for item in payload.get("payloads", []) if item.get("text"))
    return {"ok": True, "transient": False, "error": None,
            "report": report or proc.stdout, "raw": payload, "exit_code": proc.returncode}


def write_result(worker_key, brief, brief_file, outcome, started_at):
    task_id = brief.get("task_id") or brief_file.stem
    base = "%s__%s" % (task_id, worker_key)
    md_path = RESULTS_DIR / (base + ".md")
    json_path = RESULTS_DIR / (base + ".json")

    report_text = outcome.get("report") or ("(no output)\n\nerror: %s" % outcome.get("error"))
    md_path.write_text(report_text, encoding="utf-8")

    raw = outcome.get("raw") or {}
    usage = raw.get("usage") or ((raw.get("meta") or {}).get("agentMeta") or {}).get("usage")
    model = WORKER_MODEL if worker_key == "claude-code" else (((raw.get("meta") or {}).get("agentMeta") or {}).get("model"))

    envelope = {
        "task_id": task_id,
        "worker": WORKER_NAMES.get(worker_key, worker_key),
        "worker_key": worker_key,
        "status": "completed" if outcome["ok"] else "failed",
        "started_at": started_at,
        "finished_at": now_iso(),
        "model": model,
        "exit_code": outcome.get("exit_code"),
        "error": outcome.get("error"),
        "brief_file": brief_file.name,
        "report_file": md_path.name,
        "usage": usage,
        "source": "macbook-worker-runner",
    }
    json_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    return envelope


def write_skipped_result(worker_key, brief, brief_file, reason):
    outcome = {"ok": False, "error": reason, "report": "(skipped) " + reason,
               "raw": None, "exit_code": None}
    envelope = write_result(worker_key, brief, brief_file, outcome, now_iso())
    envelope_path = RESULTS_DIR / ("%s__%s.json" % (envelope["task_id"], worker_key))
    updated = dict(envelope)
    updated["status"] = "skipped"
    envelope_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def process_brief(worker_key, brief_file):
    try:
        brief = json.loads(brief_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("brief 파싱 실패 %s: %s", brief_file.name, exc)
        return None

    task_id = brief.get("task_id") or brief_file.stem
    result_json = RESULTS_DIR / ("%s__%s.json" % (task_id, worker_key))
    if result_json.exists():
        logger.info("이미 처리됨, 건너뜀: %s (%s)", task_id, worker_key)
        return "already"

    logger.info("처리 시작: %s (%s)", task_id, worker_key)
    started_at = now_iso()
    task_workspace = WORKSPACE_DIR / task_id
    task_workspace.mkdir(parents=True, exist_ok=True)

    if worker_key == "claude-code":
        outcome = run_claude(brief, task_workspace)
    elif worker_key == "openclaw":
        outcome = run_openclaw(brief, task_workspace)
    else:
        envelope = write_skipped_result(worker_key, brief, brief_file, "unknown worker")
        logger.info("처리 완료: %s (%s) → %s", task_id, worker_key, envelope["status"])
        return envelope["status"]

    if outcome.get("transient"):
        logger.warning("일시적 오류, 다음 주기에 재시도: %s — %s",
                       task_id, outcome.get("error"))
        return "retry"
    envelope = write_result(worker_key, brief, brief_file, outcome, started_at)

    logger.info("처리 완료: %s (%s) → %s", task_id, worker_key, envelope["status"])
    return envelope["status"]


def archive_brief(worker_key, brief_file):
    processed_dir = INBOX_DIR / worker_key / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    target = processed_dir / brief_file.name
    brief_file.rename(target)


def main():
    setup_logging()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    lock_handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.info("다른 러너 인스턴스 실행 중 — 종료")
        return 0

    handled = 0
    for worker_key in WORKER_NAMES:
        worker_inbox = INBOX_DIR / worker_key
        if not worker_inbox.is_dir():
            continue
        for brief_file in sorted(worker_inbox.glob("*.json")):
            status = process_brief(worker_key, brief_file)
            if status is not None and status != "retry":
                archive_brief(worker_key, brief_file)
                handled += 1

    logger.info("이번 실행에서 처리한 brief: %d건", handled)
    return 0


if __name__ == "__main__":
    sys.exit(main())
