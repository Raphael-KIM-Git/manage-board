let dashboardState = {
  overview: null,
  tasks: [],
  results: [],
  verifications: [],
  digests: [],
};

const selectedArtifacts = new Map();
let pmConversation = [
  { role: 'pm', text: 'Raphael, 이번에 어떤 업무를 움직일까요?' },
];
let pmReviewState = {
  ready: false,
  questions: [],
  checklist: {},
  interpretation: '',
};
let taskDetailReturnFocus = null;
let followUpCapabilities = { write_enabled: false, origin_required: true };
const followUpDrafts = new Map();
const followUpIdempotency = new Map();
const followUpStale = new Map();
const modalStack = [];
let detailReturnFocus = null;
let scrollLockCount = 0;

const FOCUSABLE_SELECTOR = [
  'a[href]', 'area[href]', 'button:not([disabled])', 'input:not([disabled])',
  'select:not([disabled])', 'textarea:not([disabled])', 'iframe',
  '[tabindex]:not([tabindex="-1"])', '[contenteditable="true"]',
].join(',');

function modalNode(id) { return document.getElementById(id); }

function syncModalCoordinator() {
  const ids = ['briefModal', 'taskDetailModal', 'detailModal'];
  const openIds = modalStack.filter((id) => {
    const node = modalNode(id);
    return node && !node.classList.contains('is-hidden');
  });
  ids.forEach((id) => {
    const node = modalNode(id);
    if (!node) return;
    const stackIndex = openIds.indexOf(id);
    const open = stackIndex >= 0;
    node.classList.toggle('is-hidden', !open);
    node.setAttribute('aria-hidden', open ? 'false' : 'true');
    node.setAttribute('inert', open && stackIndex === openIds.length - 1 ? '' : '');
    if (open && stackIndex === openIds.length - 1) node.removeAttribute('inert');
    if (open) node.style.zIndex = String(60 + stackIndex * 10);
  });
  const topId = openIds[openIds.length - 1];
  scrollLockCount = openIds.length;
  const shell = document.querySelector('.shell');
  if (shell) {
    if (topId) shell.setAttribute('inert', '');
    else shell.removeAttribute('inert');
  }
  document.body.classList.toggle('modal-open', Boolean(topId));
  document.body.dataset.modalLockCount = String(scrollLockCount);
  document.body.setAttribute('data-modal-lock-count', String(scrollLockCount));
}

function pushModal(id) {
  const index = modalStack.indexOf(id);
  if (index >= 0) modalStack.splice(index, 1);
  modalNode(id)?.classList.remove('is-hidden');
  modalStack.push(id);
  syncModalCoordinator();
}

function popModal(id) {
  const index = modalStack.indexOf(id);
  if (index >= 0) modalStack.splice(index, 1);
  syncModalCoordinator();
}

function topModal() { return modalStack[modalStack.length - 1]; }

function focusablesIn(node) {
  return node ? Array.from(node.querySelectorAll(FOCUSABLE_SELECTOR)).filter((item) => !item.closest('.is-hidden')) : [];
}

