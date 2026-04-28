const DATA_URL = "./data/csa600.json";
const STORAGE_KEY = "csaSpartanState:v2";
const TARGET_RECALL = 0.62;
const BASE_LR = 0.18;

const CONCEPT_LABELS_JA = {
  platform_overview: "プラットフォーム概要",
  the_instance: "インスタンス",
  next_experience_unified_navigation: "Next Experience統合ナビ",
  search_and_lists: "検索・リスト・フィルター",
  user_menu_and_roles: "ユーザーメニューと権限",
  installing_applications_and_plugins: "アプリ/プラグイン導入",
  personalizing_customizing_instance: "インスタンス個人化/カスタマイズ",
  common_user_interfaces: "共通UI",
  instance_properties: "システムプロパティ",
  lists_filters_tags: "リスト・フィルター・タグ",
  list_and_form_anatomy: "リスト/フォーム構造",
  form_configuration: "フォーム設定",
  task_management: "タスク管理",
  visual_task_boards: "Visual Task Boards",
  platform_analytics: "Platform Analytics",
  notifications: "通知",
  knowledge_management: "ナレッジ管理",
  service_catalog: "サービスカタログ",
  workflow_studio: "Workflow Studio",
  virtual_agent: "Virtual Agent",
  data_schema: "データスキーマ",
  application_access_control: "Access Control",
  importing_data: "Importing Data",
  cmdb_and_csdm: "CMDB/CSDM",
  security_center: "Security Center",
  shared_responsibility_model: "Shared Responsibility Model",
  ui_policies: "UI Policies",
  business_rules: "Business Rules",
  system_update_sets: "Update Sets",
  scripting_in_servicenow: "ServiceNow Scripting",
};

const state = {
  dataset: null,
  questionMap: new Map(),
  user: null,
  currentQuestionId: null,
  currentSelections: [],
  currentQuestionModel: null,
  hintLevel: 0,
  mockTimerHandle: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", async () => {
  cacheElements();
  bindEvents();
  await loadDataset();
  loadUserState();
  ensureSprintStart();
  renderAll();
});

function cacheElements() {
  const ids = [
    "stat-curated",
    "stat-days",
    "stat-today",
    "stat-today-sub",
    "stat-pass",
    "stat-pass-sub",
    "today-badge",
    "today-card",
    "next-preview",
    "domain-progress",
    "selection-policy",
    "reviewed-count",
    "model-summary",
    "weak-concepts",
    "drill-mode",
    "domain-filter",
    "drill-status",
    "question-meta",
    "question-card",
    "question-rationale",
    "hint-box",
    "result-box",
    "hint-button",
    "submit-answer",
    "next-question",
    "load-question",
    "jump-next",
    "start-sprint",
    "reset-progress",
    "mock-timer",
    "start-mock",
    "finish-mock",
    "mock-progress",
    "mock-question",
    "mock-prev",
    "mock-save",
    "mock-next",
    "mock-results",
    "plan-grid",
    "plan-summary",
  ];

  ids.forEach((id) => {
    els[id] = document.getElementById(id);
  });
  els.tabs = [...document.querySelectorAll(".tab-button")];
  els.views = [...document.querySelectorAll(".view")];
}

function bindEvents() {
  els.tabs.forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  els["load-question"].addEventListener("click", () => loadNextDrillQuestion());
  els["jump-next"].addEventListener("click", () => {
    switchView("drill");
    loadNextDrillQuestion();
  });
  els["hint-button"].addEventListener("click", () => revealHint());
  els["submit-answer"].addEventListener("click", () => submitCurrentQuestion());
  els["next-question"].addEventListener("click", () => loadNextDrillQuestion());
  els["drill-mode"].addEventListener("change", () => renderDrillControls());
  els["domain-filter"].addEventListener("change", () => renderDrillControls());

  els["start-sprint"].addEventListener("click", () => {
    state.user.startedAt = new Date().toISOString();
    saveUserState();
    renderAll();
  });

  els["reset-progress"].addEventListener("click", () => {
    const confirmed = window.confirm("機械学習モデルも履歴も全部消す。本当にやるか。");
    if (!confirmed) return;
    state.user = defaultUserState();
    state.currentQuestionId = null;
    state.currentSelections = [];
    state.currentQuestionModel = null;
    saveUserState();
    renderAll();
  });

  els["start-mock"].addEventListener("click", () => startMock());
  els["finish-mock"].addEventListener("click", () => finishMock());
  els["mock-prev"].addEventListener("click", () => moveMock(-1));
  els["mock-next"].addEventListener("click", () => moveMock(1));
  els["mock-save"].addEventListener("click", () => saveMockAnswer());
}

async function loadDataset() {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("学習データの読み込みに失敗");
  }
  state.dataset = await response.json();
  state.questionMap = new Map(state.dataset.questions.map((question) => [question.id, question]));
}

function defaultUserState() {
  return {
    version: 2,
    startedAt: null,
    attempts: {},
    learner: {
      overallTheta: 0,
      domainTheta: {},
      conceptTheta: {},
      questionBias: {},
    },
    mockSession: null,
  };
}

