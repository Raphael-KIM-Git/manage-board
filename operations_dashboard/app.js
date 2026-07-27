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

function authorityPresentation(projection) {
  const authority = projection?.authority_summary;
  if (!authority) return { label: '현재 데이터에서 확인 불가', className: 'authority-unknown' };
  if (authority.effective_final_approved === true) return { label: '현재 raw 근거로 검토 완료', className: 'authority-evidence' };
  return { label: authority.label || '결정 없음', className: 'authority-unknown' };
}

function pipelineShapePresentation(task) {
  const shape = task.dashboard_projection?.pipeline_shape;
  if (!shape) return { label: pipelineShapeLabel(task.pipeline_shape), className: 'pipeline-unknown' };
  return { label: shape.label, className: `pipeline-${shape.confidence || 'unknown'}` };
}

function singlePrimaryAction(item) {
  return item?.primary_action || '상세 보기';
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
    if (!compact && status === 'gate_hold') {
      const holdRow = el('div', 'stage-hold-actions');
      const approveBtn = el('button', 'gate-btn gate-approve', '승인·진행');
      approveBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'approve', approveBtn));
      const reviseBtn = el('button', 'gate-btn gate-revise', '재작업');
      reviseBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'revise', reviseBtn));
      holdRow.append(approveBtn, reviseBtn);
      copy.append(holdRow);
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
    if (!compact && status === 'entry_hold') {
      const eHold = el('div', 'stage-hold-actions');
      const goBtn = el('button', 'gate-btn gate-approve', '진행');
      goBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'approve', goBtn));
      const skipBtn = el('button', 'gate-btn gate-revise', 'research 생략');
      skipBtn.addEventListener('click', () => gateOverride(task.task_id, stage.id, 'skip', skipBtn));
      eHold.append(goBtn, skipBtn);
      copy.append(eHold);
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
    verification_summary: { state: task.verification_files?.length ? 'available_unstructured' : 'not_run', items: task.verification_files || [] },
    authority_summary: { effective_final_approved: false, label: '현재 데이터에서 확인 불가' },
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
    document.getElementById('activeWorkBoard')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    expandedTasks.add(task.task_id);
    renderTasks(dashboardState.tasks || []);
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
    const row = el('div', 'item artifact-reference');
    const name = typeof file === 'string' ? file : file?.name;
    row.append(el('div', 'item-title', `${kind} · ${name || '이름 없음'}`));
    row.append(el('div', 'item-meta', task.title || task.task_id || '업무 정보 없음'));
    row.append(el('div', 'item-preview', '현재 응답에서 확인된 읽기 전용 근거'));
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

function taskProgressSummary(task) {
  const pipeline = task.pipeline;
  if (pipeline?.current_stage) {
    const completed = Number(pipeline.completed_stages || 0);
    const total = Number(pipeline.stage_count || 0);
    return total ? `${pipeline.current_stage} · ${completed}/${total} 단계 완료` : `현재 단계: ${pipeline.current_stage}`;
  }
  const stages = task.stages || [];
  if (!stages.length) return '진행 단계 확인 불가';
  const done = stages.filter((stage) => stage.status === 'completed' || stage.status === 'skipped').length;
  const current = stages.find((stage) => ['in_progress', 'gate_hold', 'entry_hold'].includes(stage.status));
  return current ? `${current.label || '현재 단계'} · ${done}/${stages.length} 단계 완료` : `${done}/${stages.length} 단계 완료`;
}