function trapTopModal(event) {
  const node = modalNode(topModal());
  if (!node || event.key !== 'Tab') return;
  const focusables = focusablesIn(node);
  if (!focusables.length) { event.preventDefault(); return; }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed: ${url}`);
  return await res.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function badgeClass(status) {
  if (['configured', 'dispatched', 'completed', 'online'].includes(status)) return 'ok';
  if (['needs_config', 'queued', 'planned', 'partially_dispatched'].includes(status)) return 'warn';
  if (['dispatch_failed', 'dispatch_blocked', 'blocked', 'worker_missing'].includes(status)) return 'danger';
  if (['waiting_verification'].includes(status)) return 'violet';
  return 'wait';
}

function pipelineShapeLabel(shape) {
  const map = {
    full: '조사→작성→검증→최종본',
    write_verify: '작성→검증',
    research_verify: '조사→검증',
    analyze_verify: '분석→검증',
    research_only: '조사만',
  };
  return map[shape] || shape;
}

function dataQualityLabel(item) {
  const labels = { missing: '정보 없음', null: '값 비어 있음', unknown: '알 수 없는 값', artifact_ambiguous: '산출물 대상 불명확', conflict: '근거 충돌', scope_missing: '범위 확인 필요' };
  if (!item) return '확인 불가';
  return labels[item.kind] || item.kind || '확인 불가';
}

function authorityStatus(projection) {
  const rows = Array.isArray(projection?.audit_rows) ? projection.audit_rows.filter((row) => row && typeof row === 'object') : [];
  const explicit = rows.map((row) => row.status || row.state).find((value) => (
    value === 'decision-none' || value === 'unknown' || value === 'history-unavailable'
  ));
  if (explicit === 'decision-none' || explicit === 'unknown' || explicit === 'history-unavailable') return explicit;
  return 'history-unavailable';
}

function authorityPresentation(projection) {
  const labels = {
    'decision-none': '결정 없음',
    unknown: '알 수 없음',
    'history-unavailable': '이력 복구 불가',
  };
  const status = authorityStatus(projection);
  return { status, label: labels[status] || labels.unknown, className: `authority-${status}` };
}

function pipelineShapePresentation(task) {
  const shape = task.dashboard_projection?.pipeline_shape;
  if (!shape) return { label: pipelineShapeLabel(task.pipeline_shape), className: 'pipeline-unknown' };
  return { label: shape.label, className: `pipeline-${shape.confidence || 'unknown'}` };
}

function singlePrimaryAction(item) {
  return item?.primary_action || '상세 보기';
}

function cardDetailActionLabel(task) {
  const progressAction = taskProjection(task).progress?.next_pm_action;
  const queueAction = taskProjection(task).decision_queue_item;
  const label = progressAction?.label || queueAction?.primary_action;
  // Cards are a read-only overview. Older projections may still carry a
  // mutation-oriented label; never surface that label as a card control.
  if (!label || /재전송|다시\s*전송|게이트|live\s*note|라이브\s*노트|final\s*review|최종\s*검토|승인|override/i.test(label)) {
    return '업무 상세';
  }
  return label;
}

function humanStatus(status) {
  const map = {
    completed: '완료',
    cancelled: '정리됨',
    planned: '계획됨',
    in_progress: '진행 중',
    dispatch_blocked: '전송 보류',
    dispatch_failed: '전송 실패',
    waiting_verification: '검토 대기',
    queued: '대기열',
    skipped: 'PM 판단 생략',
    configured: '준비됨',
    online: '온라인',
    dispatched: '전송됨',
    worker_missing: '워커 없음',
    needs_config: '설정 필요',
    rate_limited: '세션 제한',
    results_received: '결과 도착',
    partial_results: '부분 결과 도착',
    partially_dispatched: '부분 전송',
    gate_hold: '게이트 보류',
    entry_hold: '진입 보류',
    needs_pm_review: 'PM 검토 필요',
  };
  return map[status] || status;
}

function taskSortWeight(task) {
  const status = task.status;
  if (['dispatch_blocked', 'dispatch_failed', 'blocked', 'needs_pm_review'].includes(status)) return 1;
  if (['waiting_verification'].includes(status)) return 2;
  if (['queued', 'planned', 'results_received', 'partial_results', 'partially_dispatched', 'dispatched'].includes(status)) return 3;
  if (['completed'].includes(status)) return 5;
  if (['cancelled'].includes(status)) return 6;
  return 4;
}

function taskGroupKey(task) {
  if (['dispatch_blocked', 'dispatch_failed', 'blocked', 'waiting_verification', 'needs_pm_review'].includes(task.status)) return 'attention';
  if (['completed', 'cancelled'].includes(task.status)) return 'done';
  return 'active';
}

function taskTone(status) {
  if (['dispatch_blocked', 'dispatch_failed', 'blocked'].includes(status)) return 'status-blocked';
  if (status === 'waiting_verification') return 'status-waiting';
  if (status === 'completed') return 'status-completed';
  if (status === 'cancelled') return 'status-cancelled';
  return 'status-active';
}

function renderStageChips(task, compact = false) {
  const root = el('div', 'stage-track');
  const stages = task.stages || [];
  stages.forEach((stage, index) => {
    const status = stage.status || 'planned';
    const node = el('div', `stage-node stage-${status}`);
    const marker = status === 'completed' ? '✓' : status === 'skipped' ? '–' : status === 'in_progress' ? '•' : status === 'blocked' ? '!' : (status === 'gate_hold' || status === 'entry_hold') ? '⏸' : String(index + 1);
    node.append(el('div', 'stage-node-marker', marker));
    const copy = el('div', 'stage-node-copy');
    copy.append(el('div', 'stage-node-label', stage.label));
    copy.append(el('div', 'stage-node-status', humanStatus(status)));
    if (!compact && stage.derived_task_id) copy.append(el('div', 'stage-node-id', stage.derived_task_id));
    if (!compact && stage.gate && stage.gate.decision) {
      const g = stage.gate;
      const gwrap = el('div', `stage-gate gate-${g.decision}`);
      const gLabel = { proceed: '게이트 통과', revise: '재작업 요청', hold: '보류', pending: '심사 대기' }[g.decision] || g.decision;
      gwrap.append(el('span', 'stage-gate-badge', gLabel));
      if (g.reason) gwrap.append(el('span', 'stage-gate-reason', g.reason));
      copy.append(gwrap);
    }

    if (!compact && stage.entry_gate && stage.entry_gate.decision) {
      const eg = stage.entry_gate;
      const cls = eg.decision === 'skip_research' ? 'revise' : eg.decision === 'hold' ? 'hold' : eg.decision === 'pending' ? 'pending' : 'proceed';
      const ewrap = el('div', `stage-gate gate-${cls}`);
      const eLabel = { proceed: '진입: 진행', skip_research: '진입: research 생략', hold: '진입: 보류', pending: '진입: 대기' }[eg.decision] || eg.decision;
      ewrap.append(el('span', 'stage-gate-badge', eLabel));
      if (eg.reason) ewrap.append(el('span', 'stage-gate-reason', eg.reason));
      copy.append(ewrap);
    }

    node.append(copy);
    root.append(node);
  });
  if (!stages.length) root.append(el('div', 'empty', '파이프라인 미정'));
  return root;
}

const RESULT_WORKER_ORDER = {
  'researcher-co': 1, 'researcher_agent': 1, 'HermesResearcher': 1,
  'writer-co': 2,
  'verify-co': 3, 'HermesVerifier': 3,
  'claude-code': 4, 'openclaw': 4,
};

function parseResultFileName(name) {
  const dot = name.lastIndexOf('.');
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
  const stem = dot >= 0 ? name.slice(0, dot) : name;
  const parts = stem.split('__');
  if (parts.length < 2) return null;
  return {
    name,
    ext,
    stagePart: parts[0],
    worker: parts[1],
    extra: parts.slice(2).join('__'),
  };
}

function stageLabelFromPart(stagePart, taskId) {
  let s = stagePart;
  if (taskId && s.startsWith(taskId)) s = s.slice(taskId.length);
  s = s.replace(/^-/, '');
  const map = { writing: '초안', verify: '검토', verification: '검토', final: '최종', final_write: '최종' };
  return map[s] || '';
}

function resultFileGlyph(ext) {
  if (ext === 'html') return '🌐';
  if (ext === 'md') return '📄';
  return '📎';
}

function renderWorkerResults(task) {
  const files = (task.result_files || [])
    .map((f) => ({ ...f, parsed: parseResultFileName(f.name) }))
    .filter((f) => f.parsed && ['md', 'html'].includes(f.parsed.ext));
  if (!files.length) return null;

  const groups = new Map();
  files.forEach((f) => {
    const worker = f.parsed.worker;
    if (!groups.has(worker)) groups.set(worker, []);
    groups.get(worker).push(f);
  });

  const wrap = el('div', 'result-file-groups');
  wrap.append(el('div', 'result-file-caption', '에이전트별 결과 파일'));

  const orderedWorkers = [...groups.keys()].sort(
    (a, b) => (RESULT_WORKER_ORDER[a] || 9) - (RESULT_WORKER_ORDER[b] || 9)
  );

  orderedWorkers.forEach((worker) => {
    const row = el('div', 'result-file-row');
    row.append(el('div', 'result-file-worker', worker));
    const chips = el('div', 'result-file-chips');
    groups.get(worker)
      .sort((a, b) => parseTime(a.modified_at) - parseTime(b.modified_at))
      .forEach((f) => {
        const stage = stageLabelFromPart(f.parsed.stagePart, task.task_id);
        const glyph = resultFileGlyph(f.parsed.ext);
        let label;
        if (f.parsed.ext === 'html') {
          label = f.parsed.extra || 'HTML';
        } else {
          label = stage ? `${stage} · ${f.parsed.ext}` : f.parsed.ext;
        }
        const chip = el('button', `result-file-chip ext-${f.parsed.ext} clickable`, `${glyph} ${label}`);
        chip.type = 'button';
        chip.title = `${f.name}\n${f.modified_at}\n클릭하면 새 창에서 자세히 봅니다`;
        chip.addEventListener('click', () => openDetail('results', f.name));
        chips.append(chip);
      });
    row.append(chips);
    wrap.append(row);
  });

  return wrap;
}

function fallbackProjection(task) {
  const status = task.status;
  const group = ['completed', 'cancelled'].includes(status) ? 'done' : ['blocked', 'dispatch_blocked', 'dispatch_failed'].includes(status) ? 'blocked' : 'unknown';
  const artifacts = task.result_files?.length || task.verification_files?.length;
  return {
    work_group: group,
    decision_queue_item: artifacts ? { kind: 'reviewable', question: '검토 가능한 파일이 있습니다', scope: 'unknown', primary_action: '산출물 검토' } : null,
    artifact_summary: { state: task.result_files?.length ? 'available' : 'none', items: task.result_files || [] },
    final_deliverable: { state: 'unavailable', reason_code: 'projection_missing', label: '최종 결과물 확인 불가', artifact: null, candidates: [], limitations: ['projection_missing'] },
    verification_summary: { state: task.verification_files?.length ? 'available_unstructured' : 'not_run', items: task.verification_files || [] },
    authority_summary: { status: 'history-unavailable' },
    data_quality: [{ kind: 'missing', field: 'dashboard_projection' }],
  };
}

function createDecisionQueueItem(task, item) {
  const row = el('article', `decision-queue-item queue-${item.kind || 'unknown'}`);
  const copy = el('div', 'decision-queue-copy');
  copy.append(el('div', 'decision-queue-question', item.question || '확인할 근거가 있습니다'));
  copy.append(el('div', 'decision-queue-task', task.title || task.task_id || '제목 없음'));
  const evidence = [];
  if (item.scope) evidence.push(`범위: ${item.scope}`);
  if (item.reason) evidence.push(`이유: ${item.reason}`);
  const projection = task.dashboard_projection || fallbackProjection(task);
  const artifact = projection.artifact_summary;
  if (artifact?.latest?.name) evidence.push(`산출물: ${artifact.latest.name}`);
  else if (artifact?.state === 'ambiguous') evidence.push('산출물: 후보 여러 개');
  const verification = projection.verification_summary;
  if (verification?.state === 'not_run') evidence.push('검증: 미실행');
  else if (verification?.state) evidence.push('검증 근거 있음');
  if (evidence.length) copy.append(el('div', 'decision-queue-evidence', evidence.join(' · ')));
  const quality = (projection.data_quality || []).slice(0, 2);
  if (quality.length) copy.append(el('div', 'data-quality-note', quality.map(dataQualityLabel).join(' · ')));
  row.append(copy);
  const action = el('button', 'mini-btn decision-queue-action', singlePrimaryAction(item));
  action.type = 'button';
  action.addEventListener('click', () => {
    openTaskDetail(task, action);
  });
  row.append(action);
  return row;
}

function renderMissionControl(summary, tasks = []) {
  const root = document.getElementById('missionControlCounts');
  if (!root) return;
  root.innerHTML = '';
  const counts = summary?.counts || {};
  [['decision_needed', '판단 필요'], ['active', '진행 중'], ['reviewable', '검토 가능'], ['blocked', '막힘'], ['unknown', '확인 불가']].forEach(([key, label]) => {
    const item = el('div', `mission-count mission-count-${key}`);
    item.append(el('strong', 'mission-count-value', String(counts[key] ?? 0)));
    item.append(el('span', 'mission-count-label', label));
    root.append(item);
  });
}

function renderDecisionQueue(tasks) {
  const root = document.getElementById('decisionQueueList');
  if (!root) return;
  root.innerHTML = '';
  const queue = (tasks || []).map((task) => ({ task, item: task.dashboard_projection?.decision_queue_item || fallbackProjection(task).decision_queue_item }))
    .filter(({ item }) => item)
    .sort((a, b) => ({ active_hold: 1, final_review: 2, reviewable: 3 }[a.item.kind] || 9) - ({ active_hold: 1, final_review: 2, reviewable: 3 }[b.item.kind] || 9));
  if (!queue.length) {
    root.append(el('div', 'empty decision-queue-empty', '지금 확인이 필요한 결정 항목이 없습니다. 새로운 근거가 도착하면 여기에 표시됩니다.'));
    return;
  }
  queue.forEach(({ task, item }) => root.append(createDecisionQueueItem(task, item)));
}

function renderReviewableArtifacts(tasks) {
  const root = document.getElementById('reviewableArtifactsList');
  if (!root) return;
  root.innerHTML = '';
  const items = [];
  (tasks || []).forEach((task) => {
    const projection = task.dashboard_projection || fallbackProjection(task);
    (projection.artifact_summary?.items || []).forEach((file) => items.push({ task, file, kind: '결과' }));
    (projection.verification_summary?.items || []).forEach((file) => items.push({ task, file, kind: '검증' }));
  });
  if (!items.length) { root.append(el('div', 'empty', '현재 검토 가능한 산출물이 없습니다.')); return; }
  items.slice(0, 12).forEach(({ task, file, kind }) => {
    const row = el('button', 'item artifact-reference clickable');
    row.type = 'button';
    const name = typeof file === 'string' ? file : file?.name;
    row.append(el('div', 'item-title', `${kind} · ${name || '이름 없음'}`));
    row.append(el('div', 'item-meta', task.title || task.task_id || '업무 정보 없음'));
    row.append(el('div', 'item-preview', '현재 응답에서 확인된 읽기 전용 근거'));
    row.addEventListener('click', () => openTaskDetail(task, row));
    root.append(row);
  });
}

function renderTaskSummary(tasks) {
  const root = document.getElementById('taskSummary');
  const blocked = tasks.filter((task) => ['dispatch_blocked', 'dispatch_failed', 'blocked'].includes(task.status)).length;
  const review = tasks.filter((task) => task.status === 'waiting_verification').length;
  const active = tasks.filter((task) => !['completed', 'cancelled'].includes(task.status)).length;
  root.textContent = `활성 ${active} · 막힘 ${blocked} · 검토 대기 ${review}`;
}

const expandedTasks = new Set();
const liveNoteDrafts = {};

function renderSeedWorkflow(task) {
  const wrap = el('div', 'seed-workflow');
  const interview = task.interview;
  const seed = task.seed;
  const label = el('div', 'seed-workflow-label', 'Ouroboros 방식 · Interview → Seed');
  wrap.append(label);

  const state = el('div', 'seed-workflow-state');
  state.append(el('span', `badge ${interview?.status === 'completed' ? 'ok' : 'warn'}`, interview ? `Interview: ${humanStatus(interview.status)}` : 'Interview: 미기록'));
  state.append(el('span', `badge ${seed?.status === 'approved' ? 'ok' : 'warn'}`, seed ? `Seed v${seed.version}: ${seed.status === 'approved' ? '승인됨' : '승인 대기'}` : 'Seed: 미작성'));
  wrap.append(state);

  const actions = el('div', 'seed-workflow-actions');
  if (!interview) {
    const interviewBtn = el('button', 'mini-btn subtle-btn', 'Interview 기록');
    interviewBtn.type = 'button';
    interviewBtn.addEventListener('click', () => createInterview(task.task_id, interviewBtn));
    actions.append(interviewBtn);
  }
  if (!seed || seed.status !== 'approved') {
    const draftBtn = el('button', 'mini-btn subtle-btn', seed ? '새 Seed 버전' : 'Seed 초안');
    draftBtn.type = 'button';
    draftBtn.addEventListener('click', () => createSeed(task.task_id, draftBtn));
    actions.append(draftBtn);
  }
  if (seed && seed.status === 'awaiting_approval') {
    const approveBtn = el('button', 'mini-btn', 'Seed 승인');
    approveBtn.type = 'button';
    approveBtn.addEventListener('click', () => approveSeed(task.task_id, approveBtn));
    actions.append(approveBtn);
  }
  if (actions.childNodes.length) wrap.append(actions);
  return wrap;
}

function taskProjection(task) {
  return task.dashboard_projection || fallbackProjection(task);
}

function stageCounts(task) {
  const stages = task?.stages || [];
  return {
    completed: stages.filter((stage) => stage.status === 'completed').length,
    skipped: stages.filter((stage) => stage.status === 'skipped').length,
    total: stages.length,
  };
}

function taskProgressSummary(task) {
  const stages = task.stages || [];
  if (!stages.length) return '진행 단계 확인 불가';
  const counts = stageCounts(task);
  const completed = counts.completed;
  const skipped = counts.skipped;
  const current = stages.find((stage) => ['in_progress', 'gate_hold', 'entry_hold'].includes(stage.status));
  const location = current ? `${stageDisplayLabel(current)} 진행 중` : '현재 단계 확인 불가';
  return `${location} · 완료 ${completed}/${stages.length} · 생략 ${skipped}`;
}

function currentStageForTask(task) {
  return (task.stages || []).find((stage) => ['in_progress', 'gate_hold', 'entry_hold'].includes(stage.status)) || null;
}

function stageDisplayLabel(stage) {
  const labels = { research: '리서치', writing: '작성', verification: '검증', final_write: '최종 작성' };
  return labels[stage?.id] || stage?.label || stage?.id || '단계 확인 불가';
}

function resultBundleKey(file) {
  const parsed = parseResultFileName(file?.name || '');
  if (!parsed) return null;
  return `${parsed.stagePart}__${parsed.worker}`;
}

function resultBundles(task) {
  const groups = new Map();
  (task.result_files || []).forEach((file) => {
    const key = resultBundleKey(file);
    if (!key) return;
    if (!groups.has(key)) groups.set(key, { key, worker: file.name.split('__')[1]?.split('.')[0] || 'unknown', files: [] });
    groups.get(key).files.push(file);
  });
  return [...groups.values()];
}

function stageResultBundles(task, stage) {
  if (!stage) return [];
  return resultBundles(task).filter((bundle) => bundle.files.some((file) => {
    const parsed = parseResultFileName(file.name);
    return parsed && (parsed.stagePart === stage.id || parsed.stagePart === `${task.task_id}-${stage.id}` || (stage.id === 'research' && parsed.stagePart === task.task_id));
  }));
}

function dispatchStateFor(task, worker) {
  const dispatches = task.dispatches || {};
  const match = Object.entries(dispatches).find(([name]) => name.toLowerCase() === String(worker).toLowerCase());
  return match ? match[1] : null;
}

function agentExecutionState(task, stage, worker) {
  const projected = taskProjection(task).progress?.agent_states?.[stage?.id];
  if (projected && projected[worker]) return projected[worker];
  const bundle = stageResultBundles(task, stage).find((item) => item.worker.toLowerCase() === String(worker).toLowerCase());
  const dispatch = dispatchStateFor(task, worker);
  const metadataStatus = bundle?.files.map((file) => file.status || file.metadata?.status).find(Boolean);
  if (['failed', 'blocked'].includes(metadataStatus) || ['dispatch_failed', 'dispatch_blocked', 'failed', 'blocked'].includes(dispatch)) return 'failed_or_blocked';
  if (metadataStatus === 'completed' || bundle) return 'result_received';
  if (['dispatched', 'dispatch_confirmed'].includes(dispatch)) return 'dispatch_confirmed';
  if (dispatch) return 'unknown';
  return 'not_dispatched';
}

function agentExecutionLabel(state) {
  return {
    not_dispatched: '미전송',
    dispatch_confirmed: '전송 확인 · 결과 대기',
    result_received: '결과 도착',
    failed_or_blocked: '실패·차단',
    unknown: '상태 확인 불가',
  }[state] || '상태 확인 불가';
}

function agentExecutionLimitation(task, stage, worker, state) {
  const limitation = taskProjection(task).progress?.agent_states?.[stage?.id]?._limitations?.[worker];
  if (limitation) return limitation;
  if (state === 'dispatch_confirmed') return '실행·결과 미확인';
  if (state === 'result_received') return '근거 품질 미분류';
  return '추가 확인 필요';
}

function stageArtifactState(task, stage) {
  const projected = taskProjection(task).progress?.agent_states?.[stage?.id];
  if (projected?._maturity) return projected._maturity;
  const received = stageResultBundles(task, stage).length;
  const expected = (stage?.agents || []).length;
  if (!received) return 'none';
  if (expected && received < expected) return 'partial_received';
  return 'reviewable';
}

function taskAgentSummary(task) {
  const current = currentStageForTask(task);
  if (!current) return '에이전트 계획 확인 불가';
  const stages = task.stages || [];
  const currentIndex = stages.indexOf(current);
  const agents = current.agents || [];
  const labels = agents.map((agent) => `${agent} · ${agentExecutionLabel(agentExecutionState(task, current, agent))}`);
  const preceding = stages.slice(0, currentIndex).reverse().find((stage) => stage.status === 'completed');
  const precedingText = preceding ? `${stageDisplayLabel(preceding)} 완료 · ${stageArtifactState(task, preceding) === 'reviewable' ? '결과 도착' : '결과 확인 필요'}` : '';
  return [precedingText, labels.length ? labels.join(' · ') : '에이전트 계획 확인 불가'].filter(Boolean).join(' · ');
}

function taskArtifactSummary(task) {
  const projection = taskProjection(task);
  const progress = projection.progress;
  if (progress) {
    const stages = task.stages || [];
    const current = currentStageForTask(task);
    const currentState = current ? progress.agent_states?.[current.id]?._maturity : null;
    const preceding = current && stages.slice(0, stages.indexOf(current)).reverse().find((stage) => stage.status === 'completed');
    const parts = [];
    if (preceding) parts.push(`${stageDisplayLabel(preceding)} ${progress.agent_states?.[preceding.id]?._maturity === 'reviewable' ? '결과 도착' : '결과 확인 필요'}`);
    if (current) parts.push(`${stageDisplayLabel(current)} ${currentState === 'none' ? '결과 없음' : currentState === 'partial_received' ? '결과 일부 도착' : currentState === 'reviewable' ? '결과 도착' : '범위 확인 필요'}`);
    const verification = progress.verification_state === 'not_run' ? '검증 미실행' : progress.verification_state === 'verified' ? '검증 완료' : '검증 근거 확인 필요';
    if (parts.length || verification) return `${parts.join(' · ')}${parts.length ? ' · ' : ''}${verification}`;
  }
  const artifact = projection.artifact_summary || {};
  if (artifact.state === 'ambiguous') return '산출물 후보 여러 개 · 범위 확인 필요';
  if (!artifact.items?.length && !task.result_files?.length) return '아직 확인 가능한 산출물 없음';
  return artifact.state === 'available' ? '산출물 도착 · 검토 필요' : '산출물 범위 확인 필요';
}

function taskTrustSummary(task) {
  const projection = taskProjection(task);
  const quality = (projection.data_quality || []).slice(0, 2).map(dataQualityLabel);
  const verification = projection.verification_summary;
  if (quality.length) return quality.join(' · ');
  if (verification?.state === 'not_run') return '검증 미실행';
  if (verification?.state) return '검증 근거 있음';
  return '추가 확인 필요';
}

function createTaskCard(task) {
  const card = el('article', `task-card ${taskTone(task.status)}`);

  const isDone = ['completed', 'cancelled'].includes(task.status);
  const outcome = el('div', 'task-outcome');
  outcome.append(el('div', 'task-title', task.title || task.task_id || '제목 없음'));
  outcome.append(el('div', 'task-why', isDone ? agentsUsedSummary(task) : (task.objective || '상세 목표 없음')));
  outcome.append(el('div', 'task-submeta', `${task.updated_at || task.created_at || '시간 미상'}`));
  card.append(outcome);

  const progress = el('div', 'task-card-fact task-progress');
  progress.append(el('span', 'task-fact-label', '진행'));
  progress.append(el('span', 'task-fact-value', taskProgressSummary(task)));
  card.append(progress);
  const agent = el('div', 'task-card-fact task-agent-progress');
  agent.append(el('span', 'task-fact-label', '에이전트 진행'));
  agent.append(el('span', 'task-fact-value', taskAgentSummary(task)));
  card.append(agent);
  const pipeline = pipelineShapePresentation(task);
  if (pipeline.label) card.append(el('div', 'task-pipeline-label', `파이프라인 · ${pipeline.label}`));
  const artifact = el('div', 'task-card-fact task-artifact');
  artifact.append(el('span', 'task-fact-label', '산출물'));
  artifact.append(el('span', 'task-fact-value', taskArtifactSummary(task)));
  card.append(artifact);
  const trust = el('div', 'task-card-fact task-trust');
  trust.append(el('span', 'task-fact-label', '신뢰'));
  trust.append(el('span', 'task-fact-value', taskTrustSummary(task)));
  card.append(trust);
  const limits = el('div', 'task-card-fact task-limits');
  limits.append(el('span', 'task-fact-label', '근거/한계'));
  limits.append(el('span', 'task-fact-value', (taskProjection(task).data_quality || []).slice(0, 2).map(dataQualityLabel).join(' · ') || '근거 품질 미분류'));
  card.append(limits);
  const authority = authorityPresentation(taskProjection(task));
  card.append(el('div', `data-authority ${authority.className}`, `권한 · ${authority.label}`));

  const compactHideGateDetails = taskProjection(task).compact_hide_gate_details ?? isDone;
  const extra = el('div', 'task-extra');
  extra.append(renderStageChips(task, compactHideGateDetails));
  extra.append(el('div', 'task-agent-summary', taskAgentSummary(task)));
  extra.append(renderSeedWorkflow(task));
  if (task.pm_final_review && task.pm_final_review.verdict) {
    const fr = task.pm_final_review;
    const vlabel = { meets: '충족', partial: '대체로 충족', not_meets: '미충족' }[fr.verdict] || fr.verdict;
    const frBox = el('div', `final-review fr-${fr.verdict}`);
    frBox.append(el('span', 'final-review-badge', `PM 총평: ${vlabel}`));
    if (fr.comment) frBox.append(el('span', 'final-review-comment', fr.comment));
    if (fr.gaps) frBox.append(el('div', 'final-review-gaps', `보완: ${fr.gaps}`));
    extra.append(frBox);

  }

  const workers = el('div', 'task-worker-list');
  (task.assigned_workers || []).forEach((worker) => workers.append(el('div', 'chip', worker)));
  if (!(task.assigned_workers || []).length) workers.append(el('div', 'chip', '할당 에이전트 미정'));
  extra.append(workers);
  if ((task.input_files || []).length) {
    const inputsRow = el('div', 'task-worker-list');
    task.input_files.forEach((n) => inputsRow.append(el('div', 'chip', '📎 ' + n)));
    extra.append(inputsRow);
  }

  const links = el('div', 'task-links');
  if (task.latest_result) links.append(el('div', 'task-linkline', `도착한 결과: ${task.latest_result}`));
  if (task.latest_verification) links.append(el('div', 'task-linkline', `검토 메모: ${task.latest_verification}`));
  if (task.pipeline && task.pipeline.current_stage) {
    links.append(el('div', 'task-linkline', `현재 단계: ${task.pipeline.current_stage} · 완료 ${task.pipeline.completed_stages}/${task.pipeline.stage_count}`));
  }
  const derived = (task.stages || []).filter((stage) => stage.derived_task_id);
  derived.forEach((stage) => {
    links.append(el('div', 'task-linkline', `${stage.label} 파생 작업: ${stage.derived_task_id}`));
  });
  if (task.dispatches && Object.keys(task.dispatches).length) {
    links.append(el('div', 'task-linkline', `전송 흐름: ${Object.entries(task.dispatches).map(([k, v]) => `${k}=${v}`).join(' · ')}`));
  }
  links.append(el('div', 'task-linkline', `raw task: ${task.status || '확인 불가'}`));
  if (links.childNodes.length) extra.append(links);

  const workerResults = renderWorkerResults(task);
  if (workerResults) extra.append(workerResults);


  const expanded = expandedTasks.has(task.task_id);
  extra.dataset.compactHideGateDetails = compactHideGateDetails ? 'true' : 'false';
  extra.classList.toggle('is-collapsed', !expanded);
  card.append(extra);

  const actionRow = el('div', 'task-actions task-card-primary-action');
  const toggleBtn = el('button', 'mini-btn subtle-btn', expanded ? '간단히 보기' : '상세 보기');
  toggleBtn.type = 'button';
  toggleBtn.addEventListener('click', () => {
    if (expandedTasks.has(task.task_id)) expandedTasks.delete(task.task_id);
    else expandedTasks.add(task.task_id);
    const nowOpen = expandedTasks.has(task.task_id);
    extra.classList.toggle('is-collapsed', !nowOpen);
    toggleBtn.textContent = nowOpen ? '간단히 보기' : '상세 보기';
  });
  const taskDetailBtn = el('button', 'mini-btn', cardDetailActionLabel(task));
  taskDetailBtn.type = 'button';
  taskDetailBtn.addEventListener('click', () => openTaskDetail(task, taskDetailBtn));
  actionRow.append(taskDetailBtn, toggleBtn);
  card.append(actionRow);

  return card;
}

function renderTasks(tasks) {
  const root = document.getElementById('taskBoard');
  root.innerHTML = '';
  renderTaskSummary(tasks);

  const columns = {
    attention: { title: '먼저 볼 일', hint: '지금 개입하거나 검토해야 하는 흐름', items: [] },
    active: { title: '지금 흐르는 일', hint: '이미 진행 중이거나 곧 투입할 수 있는 흐름', items: [] },
    done: { title: '정리된 일', hint: '완료되었거나 테스트용으로 닫은 흐름', items: [] },
  };

  [...tasks].sort((a, b) => taskSortWeight(a) - taskSortWeight(b)).forEach((task) => {
    columns[taskGroupKey(task)].items.push(task);
  });

  Object.values(columns).forEach((column) => {
    const section = el('section', 'task-column');
    section.append(el('div', 'task-column-title', column.title));
    section.append(el('div', 'task-column-hint', column.hint));
    const list = el('div', 'task-column-list');
    if (!column.items.length) {
      list.append(el('div', 'empty', '현재 항목이 없습니다.'));
    } else {
      column.items.forEach((task) => list.append(createTaskCard(task)));
    }
    section.append(list);
    root.append(section);
  });
}

function parseTime(value) {
  const t = Date.parse(value || '');
  return Number.isNaN(t) ? 0 : t;
}

function auditSourceLabel(source) {
  return {
    hermes_gate: '게이트 근거',
    entry_gate: '진입 근거',
    pm_final_review: '최종 검토 근거',
    final_review_override: '검토 재확인 근거',
    pm_live_notes: '비결정 맥락',
  }[source] || '현재 raw 근거';
}

function renderRecentFlow(tasks) {
  const root = document.getElementById('recentFlow');
  root.innerHTML = '';
  const merged = [];
  (tasks || []).forEach((task) => {
    const projection = taskProjection(task);
    (projection.audit_rows || []).forEach((audit, index) => {
      if (!audit || typeof audit !== 'object') return;
      merged.push({ task, audit, index });
    });
  });
  if (!merged.length) {
    root.append(el('div', 'empty', '최근 흐름이 아직 없습니다.'));
    return;
  }

  merged.slice(-12).reverse().forEach(({ task, audit }) => {
    const source = auditSourceLabel(audit.source_mechanism);
    const row = el('article', 'timeline-item kind-current-evidence');
    row.append(el('div', 'timeline-mark'));

    const body = el('div', 'timeline-body');
    body.append(el('div', 'timeline-meta', `${source} · ${audit.scope || '범위 확인 불가'}`));
    body.append(el('div', 'timeline-title', task.title || task.task_id || '제목 없음'));
    const value = audit.source_value ?? audit.reason ?? '값 확인 불가';
    body.append(el('div', 'timeline-preview', String(value)));
    row.append(body);
    root.append(row);
  });
}

function renderSimpleList(rootId, items) {
  const root = document.getElementById(rootId);
  root.innerHTML = '';
  if (!items.length) {
    root.append(el('div', 'empty', '아직 항목이 없습니다.'));
    return;
  }
  const dir = rootId === 'digestsList' ? 'digests' : 'results';
  items.slice(0, 5).forEach((item) => {
    const card = el('div', 'item clickable');
    card.append(el('div', 'item-title', item.name));
    card.append(el('div', 'item-meta', item.modified_at));
    card.append(el('div', 'item-preview', shortPreview(item.preview)));
    card.title = '클릭하면 새 창에서 자세히 봅니다';
    card.addEventListener('click', () => openDetail(dir, item.name));
    root.append(card);
  });
}

function artifactKindLabel(kind) {
  if (kind === 'review') return '검토';
  if (kind === 'digest') return '기록';
  return '결과';
}

function currentDraftFromForm() {
  const form = document.getElementById('taskForm');
  return {
    title: form.elements.title.value,
    objective: form.elements.objective.value,
    execution_mode: form.elements.execution_mode.value,
    reviewer: form.elements.reviewer.value,
    assigned_workers: form.elements.assigned_workers.value,
    context: form.elements.context.value,
    constraints: form.elements.constraints.value,
    deliverable: form.elements.deliverable.value,
  };
}

function applyDraftToForm(draft) {
  const form = document.getElementById('taskForm');
  form.elements.title.value = draft.title || '';
  form.elements.objective.value = draft.objective || '';
  form.elements.execution_mode.value = draft.execution_mode || 'research-pipeline';
  form.elements.reviewer.value = draft.reviewer || 'HermesVerifier';
  form.elements.assigned_workers.value = Array.isArray(draft.assigned_workers)
    ? draft.assigned_workers.join(', ')
    : (draft.assigned_workers || '');
  form.elements.context.value = draft.context || '';
  form.elements.constraints.value = draft.constraints || '';
  form.elements.deliverable.value = draft.deliverable || '';
  renderPmDraftPanel();
}

function renderPmDraftPanel() {
  const form = document.getElementById('taskForm');
  const titleNode = document.getElementById('pmDraftTitle');
  const objectiveNode = document.getElementById('pmDraftObjective');
  if (!form || !titleNode || !objectiveNode) return;

  const title = (form.elements.title.value || '').trim();
  const objective = (form.elements.objective.value || '').trim();

  titleNode.textContent = title || '아직 PM이 제목을 정리하지 않았습니다.';
  titleNode.classList.toggle('empty', !title);

  objectiveNode.textContent = objective || '대화를 시작하면 PM이 결과를 정리합니다.';
  objectiveNode.classList.toggle('empty', !objective);
}

function appendArtifactToContext(item) {
  const form = document.getElementById('taskForm');
  const context = form.elements.context;
  if (!selectedArtifacts.has(item.path)) {
    selectedArtifacts.set(item.path, item);
    const prefix = context.value.trim() ? '\n' : '';
    context.value += `${prefix}[참고 파일] ${item.name}\n경로: ${item.path}\n`;
  }
  renderPmDialogue();
}

function renderArtifactReferences() {
  return;
}

function renderPmChecklist() {
  const root = document.getElementById('pmChecklist');
  root.innerHTML = '';
  const items = [
    ['제목', pmReviewState.checklist?.title],
    ['결과', pmReviewState.checklist?.objective],
    ['맥락', pmReviewState.checklist?.context],
    ['산출물 형태', pmReviewState.checklist?.deliverable],
    ['에이전트', pmReviewState.checklist?.assigned_workers],
  ];
  items.forEach(([label, ok]) => {
    root.append(el('div', `pm-check ${ok ? 'ok' : 'pending'}`, `${ok ? '●' : '○'} ${label}`));
  });
}

function renderPmDialogue() {
  const root = document.getElementById('pmDialogue');
  root.innerHTML = '';
  pmConversation.forEach((message) => {
    const bubble = el('div', `pm-bubble ${message.role}`);
    bubble.append(el('div', 'pm-bubble-role', message.role === 'pm' ? 'HermesPM' : 'Raphael'));
    bubble.append(el('div', 'pm-bubble-text', message.text));
    root.append(bubble);
  });
  renderPmChecklist();
  renderPmDraftPanel();
}

async function sendPmChat() {
  const input = document.getElementById('pmChatInput');
  const status = document.getElementById('pmChatStatus');
  const sendBtn = document.getElementById('sendPmChatBtn');
  const message = input.value.trim();
  if (!message || sendBtn.disabled) return;

  pmConversation.push({ role: 'user', text: message });
  renderPmDialogue();
  sendBtn.disabled = true;
  status.textContent = 'HermesPM이 답변을 작성 중입니다... (실제 LLM 호출, 수십 초 걸릴 수 있어요)';

  try {
    const res = await fetch('/api/pm-brief-assist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, draft: currentDraftFromForm(), conversation: pmConversation }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'PM 검토 실패');

    applyDraftToForm(payload.draft || {});
    pmReviewState = {
      ready: !!payload.ready,
      questions: payload.questions || [],
      checklist: payload.checklist || {},
      interpretation: (payload.interpretation || '').trim(),
    };
    updatePmInterpretation(pmReviewState.interpretation);
    pmConversation.push({ role: 'pm', text: payload.reply || '초안을 반영했습니다.' });
    input.value = '';
    status.textContent = payload.ready
      ? 'PM 검토 완료 · 바로 진행 가능'
      : 'PM이 추가 확인이 필요하다고 판단했습니다.';
    renderPmDialogue();
  } catch (err) {
    status.textContent = `실패: ${err.message}`;
  } finally {
    sendBtn.disabled = false;
  }
}

function setModalOpen(open) {
  const modal = document.getElementById('briefModal');
  if (open) pushModal('briefModal');
  else popModal('briefModal');
  if (open) {
    renderPmDialogue();
    renderArtifactReferences();
    setTimeout(() => document.querySelector('#pmChatInput')?.focus(), 0);
  }
}

async function finalReviewOverride(taskId, action, button) {
  const siblings = button.parentElement ? Array.from(button.parentElement.querySelectorAll('button')) : [button];
  siblings.forEach((b) => (b.disabled = true));
  button.textContent = action === 'accept' ? '승인 중...' : '재작업 요청 중...';
  try {
    const res = await fetch('/api/final-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, action }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'final review override failed');
    await loadDashboard();
  } catch (err) {
    alert(`총평 처리 실패: ${err.message}`);
    siblings.forEach((b) => (b.disabled = false));
  }
}

async function gateOverride(taskId, stageId, action, button) {
  const original = button.textContent;
  const siblings = button.parentElement ? Array.from(button.parentElement.querySelectorAll('button')) : [button];
  siblings.forEach((b) => (b.disabled = true));
  button.textContent = action === 'approve' ? '승인 중...' : '요청 중...';
  try {
    const res = await fetch('/api/gate-override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, stage_id: stageId, action }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'gate override failed');
    await loadDashboard();
  } catch (err) {
    alert(`게이트 처리 실패: ${err.message}`);
    siblings.forEach((b) => (b.disabled = false));
    button.textContent = original;
  }
}

async function createInterview(taskId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '기록 중...';
  try {
    const res = await fetch('/api/interview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'Interview 기록 실패');
    await loadDashboard();
  } catch (err) {
    alert(`Interview 기록 실패: ${err.message}`);
    button.disabled = false;
    button.textContent = original;
  }
}

async function createSeed(taskId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '작성 중...';
  try {
    const res = await fetch('/api/seed', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, action: 'draft' }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'Seed 초안 작성 실패');
    await loadDashboard();
  } catch (err) {
    alert(`Seed 초안 작성 실패: ${err.message}`);
    button.disabled = false;
    button.textContent = original;
  }
}

async function approveSeed(taskId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '승인 중...';
  try {
    const res = await fetch('/api/seed', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, action: 'approve', approver: 'Raphael' }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'Seed 승인 실패');
    await loadDashboard();
  } catch (err) {
    alert(`Seed 승인 실패: ${err.message}`);
    button.disabled = false;
    button.textContent = original;
  }
}

async function dispatchTask(taskId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '보내는 중...';
  try {
    const res = await fetch('/api/dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'dispatch failed');
    await loadDashboard();
  } catch (err) {
    alert(`브리프 전송 실패: ${err.message}`);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function autoDispatchQueued(button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '정리 중...';
  try {
    const res = await fetch('/api/auto-dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || 'auto dispatch failed');
    await loadDashboard();
    const count = payload.auto_dispatch?.dispatched_count ?? 0;
    alert(`대기 중인 일 ${count}건을 보냈습니다.`);
  } catch (err) {
    alert(`일괄 전송 실패: ${err.message}`);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function consoleStateLabel(state) {
  return ({ result_received: '결과 도착', dispatch_confirmed: '전송 확인', failed_or_blocked: '실패·보류', not_dispatched: '준비됨', unknown: '알 수 없음' })[state] || state || '알 수 없음';
}

function consoleRowButton(label, taskId, className = 'console-row-action') {
  const button = el('button', className, label); button.type = 'button';
  const task = dashboardState.tasks.find((item) => item.task_id === taskId);
  if (task) button.addEventListener('click', () => openTaskDetail(task, button));
  else button.disabled = true;
  return button;
}

function renderConsoleSnapshot(snapshot) {
  const panes = snapshot?.panes || {};
  const pmRoot = document.getElementById('pmInstructionPaneBody');
  const agentRoot = document.getElementById('agentsPaneBody');
  const projectRoot = document.getElementById('projectsPaneBody');
  const missionRoot = document.getElementById('missionPaneBody');
  [pmRoot, agentRoot, projectRoot, missionRoot].forEach((root) => { if (root) root.replaceChildren(); });
  const pm = panes.pm_instruction || {};
  if (pmRoot) {
    const records = (pm.recent_instructions || []).slice(0, 3);
    pmRoot.append(el('div', 'console-summary-strip', `${records.length}개 지시 기록 · 자유 텍스트는 즉시 실행되지 않습니다.`));
    if (!records.length) pmRoot.append(el('p', 'empty', '표시할 지시 기록 없음'));
    records.forEach((record) => {
      const row = el('article', 'console-row instruction-row');
      row.append(el('strong', 'console-row-title', record.text || '내용 확인 불가'));
      row.append(el('span', 'console-row-meta', `${record.instruction_id || 'ID 확인 불가'} · ${record.state || '상태 확인 불가'}`));
      if (record.target_id) row.append(consoleRowButton('업무 상세', record.target_id));
      pmRoot.append(row);
    });
    const action = el('button', 'primary-btn console-composer-entry', '＋ 지시 작성'); action.type = 'button'; action.addEventListener('click', () => setModalOpen(true)); pmRoot.append(action);
  }
  const agents = panes.agents?.items || [];
  if (agentRoot) {
    if (!agents.length) agentRoot.append(el('p', 'empty', '관찰 가능한 agent 근거 없음'));
    agents.forEach((agent) => {
      const row = el('article', 'console-row agent-row');
      const states = [...(agent.results || [])].reverse();
      const state = states[0]?.state || (agent.dispatch?.[0]?.state === 'dispatched' ? 'dispatch_confirmed' : 'unknown');
      row.append(el('div', 'console-row-title', agent.name || agent.agent_id));
      row.append(el('span', `console-status-badge console-${state}`, consoleStateLabel(state)));
      const metadata = [agent.role, agent.model && `model ${agent.model}`, agent.provider && `provider ${agent.provider}`].filter(Boolean).join(' · ');
      row.append(el('span', 'console-row-meta', metadata || `현재 ${agent.active_count || 0} · 결과 ${agent.completed_count || 0} · 검토 ${agent.review_count || 0}`));
      if (agent.task_ids?.[0]) row.append(consoleRowButton('업무 상세', agent.task_ids[0]));
      agentRoot.append(row);
    });
  }
  const projects = panes.projects?.items || [];
  if (projectRoot) {
    if (!projects.length) projectRoot.append(el('p', 'empty', '명시적으로 연결된 프로젝트 없음'));
    projects.forEach((project) => {
      const row = el('article', 'console-row project-row');
      row.append(el('strong', 'console-row-title', project.name || project.project_id));
      row.append(el('span', 'console-status-badge console-project-state', project.bound ? '연결됨' : '프로젝트 미지정'));
      row.append(el('span', 'console-row-meta', `진행 ${project.active_count || 0} · 완료 ${project.done_count || 0} · 근거 ${project.latest_evidence_at || '확인 불가'}`));
      if (project.task_ids?.[0]) row.append(consoleRowButton('관련 업무', project.task_ids[0]));
      projectRoot.append(row);
    });
  }
  const mission = panes.mission_control?.items || [];
  const counts = mission.reduce((out, item) => { out[item.kind] = (out[item.kind] || 0) + 1; return out; }, {});
  const countRoot = document.getElementById('missionControlCounts');
  if (countRoot) { countRoot.replaceChildren(); [['blocker','blocker'], ['decision','decision'], ['reviewable','reviewable'], ['unknown','unknown']].forEach(([key, label]) => { const item = el('span', `mission-count mission-count-${key}`); item.append(el('strong', 'mission-count-value', String(counts[key] || 0)), el('span', 'mission-count-label', label)); countRoot.append(item); }); }
  if (missionRoot) {
    if (!mission.length) missionRoot.append(el('p', 'empty', '현재 확인할 판단 항목 없음'));
    mission.forEach((item) => {
      const row = el('article', `console-row mission-row mission-${item.kind || 'unknown'}`);
      row.append(el('span', 'console-status-badge', (item.kind || 'unknown').toUpperCase()));
      row.append(el('strong', 'console-row-title', item.question || '판단 근거 확인 필요'));
      row.append(el('span', 'console-row-meta', `${item.evidence_at || '근거 시각 확인 불가'} · ${item.limitation || 'raw 상태 읽기 전용'}`));
      if (item.target?.id) row.append(consoleRowButton('상세 근거', item.target.id));
      missionRoot.append(row);
    });
  }
  document.getElementById('consoleStatus').textContent = `${snapshot?.snapshot_id || 'snapshot 확인 불가'} · ${snapshot?.generated_at || '생성 시각 확인 불가'}`;
}

function setupConsoleLayout() {
  const grid = document.getElementById('consoleGrid'); if (!grid) return;
  const key = 'console-layout-v2:desktop'; const defaults = { left: 50, top: 46 };
  const read = () => { try { const value = JSON.parse(localStorage.getItem(key) || 'null'); return value && Number.isFinite(value.left) && Number.isFinite(value.top) ? value : defaults; } catch (_) { return defaults; } };
  const apply = (value) => { grid.style.setProperty('--console-left', `${Math.max(30, Math.min(70, value.left))}%`); grid.style.setProperty('--console-top', `${Math.max(35, Math.min(65, value.top))}%`); };
  apply(read());
  document.getElementById('resetConsoleLayoutBtn')?.addEventListener('click', () => { localStorage.removeItem(key); apply(defaults); document.getElementById('consoleStatus').textContent = '기본 레이아웃으로 초기화했습니다.'; });
  [['vertical', 'col-resize'], ['horizontal', 'row-resize']].forEach(([orientation, cursor]) => {
    const handle = document.createElement('button'); handle.type = 'button'; handle.className = `console-divider console-divider-${orientation}`; handle.setAttribute('role', 'separator'); handle.setAttribute('aria-orientation', orientation === 'vertical' ? 'vertical' : 'horizontal'); handle.setAttribute('aria-label', orientation === 'vertical' ? '콘솔 열 너비 조절' : '콘솔 행 높이 조절'); handle.tabIndex = 0; grid.append(handle);
    const move = (delta) => { const value = read(); value[orientation === 'vertical' ? 'left' : 'top'] += delta; apply(value); try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {} };
    handle.addEventListener('keydown', (event) => { if (event.key === 'Home') { event.preventDefault(); apply(defaults); } else if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) { event.preventDefault(); move((event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1) * (event.shiftKey ? 5 : 2)); } });
    let start = null; handle.addEventListener('pointerdown', (event) => { start = { x: event.clientX, y: event.clientY, value: read() }; handle.setPointerCapture(event.pointerId); document.body.style.cursor = cursor; });
    handle.addEventListener('pointermove', (event) => { if (!start) return; const delta = orientation === 'vertical' ? ((event.clientX - start.x) / Math.max(1, grid.clientWidth)) * 100 : ((event.clientY - start.y) / Math.max(1, grid.clientHeight)) * 100; const value = { ...start.value }; value[orientation === 'vertical' ? 'left' : 'top'] += delta; apply(value); });
    const end = () => { if (!start) return; try { localStorage.setItem(key, JSON.stringify(read())); } catch (_) {} start = null; document.body.style.cursor = ''; }; handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end);
  });
  const nav = document.getElementById('consoleJumpNav'); [['panePmInstruction','01 · 지시'],['paneAgents','02 · Agents'],['paneProjects','03 · Projects'],['paneMissionControl','04 · 판단']].forEach(([id,label]) => { const link = el('a', 'console-jump-link', label); link.href = `#${id}`; nav.append(link); });
}