function migrateState(raw) {
  const next = {
    ...defaultUserState(),
    ...raw,
    learner: {
      ...defaultUserState().learner,
      ...(raw.learner || {}),
    },
  };
  next.version = 2;
  return next;
}

function loadUserState() {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    state.user = defaultUserState();
    return;
  }
  try {
    state.user = migrateState(JSON.parse(raw));
  } catch {
    state.user = defaultUserState();
  }
}

function saveUserState() {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.user));
}

function ensureSprintStart() {
  if (!state.user.startedAt) {
    state.user.startedAt = new Date().toISOString();
    saveUserState();
  }
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function sigmoid(value) {
  return 1 / (1 + Math.exp(-value));
}

function average(values, fallback = 0) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : fallback;
}

function dueIntervalHours(halfLifeHours, targetRecall = TARGET_RECALL) {
  return halfLifeHours * (Math.log(targetRecall) / Math.log(0.5));
}

function domainByKey(domainKey) {
  return state.dataset.domains.find((domain) => domain.domain_key === domainKey);
}

function domainLabelJa(domainKey) {
  return domainByKey(domainKey)?.label_ja || domainKey;
}

function conceptLabelJa(tag) {
  return CONCEPT_LABELS_JA[tag] || tag.replaceAll("_", " ");
}

function questionById(questionId) {
  return state.questionMap.get(questionId);
}

function defaultAttemptRecord() {
  return {
    total: 0,
    correct: 0,
    streak: 0,
    halfLifeHours: null,
    dueAt: null,
    lastSeenAt: null,
    lastAnswer: [],
    lastResult: null,
    lastPredictedRecall: null,
    lastKnowledgeProb: null,
    lastHintsUsed: 0,
    history: [],
  };
}

function attemptRecord(questionId) {
  return state.user.attempts[questionId] || defaultAttemptRecord();
}

function masteryFromTheta(theta) {
  return sigmoid(theta);
}

function initialHalfLife(question) {
  let halfLife = 8;
  halfLife += question.current_relevance_score * 5;
  halfLife += question.multi_select ? 2 : 0;
  halfLife += question.concept_tags.length * 0.6;
  return clamp(halfLife, 6, 18);
}

function questionModel(question, atMs = Date.now()) {
  const learner = state.user.learner;
  const record = attemptRecord(question.id);
  const domainTheta = learner.domainTheta[question.domain_key] || 0;
  const conceptThetas = question.concept_tags.map((tag) => learner.conceptTheta[tag] || 0);
  const conceptTheta = average(conceptThetas, 0);
  const questionBias = learner.questionBias[question.id] || 0;

  const rawAbility =
    learner.overallTheta +
    domainTheta * 0.75 +
    conceptTheta * 0.82 -
    question.base_difficulty * 1.9 -
    questionBias;

  const knowledgeProb = sigmoid(rawAbility);
  const masteryProb = clamp(0.18 + knowledgeProb * 0.82, 0.18, 0.98);
  const halfLifeHours = record.halfLifeHours || initialHalfLife(question);
  const elapsedHours = record.lastSeenAt ? Math.max(0, (atMs - new Date(record.lastSeenAt).getTime()) / 3600000) : 0;
  const retrievability = record.lastSeenAt ? Math.pow(0.5, elapsedHours / halfLifeHours) : 1;
  const predictedRecall = clamp(masteryProb * retrievability, 0.03, 0.99);
  const nextDueHours = dueIntervalHours(halfLifeHours);
  const dueAtMs = record.lastSeenAt ? new Date(record.lastSeenAt).getTime() + nextDueHours * 3600000 : atMs;
  const dueInHours = (dueAtMs - atMs) / 3600000;

  return {
    knowledgeProb,
    masteryProb,
    retrievability,
    predictedRecall,
    halfLifeHours,
    elapsedHours,
    dueAtMs,
    dueInHours,
    domainTheta,
    conceptTheta,
    questionBias,
  };
}

function domainReadinessRows() {
  return state.dataset.domains.map((domain) => {
    const questions = state.dataset.questions.filter((question) => question.domain_key === domain.domain_key);
    const models = questions.map((question) => questionModel(question));
    const attempts = questions.map((question) => attemptRecord(question.id));
    const reviewed = attempts.filter((record) => record.total > 0).length;
    const totalAttempts = attempts.reduce((sum, record) => sum + record.total, 0);
    const correctAttempts = attempts.reduce((sum, record) => sum + record.correct, 0);
    const empiricalAccuracy = totalAttempts ? correctAttempts / totalAttempts : 0;
    const predictedMastery = average(models.map((model) => model.masteryProb), 0.42);
    const predictedRecall = average(models.map((model) => model.predictedRecall), 0.42);
    const dueNow = questions.filter((question, index) => attempts[index].total > 0 && models[index].dueInHours <= 0).length;
    const readiness = predictedMastery * 0.68 + empiricalAccuracy * 0.18 + predictedRecall * 0.14;
    return {
      ...domain,
      reviewed,
      totalAttempts,
      empiricalAccuracy,
      predictedMastery,
      predictedRecall,
      dueNow,
      readiness,
    };
  });
}