function taskArtifactSummary(task) {
  const artifact = taskProjection(task).artifact_summary || {};
  if (artifact.state === 'ambiguous') return '산출물 후보 여러 개 · 범위 확인 필요';
  if (artifact.latest?.name) return `최근 산출물 · ${artifact.latest.name}`;
  if (artifact.items?.length) return `산출물 ${artifact.items.length}개 확인 가능`;
  return '아직 확인 가능한 산출물 없음';
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
  outcome.append(el('div', 'task-submeta', `${humanStatus(task.status)} · ${task.updated_at || task.created_at || '시간 미상'}`));
  card.append(outcome);

  const progress = el('div', 'task-card-fact task-progress');
  progress.append(el('span', 'task-fact-label', '진행'));
  progress.append(el('span', 'task-fact-value', taskProgressSummary(task)));
  card.append(progress);
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
  const authority = authorityPresentation(taskProjection(task));
  card.append(el('div', `data-authority ${authority.className}`, `권한 · ${authority.label}`));

  const compactHideGateDetails = taskProjection(task).compact_hide_gate_details ?? isDone;
  const extra = el('div', 'task-extra');
  extra.append(renderStageChips(task, compactHideGateDetails));
  extra.append(renderSeedWorkflow(task));
  if (task.pm_final_review && task.pm_final_review.verdict) {
    const fr = task.pm_final_review;
    const vlabel = { meets: '충족', partial: '대체로 충족', not_meets: '미충족' }[fr.verdict] || fr.verdict;
    const frBox = el('div', `final-review fr-${fr.verdict}`);
    frBox.append(el('span', 'final-review-badge', `PM 총평: ${vlabel}`));
    if (fr.comment) frBox.append(el('span', 'final-review-comment', fr.comment));
    if (fr.gaps) frBox.append(el('div', 'final-review-gaps', `보완: ${fr.gaps}`));
    extra.append(frBox);
    if (task.status === 'needs_pm_review' && fr.verdict === 'not_meets') {
      const frActions = el('div', 'stage-hold-actions');
      const acceptBtn = el('button', 'gate-btn gate-approve', '이대로 승인');
      acceptBtn.addEventListener('click', () => finalReviewOverride(task.task_id, 'accept', acceptBtn));
      const reworkBtn = el('button', 'gate-btn gate-revise', '재작업');
      reworkBtn.addEventListener('click', () => finalReviewOverride(task.task_id, 'rework', reworkBtn));
      frActions.append(acceptBtn, reworkBtn);
      extra.append(frActions);
    }
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
  if (links.childNodes.length) extra.append(links);

  const workerResults = renderWorkerResults(task);
  if (workerResults) extra.append(workerResults);

  if (!isDone) {
    const liveWrap = el('div', 'live-note-row');
    const pendingNotes = (task.pm_live_notes || []).filter((n) => !n.consumed);
    if (pendingNotes.length) {
      const pendingRow = el('div', 'live-note-pending');
      pendingNotes.slice(-3).forEach((n) => pendingRow.append(el('div', 'chip live-note-chip', `지시 대기: ${n.note}`)));
      liveWrap.append(pendingRow);
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
    liveWrap.append(inputRow);
    extra.append(liveWrap);
  }

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
  const btn = el('button', 'mini-btn', '다시 전송');
  btn.disabled = ['completed', 'cancelled'].includes(task.status);
  btn.addEventListener('click', () => dispatchTask(task.task_id, btn));
  actionRow.append(toggleBtn);
  const detailActions = el('div', 'task-actions task-detail-actions');
  detailActions.append(btn);
  extra.append(detailActions);
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
  modal.classList.toggle('is-hidden', !open);
  modal.setAttribute('aria-hidden', open ? 'false' : 'true');
  document.body.classList.toggle('modal-open', open);
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

async function loadDashboard() {
  const [overview, tasks, results, verifications, digests] = await Promise.all([
    getJson('/api/overview'),
    getJson('/api/tasks'),
    getJson('/api/results'),
    getJson('/api/verifications'),
    getJson('/api/digests'),
  ]);

  dashboardState = { overview, tasks, results, verifications, digests };
  renderMissionControl(overview.dashboard_summary, tasks || []);
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
  document.addEventListener('click', (event) => {
    if (event.target?.dataset?.closeDetail === 'true') closeDetail();
  });
  document.getElementById('briefModal').addEventListener('click', (event) => {
    if (event.target?.dataset?.closeModal === 'true') setModalOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { setModalOpen(false); closeDetail(); }
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
document.getElementById('autoDispatchBtn').addEventListener('click', (e) => autoDispatchQueued(e.currentTarget));
setupAdvancedToggle();
setupModal();
setupConversationMirror();
setupPmChat();
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
  modal.classList.remove('is-hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeDetail() {
  const modal = document.getElementById('detailModal');
  if (!modal) return;
  modal.classList.add('is-hidden');
  modal.setAttribute('aria-hidden', 'true');
  document.getElementById('detailBody').innerHTML = '';
}

// 진행 상황 실시간 반영: 15초 자동 새로고침 (탭이 보일 때만)
setInterval(() => {
  if (!document.hidden) loadDashboard().catch(() => {});
}, 15000);