async function loadDashboard() {
  const [overview, tasks, results, verifications, digests, capabilities, consoleSnapshot] = await Promise.all([
    getJson('/api/overview'),
    getJson('/api/tasks'),
    getJson('/api/results'),
    getJson('/api/verifications'),
    getJson('/api/digests'),
    getJson('/api/follow-up-request-capabilities'),
    getJson('/api/dashboard-console'),
  ]);

  dashboardState = { overview, tasks, results, verifications, digests };
  followUpCapabilities = capabilities || { write_enabled: false, origin_required: true };
  renderConsoleSnapshot(consoleSnapshot);
  renderMissionControl(overview.dashboard_summary, tasks || []);
  renderOperationsEvidence(overview.operations_evidence);
  renderDecisionQueue(tasks || []);
  renderReviewableArtifacts(tasks || []);
  renderTasks(tasks || []);
  renderRecentFlow(tasks || []);
  renderSimpleList('resultsList', results || []);
  renderSimpleList('digestsList', digests || []);
  renderArtifactReferences();
  renderPmDialogue();
}

async function submitTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.getElementById('formStatus');
  const title = (form.elements.title.value || '').trim();
  const objective = (form.elements.objective.value || '').trim();
  if (!title || !objective) {
    status.textContent = '먼저 PM과 대화해서 제목과 나와야 하는 결과를 정리해 주세요.';
    return;
  }
  status.textContent = '브리프 저장 중...';
  const data = Object.fromEntries(new FormData(form).entries());
  data.pm_conversation = pmConversation.slice(-40);
  data.pm_interpretation = pmReviewState.interpretation || '';
  try {
    const fileInput = document.getElementById('taskFiles');
    const files = fileInput ? [...fileInput.files] : [];
    if (files.length) {
      status.textContent = `입력 파일 업로드 중... (${files.length}개)`;
      data.input_files = [];
      for (const f of files) {
        const up = await fetch(`/api/upload-input?name=${encodeURIComponent(f.name)}`, { method: 'POST', body: f });
        const uj = await up.json();
        if (!up.ok || !uj.ok) throw new Error(uj.error || `파일 업로드 실패: ${f.name}`);
        data.input_files.push(uj.path);
      }
      status.textContent = '브리프 저장 중...';
    }
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || '작업 생성 실패');
    const taskId = payload.task.task_id;
    status.textContent = `저장 완료: ${taskId} · HermesPM이 진입을 판단합니다 (곧 자동 진행)`;
    form.reset();
    form.reviewer.value = 'HermesVerifier';
    form.execution_mode.value = 'research-pipeline';
    selectedArtifacts.clear();
    pmConversation = [{ role: 'pm', text: 'Raphael, 이번에 어떤 업무를 움직일까요?' }];
    pmReviewState = { ready: false, questions: [], checklist: {}, interpretation: '' };
    updatePmInterpretation('');
    document.getElementById('pmChatInput').value = '';
    document.getElementById('pmChatStatus').textContent = '';
    document.getElementById('advancedFields').classList.add('is-collapsed');
    document.getElementById('toggleAdvancedBtn').textContent = '세부 옵션';
    await loadDashboard();
    setTimeout(() => setModalOpen(false), 400);
  } catch (err) {
    status.textContent = `실패: ${err.message}`;
  }
}