function conceptRows() {
  const counts = new Map();
  state.dataset.questions.forEach((question) => {
    question.concept_tags.forEach((tag) => {
      if (!counts.has(tag)) counts.set(tag, []);
      counts.get(tag).push(question);
    });
  });

  return [...counts.entries()]
    .map(([tag, questions]) => {
      const theta = state.user.learner.conceptTheta[tag] || 0;
      const mastery = masteryFromTheta(theta);
      const dueNow = questions.filter((question) => {
        const record = attemptRecord(question.id);
        if (record.total === 0) return false;
        return questionModel(question).dueInHours <= 0;
      }).length;
      const seen = questions.filter((question) => attemptRecord(question.id).total > 0).length;
      const examMass = average(questions.map((question) => question.exam_weight), 0.15);
      return {
        tag,
        label: conceptLabelJa(tag),
        mastery,
        dueNow,
        seen,
        total: questions.length,
        examMass,
      };
    })
    .sort((a, b) => a.mastery - b.mastery || b.examMass - a.examMass);
}

function weightedReadiness() {
  return domainReadinessRows().reduce((sum, row) => sum + row.readiness * row.weight, 0);
}

function reviewedStats() {
  const attempts = Object.values(state.user.attempts);
  return {
    reviewed: attempts.filter((record) => record.total > 0).length,
    totalAttempts: attempts.reduce((sum, record) => sum + record.total, 0),
    dueNow: Object.keys(state.user.attempts).filter((questionId) => {
      const record = attemptRecord(questionId);
      return record.total > 0 && questionModel(questionById(questionId)).dueInHours <= 0;
    }).length,
  };
}

function passProbability() {
  const rows = domainReadinessRows();
  const readiness = rows.reduce((sum, row) => sum + row.readiness * row.weight, 0);
  const { reviewed } = reviewedStats();
  const coverage = reviewed / state.dataset.meta.curated_count;
  return clamp(0.26 + readiness * 0.56 + coverage * 0.18, 0.18, 0.98);
}

function sprintDay() {
  const started = new Date(state.user.startedAt || new Date().toISOString());
  const today = new Date();
  const diff = today.setHours(0, 0, 0, 0) - started.setHours(0, 0, 0, 0);
  const day = Math.floor(diff / (24 * 60 * 60 * 1000)) + 1;
  return Math.min(state.dataset.plan.days, Math.max(1, day));
}

function todayPlan() {
  return state.dataset.plan.schedule[sprintDay() - 1];
}

function adaptiveTodaySummary() {
  const baseline = todayPlan();
  const rows = domainReadinessRows().sort((a, b) => a.readiness - b.readiness);
  const weakDomains = rows.slice(0, 3);
  const { dueNow } = reviewedStats();
  const hours = state.dataset.meta.daily_hours;
  const baseBudget = Math.round(hours * 8.5);
  const target = clamp(baseBudget + Math.round(dueNow * 0.3), 18, 32);
  const reviewTarget = clamp(Math.round(target * 0.46 + dueNow * 0.25), 8, 18);
  const newTarget = Math.max(8, target - reviewTarget);
  return {
    target,
    reviewTarget,
    newTarget,
    dueNow,
    weakDomains,
    baseline,
  };
}

function currentDomainMode() {
  return els["drill-mode"].value === "focus" ? els["domain-filter"].value : null;
}

function recommendationForQuestion(question, domainKey = null, domainLookup = null) {
  const model = questionModel(question);
  const record = attemptRecord(question.id);
  const domain = domainByKey(question.domain_key);
  const rows =
    domainLookup ||
    Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const domainReadiness = rows[question.domain_key]?.readiness || 0.4;
  const weakConceptPenalty = average(
    question.concept_tags.map((tag) => 1 - masteryFromTheta(state.user.learner.conceptTheta[tag] || 0)),
    0.35
  );
  const dueUrgency = record.total > 0 ? clamp((-model.dueInHours + 6) / 24, -0.2, 1.3) : 0.18;
  const sweetSpot = clamp(1 - Math.abs(model.predictedRecall - 0.58) / 0.58, 0, 1);
  const unseenBoost = record.total === 0 ? 0.34 : 0;
  const difficultyFit = clamp(1 - Math.abs(model.knowledgeProb - 0.63) / 0.63, 0, 1);
  const focusBoost = domainKey && domainKey === question.domain_key ? 0.3 : 0;

  const score =
    question.yield_score * 0.55 +
    sweetSpot * 24 +
    weakConceptPenalty * 18 +
    (1 - domainReadiness) * 18 +
    dueUrgency * 20 +
    unseenBoost * 18 +
    difficultyFit * 12 +
    question.current_relevance_score * 14 +
    domain.weight * 18 +
    focusBoost * 10;

  const reasons = [];
  if (record.total > 0 && model.dueInHours <= 0) reasons.push("忘却曲線上、今が復習タイミング");
  if (sweetSpot >= 0.72) reasons.push("今解くと伸びしろが最大");
  if (question.current_relevance_score >= 0.45) reasons.push("2026現行トピック");
  if (1 - domainReadiness >= 0.45) reasons.push("弱点ドメインを補強");
  if (record.total === 0) reasons.push("未着手の高優先問題");
  if (!reasons.length) reasons.push("理解度モデル上の最適候補");

  return {
    score,
    reasons,
    model,
    record,
    domainReadiness,
    weakConceptPenalty,
  };
}