function setupAdvancedToggle() {
  const button = document.getElementById('toggleAdvancedBtn');
  const fields = document.getElementById('advancedFields');
  button.addEventListener('click', () => {
    const collapsed = fields.classList.toggle('is-collapsed');
    button.textContent = collapsed ? '세부 옵션' : '세부 옵션 접기';
  });
}

function setupModal() {
  document.getElementById('openBriefModalBtn').addEventListener('click', () => setModalOpen(true));
  document.getElementById('closeBriefModalBtn').addEventListener('click', () => setModalOpen(false));
  document.getElementById('closeDetailBtn').addEventListener('click', closeDetail);
  document.getElementById('closeTaskDetailBtn').addEventListener('click', closeTaskDetail);
  document.addEventListener('click', (event) => {
    if (event.target?.dataset?.closeDetail === 'true') closeDetail();
    if (event.target?.dataset?.closeTaskDetail === 'true') closeTaskDetail();
  });
  document.getElementById('briefModal').addEventListener('click', (event) => {
    if (event.target?.dataset?.closeModal === 'true') setModalOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.isComposing) return;
    if (event.key === 'Tab') { trapTopModal(event); return; }
    if (event.key === 'Escape') {
      const top = topModal();
      if (top === 'detailModal') closeDetail();
      else if (top === 'taskDetailModal') closeTaskDetail();
      else if (top === 'briefModal') setModalOpen(false);
    }
  });
}