function nextRecommendedQuestion(domainKey = null, excludeIds = []) {
  const excluded = new Set(excludeIds);
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const candidates = state.dataset.questions.filter(
    (question) => !excluded.has(question.id) && (!domainKey || question.domain_key === domainKey)
  );
  const ranked = candidates
    .map((question) => ({ question, rec: recommendationForQuestion(question, domainKey, domainLookup) }))
    .sort((a, b) => b.rec.score - a.rec.score || a.question.curated_index - b.question.curated_index);
  return ranked[0] || null;
}

function renderAll() {
  populateDomainFilter();
  renderHero();
  renderDashboard();
  renderPlan();
  renderDrillControls();
  if (state.currentQuestionId) renderCurrentQuestion();
  renderMock();
}

function populateDomainFilter() {
  if (els["domain-filter"].childElementCount > 0) return;
  state.dataset.domains.forEach((domain) => {
    const option = document.createElement("option");
    option.value = domain.domain_key;
    option.textContent = domain.label_ja;
    els["domain-filter"].appendChild(option);
  });
}

function switchView(viewName) {
  els.tabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  els.views.forEach((view) => {
    view.classList.toggle("active", view.id === `view-${viewName}`);
  });
  if (viewName === "mock") renderMock();
}

function renderHero() {
  els["stat-curated"].textContent = `${state.dataset.meta.curated_count}`;
  els["stat-days"].textContent = `${state.dataset.plan.days}日`;
  const adaptiveToday = adaptiveTodaySummary();
  els["stat-today"].textContent = `${adaptiveToday.target}問`;
  els["stat-today-sub"].textContent = `復習 ${adaptiveToday.reviewTarget} / 新規 ${adaptiveToday.newTarget}`;

  const probability = passProbability();
  els["stat-pass"].textContent = `${Math.round(probability * 100)}%`;
  els["stat-pass-sub"].textContent =
    probability >= 0.78 ? "合格圏。再現性を磨け" : probability >= 0.62 ? "届く。弱点を詰めろ" : "まだ甘い。穴を塞げ";
}

function renderDashboard() {
  const adaptiveToday = adaptiveTodaySummary();
  const baseline = adaptiveToday.baseline;
  els["today-badge"].textContent = `Day ${baseline.day}`;
  els["today-card"].innerHTML = "";
  els["today-card"].appendChild(renderTodayBox(adaptiveToday));

  els["selection-policy"].innerHTML = "";
  state.dataset.selection_policy.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    els["selection-policy"].appendChild(li);
  });

  const progress = domainReadinessRows();
  const stats = reviewedStats();
  els["reviewed-count"].textContent = `${stats.reviewed} / ${state.dataset.meta.curated_count}問着手 | 期限切れ ${stats.dueNow}問`;
  els["domain-progress"].innerHTML = "";
  progress.forEach((domain) => {
    els["domain-progress"].appendChild(renderProgressRow(domain));
  });

  renderNextPreview();
  renderModelSummary();
  renderWeakConcepts();
}

function renderTodayBox(summary) {
  const div = document.createElement("div");
  div.className = "today-box";
  div.innerHTML = `
    <strong>${summary.baseline.label} | ${summary.baseline.message}</strong>
    <div>ML目標: ${summary.target}問</div>
    <div>内訳: 復習 ${summary.reviewTarget} / 新規 ${summary.newTarget} / 期限切れ ${summary.dueNow}</div>
    <div>想定時間: 約${state.dataset.meta.daily_hours}時間</div>
    <div>重点分野: ${summary.weakDomains.map((row) => `${row.label_ja} ${Math.round(row.readiness * 100)}%`).join(" / ")}</div>
    <div class="muted">固定計画 ${summary.baseline.new_questions_target + summary.baseline.review_questions_target + summary.baseline.mock_questions}問は目安。今日は理解度モデルを優先する。</div>
  `;
  return div;
}

function renderProgressRow(domain) {
  const wrap = document.createElement("div");
  wrap.className = "progress-row";
  const readiness = Math.round(domain.readiness * 100);
  wrap.innerHTML = `
    <div class="progress-label">
      <span>${domain.label_ja}</span>
      <span>${readiness}% | 期限切れ ${domain.dueNow} | 着手 ${domain.reviewed}/${domain.actual_count}</span>
    </div>
    <div class="bar">
      <div class="bar-fill" style="width:${readiness}%"></div>
    </div>
  `;
  return wrap;
}

function renderModelSummary() {
  const rows = domainReadinessRows().sort((a, b) => a.readiness - b.readiness);
  const readiness = weightedReadiness();
  const probability = passProbability();
  const official = state.dataset.official_context;
  const dueNow = reviewedStats().dueNow;
  els["model-summary"].innerHTML = `
    <div class="today-box">
      <strong>リアルタイム学習モデル</strong>
      <div>総合理解度: ${Math.round(readiness * 100)}%</div>
      <div>推定合格率: ${Math.round(probability * 100)}%</div>
      <div>今すぐ再出題すべき問題: ${dueNow}問</div>
      <div>最弱ドメイン: ${rows.slice(0, 3).map((row) => row.label_ja).join(" / ")}</div>
      <div class="muted">公式前提: CSA Blueprint ${official.exam_blueprint_updated} / Docs ${official.current_release_family} (${official.current_release_updated})</div>
    </div>
  `;
}

function renderWeakConcepts() {
  const weakest = conceptRows().slice(0, 6);
  els["weak-concepts"].innerHTML = "";
  const card = document.createElement("div");
  card.className = "today-box";
  card.innerHTML = `<strong>概念弱点トップ6</strong>`;
  const list = document.createElement("div");
  list.className = "concept-stack";
  weakest.forEach((concept) => {
    const row = document.createElement("div");
    row.className = "concept-row";
    row.innerHTML = `
      <span>${concept.label}</span>
      <span>${Math.round(concept.mastery * 100)}% | 期限切れ ${concept.dueNow}</span>
    `;
    list.appendChild(row);
  });
  card.appendChild(list);
  els["weak-concepts"].appendChild(card);
}

function renderNextPreview() {
  const next = nextRecommendedQuestion(currentDomainMode());
  els["next-preview"].innerHTML = "";
  if (!next) {
    els["next-preview"].innerHTML = "<p>出題候補がない。全部回したなら模試へ行け。</p>";
    return;
  }
  const { question, rec } = next;
  const card = document.createElement("div");
  card.className = "preview-card";
  card.innerHTML = `
    <strong>${question.id} | ${question.domain_label_ja}</strong>
    <div>${question.prompt}</div>
    <div>予測再現率 ${Math.round(rec.model.predictedRecall * 100)}% / 半減期 ${rec.model.halfLifeHours.toFixed(1)}h</div>
    <div class="muted">推奨理由: ${rec.reasons.join(" / ")}</div>
  `;
  els["next-preview"].appendChild(card);
}

function renderDrillControls() {
  const mode = els["drill-mode"].value;
  els["domain-filter"].disabled = mode !== "focus";
  els["drill-status"].textContent = mode === "focus" ? domainLabelJa(els["domain-filter"].value) : "全範囲";
  renderNextPreview();
}

function loadNextDrillQuestion() {
  const next = nextRecommendedQuestion(currentDomainMode(), state.currentQuestionId ? [state.currentQuestionId] : []);
  if (!next) return;
  state.currentQuestionId = next.question.id;
  state.currentSelections = [];
  state.currentQuestionModel = next.rec.model;
  state.hintLevel = 0;
  renderCurrentQuestion();
}

function renderCurrentQuestion() {
  const question = questionById(state.currentQuestionId);
  if (!question) {
    els["question-card"].className = "question-card empty";
    els["question-card"].innerHTML = "<p>次の問題を出せ。</p>";
    return;
  }

  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const rec = recommendationForQuestion(question, currentDomainMode(), domainLookup);
  state.currentQuestionModel = rec.model;
  els["question-meta"].innerHTML = `
    <span class="pill">${question.id}</span>
    <span class="pill">${question.domain_label_ja}</span>
    <span class="pill">予測再現率 ${Math.round(rec.model.predictedRecall * 100)}%</span>
    <span class="pill">半減期 ${rec.model.halfLifeHours.toFixed(1)}h</span>
    <span class="pill">正答数 ${question.choose_count}</span>
  `;

  els["question-rationale"].classList.remove("hidden");
  els["question-rationale"].innerHTML = `
    <strong>ML推薦理由</strong>
    <div>${rec.reasons.join(" / ")}</div>
    <div class="muted">概念: ${question.concept_tags.map(conceptLabelJa).join(" / ") || "未分類"} | 現行トピック: ${question.current_service_tags.map(conceptLabelJa).join(" / ") || "なし"}</div>
  `;

  els["question-card"].className = "question-card";
  els["question-card"].innerHTML = "";
  const prompt = document.createElement("p");
  prompt.className = "question-text";
  prompt.textContent = question.prompt;
  const choiceList = document.createElement("div");
  choiceList.className = "choice-list";

  question.choices.forEach((choice) => {
    const button = document.createElement("button");
    button.className = "choice-button";
    button.type = "button";
    button.dataset.choiceId = choice.id;
    button.innerHTML = `<strong>${choice.id}.</strong> ${choice.text}`;
    button.addEventListener("click", () => toggleSelection(choice.id));
    if (state.currentSelections.includes(choice.id)) button.classList.add("selected");
    choiceList.appendChild(button);
  });

  els["question-card"].append(prompt, choiceList);
  els["hint-button"].disabled = false;
  els["submit-answer"].disabled = state.currentSelections.length === 0;
  els["next-question"].disabled = true;
  els["hint-box"].classList.add("hidden");
  els["result-box"].classList.add("hidden");
  els["hint-box"].innerHTML = "";
  els["result-box"].innerHTML = "";
}