function setupConversationMirror() {
  const form = document.getElementById('taskForm');
  ['title', 'objective', 'context'].forEach((name) => {
    form.elements[name].addEventListener('input', () => renderPmDialogue());
  });
  renderPmDraftPanel();
}

function setupPmChat() {
  document.getElementById('sendPmChatBtn').addEventListener('click', sendPmChat);
  document.getElementById('pmChatInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendPmChat();
    }
  });
}

document.getElementById('taskForm').addEventListener('submit', submitTask);
document.getElementById('refreshBtn').addEventListener('click', loadDashboard);
setupAdvancedToggle();
setupModal();
setupConversationMirror();
setupPmChat();
setupConsoleLayout();
loadDashboard().catch((err) => {
  document.getElementById('formStatus').textContent = `초기 로드 실패: ${err.message}`;
});


function agentsUsedSummary(task) {
  const workers = new Set();
  (task.result_files || []).forEach((f) => {
    const parsed = parseResultFileName(f.name);
    if (parsed?.worker) workers.add(parsed.worker);
  });
  const list = workers.size
    ? [...workers].sort((x, y) => (RESULT_WORKER_ORDER[x] || 9) - (RESULT_WORKER_ORDER[y] || 9))
    : (task.assigned_workers || []);
  const fileCount = (task.result_files || []).length;
  if (!list.length) return fileCount ? `결과 파일 ${fileCount}개` : '산출물 없음';
  return `산출물: ${list.join(' · ')}${fileCount ? ` · 파일 ${fileCount}개` : ''}`;
}