function toggleSelection(choiceId) {
  const question = questionById(state.currentQuestionId);
  if (!question) return;
  if (question.choose_count === 1) {
    state.currentSelections = [choiceId];
  } else if (state.currentSelections.includes(choiceId)) {
    state.currentSelections = state.currentSelections.filter((id) => id !== choiceId);
  } else {
    state.currentSelections = [...state.currentSelections, choiceId];
  }
  document.querySelectorAll("#question-card .choice-button").forEach((button) => {
    button.classList.toggle("selected", state.currentSelections.includes(button.dataset.choiceId));
  });
  els["submit-answer"].disabled = state.currentSelections.length === 0;
}

function revealHint() {
  const question = questionById(state.currentQuestionId);
  if (!question) return;
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const rec = recommendationForQuestion(question, currentDomainMode(), domainLookup);
  state.hintLevel += 1;
  els["hint-box"].classList.remove("hidden");

  const wrongChoice = question.choices.find((choice) => !question.correct_choice_ids.includes(choice.id));
  const hints = [
    `ヒント1: 正答は ${question.choose_count} 個。数を外すな。`,
    `ヒント2: この問題の核は ${question.concept_tags.slice(0, 2).map(conceptLabelJa).join(" / ") || question.domain_label_ja}。`,
    `ヒント3: ${wrongChoice ? `${wrongChoice.id} は切れる可能性が高い。` : "誤答選択肢の根拠を探せ。"}`,
    `ヒント4: 予測再現率 ${Math.round(rec.model.predictedRecall * 100)}% だ。思い出せるギリギリの帯だ。`,
  ];

  els["hint-box"].innerHTML = `
    <strong>ビシビシヒント</strong>
    <div>${hints.slice(0, state.hintLevel).join("<br>")}</div>
  `;

  if (state.hintLevel >= 3 && wrongChoice) {
    const button = document.querySelector(`#question-card .choice-button[data-choice-id="${wrongChoice.id}"]`);
    button?.classList.add("eliminated");
  }
}

function applyAdaptiveUpdate(question, correct, userIds) {
  const learner = state.user.learner;
  const record = attemptRecord(question.id);
  const before = state.currentQuestionModel || questionModel(question);
  const hintsUsed = state.hintLevel;

  const observed = correct
    ? clamp(1 - hintsUsed * 0.12, 0.58, 1)
    : clamp(0.12 + hintsUsed * 0.03, 0.05, 0.28);
  const error = observed - before.knowledgeProb;
  const lr = clamp(BASE_LR - question.base_difficulty * 0.05, 0.12, 0.22);

  learner.overallTheta += error * lr * 0.55;
  learner.domainTheta[question.domain_key] = (learner.domainTheta[question.domain_key] || 0) + error * lr * 0.82;
  question.concept_tags.forEach((tag) => {
    learner.conceptTheta[tag] = (learner.conceptTheta[tag] || 0) + error * lr * (0.9 / Math.max(1, question.concept_tags.length));
  });
  learner.questionBias[question.id] = (learner.questionBias[question.id] || 0) + (-error) * lr * 0.42;

  const prevHalfLife = record.halfLifeHours || initialHalfLife(question);
  const hintFactor = clamp(1 - hintsUsed * 0.08, 0.72, 1);
  const desirableDifficulty = clamp(1 + (0.68 - before.predictedRecall) * 0.45, 0.82, 1.28);

  let nextHalfLife = prevHalfLife;
  if (correct) {
    const growth = 1.34 + before.knowledgeProb * 0.72 + question.current_relevance_score * 0.18;
    nextHalfLife = Math.max(prevHalfLife + 2.5, prevHalfLife * growth * hintFactor * desirableDifficulty);
  } else {
    const shrink = 0.42 + before.knowledgeProb * 0.16;
    nextHalfLife = Math.max(2, prevHalfLife * shrink);
  }

  const nowIso = new Date().toISOString();
  const nextDueHours = dueIntervalHours(nextHalfLife);

  record.total += 1;
  if (correct) {
    record.correct += 1;
    record.streak += 1;
  } else {
    record.streak = 0;
  }
  record.lastAnswer = userIds;
  record.lastResult = correct;
  record.lastSeenAt = nowIso;
  record.lastPredictedRecall = before.predictedRecall;
  record.lastKnowledgeProb = before.knowledgeProb;
  record.lastHintsUsed = hintsUsed;
  record.halfLifeHours = clamp(nextHalfLife, 2, 720);
  record.dueAt = new Date(Date.now() + nextDueHours * 3600000).toISOString();
  record.history = [
    ...record.history,
    {
      at: nowIso,
      correct,
      selectedIds: userIds,
      predictedRecall: before.predictedRecall,
      knowledgeProb: before.knowledgeProb,
      hintsUsed,
      halfLifeHours: record.halfLifeHours,
    },
  ].slice(-30);

  state.user.attempts[question.id] = record;
  saveUserState();

  return {
    before,
    after: questionModel(question),
    record,
    hintsUsed,
  };
}