function updatePmInterpretation(text) {
  const node = document.getElementById('pmDraftInterpretation');
  if (!node) return;
  if (text) {
    node.textContent = text;
    node.classList.remove('empty');
  } else {
    node.textContent = 'PM이 요청을 어떻게 이해했는지 여기 표시됩니다.';
    node.classList.add('empty');
  }
}

async function submitLiveNote(taskId, input, btn) {
  const note = (input.value || '').trim();
  if (!note) return;
  btn.disabled = true;
  btn.textContent = '전달 중...';
  try {
    const res = await fetch('/api/live-note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, note }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) throw new Error(payload.error || '전달 실패');
    input.value = '';
    delete liveNoteDrafts[taskId];
    btn.textContent = '전달됨';
    setTimeout(() => { btn.textContent = '지시 전달'; btn.disabled = false; }, 1500);
  } catch (err) {
    btn.textContent = '실패 — 다시';
    btn.disabled = false;
  }
}

function shortPreview(text) {
  const t = (text || '').replace(/\s+/g, ' ').trim();
  if (!t) return '미리보기가 없습니다.';
  return t.length > 160 ? t.slice(0, 160) + '…' : t;
}

function detailDirForKind(kind) {
  if (kind === 'review') return 'verifications';
  if (kind === 'digest') return 'digests';
  return 'results';
}

function openDetail(dir, name) {
  const modal = document.getElementById('detailModal');
  detailReturnFocus = document.activeElement;
  const rawUrl = `/files/${dir}/${encodeURIComponent(name)}`;
  const ext = (name.split('.').pop() || '').toLowerCase();
  const dirLabel = { results: '도착한 결과', verifications: '검토 메모', digests: '운영 기록' }[dir] || dir;
  document.getElementById('detailKicker').textContent = dirLabel;
  document.getElementById('detailTitle').textContent = name;
  document.getElementById('detailDownload').href = rawUrl + '?download=1';
  document.getElementById('detailNewTab').href = `/detail.html?dir=${dir}&file=${encodeURIComponent(name)}`;
  const body = document.getElementById('detailBody');
  body.innerHTML = '';
  if (ext === 'html') {
    const iframe = document.createElement('iframe');
    iframe.className = 'detail-iframe';
    iframe.setAttribute('sandbox', 'allow-downloads');
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    iframe.title = `${name} 안전 미리보기`;
    iframe.src = rawUrl;
    body.append(iframe);
  } else {
    const pre = document.createElement('pre');
    pre.className = 'detail-pre';
    pre.textContent = '불러오는 중…';
    body.append(pre);
    fetch(rawUrl)
      .then((res) => { if (!res.ok) throw new Error(`파일을 불러오지 못했습니다 (${res.status})`); return res.text(); })
      .then((text) => { pre.textContent = ext === 'json' ? JSON.stringify(JSON.parse(text), null, 2) : text; })
      .catch((err) => { pre.textContent = err.message; });
  }
  pushModal('detailModal');
  setTimeout(() => document.getElementById('closeDetailBtn')?.focus(), 0);
}

function closeDetail() {
  const modal = document.getElementById('detailModal');
  if (!modal) return;
  popModal('detailModal');
  document.getElementById('detailBody').innerHTML = '';
  if (detailReturnFocus && typeof detailReturnFocus.focus === 'function' && document.contains(detailReturnFocus)) detailReturnFocus.focus();
  else if (topModal() === 'taskDetailModal') document.getElementById('closeTaskDetailBtn')?.focus();
  detailReturnFocus = null;
}

function detailValue(value, fallback = '확인 불가') {
  if (value === undefined || value === null || value === '') return fallback;
  return String(value);
}

function detailSection(title, className, content) {
  const section = el('section', `task-detail-section ${className}`);
  section.append(el('h3', 'task-detail-section-title', title));
  section.append(content);
  return section;
}

function renderTaskStageTimeline(task) {
  const root = el('div', 'stage-timeline-summary');
  const stages = task?.stages || [];
  stages.forEach((stage) => {
    const row = el('div', 'stage-timeline-summary-row');
    row.append(el('span', 'stage-timeline-summary-stage', stageDisplayLabel(stage)));
    row.append(el('span', 'stage-timeline-summary-status', humanStatus(stage.status || 'unknown')));
    const agents = el('span', 'stage-timeline-summary-agents');
    (stage.agents || []).forEach((agent) => agents.append(el('span', 'chip', agent)));
    if (!(stage.agents || []).length) agents.append(el('span', 'stage-timeline-summary-empty', '에이전트 정보 없음'));
    row.append(agents);
    const controls = renderScopedGateControls(task, stage);
    if (controls) row.append(controls);
    root.append(row);
  });
  if (!stages.length) root.append(el('p', 'empty', '진행 단계 확인 불가'));
  return root;
}

function renderAgentExecution(task) {
  const root = el('div', 'agent-execution-table');
  (task?.stages || []).forEach((stage) => {
    (stage.agents || []).forEach((worker) => {
      const state = agentExecutionState(task, stage, worker);
      const row = el('div', `agent-execution-row agent-${state}`);
      row.append(el('span', 'agent-execution-worker', worker));
      row.append(el('span', 'agent-execution-stage', stageDisplayLabel(stage)));
      row.append(el('span', 'agent-execution-dispatch', dispatchStateFor(task, worker) || '전송 이력 없음'));
      row.append(el('span', 'agent-execution-result', agentExecutionLabel(state)));
      row.append(el('span', 'agent-execution-limit', agentExecutionLimitation(task, stage, worker, state)));
      root.append(row);
    });
  });
  if (!root.childNodes.length) root.append(el('p', 'empty', '에이전트 계획 확인 불가'));
  return root;
}

function renderEvidenceLimits(task) {
  const root = el('div', 'evidence-limits');
  const state = stageArtifactState(task, currentStageForTask(task));
  const verification = taskProjection(task).verification_summary;
  const lines = [
    state === 'partial_received' ? '결과 일부 도착 · 단계 완결성 미확인' : state === 'reviewable' ? '결과 도착 · 근거 품질 미분류' : '현재 단계 결과 없음',
    verification?.state === 'not_run' ? '검증 미실행' : '검증 근거는 원시 파일에서 확인',
    '검색 스니펫·자유 텍스트만으로 직접 검증 완료를 추론하지 않음',
  ];
  lines.forEach((line) => root.append(el('p', 'evidence-limit-item', line)));
  return root;
}

function rawGateValue(row) {
  return detailValue(row?.source_value, '값 확인 불가');
}

function renderScopedGateControls(task, stage) {
  if (!task || !stage) return null;
  const actions = el('div', 'stage-hold-actions task-detail-gate-actions');
  if (stage.status === 'entry_hold') {
    const goBtn = el('button', 'gate-btn gate-approve', '진행');
    goBtn.type = 'button';
    goBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'approve', goBtn));
    const skipBtn = el('button', 'gate-btn gate-revise', 'research 생략');
    skipBtn.type = 'button';
    skipBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'skip', skipBtn));
    actions.append(goBtn, skipBtn);
  } else if (stage.status === 'gate_hold') {
    const approveBtn = el('button', 'gate-btn gate-approve', '승인·진행');
    approveBtn.type = 'button';
    approveBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'approve', approveBtn));
    const reviseBtn = el('button', 'gate-btn gate-revise', '재작업');
    reviseBtn.type = 'button';
    reviseBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'revise', reviseBtn));
    actions.append(approveBtn, reviseBtn);
  }
  return actions.childNodes.length ? actions : null;
}

function renderTaskLiveNoteContext(task) {
  const section = el('section', 'task-detail-live-context');
  section.append(el('h3', 'task-detail-section-title', 'Live note context'));
  section.append(el('p', 'task-detail-meta', '비결정 맥락 · 다음 심사·단계부터 반영됩니다.'));
  const pendingNotes = (task.pm_live_notes || []).filter((n) => !n.consumed);
  if (pendingNotes.length) {
    const pending = el('div', 'live-note-pending');
    pendingNotes.slice(-3).forEach((n) => pending.append(el('p', 'live-note-context-item', `지시 대기: ${detailValue(n.note, '내용 확인 불가')}`)));
    section.append(pending);
  }
  const inputRow = el('div', 'live-note-input-row');
  const noteInput = document.createElement('input');
  noteInput.type = 'text';
  noteInput.className = 'live-note-input';
  noteInput.placeholder = 'PM 지시 추가 — 다음 심사·단계부터 반영 (보류 중이면 재심사)';
  noteInput.value = liveNoteDrafts[task.task_id] || '';
  noteInput.addEventListener('input', () => { liveNoteDrafts[task.task_id] = noteInput.value; });
  const sendBtn = el('button', 'mini-btn', '지시 전달');
  sendBtn.type = 'button';
  sendBtn.addEventListener('click', () => submitLiveNote(task.task_id, noteInput, sendBtn));
  noteInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submitLiveNote(task.task_id, noteInput, sendBtn); }
  });
  inputRow.append(noteInput, sendBtn);
  section.append(inputRow);
  return section;
}

function followUpDraft(taskId) {
  if (!followUpDrafts.has(taskId)) followUpDrafts.set(taskId, { title: '', desired_outcome: '', context: '', request_type: 'supplement', priority_requested: 'medium' });
  return followUpDrafts.get(taskId);
}

function renderFollowUpPanel(task) {
  const section = el('section', 'task-detail-followup');
  section.append(el('h3', 'task-detail-section-title', 'Follow-up request'));
  section.append(el('p', 'task-detail-meta', '추가 작업 의도만 접수합니다. 제출 즉시 실행·승인·dispatch되지 않으며 PM 재평가 대기로 남습니다. 원본 task와 완료 상태는 변경되지 않습니다.'));
  const history = el('div', 'followup-history');
  section.append(el('h4', 'followup-subtitle', '요청 이력'));
  history.append(el('p', 'empty', '요청 이력을 불러오는 중…'));
  section.append(history);
  if (!followUpCapabilities.write_enabled) {
    section.append(el('p', 'followup-disabled', '인증 또는 same-origin 사전조건이 확인되지 않아 요청 작성은 비활성화되어 있습니다.'));
    return section;
  }
  section.append(el('h4', 'followup-subtitle', '새 요청'));
  const draft = followUpDraft(task.task_id);
  const form = el('form', 'followup-form');
  [['title', '요청 제목', '예: 모바일 실기기 검증 추가', 180], ['desired_outcome', '원하는 결과', '무엇이 남아야 하는지 구체적으로 적어 주세요.', 1200], ['context', '배경과 제약', '기존 결과의 어떤 부분을 보완하는지 (선택)', 1200]].forEach(([name, label, placeholder, max]) => {
    const labelNode = document.createElement('label'); labelNode.className = 'followup-field'; labelNode.append(el('span', '', label));
    const input = name === 'title' ? document.createElement('input') : document.createElement('textarea');
    input.name = name; input.maxLength = max; input.placeholder = placeholder; input.value = draft[name] || ''; input.required = name !== 'context';
    input.addEventListener('input', () => { draft[name] = input.value; }); labelNode.append(input); form.append(labelNode);
  });
  const typeLabel = document.createElement('label'); typeLabel.className = 'followup-field'; typeLabel.append(el('span', '', '요청 유형'));
  const select = document.createElement('select'); select.name = 'request_type';
  [['supplement', '보완'], ['research', '추가 조사'], ['revision', '수정'], ['verification', '검증'], ['new_artifact', '새 산출물'], ['other', '기타']].forEach(([value, label]) => { const option = document.createElement('option'); option.value = value; option.textContent = label; option.selected = draft.request_type === value; select.append(option); });
  select.addEventListener('change', () => { draft.request_type = select.value; }); typeLabel.append(select); form.append(typeLabel);
  const status = el('p', 'status-text followup-status'); const submit = el('button', 'primary-btn', 'PM 재평가 요청 제출'); submit.type = 'submit'; form.append(submit, status); section.append(form);
  const refresh = el('button', 'mini-btn followup-refresh', '현재 이력 새로고침'); refresh.type = 'button'; refresh.hidden = true; section.append(refresh);
  refresh.addEventListener('click', async () => { await loadFollowUpHistory(task.task_id, history); followUpStale.delete(task.task_id); refresh.hidden = true; status.textContent = '현재 이력을 확인했습니다. 초안을 검토한 뒤 다시 제출할 수 있습니다.'; });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!draft.title.trim() || !draft.desired_outcome.trim()) { status.textContent = '제목과 원하는 결과를 입력해 주세요.'; return; }
    if (followUpStale.get(task.task_id)) { status.textContent = '이력이 변경되었습니다. 초안을 유지한 채 먼저 현재 이력을 새로고침해 주세요.'; refresh.hidden = false; return; }
    submit.disabled = true; status.textContent = '감사 가능한 요청 레코드 저장 중…';
    const key = followUpIdempotency.get(task.task_id) || `dashboard-${task.task_id}-${crypto.randomUUID()}`; followUpIdempotency.set(task.task_id, key);
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(task.task_id)}/follow-up-requests`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(draft) });
      const result = await response.json(); if (!response.ok || !result.ok) { const error = new Error(result.error || '요청 저장 실패'); error.status = response.status; throw error; }
      followUpDrafts.delete(task.task_id); followUpIdempotency.delete(task.task_id); status.textContent = `접수됨 · ${result.request.request_id} · v${result.request.version} · PM 재평가 대기`; await loadFollowUpHistory(task.task_id, history);
    } catch (error) {
      if (error.status === 409) { followUpStale.set(task.task_id, true); refresh.hidden = false; status.textContent = '이력이 변경되어 제출하지 않았습니다. 초안은 그대로 유지됩니다. 먼저 현재 이력을 새로고침해 주세요.'; }
      else status.textContent = `저장 실패 — 초안은 유지됩니다: ${error.message}`;
    } finally { submit.disabled = false; }
  });
  loadFollowUpHistory(task.task_id, history);
  return section;
}

async function loadFollowUpHistory(taskId, root) {
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/follow-up-requests`); const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || '이력 조회 실패');
    root.innerHTML = ''; if (!result.requests.length) { root.append(el('p', 'empty', '아직 제출한 후속 요청이 없습니다.')); return; }
    result.requests.forEach((request) => { const row = el('article', 'followup-history-row'); row.append(el('strong', '', `${request.request_id} · v${request.version} · ${request.state}`)); row.append(el('span', '', request.title)); row.append(el('small', '', `${request.submitted_at} · ${request.submitted_by?.actor_id || 'server actor'}`)); row.append(el('p', 'followup-history-outcome', request.desired_outcome || '원하는 결과 확인 불가')); root.append(row); });
  } catch (error) { root.innerHTML = ''; root.append(el('p', 'followup-disabled', `이력 확인 불가: ${error.message}`)); }
}

function rawGateLabel(row, index) {
  return `원시 게이트 근거 ${index + 1}`;
}

function rawGateDecisionLabel(row) {
  if (row?.source_value === undefined || row?.source_value === null || row?.source_value === '') return '결정 없음';
  return String(row.source_value);
}

function renderRawGateAudit(projection) {
  const disclosure = el('details', 'raw-gate-disclosure');
  disclosure.append(el('summary', '', '원시 게이트 이력'));
  const rows = el('div', 'raw-gate-audit-list');
  (projection?.audit_rows || []).forEach((audit, index) => {
    if (!audit || typeof audit !== 'object') return;
    const item = el('article', 'raw-gate-audit-row');
    item.append(el('div', 'raw-gate-audit-heading', `${rawGateLabel(audit, index)} · ${rawGateDecisionLabel(audit)}`));
    const fields = [
      ['source', audit.source_mechanism || audit.source],
      ['value', rawGateValue(audit)],
      ['scope', audit.scope],
      ['reason', audit.reason],
      ['time', audit.time || audit.at || audit.timestamp],
      ['actor', audit.actor],
      ['correlation', audit.correlation || audit.correlation_id],
      ['version', audit.version],
    ];
    fields.forEach(([label, value]) => {
      const field = el('div', 'raw-gate-audit-field');
      field.append(el('span', 'raw-gate-audit-key', label));
      field.append(el('span', 'raw-gate-audit-value', detailValue(value, '현재 raw에서 복구할 수 없음')));
      item.append(field);
    });
    rows.append(item);
  });
  if (!rows.childNodes.length) rows.append(el('p', 'empty', '현재 원시 게이트 근거 없음'));
  disclosure.append(rows);
  return disclosure;
}

function artifactBindingPresentation(task, projection) {
  const review = task?.pm_final_review;
  const artifact = projection?.artifact_summary || {};
  const latest = artifact.latest || {};
  const binding = review && (review.artifact_id || review.result_artifact_id || review.artifact_version || review.result_version);
  const matches = Boolean(binding && artifact.state === 'available' && (
    (review.artifact_id && review.artifact_id === (latest.name || latest.id))
    || (review.result_artifact_id && review.result_artifact_id === (latest.name || latest.id))
    || (review.artifact_version && review.artifact_version === latest.version)
    || (review.result_version && review.result_version === latest.version)
  ));
  return {
    available: matches,
    label: matches ? '최종 검토 대상 연결 확인됨' : '최종본 연결 확인 불가',
    warning: matches ? '' : '최종 산출물 또는 버전에 연결된 최종 검토 근거가 없어 override 요청을 안전하게 확인할 수 없습니다.',
  };
}

function renderArtifactReviewPanel(task, projection) {
  const panel = el('section', 'artifact-review-panel');
  panel.append(el('h3', 'task-detail-section-title', 'Artifact Review'));
  const artifact = projection?.artifact_summary || {};
  const latest = artifact.latest || {};
  const artifacts = el('div', 'artifact-review-block');
  artifacts.append(el('h4', 'artifact-review-label', 'Artifacts'));
  const artifactItems = artifact.items || [];
  if (!artifactItems.length) artifacts.append(el('p', 'empty', '현재 확인 가능한 산출물이 없습니다.'));
  artifactItems.forEach((file) => {
    const name = typeof file === 'string' ? file : file?.name;
    if (!name) return;
    const button = el('button', 'item artifact-reference clickable', `결과 · ${name}`);
    button.type = 'button';
    button.addEventListener('click', () => openDetail('results', name));
    artifacts.append(button);
  });
  if (latest.name || latest.id || latest.version || latest.size !== undefined) {
    const metadata = el('div', 'artifact-review-metadata');
    [['name', latest.name], ['id', latest.id], ['version', latest.version], ['size', latest.size]].forEach(([label, value]) => {
      if (value === undefined || value === null || value === '') return;
      metadata.append(el('span', 'artifact-review-meta-item', `${label}: ${value}`));
    });
    artifacts.append(metadata);
  }
  panel.append(artifacts);

  const acceptance = el('div', 'artifact-review-block');
  acceptance.append(el('h4', 'artifact-review-label', 'Acceptance criteria'));
  const acceptanceCriteria = task?.acceptance_criteria;
  if (Array.isArray(acceptanceCriteria) && acceptanceCriteria.length) {
    acceptanceCriteria.forEach((criterion) => acceptance.append(el('p', 'task-detail-lead', detailValue(criterion, '확인 불가'))));
  } else if (typeof acceptanceCriteria === 'string' && acceptanceCriteria.trim()) {
    acceptance.append(el('p', 'task-detail-lead', acceptanceCriteria));
  } else {
    acceptance.append(el('p', 'artifact-review-warning-detail', 'AC를 사용할 수 없습니다.'));
  }
  panel.append(acceptance);

  const verification = el('div', 'artifact-review-block');
  verification.append(el('h4', 'artifact-review-label', 'Verification'));
  const verificationSummary = projection?.verification_summary || {};
  verification.append(el('p', 'task-detail-lead', verificationSummary.state === 'not_run' ? '검증 근거를 사용할 수 없습니다 — 검증 미실행' : detailValue(verificationSummary.state, '검증 상태 확인 불가')));
  (verificationSummary.items || []).forEach((file) => {
    const name = typeof file === 'string' ? file : file?.name;
    if (!name) return;
    const button = el('button', 'mini-btn subtle-btn', `검증 파일 · ${name}`);
    button.type = 'button';
    button.addEventListener('click', () => openDetail('verifications', name));
    verification.append(button);
  });
  panel.append(verification);

  const scope = projection?.decision_queue_item?.scope;
  const scopeBlock = el('div', 'artifact-review-block');
  scopeBlock.append(el('h4', 'artifact-review-label', 'Target scope'));
  scopeBlock.append(el('p', 'task-detail-lead', detailValue(scope, '대상 범위 확인 불가')));
  panel.append(scopeBlock);

  const binding = artifactBindingPresentation(task, projection);
  const unavailableLabel = '최종본 연결 확인 불가';
  const bindingBlock = el('div', `artifact-review-binding ${binding.available ? 'is-available' : 'is-unavailable'}`);
  bindingBlock.append(el('p', 'artifact-review-warning', binding.available ? binding.label : `주의: ${unavailableLabel}`));
  if (binding.warning) bindingBlock.append(el('p', 'artifact-review-warning-detail', binding.warning));
  panel.append(bindingBlock);

  const review = task?.pm_final_review || {};
  if (task.status === 'needs_pm_review' && review.verdict === 'not_meets') {
    const actions = el('div', 'artifact-review-actions');
    const acceptBtn = el('button', 'gate-btn gate-approve', '최종 검토 override 요청');
    acceptBtn.addEventListener('click', () => finalReviewOverride(task.task_id, 'accept', acceptBtn));
    const reworkBtn = el('button', 'gate-btn gate-revise', '재작업 override 요청');
    reworkBtn.addEventListener('click', () => finalReviewOverride(task.task_id, 'rework', reworkBtn));
    actions.append(acceptBtn, reworkBtn);
    panel.append(actions);
  }
  return panel;
}