function submitCurrentQuestion() {
  const question = questionById(state.currentQuestionId);
  if (!question) return;
  const userIds = [...state.currentSelections].sort();
  const correctIds = [...question.correct_choice_ids].sort();
  const correct = JSON.stringify(userIds) === JSON.stringify(correctIds);
  const update = applyAdaptiveUpdate(question, correct, userIds);

  document.querySelectorAll("#question-card .choice-button").forEach((button) => {
    const choiceId = button.dataset.choiceId;
    if (question.correct_choice_ids.includes(choiceId)) button.classList.add("correct");
    if (state.currentSelections.includes(choiceId) && !question.correct_choice_ids.includes(choiceId)) {
      button.classList.add("incorrect");
    }
  });

  const box = els["result-box"];
  box.className = `result-box ${correct ? "good" : "bad"}`;
  box.classList.remove("hidden");
  const coach = correct
    ? "正解。だが偶然なら価値はない。なぜ正しいかを自分の言葉で再構成しろ。"
    : "不正解。理解が雑だ。誤答を切れない理由を放置するな。";
  const nextReview = update.record.halfLifeHours * (Math.log(TARGET_RECALL) / Math.log(0.5));
  box.innerHTML = `
    <strong>${correct ? "正解" : "不正解"} | 正答 ${correctIds.join(",")}</strong>
    <div>${coach}</div>
    <div>モデル更新: 再現率予測 ${Math.round(update.before.predictedRecall * 100)}% → ${Math.round(update.after.predictedRecall * 100)}%</div>
    <div>記憶半減期: ${update.before.halfLifeHours.toFixed(1)}h → ${update.record.halfLifeHours.toFixed(1)}h | 次回推奨 ${nextReview.toFixed(1)}h後</div>
    <div>ヒント使用: ${update.hintsUsed}</div>
    <div>${question.explanation}</div>
    <div>${question.docs.map((url) => `<a href="${url}" target="_blank" rel="noreferrer">公式ドキュメント</a>`).join(" / ")}</div>
  `;

  els["hint-button"].disabled = true;
  els["submit-answer"].disabled = true;
  els["next-question"].disabled = false;
  renderHero();
  renderDashboard();
}

function renderPlan() {
  const adaptive = adaptiveTodaySummary();
  els["plan-summary"].textContent = `固定計画は土台。実運用はML目標 ${adaptive.target}問/日で回す`;
  els["plan-grid"].innerHTML = "";
  const activeDay = sprintDay();
  state.dataset.plan.schedule.forEach((day) => {
    const card = document.createElement("article");
    card.className = `plan-card ${day.day === activeDay ? "active" : ""}`;
    card.innerHTML = `
      <strong>${day.label}</strong>
      <div>${day.message}</div>
      <div>固定: 新規 ${day.new_questions_target} / 復習 ${day.review_questions_target}${day.mock_questions ? ` / 模試 ${day.mock_questions}` : ""}</div>
      <div>重点: ${day.domain_split.map((item) => `${domainLabelJa(item.domain_key)} ${item.count}`).join(" / ") || "復習専念"}</div>
    `;
    els["plan-grid"].appendChild(card);
  });
}

function startMock() {
  const questions = buildMockQuestionSet();
  state.user.mockSession = {
    startedAt: new Date().toISOString(),
    endsAt: new Date(Date.now() + 90 * 60 * 1000).toISOString(),
    questionIds: questions.map((question) => question.id),
    answers: {},
    currentIndex: 0,
    finished: false,
  };
  saveUserState();
  renderMock();
}

function buildMockQuestionSet() {
  const quotas = domainQuotasFor(60);
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const picked = [];
  Object.entries(quotas).forEach(([domainKey, count]) => {
    const pool = state.dataset.questions
      .filter((question) => question.domain_key === domainKey)
      .map((question) => ({ question, rec: recommendationForQuestion(question, null, domainLookup) }))
      .sort((a, b) => b.rec.score - a.rec.score || a.question.curated_index - b.question.curated_index)
      .slice(0, count)
      .map((item) => item.question);
    picked.push(...pool);
  });
  return shuffle(picked).slice(0, 60);
}

function domainQuotasFor(total) {
  const quotas = {};
  let sum = 0;
  const entries = state.dataset.domains.map((domain) => ({
    key: domain.domain_key,
    quota: Math.floor(domain.weight * total),
    fraction: domain.weight * total - Math.floor(domain.weight * total),
  }));
  entries.forEach((entry) => {
    quotas[entry.key] = entry.quota;
    sum += entry.quota;
  });
  entries
    .sort((a, b) => b.fraction - a.fraction)
    .slice(0, total - sum)
    .forEach((entry) => {
      quotas[entry.key] += 1;
    });
  return quotas;
}

function shuffle(items) {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[swap]] = [copy[swap], copy[index]];
  }
  return copy;
}