function renderFinalDeliverable(task, projection) {
  const final = projection?.final_deliverable || { state: 'unavailable', label: '최종 결과물 확인 불가', candidates: [], limitations: ['projection_missing'] };
  const confirmed = final.state === 'confirmed' && final.artifact?.name;
  const stateLabels = { confirmed: '확인됨', candidate_unconfirmed: '근거 부족', ambiguous: '후보 여러 개', conflict: '근거 충돌', unavailable: '확인 불가', unknown: '확인 불가' };
  const section = el('section', `final-deliverable-section final-deliverable-${final.state || 'unknown'}`);
  const heading = el('div', 'final-deliverable-heading');
  heading.append(el('span', 'final-deliverable-kicker', 'FINAL DELIVERABLE'));
  heading.append(el('span', 'final-deliverable-badge', stateLabels[final.state] || '확인 불가'));
  section.append(heading);
  section.append(el('h3', 'final-deliverable-title', confirmed ? final.artifact.name : '최종 결과물 확인 불가'));
  const description = confirmed
    ? (final.source_mode === 'final_write' ? '최종 작성 결과와 artifact 연결이 확인되었습니다.' : '최종 작성은 생략되었으며 writing 산출물이 검증·PM review와 동일 artifact로 연결되었습니다.')
    : (final.reason_code === 'multiple_equal_candidates' ? '후보가 여러 개여서 최종 결과물을 확인할 수 없습니다.' : '최종 결과물로 확정할 수 있는 artifact binding 근거가 부족합니다.');
  section.append(el('p', 'final-deliverable-description', description));
  const facts = el('div', 'final-deliverable-facts');
  const stage = final.deliverable_stage || {};
  [['source stage', stage.id], ['stage status', stage.raw_status], ['active attempt', stage.derived_task_id], ['version', final.artifact?.version || '확인 불가'], ['verification', final.verification?.state], ['PM final review', final.pm_final_review?.verdict || final.pm_final_review?.state]].forEach(([label, value]) => {
    if (value === undefined || value === null || value === '') return;
    const fact = el('div', 'final-deliverable-fact');
    fact.append(el('span', 'final-deliverable-fact-label', label));
    fact.append(el('strong', 'final-deliverable-fact-value', String(value)));
    facts.append(fact);
  });
  if (facts.childNodes.length) section.append(facts);
  if (confirmed) {
    const open = el('button', 'mini-btn final-deliverable-open', '최종 결과물 열기');
    open.type = 'button';
    open.addEventListener('click', () => openDetail(final.artifact.dir || 'results', final.artifact.name));
    section.append(open);
  } else {
    section.append(el('p', 'final-deliverable-guidance', `일반 Artifacts에서 후보 확인 · 후보 ${final.candidates?.length || 0}개`));
  }
  return section;
}

function renderOperationsEvidence(evidence) {
  const root = document.getElementById('operationsEvidence');
  if (!root) return;
  root.innerHTML = '';
  const heading = el('div', 'operations-evidence-heading');
  heading.append(el('strong', '', '운영 관찰 근거'));
  heading.append(el('span', 'task-detail-meta', '전역 관찰은 raw task 상태를 덮어쓰지 않습니다.'));
  root.append(heading);
  const grid = el('div', 'operations-evidence-grid');
  [['sync', 'Sync'], ['watchdog', 'Watchdog']].forEach(([key, label]) => {
    const item = evidence?.[key] || { state: 'unknown' };
    const state = item.state || 'unknown';
    const row = el('div', `operations-evidence-item evidence-${state}`);
    row.append(el('span', 'operations-evidence-label', label));
    row.append(el('strong', 'operations-evidence-state', ({ success: '성공', error: '오류', stale: '오래된 관찰', never_observed: '관찰 기록 없음', unknown: '확인 불가' }[state] || state)));
    row.append(el('span', 'operations-evidence-meta', item.observed_at ? `관찰 ${item.observed_at}` : '관찰 시각 없음'));
    if (item.source_limitation) row.append(el('span', 'operations-evidence-limit', `한계 · ${item.source_limitation === 'malformed_snapshot' ? 'unknown · malformed_snapshot' : item.source_limitation}`));
    if (key === 'sync') row.append(el('span', 'operations-evidence-meta', `task 전이 근거 ${item.task_transition_evidence?.length || 0}건`));
    grid.append(row);
  });
  root.append(grid);
}

function renderTaskOperationsEvidence(task) {
  const wrap = el('div', 'task-operations-evidence');
  const evidence = taskProjection(task).operations_evidence || task.operations_evidence || {};
  [['sync', 'Sync'], ['watchdog', 'Watchdog']].forEach(([key, label]) => {
    const item = evidence[key] || { state: 'unknown' };
    const line = el('div', `task-operations-evidence-row evidence-${item.state || 'unknown'}`);
    line.append(el('strong', '', `${label} · ${item.state || 'unknown'}`));
    line.append(el('span', '', item.observed_at ? `observed_at ${item.observed_at}` : '관찰 시각 없음'));
    if (item.source_limitation) line.append(el('span', 'data-quality-note', `한계 · ${item.source_limitation === 'malformed_snapshot' ? 'unknown · malformed_snapshot' : item.source_limitation}`));
    if (key === 'sync') line.append(el('span', '', `task 전이 근거 ${item.task_transition_evidence?.length || 0}건`));
    wrap.append(line);
  });
  return wrap;
}

function renderTaskDetail(task) {
  const body = document.getElementById('taskDetailBody');
  if (!body) return;
  body.innerHTML = '';
  if (!task) {
    body.append(el('p', 'empty', '선택된 업무 정보를 확인할 수 없습니다.'));
    return;
  }
  const projection = taskProjection(task);
  body.append(renderFinalDeliverable(task, projection));
  const outcome = el('div', 'task-detail-copy');
  outcome.append(el('p', 'task-detail-lead', detailValue(task.objective, '업무 목표 확인 불가')));
  outcome.append(el('p', 'task-detail-meta', `${humanStatus(task.status)} · ${detailValue(task.updated_at || task.created_at, '시간 확인 불가')}`));
  body.append(detailSection('Outcome', 'task-detail-outcome', outcome));

  const progress = taskProjection(task).progress || {};
  const progressOverview = el('div', 'task-detail-copy');
  progressOverview.append(el('p', 'task-detail-lead', taskProgressSummary(task)));
  progressOverview.append(el('p', 'task-detail-meta', `다음 PM 조치 · ${progress.next_pm_action?.label || '진행 상세 보기'}`));
  body.append(detailSection('Progress overview', 'task-detail-progress-section', progressOverview));

  const stage = el('div', 'task-detail-stage');
  stage.append(renderTaskStageTimeline(task));
  body.append(detailSection('Stage timeline', 'task-detail-stage-section', stage));
  body.append(detailSection('Agent execution', 'task-detail-agent-section', renderAgentExecution(task)));

  // Evidence-first sections: 'Artifacts' -> 'Verification'.
  body.append(renderArtifactReviewPanel(task, projection));
  body.append(detailSection('Sync / Watchdog evidence', 'task-detail-operations-evidence', renderTaskOperationsEvidence(task)));
  body.append(detailSection('Evidence quality & limits', 'task-detail-evidence-section', renderEvidenceLimits(task)));

  const authority = el('div', 'task-detail-copy');
  const authorityInfo = authorityPresentation(projection);
  authority.append(el('p', 'audit-top-notice', '감사 패널은 현재 raw 상태에서 복구할 수 있는 내용으로 제한됩니다.'));
  authority.append(el('p', `task-detail-authority ${authorityInfo.className}`, `현재 권한 상태 · ${authorityInfo.label}`));
  const audit = projection.audit_rows || [];
  authority.append(el('p', 'task-detail-meta', audit.length ? `현재 raw 감사 근거 ${audit.length}건` : '현재 raw 감사 이력 복구 불가'));
  authority.append(renderRawGateAudit(projection));
  body.append(detailSection('Authority / Audit', 'task-detail-authority-audit', authority));
  if (!['completed', 'cancelled'].includes(task.status)) body.append(renderTaskLiveNoteContext(task));
  body.append(renderFollowUpPanel(task));
}

function openTaskDetail(task, returnFocus) {
  const modal = document.getElementById('taskDetailModal');
  if (!modal) return;
  taskDetailReturnFocus = returnFocus || document.activeElement;
  document.getElementById('taskDetailTitle').textContent = detailValue(task?.title || task?.task_id, '업무 상세');
  renderTaskDetail(task);
  pushModal('taskDetailModal');
  setTimeout(() => document.getElementById('closeTaskDetailBtn')?.focus(), 0);
}

function closeTaskDetail() {
  const modal = document.getElementById('taskDetailModal');
  if (!modal) return;
  popModal('taskDetailModal');
  document.getElementById('taskDetailBody').innerHTML = '';
  if (taskDetailReturnFocus && typeof taskDetailReturnFocus.focus === 'function' && document.contains(taskDetailReturnFocus)) taskDetailReturnFocus.focus();
  taskDetailReturnFocus = null;
}

// 진행 상황 실시간 반영: 15초 자동 새로고침 (탭이 보일 때만)
setInterval(() => {
  if (!document.hidden) loadDashboard().catch(() => {});
}, 15000);