function renderMock() {
  const session = state.user.mockSession;
  clearInterval(state.mockTimerHandle);
  if (!session) {
    els["mock-progress"].innerHTML = "";
    els["mock-question"].className = "question-card empty";
    els["mock-question"].innerHTML = "<p>模試を開始しろ。</p>";
    els["mock-results"].innerHTML = "<p>模試を完了するとここに結果が出る。</p>";
    setMockButtonsDisabled(true);
    return;
  }

  updateMockTimer();
  state.mockTimerHandle = window.setInterval(updateMockTimer, 1000);

  const currentId = session.questionIds[session.currentIndex];
  const question = questionById(currentId);
  const savedAnswer = session.answers[currentId]?.selectedIds || [];
  renderMockQuestion(question, savedAnswer);

  const answered = Object.keys(session.answers).length;
  els["mock-progress"].innerHTML = `
    <span class="pill">${session.currentIndex + 1} / ${session.questionIds.length}</span>
    <span class="pill">回答済み ${answered}</span>
    <span class="pill">${question.domain_label_ja}</span>
  `;
  setMockButtonsDisabled(false);

  if (session.finished) renderMockResults();
}

function updateMockTimer() {
  const session = state.user.mockSession;
  if (!session) return;
  const remainingMs = new Date(session.endsAt).getTime() - Date.now();
  if (remainingMs <= 0 && !session.finished) {
    finishMock();
    return;
  }
  const totalSeconds = Math.max(0, Math.floor(remainingMs / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  els["mock-timer"].textContent = `${minutes}:${seconds}`;
}

function renderMockQuestion(question, savedAnswer) {
  const wrap = document.createElement("div");
  wrap.id = "mock-question";
  wrap.className = "question-card";
  const prompt = document.createElement("p");
  prompt.className = "question-text";
  prompt.textContent = question.prompt;
  const choices = document.createElement("div");
  choices.className = "choice-list";
  question.choices.forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "choice-button";
    button.dataset.choiceId = choice.id;
    button.classList.toggle("selected", savedAnswer.includes(choice.id));
    button.innerHTML = `<strong>${choice.id}.</strong> ${choice.text}`;
    button.addEventListener("click", () => toggleMockSelection(choice.id, question.choose_count));
    choices.appendChild(button);
  });
  wrap.append(prompt, choices);
  els["mock-question"].replaceWith(wrap);
  els["mock-question"] = wrap;
}

function toggleMockSelection(choiceId, chooseCount) {
  const session = state.user.mockSession;
  if (!session || session.finished) return;
  const currentId = session.questionIds[session.currentIndex];
  const saved = session.answers[currentId]?.selectedIds || [];
  let next = [];
  if (chooseCount === 1) {
    next = [choiceId];
  } else if (saved.includes(choiceId)) {
    next = saved.filter((id) => id !== choiceId);
  } else {
    next = [...saved, choiceId];
  }
  session.answers[currentId] = { selectedIds: next };
  saveUserState();
  document.querySelectorAll("#view-mock .choice-button").forEach((button) => {
    button.classList.toggle("selected", next.includes(button.dataset.choiceId));
  });
}

function saveMockAnswer() {
  saveUserState();
  moveMock(1);
}

function moveMock(delta) {
  const session = state.user.mockSession;
  if (!session) return;
  session.currentIndex = clamp(session.currentIndex + delta, 0, session.questionIds.length - 1);
  saveUserState();
  renderMock();
}

function finishMock() {
  const session = state.user.mockSession;
  if (!session) return;
  session.finished = true;
  saveUserState();
  renderMockResults();
}

function renderMockResults() {
  const session = state.user.mockSession;
  if (!session) return;
  let correct = 0;
  const byDomain = {};
  session.questionIds.forEach((questionId) => {
    const question = questionById(questionId);
    const answer = [...(session.answers[questionId]?.selectedIds || [])].sort();
    const expected = [...question.correct_choice_ids].sort();
    const isCorrect = JSON.stringify(answer) === JSON.stringify(expected);
    if (isCorrect) correct += 1;
    if (!byDomain[question.domain_key]) {
      byDomain[question.domain_key] = { label: question.domain_label_ja, correct: 0, total: 0 };
    }
    byDomain[question.domain_key].total += 1;
    if (isCorrect) byDomain[question.domain_key].correct += 1;
  });

  const score = Math.round((correct / session.questionIds.length) * 100);
  const weakest = Object.values(byDomain)
    .sort((a, b) => a.correct / a.total - b.correct / b.total)
    .slice(0, 3);

  els["mock-results"].innerHTML = `
    <div class="mock-card">
      <strong>模試スコア</strong>
      <div class="mock-score">${score}%</div>
      <div>${correct} / ${session.questionIds.length} 問正解</div>
      <div>弱点: ${weakest.map((item) => `${item.label} ${Math.round((item.correct / item.total) * 100)}%`).join(" / ")}</div>
      <div>${score >= 80 ? "合格圏。だが油断するな。弱点の再現率を安定させろ。" : "まだ甘い。弱点3分野を回してから再受験だ。"}</div>
    </div>
  `;
}

function setMockButtonsDisabled(disabled) {
  els["mock-prev"].disabled = disabled;
  els["mock-save"].disabled = disabled;
  els["mock-next"].disabled = disabled;
}
