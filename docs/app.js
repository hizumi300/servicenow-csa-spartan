const DATA_URL = "./data/csa600.json";
const STORAGE_KEYS = ["csaSpartanState:v4", "csaSpartanState:v3", "csaSpartanState:v2"];
const STORAGE_KEY = STORAGE_KEYS[0];
const TARGET_RECALL = 0.62;
const BASE_LR = 0.18;
const ACTIVE_SET_MIN = 420;
const ACTIVE_SET_MAX = 560;
const ACTIVE_SET_STEP = 20;
const ACTIVE_SET_DEFAULT = 480;
const SHADOW_LOG_LIMIT = 240;
const SHADOW_STORAGE_KEY = "csaSpartanShadow:v1";

const CONFIDENCE_META = {
  confident: { label: "自信あり" },
  unsure: { label: "迷った" },
  guess: { label: "勘" },
};

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
  currentConfidenceKey: null,
  currentQuestionModel: null,
  currentQuestionSource: "active_pool",
  currentContrastiveItem: null,
  currentQuestionLocked: false,
  currentQuestionFeedback: null,
  currentQuestionServedAt: null,
  hintLevel: 0,
  mockTimerHandle: null,
  liveOfficialEvidence: {},
  liveOfficialEvidenceRequests: {},
  officialDocsApiAvailable: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", async () => {
  cacheElements();
  bindEvents();
  await loadDataset();
  loadUserState();
  hydrateShadowLog();
  ensureSprintStart();
  sanitizeUserState();
  renderAll();
  shadowLog("app_ready", {
    questionCount: state.dataset.questions.length,
    activePoolDefault: activePoolConfig().defaultSize,
  });
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
    "confidence-box",
    "contrastive-box",
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
    "mock-strategy-strip",
    "mock-question",
    "mock-confidence-box",
    "mock-prev",
    "mock-save",
    "mock-next",
    "mock-results",
    "plan-grid",
    "plan-summary",
    "active-set-size",
    "active-set-value",
    "active-pool-summary",
    "reset-active-pool",
    "contrastive-summary",
    "delta-mode-summary",
    "shadow-telemetry",
    "export-shadow-log",
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
  els["drill-mode"].addEventListener("change", () => {
    renderDrillControls();
    if (state.currentQuestionId) renderCurrentQuestion();
  });
  els["domain-filter"].addEventListener("change", () => {
    renderDrillControls();
    if (state.currentQuestionId) renderCurrentQuestion();
  });

  els["active-set-size"].addEventListener("input", (event) => {
    els["active-set-value"].textContent = `${nearestActiveWorkingSetSize(Number(event.target.value))}問`;
  });
  els["active-set-size"].addEventListener("change", (event) => {
    updateActiveWorkingSetSize(Number(event.target.value));
  });
  els["reset-active-pool"]?.addEventListener("click", () => resetActiveWorkingSetSize());
  els["export-shadow-log"]?.addEventListener("click", () => exportShadowLog());

  els["start-sprint"].addEventListener("click", () => {
    state.user.startedAt = new Date().toISOString();
    saveUserState();
    renderHero();
    renderDashboard();
    renderPlan();
  });

  els["reset-progress"].addEventListener("click", () => {
    const confirmed = window.confirm("機械学習モデルも履歴も全部消す。本当にやるか。");
    if (!confirmed) return;
    state.user = defaultUserState();
    state.currentQuestionId = null;
    state.currentSelections = [];
    state.currentConfidenceKey = null;
    state.currentQuestionModel = null;
    state.currentQuestionSource = "active_pool";
    state.currentContrastiveItem = null;
    state.currentQuestionLocked = false;
    state.currentQuestionFeedback = null;
    state.currentQuestionServedAt = null;
    state.hintLevel = 0;
    ensureSprintStart();
    saveUserState();
    renderAll();
    shadowLog("progress_reset");
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
  state.questionMap = new Map(
    [...state.dataset.questions]
      .sort((a, b) => a.curated_index - b.curated_index)
      .map((question) => [question.id, question])
  );
  shadowLog("dataset_loaded", {
    questionCount: state.dataset.questions.length,
    deltaQuestionCount: state.dataset.questions.filter((question) => deltaMetadata(question).active).length,
  });
}

function staticOfficialEvidence(question) {
  return question?.official_doc_evidence || null;
}

function officialEvidenceForQuestion(question) {
  return state.liveOfficialEvidence[question.id] || staticOfficialEvidence(question);
}

function officialDocLinks(question) {
  const evidence = officialEvidenceForQuestion(question);
  const links = [];
  if (evidence?.url) links.push(evidence.url);
  (question.docs || []).forEach((url) => {
    if (!links.includes(url)) links.push(url);
  });
  return links;
}

async function ensureLiveOfficialEvidence(question, force = false) {
  if (!question?.id) return;
  if (!force && state.liveOfficialEvidence[question.id]) return;
  if (!force && state.officialDocsApiAvailable === false) return;
  if (state.liveOfficialEvidenceRequests[question.id]) return;

  state.liveOfficialEvidenceRequests[question.id] = true;
  try {
    const response = await fetch(`./api/official-docs?questionId=${encodeURIComponent(question.id)}${force ? "&force=1" : ""}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      if (response.status === 404 && !contentType.includes("application/json")) {
        state.officialDocsApiAvailable = false;
      }
      return;
    }
    const evidence = await response.json();
    if (!evidence?.url) return;
    state.officialDocsApiAvailable = true;
    state.liveOfficialEvidence[question.id] = evidence;
    if (state.currentQuestionId === question.id) renderCurrentQuestion();
    renderDashboard();
  } catch (_error) {
    if (state.officialDocsApiAvailable == null) state.officialDocsApiAvailable = false;
  } finally {
    delete state.liveOfficialEvidenceRequests[question.id];
  }
}

function defaultConfidenceMix() {
  return {
    confident: 0,
    unsure: 0,
    guess: 0,
  };
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
    lastConfidence: null,
    confidenceCounts: defaultConfidenceMix(),
    history: [],
  };
}

function defaultFamilyRecord() {
  return {
    exposures: 0,
    misses: 0,
    unsure: 0,
    guesses: 0,
    confidentMisses: 0,
    lastSeenAt: null,
    lastIncorrectAt: null,
    questionIds: [],
  };
}

function defaultUserState() {
  return {
    version: 4,
    startedAt: null,
    attempts: {},
    learner: {
      overallTheta: 0,
      domainTheta: {},
      conceptTheta: {},
      questionBias: {},
      questionDifficulty: {},
      questionDiscrimination: {},
    },
    bandit: {
      totalPulls: 0,
      arms: {},
    },
    preferences: {
      activeWorkingSetSize: null,
    },
    confusion: {
      families: {},
      pairs: {},
    },
    contrastiveQueue: [],
    mockSession: null,
    analytics: {
      drill: {
        confidenceMix: defaultConfidenceMix(),
      },
      mockHistory: [],
    },
  };
}

function normalizeAttemptRecord(record) {
  return {
    ...defaultAttemptRecord(),
    ...record,
    lastAnswer: Array.isArray(record?.lastAnswer) ? record.lastAnswer : [],
    confidenceCounts: {
      ...defaultConfidenceMix(),
      ...(record?.confidenceCounts || {}),
    },
    history: Array.isArray(record?.history) ? record.history : [],
  };
}

function normalizeContrastiveQueue(queue) {
  if (!Array.isArray(queue)) return [];
  return queue
    .map((item) => {
      if (typeof item === "string") {
        return {
          questionId: item,
          sourceQuestionId: null,
          familyKey: null,
          reason: "未処理の混同キュー",
          intensity: 1,
          queuedAt: null,
        };
      }
      if (!item || typeof item !== "object" || !item.questionId) return null;
      return {
        questionId: item.questionId,
        sourceQuestionId: item.sourceQuestionId || null,
        familyKey: item.familyKey || null,
        reason: item.reason || "未処理の混同キュー",
        intensity: numberOr(item.intensity, 1),
        queuedAt: item.queuedAt || null,
      };
    })
    .filter(Boolean)
    .slice(-16);
}

function normalizeMockSession(session) {
  if (!session || typeof session !== "object") return null;
  const answers = {};
  Object.entries(session.answers || {}).forEach(([questionId, answer]) => {
    answers[questionId] = {
      selectedIds: Array.isArray(answer?.selectedIds) ? answer.selectedIds : [],
      confidenceKey: answer?.confidenceKey || null,
      touchedAt: answer?.touchedAt || null,
      savedAt: answer?.savedAt || null,
      changeCount: numberOr(answer?.changeCount, 0),
    };
  });
  return {
    startedAt: session.startedAt || null,
    endsAt: session.endsAt || null,
    finishedAt: session.finishedAt || null,
    questionIds: Array.isArray(session.questionIds) ? session.questionIds : [],
    answers,
    currentIndex: numberOr(session.currentIndex, 0),
    finished: Boolean(session.finished),
    summary: session.summary || null,
  };
}

function migrateState(raw) {
  const base = defaultUserState();
  const next = {
    ...base,
    ...raw,
    learner: {
      ...base.learner,
      ...(raw?.learner || {}),
      questionDifficulty: {
        ...base.learner.questionDifficulty,
        ...(raw?.learner?.questionDifficulty || {}),
      },
      questionDiscrimination: {
        ...base.learner.questionDiscrimination,
        ...(raw?.learner?.questionDiscrimination || {}),
      },
    },
    bandit: {
      ...base.bandit,
      ...(raw?.bandit || {}),
      arms: {
        ...base.bandit.arms,
        ...(raw?.bandit?.arms || {}),
      },
    },
    preferences: {
      ...base.preferences,
      ...(raw?.preferences || {}),
    },
    confusion: {
      ...base.confusion,
      ...(raw?.confusion || {}),
      families: {
        ...base.confusion.families,
        ...(raw?.confusion?.families || {}),
      },
      pairs: {
        ...base.confusion.pairs,
        ...(raw?.confusion?.pairs || {}),
      },
    },
    analytics: {
      ...base.analytics,
      ...(raw?.analytics || {}),
      drill: {
        ...base.analytics.drill,
        ...(raw?.analytics?.drill || {}),
        confidenceMix: {
          ...base.analytics.drill.confidenceMix,
          ...(raw?.analytics?.drill?.confidenceMix || {}),
        },
      },
      mockHistory: Array.isArray(raw?.analytics?.mockHistory) ? raw.analytics.mockHistory : [],
    },
  };

  next.attempts = Object.fromEntries(
    Object.entries(raw?.attempts || {}).map(([questionId, record]) => [questionId, normalizeAttemptRecord(record)])
  );

  next.confusion.families = Object.fromEntries(
    Object.entries(next.confusion.families || {}).map(([key, value]) => [
      key,
      {
        ...defaultFamilyRecord(),
        ...value,
        questionIds: Array.isArray(value?.questionIds) ? value.questionIds : [],
      },
    ])
  );

  next.contrastiveQueue = normalizeContrastiveQueue(raw?.contrastiveQueue);
  next.mockSession = normalizeMockSession(raw?.mockSession);
  next.version = 4;
  return next;
}

function loadUserState() {
  for (const key of STORAGE_KEYS) {
    const raw = window.localStorage.getItem(key);
    if (!raw) continue;
    try {
      state.user = migrateState(JSON.parse(raw));
      return;
    } catch {
      continue;
    }
  }
  state.user = defaultUserState();
}

function saveUserState() {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.user));
}

function hydrateShadowLog() {
  try {
    const raw = window.localStorage.getItem(SHADOW_STORAGE_KEY);
    window.__CSA_SHADOW_LOG__ = raw ? JSON.parse(raw) : [];
  } catch {
    window.__CSA_SHADOW_LOG__ = [];
  }
}

function sanitizeUserState() {
  state.user.contrastiveQueue = state.user.contrastiveQueue.filter((item) => questionById(item.questionId));
  if (state.user.mockSession) {
    state.user.mockSession.questionIds = state.user.mockSession.questionIds.filter((questionId) => questionById(questionId));
    if (!state.user.mockSession.questionIds.length) {
      state.user.mockSession = null;
    }
  }
  saveUserState();
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

function numberOr(value, fallback) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function dueIntervalHours(halfLifeHours, targetRecall = TARGET_RECALL) {
  return halfLifeHours * (Math.log(targetRecall) / Math.log(0.5));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

function nowIso() {
  return new Date().toISOString();
}

function hoursSince(iso) {
  if (!iso) return Number.POSITIVE_INFINITY;
  return Math.max(0, (Date.now() - new Date(iso).getTime()) / 3600000);
}

function textBits(value) {
  if (typeof value === "string") {
    return value.trim() ? [value.trim()] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => textBits(item));
  }
  if (value && typeof value === "object") {
    return Object.values(value).flatMap((item) => textBits(item));
  }
  return [];
}

function shortSnippet(value, max = 84) {
  const text = String(value ?? "").trim().replaceAll(/\s+/g, " ");
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function intersectionCount(left, right) {
  const rightSet = new Set(right);
  return left.filter((item) => rightSet.has(item)).length;
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

function confidenceLabel(key, correct = null) {
  if (key === "guess" && correct === true) return "当てた";
  if (key === "guess" && correct === false) return "勘で外した";
  return CONFIDENCE_META[key]?.label || "未設定";
}

function confidenceChoicesForMock() {
  return [
    { key: "confident", label: "自信あり" },
    { key: "unsure", label: "迷った" },
    { key: "guess", label: "勘" },
  ];
}

function defaultBanditArm() {
  return {
    pulls: 0,
    rewardSum: 0,
    correctSum: 0,
    recentRewards: [],
  };
}

function banditArm(key) {
  return state.user.bandit.arms[key] || defaultBanditArm();
}

function banditContextKeys(question) {
  const keys = [
    `question:${question.id}`,
    `domain:${question.domain_key}`,
    question.confusion_family ? `family:${question.confusion_family}` : null,
    question.canonical_id ? `canonical:${question.canonical_id}` : null,
    ...(question.concept_tags || []).slice(0, 3).map((tag) => `concept:${tag}`),
  ];
  return unique(keys);
}

function banditDetailForQuestion(question, signals = null) {
  const detail = signals || questionSignals(question);
  const totalPulls = Math.max(1, state.user.bandit.totalPulls || 0);
  const contexts = banditContextKeys(question);
  const weighted = contexts.map((key, index) => {
    const arm = banditArm(key);
    const meanReward = arm.pulls ? arm.rewardSum / arm.pulls : 0.56;
    const uncertainty = Math.sqrt((2 * Math.log(totalPulls + 2)) / (arm.pulls + 1));
    const weight = index === 0 ? 0.34 : key.startsWith("family:") ? 0.2 : key.startsWith("concept:") ? 0.15 : 0.11;
    return {
      key,
      weight,
      meanReward,
      uncertainty,
    };
  });

  const weightSum = weighted.reduce((sum, item) => sum + item.weight, 0) || 1;
  const expectedReward = weighted.reduce((sum, item) => sum + item.meanReward * item.weight, 0) / weightSum;
  const uncertaintyBonus = weighted.reduce((sum, item) => sum + item.uncertainty * item.weight, 0) / weightSum;
  const irtGainPotential =
    clamp(1 - Math.abs(detail.model.knowledgeProb - 0.64) / 0.64, 0, 1) * 0.42 +
    clamp(1 - detail.model.predictedRecall, 0, 1) * 0.38 +
    detail.confusionPressure * 0.12 +
    detail.confidencePressure * 0.08 +
    detail.shadowBoost * 0.12;

  return {
    contexts,
    expectedReward,
    uncertaintyBonus,
    irtGainPotential,
    score: expectedReward * 22 + uncertaintyBonus * 16 + irtGainPotential * 28,
  };
}

function updateBanditState(question, reward, correct) {
  state.user.bandit.totalPulls = (state.user.bandit.totalPulls || 0) + 1;
  banditContextKeys(question).forEach((key) => {
    const arm = {
      ...defaultBanditArm(),
      ...banditArm(key),
    };
    arm.pulls += 1;
    arm.rewardSum += reward;
    arm.correctSum += correct ? 1 : 0;
    arm.recentRewards = [...(arm.recentRewards || []), reward].slice(-12);
    state.user.bandit.arms[key] = arm;
  });
}

function activePoolConfig() {
  const raw =
    state.dataset?.active_pool ||
    state.dataset?.active_pool_config ||
    state.dataset?.meta?.active_pool ||
    state.dataset?.meta?.active_pool_config ||
    state.dataset?.meta?.active_pool_bounds ||
    {};
  return {
    min: nearestActiveWorkingSetSize(raw.min_size ?? raw.min ?? ACTIVE_SET_MIN),
    max: nearestActiveWorkingSetSize(raw.max_size ?? raw.max ?? ACTIVE_SET_MAX),
    step: ACTIVE_SET_STEP,
    defaultSize: nearestActiveWorkingSetSize(
      raw.default_size ?? raw.default ?? raw.size ?? state.dataset?.meta?.active_pool_default ?? ACTIVE_SET_DEFAULT
    ),
  };
}

function nearestActiveWorkingSetSize(value) {
  const size = Number.isFinite(Number(value)) ? Number(value) : ACTIVE_SET_DEFAULT;
  const rounded = Math.round((size - ACTIVE_SET_MIN) / ACTIVE_SET_STEP) * ACTIVE_SET_STEP + ACTIVE_SET_MIN;
  return clamp(rounded, ACTIVE_SET_MIN, ACTIVE_SET_MAX);
}

function activeWorkingSetRecommendation() {
  const config = activePoolConfig();
  const stats = reviewedStats();
  const confidence = recentConfidenceStats();
  const concepts = conceptRows();
  const pass = passProbability();
  const uncoveredCore = concepts.filter((row) => row.seen === 0 && row.examMass >= 0.16).length;
  const weakLowCoverage = concepts.filter((row) => row.mastery < 0.58 && row.seen < 2).length;
  const backlog = state.user.contrastiveQueue.length;

  let size = config.defaultSize;
  const reasons = [];

  if (stats.dueNow >= 18) {
    size -= Math.min(70, stats.dueNow * 2.2);
    reasons.push(`期限切れ ${stats.dueNow}問が多いので圧縮`);
  }
  if (confidence.confidentWrong >= 3) {
    size -= Math.min(50, confidence.confidentWrong * 8);
    reasons.push(`自信あり誤答 ${confidence.confidentWrong}件を先に矯正`);
  }
  if (backlog >= 6) {
    size -= Math.min(30, backlog * 2.6);
    reasons.push(`混同 backlog ${backlog}件を先に回収`);
  }
  if (uncoveredCore >= 3 || weakLowCoverage >= 6) {
    size += Math.min(60, uncoveredCore * 7 + weakLowCoverage * 2.5);
    reasons.push(`未カバー概念 ${uncoveredCore} / 薄い弱点 ${weakLowCoverage} を広めに拾う`);
  }
  if (pass >= 0.7 && stats.dueNow < 12 && confidence.confidentWrong < 3) {
    size += 40;
    reasons.push("合格圏に近いので裾野を広げる");
  }

  const recommended = clamp(nearestActiveWorkingSetSize(size), config.min, config.max);
  return {
    recommended,
    dueNow: stats.dueNow,
    uncoveredCore,
    weakLowCoverage,
    confidentWrong: confidence.confidentWrong,
    backlog,
    pass,
    reasons: reasons.length ? reasons : ["現在は標準レンジで維持"],
  };
}

function activeWorkingSetSize() {
  const preferred = state.user?.preferences?.activeWorkingSetSize;
  if (preferred != null) {
    const config = activePoolConfig();
    return clamp(nearestActiveWorkingSetSize(preferred), config.min, config.max);
  }
  return activeWorkingSetRecommendation().recommended;
}

function updateActiveWorkingSetSize(value) {
  state.user.preferences.activeWorkingSetSize = nearestActiveWorkingSetSize(value);
  saveUserState();
  renderHero();
  renderDashboard();
  renderPlan();
  renderDrillControls();
  if (state.currentQuestionId) renderCurrentQuestion();
  shadowLog("active_pool_resized", { size: activeWorkingSetSize() });
}

function resetActiveWorkingSetSize() {
  state.user.preferences.activeWorkingSetSize = null;
  saveUserState();
  renderAll();
  shadowLog("active_pool_reset", { size: activeWorkingSetSize() });
}

function shadowModelSummary() {
  return state.dataset?.shadow_model || {
    promoted: false,
    active_model: "baseline",
    champion_model: "baseline",
    promotion_reason: "shadow training 未実行",
    valid_examples: 0,
    metrics: null,
  };
}

function shadowRuntimeForQuestion(question) {
  return question?.shadow_runtime || null;
}

function syncActiveSetControl() {
  const config = activePoolConfig();
  const size = activeWorkingSetSize();
  els["active-set-size"].min = String(config.min);
  els["active-set-size"].max = String(config.max);
  els["active-set-size"].step = String(config.step);
  els["active-set-size"].value = String(size);
  els["active-set-value"].textContent = `${size}問`;
}

function attemptRecord(questionId) {
  return state.user.attempts[questionId] || defaultAttemptRecord();
}

function masteryFromTheta(theta) {
  return sigmoid(theta);
}

function initialHalfLife(question) {
  let halfLife = 8;
  halfLife += (question.current_relevance_score || 0) * 5;
  halfLife += question.multi_select ? 2 : 0;
  halfLife += (question.concept_tags?.length || 0) * 0.6;
  if (deltaMetadata(question).active) halfLife += 1.1;
  return clamp(halfLife, 6, 20);
}

function questionModel(question, atMs = Date.now()) {
  const learner = state.user.learner;
  const record = attemptRecord(question.id);
  const shadowSummary = shadowModelSummary();
  const shadowRuntime = shadowRuntimeForQuestion(question);
  const domainTheta = learner.domainTheta[question.domain_key] || 0;
  const conceptThetas = (question.concept_tags || []).map((tag) => learner.conceptTheta[tag] || 0);
  const conceptTheta = average(conceptThetas, 0);
  const questionBias = learner.questionBias[question.id] || 0;
  const adaptiveDifficulty = question.irt_difficulty ?? question.base_difficulty ?? 0.5;
  const adaptiveDiscrimination = question.irt_discrimination ?? 1.0;
  const adaptiveGuess = question.irt_guess ?? 0.08;
  const difficultyDrift = learner.questionDifficulty[question.id] || 0;
  const discriminationDrift = learner.questionDiscrimination[question.id] || 0;
  const effectiveDifficulty = clamp(adaptiveDifficulty + difficultyDrift, 0.18, 1.15);
  const effectiveDiscrimination = clamp(adaptiveDiscrimination + discriminationDrift, 0.75, 2.6);

  const rawAbility =
    learner.overallTheta +
    domainTheta * 0.78 +
    conceptTheta * 0.86 -
    effectiveDifficulty * 1.9 -
    questionBias * 0.35;

  const latentProb = sigmoid(effectiveDiscrimination * rawAbility);
  let knowledgeProb = clamp(adaptiveGuess + (1 - adaptiveGuess) * latentProb, 0.03, 0.99);
  const shadowPromoted = Boolean(shadowSummary.promoted && shadowRuntime?.promoted && shadowSummary.active_model !== "baseline");
  const shadowPredictedSuccess = shadowPromoted ? clamp(numberOr(shadowRuntime.predicted_success, knowledgeProb), 0.03, 0.99) : null;
  const shadowUncertainty = shadowPromoted ? clamp(numberOr(shadowRuntime.uncertainty, 0.45), 0, 1.4) : null;
  const shadowOpportunity = shadowPromoted ? clamp(numberOr(shadowRuntime.opportunity, 0.4), 0, 1.5) : 0;
  if (shadowPromoted && shadowPredictedSuccess != null) {
    const blend = clamp(0.16 + (1 - (shadowUncertainty || 0.5)) * 0.24, 0.16, 0.38);
    knowledgeProb = clamp(knowledgeProb * (1 - blend) + shadowPredictedSuccess * blend, 0.03, 0.99);
  }
  const masteryProb = clamp(0.14 + knowledgeProb * 0.86, 0.14, 0.99);
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
    irtDifficulty: effectiveDifficulty,
    irtDiscrimination: effectiveDiscrimination,
    irtGuess: adaptiveGuess,
    uncertainty: 1 / Math.sqrt(record.total + 1),
    shadowPromoted,
    shadowModel: shadowSummary.active_model,
    shadowPredictedSuccess,
    shadowUncertainty,
    shadowOpportunity,
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
    const confidenceGap = average(
      attempts.map((record) => {
        const total = (record.confidenceCounts?.confident || 0) + (record.confidenceCounts?.unsure || 0) + (record.confidenceCounts?.guess || 0);
        return total ? ((record.confidenceCounts?.confident || 0) + (record.confidenceCounts?.guess || 0)) / total : 0;
      }),
      0
    );
    const readiness = predictedMastery * 0.64 + empiricalAccuracy * 0.18 + predictedRecall * 0.12 - confidenceGap * 0.06;
    return {
      ...domain,
      reviewed,
      totalAttempts,
      empiricalAccuracy,
      predictedMastery,
      predictedRecall,
      dueNow,
      readiness: clamp(readiness, 0.08, 0.98),
    };
  });
}

function conceptRows() {
  const counts = new Map();
  state.dataset.questions.forEach((question) => {
    (question.concept_tags || []).forEach((tag) => {
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

function reviewedStats() {
  const attempts = Object.entries(state.user.attempts);
  return {
    reviewed: attempts.filter(([, record]) => record.total > 0).length,
    totalAttempts: attempts.reduce((sum, [, record]) => sum + record.total, 0),
    dueNow: attempts.filter(([questionId, record]) => {
      const question = questionById(questionId);
      return question && record.total > 0 && questionModel(question).dueInHours <= 0;
    }).length,
  };
}

function weightedReadiness() {
  return domainReadinessRows().reduce((sum, row) => sum + row.readiness * row.weight, 0);
}

function passProbability() {
  const rows = domainReadinessRows();
  const readiness = rows.reduce((sum, row) => sum + row.readiness * row.weight, 0);
  const { reviewed } = reviewedStats();
  const coverage = reviewed / state.dataset.meta.curated_count;
  const confusionLoad = average(
    Object.values(state.user.confusion.families).map((family) => {
      const exposures = family.exposures || 0;
      if (!exposures) return 0;
      return (family.misses + family.confidentMisses * 0.6) / exposures;
    }),
    0
  );
  return clamp(0.24 + readiness * 0.56 + coverage * 0.18 - confusionLoad * 0.08, 0.16, 0.98);
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
  const activeSetOffset = Math.round((activeWorkingSetSize() - ACTIVE_SET_DEFAULT) / 20);
  const target = clamp(baseBudget + Math.round(dueNow * 0.3) + activeSetOffset, 18, 34);
  const reviewTarget = clamp(Math.round(target * 0.46 + dueNow * 0.25), 8, 20);
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

function currentDrillMode() {
  return els["drill-mode"].value;
}

function currentDomainMode() {
  return currentDrillMode() === "focus" ? els["domain-filter"].value : null;
}

function questionDiversityKey(question) {
  return (
    question.duplicate_group_id ||
    question.canonical_id ||
    question.signature ||
    question.cluster_key ||
    question.semantic_cluster_id ||
    question.id
  );
}

function confusionGroupKeys(question) {
  const keys = [
    question.confusion_family ? `family:${question.confusion_family}` : null,
    question.semantic_cluster_id ? `cluster:${question.semantic_cluster_id}` : null,
    question.duplicate_group_id ? `dup:${question.duplicate_group_id}` : null,
    question.canonical_id ? `canon:${question.canonical_id}` : null,
    question.cluster_key ? `cluster-key:${question.cluster_key}` : null,
  ];
  const conceptKey = unique([...(question.concept_tags || [])].sort()).slice(0, 2).join("|");
  if (conceptKey) keys.push(`concept:${question.domain_key}:${conceptKey}`);
  return unique(keys);
}

function primaryConfusionKey(question) {
  return confusionGroupKeys(question)[0] || `domain:${question.domain_key}`;
}

function familyStatsForQuestion(question) {
  const key = primaryConfusionKey(question);
  return {
    key,
    ...(state.user.confusion.families[key] || defaultFamilyRecord()),
  };
}

function deltaMetadata(question) {
  const raw = question.delta_mode_metadata ?? question.delta_mode ?? null;
  const fallbackActive = Boolean((question.current_service_tags || []).length && (question.current_relevance_score || 0) >= 0.3);
  if (!raw && !fallbackActive) {
    return {
      active: false,
      priority: 0,
      label: null,
      reason: null,
      releaseFamily: state.dataset?.official_context?.current_release_family || null,
      snippets: [],
      basis: [],
    };
  }

  const objectLike = raw && typeof raw === "object" ? raw : {};
  const active = typeof raw === "boolean" ? raw : objectLike.active ?? objectLike.enabled ?? true;
  const releaseFamily =
    objectLike.release_family ||
    objectLike.releaseFamily ||
    state.dataset?.official_context?.current_release_family ||
    null;
  const label =
    (typeof raw === "string" ? raw : null) ||
    objectLike.label ||
    objectLike.mode ||
    objectLike.summary ||
    (fallbackActive ? `${releaseFamily || "現行"}差分` : null);
  const reason =
    objectLike.reason ||
    objectLike.summary ||
    unique((question.current_service_tags || []).map((tag) => conceptLabelJa(tag))).join(" / ") ||
    null;
  const priority = clamp(
    numberOr(objectLike.priority, numberOr(objectLike.score, question.current_relevance_score || 0.25)),
    0,
    1.6
  );

  return {
    active: Boolean(active),
    priority,
    label,
    reason,
    releaseFamily,
    snippets: textBits(question.root_snippet || objectLike.root_snippet).slice(0, 2),
    basis: textBits(question.doc_basis || objectLike.doc_basis).slice(0, 2),
  };
}

function confidencePressureForQuestion(question) {
  const record = attemptRecord(question.id);
  const recent = (record.history || []).slice(-8);
  if (!recent.length) return 0;

  const pressure = recent.reduce((sum, entry) => {
    if (entry.confidenceKey === "confident" && entry.correct === false) return sum + 1.12;
    if (entry.confidenceKey === "guess" && entry.correct === true) return sum + 0.78;
    if (entry.confidenceKey === "unsure") return sum + 0.42;
    if (entry.confidenceKey === "confident" && entry.correct === true) return sum - 0.22;
    return sum;
  }, 0);

  return clamp(pressure / recent.length, 0, 1.35);
}

function confusionPressureForQuestion(question) {
  const family = familyStatsForQuestion(question);
  const exposures = family.exposures || 0;
  if (!exposures) return state.user.contrastiveQueue.some((item) => item.questionId === question.id) ? 0.42 : 0;

  const queueBoost = state.user.contrastiveQueue.some((item) => item.questionId === question.id) ? 0.42 : 0;
  const missRate = (family.misses + family.guesses * 0.7 + family.unsure * 0.4) / exposures;
  const confidentMissRate = (family.confidentMisses || 0) / exposures;
  const recencyBoost = family.lastIncorrectAt ? clamp((72 - hoursSince(family.lastIncorrectAt)) / 72, 0, 1) * 0.34 : 0;
  return clamp(missRate + confidentMissRate * 0.7 + recencyBoost + queueBoost, 0, 1.6);
}

function questionSignals(question, domainKey = null, domainLookup = null) {
  const model = questionModel(question);
  const record = attemptRecord(question.id);
  const rows = domainLookup || Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const domain = domainByKey(question.domain_key);
  const domainReadiness = rows[question.domain_key]?.readiness || 0.4;
  const weakConceptPenalty = average(
    (question.concept_tags || []).map((tag) => 1 - masteryFromTheta(state.user.learner.conceptTheta[tag] || 0)),
    0.35
  );
  const dueUrgency = record.total > 0 ? clamp((-model.dueInHours + 8) / 30, -0.12, 1.3) : 0.16;
  const sweetSpot = clamp(1 - Math.abs(model.predictedRecall - 0.58) / 0.58, 0, 1);
  const unseenBoost = record.total === 0 ? 0.34 : 0;
  const difficultyFit = clamp(1 - Math.abs(model.knowledgeProb - 0.63) / 0.63, 0, 1);
  const focusBoost = domainKey && domainKey === question.domain_key ? 0.3 : 0;
  const confidencePressure = confidencePressureForQuestion(question);
  const confusionPressure = confusionPressureForQuestion(question);
  const delta = deltaMetadata(question);
  const deltaBoost = delta.active ? clamp(delta.priority, 0.18, 1.3) : 0;
  const shadowBoost = model.shadowPromoted ? clamp(model.shadowOpportunity || 0, 0, 1.5) : 0;

  return {
    model,
    record,
    domain,
    domainReadiness,
    weakConceptPenalty,
    dueUrgency,
    sweetSpot,
    unseenBoost,
    difficultyFit,
    focusBoost,
    confidencePressure,
    confusionPressure,
    delta,
    deltaBoost,
    shadowBoost,
  };
}

function backendActivePoolScore(question) {
  const value = question.active_pool_score;
  if (!Number.isFinite(Number(value))) return null;
  const numeric = Number(value);
  return numeric <= 1.5 ? numeric * 100 : numeric;
}

function activePoolScoreForQuestion(question, signals = null) {
  const detail = signals || questionSignals(question);
  const backendScore = backendActivePoolScore(question);
  const computedScore =
    question.yield_score * 0.44 +
    detail.dueUrgency * 22 +
    detail.weakConceptPenalty * 18 +
    (1 - detail.domainReadiness) * 16 +
    detail.confidencePressure * 18 +
    detail.confusionPressure * 20 +
    (question.current_relevance_score || 0) * 18 +
    detail.unseenBoost * 12 +
    detail.deltaBoost * 10 +
    detail.domain.weight * 16;

  const score = backendScore == null ? computedScore : backendScore * 0.72 + computedScore * 0.28;
  return {
    score,
    backendScore,
  };
}

function recommendationForQuestion(question, domainKey = null, domainLookup = null, options = {}) {
  const detail = questionSignals(question, domainKey, domainLookup);
  const poolInfo = activePoolScoreForQuestion(question, detail);
  const bandit = banditDetailForQuestion(question, detail);
  const contrastiveItem = state.user.contrastiveQueue.find((item) => item.questionId === question.id) || null;
  const contrastiveBoost = contrastiveItem ? 0.72 : 0;
  const contrastiveMode = options.mode === "contrastive";

  const score =
    poolInfo.score * 0.66 +
    detail.sweetSpot * 24 +
    detail.dueUrgency * 18 +
    detail.difficultyFit * 12 +
    detail.focusBoost * 12 +
    detail.confidencePressure * 10 +
    detail.confusionPressure * 12 +
    (question.current_relevance_score || 0) * 12 +
    detail.deltaBoost * 12 +
    detail.shadowBoost * 16 +
    bandit.score +
    contrastiveBoost * 22 +
    (contrastiveMode ? detail.confusionPressure * 18 + contrastiveBoost * 18 : 0);

  const reasons = [];
  if (contrastiveItem) reasons.push(`混同対比: ${contrastiveItem.reason}`);
  if (detail.confusionPressure >= 0.72) reasons.push("混同ファミリーの取り違えを矯正");
  if (detail.confidencePressure >= 0.62) reasons.push("自信と実力のズレを補正");
  if (bandit.uncertaintyBonus >= 1.1) reasons.push("contextual bandit が探索価値ありと判定");
  if (bandit.irtGainPotential >= 0.7) reasons.push("IRT上の学習利得が大きい");
  if (detail.model.shadowPromoted && detail.shadowBoost >= 0.55) {
    reasons.push(`${String(detail.model.shadowModel || "shadow").toUpperCase()} が本番選問へ昇格済み`);
  }
  if (detail.record.total > 0 && detail.model.dueInHours <= 0) reasons.push("忘却曲線上、今が復習タイミング");
  if (detail.delta.active || (question.current_relevance_score || 0) >= 0.45) reasons.push("現行リリース差分を優先");
  if (detail.record.total === 0) reasons.push("未着手の高優先問題");
  if (!reasons.length) reasons.push("理解度モデル上の最適候補");

  return {
    score,
    reasons,
    model: detail.model,
    record: detail.record,
    domainReadiness: detail.domainReadiness,
    weakConceptPenalty: detail.weakConceptPenalty,
    activePoolScore: poolInfo.score,
    backendPoolScore: poolInfo.backendScore,
    confidencePressure: detail.confidencePressure,
    confusionPressure: detail.confusionPressure,
    bandit,
    delta: detail.delta,
    contrastiveItem,
    shadowBoost: detail.shadowBoost,
  };
}

function activePoolEntries() {
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const scored = state.dataset.questions
    .map((question) => {
      const detail = questionSignals(question, null, domainLookup);
      const poolInfo = activePoolScoreForQuestion(question, detail);
      return {
        question,
        detail,
        score: poolInfo.score,
        backendScore: poolInfo.backendScore,
      };
    })
    .sort((a, b) => b.score - a.score || a.question.curated_index - b.question.curated_index);

  const picked = [];
  const overflow = [];
  const seenGroups = new Set();
  const targetSize = activeWorkingSetSize();

  scored.forEach((item) => {
    const diversityKey = questionDiversityKey(item.question);
    if (!seenGroups.has(diversityKey)) {
      seenGroups.add(diversityKey);
      picked.push(item);
    } else {
      overflow.push(item);
    }
  });

  while (picked.length < targetSize && overflow.length) {
    picked.push(overflow.shift());
  }

  return picked.slice(0, targetSize);
}

function activePoolRank(questionId) {
  const index = activePoolEntries().findIndex((item) => item.question.id === questionId);
  return index >= 0 ? index + 1 : null;
}

function selectionPolicyLines() {
  const auto = state.user?.preferences?.activeWorkingSetSize == null;
  const shadow = shadowModelSummary();
  return [
    ...state.dataset.selection_policy,
    `稼働セット ${activeWorkingSetSize()}問。${auto ? "自動制御" : "手動固定"}で、自信度 / 混同圧 / 現行性 / 復習期限を混ぜた hybrid を回す。`,
    "重複グループや canonical 候補は、アクティブプールでまず散らして偏りを抑える。",
    shadow.promoted
      ? `shadow ${String(shadow.active_model).toUpperCase()} を本番選問へ昇格。理由: ${shadow.promotion_reason}`
      : `shadow は ${shadow.active_model}。${shadow.promotion_reason}`,
  ];
}

function relatedQuestionsFor(question) {
  return state.dataset.questions
    .filter((candidate) => candidate.id !== question.id)
    .map((candidate) => ({
      question: candidate,
      score: contrastiveSimilarity(question, candidate),
    }))
    .filter((item) => item.score > 0.8)
    .sort((a, b) => b.score - a.score || a.question.curated_index - b.question.curated_index)
    .map((item) => item.question);
}

function contrastiveSimilarity(left, right) {
  let score = 0;
  if (left.confusion_family && left.confusion_family === right.confusion_family) score += 4;
  if (left.semantic_cluster_id && left.semantic_cluster_id === right.semantic_cluster_id) score += 3;
  if (left.duplicate_group_id && left.duplicate_group_id === right.duplicate_group_id) score += 2.6;
  if (left.canonical_id && left.canonical_id === right.canonical_id) score += 2;
  if (left.cluster_key && left.cluster_key === right.cluster_key) score += 1.8;
  score += intersectionCount(left.concept_tags || [], right.concept_tags || []) * 1.4;
  score += intersectionCount(left.current_service_tags || [], right.current_service_tags || []) * 1.1;
  if (left.domain_key === right.domain_key) score += 0.9;
  if (left.choose_count === right.choose_count) score += 0.3;
  if ((left.correct_choice_ids || []).join(",") !== (right.correct_choice_ids || []).join(",")) score += 0.4;
  return score;
}

function queueContrastiveItems(sourceQuestion, correct, confidenceKey) {
  const shouldQueue = !correct || confidenceKey !== "confident";
  if (!shouldQueue) return [];

  const cap = !correct && confidenceKey === "confident" ? 3 : 2;
  const candidates = relatedQuestionsFor(sourceQuestion).slice(0, cap);
  const queued = [];
  const queueById = new Map(state.user.contrastiveQueue.map((item) => [item.questionId, item]));

  candidates.forEach((question) => {
    const intensity = contrastiveSimilarity(sourceQuestion, question) + (!correct ? 1.1 : 0.4);
    const reason = !correct
      ? `${sourceQuestion.id} と論点が近い。誤差分を対比で潰す`
      : `${sourceQuestion.id} は曖昧だった。近接論点で境界を固める`;
    const nextItem = {
      questionId: question.id,
      sourceQuestionId: sourceQuestion.id,
      familyKey: primaryConfusionKey(question),
      reason,
      intensity,
      queuedAt: nowIso(),
    };
    queueById.set(question.id, nextItem);
    queued.push(question);
  });

  state.user.contrastiveQueue = [...queueById.values()]
    .filter((item) => questionById(item.questionId))
    .sort((a, b) => b.intensity - a.intensity || String(b.queuedAt).localeCompare(String(a.queuedAt)))
    .slice(0, 16);

  return queued;
}

function consumeContrastiveItem(questionId) {
  state.user.contrastiveQueue = state.user.contrastiveQueue.filter((item) => item.questionId !== questionId);
}

function updateConfusionState(question, correct, confidenceKey) {
  const key = primaryConfusionKey(question);
  const family = {
    ...defaultFamilyRecord(),
    ...(state.user.confusion.families[key] || {}),
  };
  family.exposures += 1;
  if (!correct) family.misses += 1;
  if (confidenceKey === "unsure") family.unsure += 1;
  if (confidenceKey === "guess") family.guesses += 1;
  if (!correct && confidenceKey === "confident") family.confidentMisses += 1;
  family.lastSeenAt = nowIso();
  if (!correct) family.lastIncorrectAt = family.lastSeenAt;
  family.questionIds = unique([...family.questionIds, question.id]).slice(-8);
  state.user.confusion.families[key] = family;

  if (state.currentContrastiveItem?.sourceQuestionId) {
    const pairKey = [state.currentContrastiveItem.sourceQuestionId, question.id].sort().join("::");
    const pair = state.user.confusion.pairs[pairKey] || {
      exposures: 0,
      misses: 0,
      lastSeenAt: null,
      sourceQuestionId: state.currentContrastiveItem.sourceQuestionId,
      targetQuestionId: question.id,
    };
    pair.exposures += 1;
    if (!correct) pair.misses += 1;
    pair.lastSeenAt = family.lastSeenAt;
    state.user.confusion.pairs[pairKey] = pair;
  }

  return key;
}

function confidenceOutcomeProfile(correct, confidenceKey, hintsUsed) {
  if (correct) {
    const profiles = {
      confident: { observed: 0.98, lrAdjust: 0.02, retention: 1.16, amplifier: 1.06 },
      unsure: { observed: 0.78, lrAdjust: 0, retention: 0.96, amplifier: 0.96 },
      guess: { observed: 0.58, lrAdjust: -0.02, retention: 0.74, amplifier: 0.84 },
    };
    const profile = profiles[confidenceKey];
    return {
      observed: clamp(profile.observed - hintsUsed * 0.08, 0.44, 1),
      lrAdjust: profile.lrAdjust,
      retention: clamp(profile.retention - hintsUsed * 0.05, 0.64, 1.18),
      amplifier: profile.amplifier,
    };
  }

  const profiles = {
    confident: { observed: 0.04, lrAdjust: 0.03, retention: 0.58, amplifier: 1.18 },
    unsure: { observed: 0.15, lrAdjust: 0.01, retention: 0.72, amplifier: 1.02 },
    guess: { observed: 0.21, lrAdjust: -0.01, retention: 0.84, amplifier: 0.88 },
  };
  const profile = profiles[confidenceKey];
  return {
    observed: clamp(profile.observed + hintsUsed * 0.03, 0.03, 0.32),
    lrAdjust: profile.lrAdjust,
    retention: profile.retention,
    amplifier: profile.amplifier,
  };
}

function applyAdaptiveUpdate(question, correct, userIds, confidenceKey) {
  const learner = state.user.learner;
  const record = attemptRecord(question.id);
  const before = state.currentQuestionModel || questionModel(question);
  const hintsUsed = state.hintLevel;
  const profile = confidenceOutcomeProfile(correct, confidenceKey, hintsUsed);
  const error = (profile.observed - before.knowledgeProb) * profile.amplifier;
  const lr = clamp(BASE_LR - question.base_difficulty * 0.05 + profile.lrAdjust, 0.1, 0.28);

  learner.overallTheta += error * lr * 0.55;
  learner.domainTheta[question.domain_key] = (learner.domainTheta[question.domain_key] || 0) + error * lr * 0.82;
  (question.concept_tags || []).forEach((tag) => {
    learner.conceptTheta[tag] = (learner.conceptTheta[tag] || 0) + error * lr * (0.9 / Math.max(1, question.concept_tags.length));
  });
  learner.questionBias[question.id] = (learner.questionBias[question.id] || 0) + (-error) * lr * 0.42;
  learner.questionDifficulty[question.id] = clamp(
    (learner.questionDifficulty[question.id] || 0) + (-error) * lr * 0.12,
    -0.45,
    0.45
  );
  learner.questionDiscrimination[question.id] = clamp(
    (learner.questionDiscrimination[question.id] || 0) +
      ((Math.abs(error) > 0.18 ? 1 : -1) * lr * 0.04 + (confidenceKey === "confident" && !correct ? 0.02 : 0)),
    -0.35,
    0.5
  );

  const prevHalfLife = record.halfLifeHours || initialHalfLife(question);
  const desirableDifficulty = clamp(1 + (0.68 - before.predictedRecall) * 0.45, 0.82, 1.28);
  const hintFactor = clamp(1 - hintsUsed * 0.08, 0.72, 1);

  let nextHalfLife = prevHalfLife;
  if (correct) {
    const growth = 1.3 + before.knowledgeProb * 0.7 + (question.current_relevance_score || 0) * 0.2;
    nextHalfLife = Math.max(prevHalfLife + 2, prevHalfLife * growth * hintFactor * desirableDifficulty * profile.retention);
  } else {
    const shrink = 0.44 + before.knowledgeProb * 0.18;
    nextHalfLife = Math.max(2, prevHalfLife * shrink * profile.retention);
  }

  record.total += 1;
  if (correct) {
    record.correct += 1;
    record.streak += 1;
  } else {
    record.streak = 0;
  }

  record.lastAnswer = userIds;
  record.lastResult = correct;
  record.lastSeenAt = nowIso();
  record.lastPredictedRecall = before.predictedRecall;
  record.lastKnowledgeProb = before.knowledgeProb;
  record.lastHintsUsed = hintsUsed;
  record.lastConfidence = confidenceKey;
  record.confidenceCounts[confidenceKey] = (record.confidenceCounts[confidenceKey] || 0) + 1;
  record.halfLifeHours = clamp(nextHalfLife, 2, 720);
  record.dueAt = new Date(Date.now() + dueIntervalHours(nextHalfLife) * 3600000).toISOString();
  record.history = [
    ...record.history,
    {
      at: record.lastSeenAt,
      correct,
      selectedIds: userIds,
      predictedRecall: before.predictedRecall,
      knowledgeProb: before.knowledgeProb,
      hintsUsed,
      halfLifeHours: record.halfLifeHours,
      confidenceKey,
      questionSource: state.currentQuestionSource,
      contrastiveFrom: state.currentContrastiveItem?.sourceQuestionId || null,
    },
  ].slice(-36);
  state.user.attempts[question.id] = record;

  state.user.analytics.drill.confidenceMix[confidenceKey] =
    (state.user.analytics.drill.confidenceMix[confidenceKey] || 0) + 1;

  const familyKey = updateConfusionState(question, correct, confidenceKey);
  consumeContrastiveItem(question.id);
  const queued = queueContrastiveItems(question, correct, confidenceKey);
  const after = questionModel(question);
  const reward =
    clamp(after.predictedRecall - before.predictedRecall + (correct ? 0.16 : -0.08), -0.3, 0.6) +
    clamp(profile.observed - 0.5, -0.2, 0.22) +
    (confidenceKey === "confident" && !correct ? 0.06 : 0) +
    (confidenceKey === "guess" && correct ? 0.05 : 0);
  updateBanditState(question, reward, correct);
  saveUserState();

  shadowLog("drill_answer_recorded", {
    questionId: question.id,
    correct,
    confidenceKey,
    hintsUsed,
    selectedChoiceIds: userIds,
    presentedAt: state.currentQuestionServedAt,
    submittedAt: nowIso(),
    source: state.currentQuestionSource,
    contrastiveFrom: state.currentContrastiveItem?.sourceQuestionId || null,
    familyKey,
    predictedRecallBefore: before.predictedRecall,
    predictedRecallAfter: after.predictedRecall,
    knowledgeProbBefore: before.knowledgeProb,
    knowledgeProbAfter: after.knowledgeProb,
    irtDifficulty: after.irtDifficulty,
    irtDiscrimination: after.irtDiscrimination,
    banditReward: reward,
    queuedQuestionIds: queued.map((item) => item.id),
    ...shadowQuestionMeta(question),
  });

  return {
    before,
    after,
    record,
    hintsUsed,
    confidenceKey,
    familyKey,
    reward,
    queued,
  };
}

function nextRecommendedQuestion(domainKey = null, excludeIds = [], mode = currentDrillMode()) {
  const excluded = new Set(excludeIds);
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const queued = state.user.contrastiveQueue
    .filter((item) => questionById(item.questionId))
    .filter((item) => !excluded.has(item.questionId))
    .filter((item) => !domainKey || questionById(item.questionId).domain_key === domainKey);

  if (mode === "contrastive" && queued.length) {
    const rankedQueue = queued
      .map((item) => {
        const question = questionById(item.questionId);
        const rec = recommendationForQuestion(question, domainKey, domainLookup, { mode });
        return { question, rec, item };
      })
      .sort((a, b) => b.rec.score - a.rec.score || b.item.intensity - a.item.intensity);

    if (rankedQueue.length) {
      return {
        question: rankedQueue[0].question,
        rec: rankedQueue[0].rec,
        source: "contrastive",
        queueItem: rankedQueue[0].item,
      };
    }
  }

  const pool = activePoolEntries()
    .filter((item) => !excluded.has(item.question.id))
    .filter((item) => !domainKey || item.question.domain_key === domainKey)
    .map((item) => ({
      question: item.question,
      rec: recommendationForQuestion(item.question, domainKey, domainLookup, { mode }),
    }))
    .sort((a, b) => b.rec.score - a.rec.score || a.question.curated_index - b.question.curated_index);

  if (pool.length) {
    return {
      question: pool[0].question,
      rec: pool[0].rec,
      source: mode === "contrastive" ? "contrastive-candidate" : "active_pool",
    };
  }

  const fallback = state.dataset.questions
    .filter((question) => !excluded.has(question.id))
    .filter((question) => !domainKey || question.domain_key === domainKey)
    .map((question) => ({
      question,
      rec: recommendationForQuestion(question, domainKey, domainLookup, { mode }),
    }))
    .sort((a, b) => b.rec.score - a.rec.score || a.question.curated_index - b.question.curated_index);

  return fallback[0]
    ? {
        question: fallback[0].question,
        rec: fallback[0].rec,
        source: "fallback",
      }
    : null;
}

function renderAll() {
  populateDomainFilter();
  syncActiveSetControl();
  renderHero();
  renderDashboard();
  renderPlan();
  renderDrillControls();
  if (state.currentQuestionId) {
    renderCurrentQuestion();
  } else {
    clearCurrentQuestion();
  }
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
  els["stat-today-sub"].textContent = `復習 ${adaptiveToday.reviewTarget} / 新規 ${adaptiveToday.newTarget} | 稼働 ${activeWorkingSetSize()}`;

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
  selectionPolicyLines().forEach((line) => {
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
  renderActivePoolSummary();
  renderContrastiveSummary();
  renderDeltaModeSummary();
  renderShadowTelemetry();
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
    <div>稼働セット: ${activeWorkingSetSize()}問</div>
    <div class="muted">固定計画 ${summary.baseline.new_questions_target + summary.baseline.review_questions_target + summary.baseline.mock_questions}問は目安。今日は hybrid 推薦を優先する。</div>
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

function recentConfidenceStats() {
  const entries = Object.entries(state.user.attempts)
    .flatMap(([questionId, record]) =>
      (record.history || []).map((entry) => ({
        ...entry,
        questionId,
      }))
    )
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, 24);

  return {
    total: entries.length,
    confidentWrong: entries.filter((entry) => entry.confidenceKey === "confident" && entry.correct === false).length,
    guessedRight: entries.filter((entry) => entry.confidenceKey === "guess" && entry.correct === true).length,
    unsure: entries.filter((entry) => entry.confidenceKey === "unsure").length,
  };
}

function renderModelSummary() {
  const rows = domainReadinessRows().sort((a, b) => a.readiness - b.readiness);
  const readiness = weightedReadiness();
  const probability = passProbability();
  const official = state.dataset.official_context;
  const shadow = shadowModelSummary();
  const dueNow = reviewedStats().dueNow;
  const confidenceStats = recentConfidenceStats();
  const contrastiveBacklog = state.user.contrastiveQueue.length;
  els["model-summary"].innerHTML = `
    <div class="today-box">
      <strong>リアルタイム学習モデル</strong>
      <div>総合理解度: ${Math.round(readiness * 100)}%</div>
      <div>推定合格率: ${Math.round(probability * 100)}%</div>
      <div>今すぐ再出題すべき問題: ${dueNow}問</div>
      <div>直近の自信あり誤答: ${confidenceStats.confidentWrong}件 | 当てた寄り: ${confidenceStats.guessedRight}件</div>
      <div>混同キュー残: ${contrastiveBacklog}件</div>
      <div>最弱ドメイン: ${rows.slice(0, 3).map((row) => row.label_ja).join(" / ")}</div>
      <div>Shadow: ${shadow.promoted ? `${String(shadow.active_model).toUpperCase()} 昇格済み` : "baseline維持"} | 検証 ${shadow.valid_examples || 0}例</div>
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
  const next = nextRecommendedQuestion(currentDomainMode(), state.currentQuestionId ? [state.currentQuestionId] : [], currentDrillMode());
  els["next-preview"].innerHTML = "";
  if (!next) {
    els["next-preview"].innerHTML = "<p>出題候補がない。全部回したなら模試へ行け。</p>";
    return;
  }

  const { question, rec, source } = next;
  const card = document.createElement("div");
  card.className = "preview-card";
  card.innerHTML = `
    <strong>${question.id} | ${question.domain_label_ja}</strong>
    <div>${escapeHtml(shortSnippet(question.prompt, 120))}</div>
    <div>予測再現率 ${Math.round(rec.model.predictedRecall * 100)}% / 稼働順位 #${activePoolRank(question.id) || "-"} / 優先度 ${Math.round(rec.activePoolScore)}</div>
    <div class="muted">推奨理由: ${rec.reasons.join(" / ")}</div>
    <div class="muted">bandit ${Math.round(rec.bandit.expectedReward * 100)} / UCB ${Math.round(rec.bandit.uncertaintyBonus * 100)} / IRT利得 ${Math.round(rec.bandit.irtGainPotential * 100)}</div>
    ${
      rec.model.shadowPromoted
        ? `<div class="muted">shadow ${escapeHtml(String(rec.model.shadowModel).toUpperCase())} / 予測成功 ${Math.round((rec.model.shadowPredictedSuccess || 0) * 100)} / 機会 ${Math.round((rec.model.shadowOpportunity || 0) * 100)}</div>`
        : ""
    }
    <div class="muted">出所: ${source === "contrastive" ? "混同キュー" : "稼働ワーキングセット"}${rec.delta.active ? ` | ${rec.delta.label}` : ""}</div>
  `;
  els["next-preview"].appendChild(card);
}

function activePoolSummary() {
  const pool = activePoolEntries();
  const recommendation = activeWorkingSetRecommendation();
  const manual = state.user?.preferences?.activeWorkingSetSize != null;
  return {
    size: pool.length,
    recommendation,
    manual,
    dueNow: pool.filter((item) => item.detail.record.total > 0 && item.detail.model.dueInHours <= 0).length,
    unseen: pool.filter((item) => item.detail.record.total === 0).length,
    delta: pool.filter((item) => item.detail.delta.active).length,
    confusion: pool.filter((item) => item.detail.confusionPressure >= 0.5).length,
    backendScored: pool.filter((item) => item.backendScore != null).length,
    topDomains: Object.entries(
      pool.reduce((acc, item) => {
        acc[item.question.domain_key] = (acc[item.question.domain_key] || 0) + 1;
        return acc;
      }, {})
    )
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([domainKey, count]) => `${domainLabelJa(domainKey)} ${count}`),
  };
}

function renderActivePoolSummary() {
  const summary = activePoolSummary();
  els["active-pool-summary"].innerHTML = `
    <div class="today-box">
      <strong>今の稼働面</strong>
      <div>${summary.size}問を常時ワーキングセット化 ${summary.manual ? "(手動固定)" : "(自動制御)"}</div>
      <div>期限切れ ${summary.dueNow} / 未着手 ${summary.unseen} / 現行差分 ${summary.delta} / 混同補正 ${summary.confusion}</div>
      <div>推奨サイズ ${summary.recommendation.recommended}問 | 自信あり誤答 ${summary.recommendation.confidentWrong} / 未カバー中核 ${summary.recommendation.uncoveredCore}</div>
      <div>厚めのドメイン: ${summary.topDomains.join(" / ") || "全体分散"}</div>
      <div class="muted">${summary.recommendation.reasons.join(" / ")}</div>
      <div class="muted">backend の active_pool_score を持つ問題: ${summary.backendScored}問。足りない分は front 側で補完する。</div>
    </div>
  `;
}

function renderContrastiveSummary() {
  const items = state.user.contrastiveQueue
    .filter((item) => questionById(item.questionId))
    .slice(0, 3)
    .map((item) => {
      const question = questionById(item.questionId);
      const source = item.sourceQuestionId ? questionById(item.sourceQuestionId) : null;
      return `
        <div class="mini-row">
          <strong>${question.id}</strong>
          <span>${escapeHtml(shortSnippet(question.prompt, 72))}</span>
          <span class="muted">${source ? `${source.id} 起点` : "混同起点"} | ${escapeHtml(item.reason)}</span>
        </div>
      `;
    });

  const families = Object.entries(state.user.confusion.families || {})
    .map(([key, family]) => ({
      key,
      pressure:
        family.exposures > 0
          ? (family.misses + family.guesses * 0.7 + family.confidentMisses * 0.6) / family.exposures
          : 0,
    }))
    .sort((a, b) => b.pressure - a.pressure)
    .slice(0, 2);

  els["contrastive-summary"].innerHTML = `
    <div class="today-box">
      <strong>混同対比の待ち行列</strong>
      <div>保留 ${state.user.contrastiveQueue.length}件</div>
      <div>濃いファミリー: ${families.map((item) => item.key).join(" / ") || "まだなし"}</div>
      <div class="mini-stack">
        ${items.length ? items.join("") : '<div class="muted">不正解や曖昧正解が出ると、近接論点をここへ積む。</div>'}
      </div>
    </div>
  `;
}

function deltaSurfaceRows() {
  const pool = activePoolEntries()
    .filter((item) => item.detail.delta.active)
    .sort((a, b) => b.detail.delta.priority - a.detail.delta.priority || b.score - a.score)
    .slice(0, 3);
  return pool.map((item) => ({
    question: item.question,
    delta: item.detail.delta,
  }));
}

function renderDeltaModeSummary() {
  const official = state.dataset.official_context;
  const rows = deltaSurfaceRows();
  const fullCount = state.dataset.questions.filter((question) => deltaMetadata(question).active).length;
  els["delta-mode-summary"].innerHTML = `
    <div class="today-box">
      <strong>${official.current_release_family} 差分サーフェス</strong>
      <div>全体 ${fullCount}問 / 稼働面 ${rows.length}問が delta 系</div>
      <div>基準日: ${official.current_release_updated}</div>
      <div class="mini-stack">
        ${
          rows.length
            ? rows
                .map(
                  ({ question, delta }) => `
                    <div class="mini-row">
                      <strong>${question.id}</strong>
                      <span>${escapeHtml(delta.label || "差分候補")}</span>
                      <span class="muted">${escapeHtml(shortSnippet(delta.reason || question.prompt, 72))}</span>
                    </div>
                  `
                )
                .join("")
            : '<div class="muted">delta_mode メタが未着でも current relevance から表面化する。</div>'
        }
      </div>
    </div>
  `;
}

function renderShadowTelemetry() {
  const entries = window.__CSA_SHADOW_LOG__ || [];
  const installed = typeof window.__CSA_SHADOW_HOOK__ === "function";
  const shadow = shadowModelSummary();
  const recent = entries.slice(-4).reverse();
  els["shadow-telemetry"].innerHTML = `
    <div class="today-box">
      <strong>Shadow KT</strong>
      <div>${shadow.promoted ? `${String(shadow.active_model).toUpperCase()} 昇格済み` : "baseline 維持"} | ${installed ? "外部連携フックあり" : "フック未接続"} | バッファ ${entries.length}/${SHADOW_LOG_LIMIT}</div>
      <div class="muted">理由: ${escapeHtml(shadow.promotion_reason || "shadow training 未実行")}</div>
      <div class="mini-stack">
        ${
          recent.length
            ? recent
                .map(
                  (entry) => `
                    <div class="mini-row">
                      <strong>${escapeHtml(entry.type)}</strong>
                      <span class="muted">${escapeHtml(shortSnippet(JSON.stringify(entry), 96))}</span>
                    </div>
                  `
                )
                .join("")
            : '<div class="muted">export した JSONL を shadow-train に掛けると、DKT/SAKT の champion を本番選問へ昇格できる。</div>'
        }
      </div>
    </div>
  `;
}

function renderDrillControls() {
  const mode = currentDrillMode();
  els["domain-filter"].disabled = mode !== "focus";
  if (mode === "focus") {
    els["drill-status"].textContent = domainLabelJa(els["domain-filter"].value);
  } else if (mode === "contrastive") {
    els["drill-status"].textContent = state.user.contrastiveQueue.length
      ? `混同対比 ${state.user.contrastiveQueue.length}`
      : "混同待機";
  } else {
    els["drill-status"].textContent = "全範囲";
  }
  renderNextPreview();
}

function clearCurrentQuestion() {
  els["question-meta"].innerHTML = "";
  els["question-rationale"].classList.add("hidden");
  els["question-card"].className = "question-card empty";
  els["question-card"].innerHTML = "<p>出題ボタンを押せ。逃げるな。</p>";
  els["hint-box"].classList.add("hidden");
  els["result-box"].classList.add("hidden");
  els["confidence-box"].classList.add("hidden");
  els["contrastive-box"].classList.add("hidden");
  els["hint-button"].disabled = true;
  els["submit-answer"].disabled = true;
  els["next-question"].disabled = true;
}

function loadNextDrillQuestion() {
  const next = nextRecommendedQuestion(
    currentDomainMode(),
    state.currentQuestionId ? [state.currentQuestionId] : [],
    currentDrillMode()
  );
  if (!next) return;

  state.currentQuestionId = next.question.id;
  state.currentSelections = [];
  state.currentConfidenceKey = null;
  state.currentQuestionModel = next.rec.model;
  state.currentQuestionSource = next.source || "active_pool";
  state.currentContrastiveItem = next.queueItem || next.rec.contrastiveItem || null;
  state.currentQuestionLocked = false;
  state.currentQuestionFeedback = null;
  state.currentQuestionServedAt = nowIso();
  state.hintLevel = 0;
  renderCurrentQuestion();
  shadowLog("drill_question_served", {
    questionId: next.question.id,
    mode: currentDrillMode(),
    source: state.currentQuestionSource,
    activePoolRank: activePoolRank(next.question.id),
    contrastiveFrom: state.currentContrastiveItem?.sourceQuestionId || null,
    ...shadowQuestionMeta(next.question),
  });
}

function questionEvidenceHtml(question) {
  const delta = deltaMetadata(question);
  const lines = [];
  const evidence = officialEvidenceForQuestion(question);
  if (evidence?.title) {
    const metaBits = [evidence.release_family, evidence.updated_on].filter(Boolean).join(" / ");
    lines.push(
      `<div><strong>公式Docs</strong>: <a href="${escapeHtml(evidence.url)}" target="_blank" rel="noreferrer">${escapeHtml(
        evidence.title
      )}</a>${metaBits ? ` <span class="muted">(${escapeHtml(metaBits)})</span>` : ""}</div>`
    );
  }
  if (evidence?.snippet) {
    lines.push(`<div><strong>公式要約</strong>: ${escapeHtml(shortSnippet(evidence.snippet, 180))}</div>`);
  }
  if (delta.snippets.length) {
    lines.push(`<div><strong>根拠要点</strong>: ${escapeHtml(shortSnippet(delta.snippets.join(" / "), 140))}</div>`);
  }
  if (delta.basis.length) {
    lines.push(`<div><strong>参照論点</strong>: ${escapeHtml(shortSnippet(delta.basis.join(" / "), 140))}</div>`);
  }
  return lines.join("");
}

function renderCurrentQuestion() {
  const question = questionById(state.currentQuestionId);
  if (!question) {
    clearCurrentQuestion();
    return;
  }
  void ensureLiveOfficialEvidence(question);

  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const rec = recommendationForQuestion(question, currentDomainMode(), domainLookup, { mode: currentDrillMode() });
  state.currentQuestionModel = rec.model;

  const pills = [
    question.id,
    question.domain_label_ja,
    `予測再現率 ${Math.round(rec.model.predictedRecall * 100)}%`,
    `半減期 ${rec.model.halfLifeHours.toFixed(1)}h`,
    `正答数 ${question.choose_count}`,
    `稼働順位 #${activePoolRank(question.id) || "-"}`,
  ];
  if (rec.delta.active) pills.push(rec.delta.label || "Delta");
  if (state.currentQuestionSource.startsWith("contrastive")) pills.push("混同対比");

  els["question-meta"].innerHTML = pills.map((pill) => `<span class="pill">${escapeHtml(pill)}</span>`).join("");

  const familyKey = primaryConfusionKey(question);
  els["question-rationale"].classList.remove("hidden");
  els["question-rationale"].innerHTML = `
    <strong>Hybrid推薦理由</strong>
    <div>${rec.reasons.join(" / ")}</div>
    <div class="muted">概念: ${(question.concept_tags || []).map(conceptLabelJa).join(" / ") || "未分類"} | 現行トピック: ${(question.current_service_tags || []).map(conceptLabelJa).join(" / ") || "なし"}</div>
    <div class="muted">混同キー: ${escapeHtml(familyKey)} | 自信圧 ${Math.round(rec.confidencePressure * 100)} / 混同圧 ${Math.round(rec.confusionPressure * 100)}</div>
    <div class="muted">IRT難度 ${rec.model.irtDifficulty.toFixed(2)} / 識別力 ${rec.model.irtDiscrimination.toFixed(2)} / bandit利得 ${Math.round(rec.bandit.expectedReward * 100)} / 探索 ${Math.round(rec.bandit.uncertaintyBonus * 100)}</div>
    ${
      rec.model.shadowPromoted
        ? `<div class="muted">shadow ${escapeHtml(String(rec.model.shadowModel).toUpperCase())} / 予測成功 ${Math.round((rec.model.shadowPredictedSuccess || 0) * 100)} / 不確実性 ${Math.round((rec.model.shadowUncertainty || 0) * 100)} / 学習機会 ${Math.round((rec.model.shadowOpportunity || 0) * 100)}</div>`
        : ""
    }
    ${questionEvidenceHtml(question)}
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
    button.type = "button";
    button.className = "choice-button";
    button.dataset.choiceId = choice.id;
    button.innerHTML = `<strong>${choice.id}.</strong> ${escapeHtml(choice.text)}`;
    button.classList.toggle("selected", state.currentSelections.includes(choice.id));
    button.addEventListener("click", () => toggleSelection(choice.id));
    choiceList.appendChild(button);
  });

  els["question-card"].append(prompt, choiceList);
  renderDrillConfidenceBox();
  renderCurrentContrastiveBox();

  els["hint-box"].classList.add("hidden");
  els["hint-box"].innerHTML = "";
  els["hint-button"].disabled = state.currentQuestionLocked;
  els["next-question"].disabled = !state.currentQuestionLocked;

  if (state.currentQuestionLocked && state.currentQuestionFeedback?.questionId === question.id) {
    applyLockedDrillFeedback(question);
    return;
  }

  els["result-box"].classList.add("hidden");
  els["result-box"].innerHTML = "";
  updateDrillSubmitDisabled();
}

function renderDrillConfidenceBox() {
  const wrap = els["confidence-box"];
  wrap.className = "confidence-box";
  if (state.currentQuestionLocked) {
    wrap.classList.add("locked");
    wrap.innerHTML = `
      <strong>記録した手応え</strong>
      <div>${confidenceLabel(state.currentConfidenceKey, state.currentQuestionFeedback?.correct)}</div>
      <div class="muted">この自信度は学習更新と模試分析に使う。</div>
    `;
    return;
  }

  wrap.classList.remove("hidden", "locked");
  wrap.innerHTML = `
    <strong>採点前に手応えを打て</strong>
    <div class="button-strip"></div>
    <div class="muted">必須。自信度を入れてから採点する。</div>
  `;

  const strip = wrap.querySelector(".button-strip");
  confidenceChoicesForMock().forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tag-button ${state.currentConfidenceKey === choice.key ? "active" : ""}`;
    button.textContent = choice.label;
    button.addEventListener("click", () => setDrillConfidence(choice.key));
    strip.appendChild(button);
  });
}

function renderCurrentContrastiveBox() {
  const wrap = els["contrastive-box"];
  const current = state.currentContrastiveItem;
  if (!current || state.currentQuestionLocked) {
    wrap.classList.add("hidden");
    wrap.innerHTML = "";
    return;
  }
  const source = current.sourceQuestionId ? questionById(current.sourceQuestionId) : null;
  wrap.classList.remove("hidden");
  wrap.innerHTML = `
    <strong>混同対比キュー</strong>
    <div>${escapeHtml(current.reason || "混同対比キューから投入")}</div>
    <div class="muted">${source ? `${source.id} | ${escapeHtml(shortSnippet(source.prompt, 84))}` : "直近の混同ファミリーから選抜"}</div>
  `;
}

function setDrillConfidence(key) {
  if (state.currentQuestionLocked) return;
  state.currentConfidenceKey = key;
  renderDrillConfidenceBox();
  updateDrillSubmitDisabled();
}

function toggleSelection(choiceId) {
  if (state.currentQuestionLocked) return;
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
  updateDrillSubmitDisabled();
}

function updateDrillSubmitDisabled() {
  els["submit-answer"].disabled = state.currentQuestionLocked || state.currentSelections.length === 0 || !state.currentConfidenceKey;
}

function revealHint() {
  const question = questionById(state.currentQuestionId);
  if (!question || state.currentQuestionLocked) return;

  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const rec = recommendationForQuestion(question, currentDomainMode(), domainLookup, { mode: currentDrillMode() });
  state.hintLevel += 1;
  els["hint-box"].classList.remove("hidden");

  const wrongChoice = question.choices.find((choice) => !question.correct_choice_ids.includes(choice.id));
  const evidence = officialEvidenceForQuestion(question)?.snippet || deltaMetadata(question).snippets[0];
  const hints = [
    `ヒント1: 正答は ${question.choose_count} 個。数を外すな。`,
    `ヒント2: この問題の核は ${(question.concept_tags || []).slice(0, 2).map(conceptLabelJa).join(" / ") || question.domain_label_ja}。`,
    `ヒント3: ${wrongChoice ? `${wrongChoice.id} は切れる可能性が高い。` : "誤答選択肢の根拠を探せ。"}`,
    `ヒント4: 予測再現率 ${Math.round(rec.model.predictedRecall * 100)}% だ。思い出せるギリギリの帯だ。`,
    evidence ? `ヒント5: ${escapeHtml(shortSnippet(evidence, 120))}` : "",
  ].filter(Boolean);

  els["hint-box"].innerHTML = `
    <strong>ビシビシヒント</strong>
    <div>${hints.slice(0, state.hintLevel).join("<br>")}</div>
  `;

  if (state.hintLevel >= 3 && wrongChoice) {
    const button = document.querySelector(`#question-card .choice-button[data-choice-id="${wrongChoice.id}"]`);
    button?.classList.add("eliminated");
  }
}

function submitCurrentQuestion() {
  const question = questionById(state.currentQuestionId);
  if (!question || state.currentQuestionLocked || !state.currentConfidenceKey) return;

  const userIds = [...state.currentSelections].sort();
  const correctIds = [...question.correct_choice_ids].sort();
  const correct = JSON.stringify(userIds) === JSON.stringify(correctIds);
  const update = applyAdaptiveUpdate(question, correct, userIds, state.currentConfidenceKey);

  document.querySelectorAll("#question-card .choice-button").forEach((button) => {
    const choiceId = button.dataset.choiceId;
    if (question.correct_choice_ids.includes(choiceId)) button.classList.add("correct");
    if (state.currentSelections.includes(choiceId) && !question.correct_choice_ids.includes(choiceId)) {
      button.classList.add("incorrect");
    }
  });

  const nextReview = dueIntervalHours(update.record.halfLifeHours);
  const docsHtml = officialDocLinks(question)
    .map((url, index) => `<a href="${url}" target="_blank" rel="noreferrer">公式${index + 1}</a>`)
    .join(" / ");
  const queuedLine = update.queued.length
    ? `対比キュー追加: ${update.queued.map((item) => item.id).join(" / ")}`
    : "対比キュー追加なし";
  const coach = correct
    ? update.confidenceKey === "guess"
      ? "正解だが、当てただけなら定着ではない。近接論点で境界を固める。"
      : "正解。理由を言語化して再現性に変えろ。"
    : update.confidenceKey === "confident"
      ? "不正解。自信ありで落とした論点は優先矯正だ。"
      : "不正解。曖昧なまま進むな。選択肢の切り分けを作り直せ。";

  const resultHtml = `
    <strong>${correct ? "正解" : "不正解"} | 正答 ${correctIds.join(",")} | ${confidenceLabel(update.confidenceKey, correct)}</strong>
    <div>${coach}</div>
    <div>モデル更新: 再現率予測 ${Math.round(update.before.predictedRecall * 100)}% → ${Math.round(update.after.predictedRecall * 100)}%</div>
    <div>記憶半減期: ${update.before.halfLifeHours.toFixed(1)}h → ${update.record.halfLifeHours.toFixed(1)}h | 次回推奨 ${nextReview.toFixed(1)}h後</div>
    <div>ヒント使用: ${update.hintsUsed} | 混同キー: ${escapeHtml(update.familyKey)}</div>
    <div>${escapeHtml(question.explanation)}</div>
    <div>${queuedLine}</div>
    <div>${docsHtml}</div>
  `;

  const contrastiveHtml = update.queued.length
    ? `
      <strong>次の混同対比</strong>
      <div>${update.queued.map((item) => `${item.id} | ${escapeHtml(shortSnippet(item.prompt, 88))}`).join("<br>")}</div>
    `
    : "";

  state.currentQuestionLocked = true;
  state.currentQuestionFeedback = {
    questionId: question.id,
    correct,
    correctIds,
    resultClass: correct ? "good" : "bad",
    resultHtml,
    contrastiveHtml,
  };

  applyLockedDrillFeedback(question);
  renderHero();
  renderDashboard();
}

function applyLockedDrillFeedback(question) {
  const feedback = state.currentQuestionFeedback;
  if (!feedback || feedback.questionId !== question.id) return;

  document.querySelectorAll("#question-card .choice-button").forEach((button) => {
    const choiceId = button.dataset.choiceId;
    if (feedback.correctIds.includes(choiceId)) button.classList.add("correct");
    if (state.currentSelections.includes(choiceId) && !feedback.correctIds.includes(choiceId)) {
      button.classList.add("incorrect");
    }
  });

  els["result-box"].className = `result-box ${feedback.resultClass}`;
  els["result-box"].classList.remove("hidden");
  els["result-box"].innerHTML = feedback.resultHtml;
  renderDrillConfidenceBox();
  els["hint-button"].disabled = true;
  els["submit-answer"].disabled = true;
  els["next-question"].disabled = false;

  if (feedback.contrastiveHtml) {
    els["contrastive-box"].classList.remove("hidden");
    els["contrastive-box"].innerHTML = feedback.contrastiveHtml;
  } else {
    els["contrastive-box"].classList.add("hidden");
    els["contrastive-box"].innerHTML = "";
  }
}

function renderPlan() {
  const adaptive = adaptiveTodaySummary();
  els["plan-summary"].textContent = `固定計画は土台。実運用はML目標 ${adaptive.target}問/日、稼働セット ${activeWorkingSetSize()}問で回す`;
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
    startedAt: nowIso(),
    endsAt: new Date(Date.now() + 90 * 60 * 1000).toISOString(),
    finishedAt: null,
    questionIds: questions.map((question) => question.id),
    answers: {},
    currentIndex: 0,
    finished: false,
    summary: null,
  };
  saveUserState();
  renderMock();
  shadowLog("mock_started", { questionCount: questions.length });
}

function buildMockQuestionSet() {
  const quotas = domainQuotasFor(60);
  const domainLookup = Object.fromEntries(domainReadinessRows().map((row) => [row.domain_key, row]));
  const activeSetIds = new Set(activePoolEntries().map((item) => item.question.id));
  const picked = [];

  Object.entries(quotas).forEach(([domainKey, count]) => {
    const pool = state.dataset.questions
      .filter((question) => question.domain_key === domainKey)
      .map((question) => {
        const rec = recommendationForQuestion(question, null, domainLookup);
        const activeBoost = activeSetIds.has(question.id) ? 12 : 0;
        return {
          question,
          score: rec.score + activeBoost,
        };
      })
      .sort((a, b) => b.score - a.score || a.question.curated_index - b.question.curated_index)
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

function currentMockSession() {
  return state.user.mockSession;
}

function ensureMockAnswer(questionId) {
  const session = currentMockSession();
  if (!session) return null;
  if (!session.answers[questionId]) {
    session.answers[questionId] = {
      selectedIds: [],
      confidenceKey: null,
      touchedAt: null,
      savedAt: null,
      changeCount: 0,
    };
  }
  return session.answers[questionId];
}

function renderMock() {
  const session = currentMockSession();
  clearInterval(state.mockTimerHandle);

  if (!session) {
    els["mock-timer"].textContent = "90:00";
    els["mock-progress"].innerHTML = "";
    els["mock-strategy-strip"].innerHTML = "";
    els["mock-question"].className = "question-card empty";
    els["mock-question"].innerHTML = "<p>模試を開始しろ。</p>";
    els["mock-confidence-box"].classList.add("hidden");
    els["mock-results"].innerHTML = "<p>模試を完了するとここに結果が出る。</p>";
    setMockButtonsDisabled(true);
    return;
  }

  if (session.finished) {
    els["mock-timer"].textContent = "完了";
  } else {
    updateMockTimer();
    state.mockTimerHandle = window.setInterval(updateMockTimer, 1000);
  }

  const currentId = session.questionIds[session.currentIndex];
  const question = questionById(currentId);
  const savedAnswer = session.answers[currentId] || {
    selectedIds: [],
    confidenceKey: null,
  };
  renderMockQuestion(question, savedAnswer.selectedIds);
  renderMockConfidenceBox(savedAnswer.confidenceKey, session.finished);
  renderMockStrategyStrip(session);

  const answered = Object.values(session.answers).filter((answer) => answer.selectedIds.length > 0).length;
  const confident = Object.values(session.answers).filter((answer) => answer.confidenceKey === "confident").length;
  els["mock-progress"].innerHTML = `
    <span class="pill">${session.currentIndex + 1} / ${session.questionIds.length}</span>
    <span class="pill">回答済み ${answered}</span>
    <span class="pill">自信あり ${confident}</span>
    <span class="pill">${question.domain_label_ja}</span>
  `;

  setMockButtonsDisabled(false);
  els["mock-save"].disabled = session.finished;

  if (session.finished) {
    renderMockResults();
  } else {
    els["mock-results"].innerHTML = "<p>模試を完了すると、ここに戦略分析が出る。</p>";
  }
}

function updateMockTimer() {
  const session = currentMockSession();
  if (!session || session.finished) return;
  const remainingMs = new Date(session.endsAt).getTime() - Date.now();
  if (remainingMs <= 0) {
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
    button.innerHTML = `<strong>${choice.id}.</strong> ${escapeHtml(choice.text)}`;
    button.addEventListener("click", () => toggleMockSelection(choice.id, question.choose_count));
    choices.appendChild(button);
  });

  wrap.append(prompt, choices);
  els["mock-question"].replaceWith(wrap);
  els["mock-question"] = wrap;
}

function renderMockConfidenceBox(confidenceKey, disabled = false) {
  const wrap = els["mock-confidence-box"];
  wrap.className = "confidence-box";
  wrap.classList.remove("hidden", "locked");
  if (disabled) wrap.classList.add("locked");
  wrap.innerHTML = `
    <strong>本番想定の手応え</strong>
    <div class="button-strip"></div>
    <div class="muted">mock analytics で confident-wrong / slump / multi-select misses を見る。</div>
  `;
  const strip = wrap.querySelector(".button-strip");
  confidenceChoicesForMock().forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tag-button ${confidenceKey === choice.key ? "active" : ""}`;
    button.textContent = choice.label;
    button.disabled = disabled;
    button.addEventListener("click", () => setMockConfidence(choice.key));
    strip.appendChild(button);
  });
}

function renderMockStrategyStrip(session) {
  const answered = Object.values(session.answers).filter((answer) => answer.selectedIds.length > 0).length;
  const withConfidence = Object.values(session.answers).filter((answer) => Boolean(answer.confidenceKey)).length;
  const multiSelectAnswered = session.questionIds.filter((questionId) => {
    const question = questionById(questionId);
    return question.multi_select && (session.answers[questionId]?.selectedIds.length || 0) > 0;
  }).length;
  const lateWindowStart = new Date(new Date(session.endsAt).getTime() - 20 * 60 * 1000);
  const lateTouched = Object.values(session.answers).filter((answer) => answer.savedAt && new Date(answer.savedAt) >= lateWindowStart).length;

  els["mock-strategy-strip"].innerHTML = `
    <span class="pill">自信度入力 ${withConfidence}</span>
    <span class="pill">multi-select 着手 ${multiSelectAnswered}</span>
    <span class="pill">${lateTouched ? `終盤20分回答 ${lateTouched}` : "終盤20分は未到達"}</span>
    <span class="pill">残り未回答 ${session.questionIds.length - answered}</span>
  `;
}

function toggleMockSelection(choiceId, chooseCount) {
  const session = currentMockSession();
  if (!session || session.finished) return;

  const currentId = session.questionIds[session.currentIndex];
  const answer = ensureMockAnswer(currentId);
  const saved = answer.selectedIds || [];
  let next = [];
  if (chooseCount === 1) {
    next = [choiceId];
  } else if (saved.includes(choiceId)) {
    next = saved.filter((id) => id !== choiceId);
  } else {
    next = [...saved, choiceId];
  }
  answer.selectedIds = next;
  answer.touchedAt = nowIso();
  answer.changeCount = (answer.changeCount || 0) + 1;
  saveUserState();
  document.querySelectorAll("#view-mock .choice-button").forEach((button) => {
    button.classList.toggle("selected", next.includes(button.dataset.choiceId));
  });
  renderMockStrategyStrip(session);
}

function setMockConfidence(key) {
  const session = currentMockSession();
  if (!session || session.finished) return;
  const currentId = session.questionIds[session.currentIndex];
  const answer = ensureMockAnswer(currentId);
  answer.confidenceKey = key;
  answer.touchedAt = nowIso();
  saveUserState();
  renderMockConfidenceBox(key, false);
  renderMockStrategyStrip(session);
}

function saveMockAnswer() {
  const session = currentMockSession();
  if (!session || session.finished) return;
  const currentId = session.questionIds[session.currentIndex];
  const answer = ensureMockAnswer(currentId);
  answer.savedAt = nowIso();
  saveUserState();
  shadowLog("mock_answer_saved", {
    questionId: currentId,
    selectedCount: answer.selectedIds.length,
    confidenceKey: answer.confidenceKey,
    index: session.currentIndex + 1,
  });
  moveMock(1);
}

function moveMock(delta) {
  const session = currentMockSession();
  if (!session) return;
  session.currentIndex = clamp(session.currentIndex + delta, 0, session.questionIds.length - 1);
  saveUserState();
  renderMock();
}

function finishMock() {
  const session = currentMockSession();
  if (!session || session.finished) return;
  session.finished = true;
  session.finishedAt = nowIso();
  session.summary = computeMockSummary(session);
  state.user.analytics.mockHistory = [session.summary, ...state.user.analytics.mockHistory].slice(0, 8);
  saveUserState();
  renderMock();
  shadowLog("mock_finished", {
    score: session.summary.score,
    confidentWrong: session.summary.confidentWrong,
    multiSelectMisses: session.summary.multiSelectMisses,
    slumpDelta: session.summary.slumpDelta,
  });
}

function computeMockSummary(session) {
  let correct = 0;
  const byDomain = {};
  let unanswered = 0;
  let confidentWrong = 0;
  let lowConfidenceHits = 0;
  let multiSelectMisses = 0;
  let wrongCardinality = 0;
  let lateCorrect = 0;
  let lateTotal = 0;
  let earlyCorrect = 0;
  let earlyTotal = 0;
  const lateWindowStart = new Date(new Date(session.endsAt).getTime() - 20 * 60 * 1000);

  session.questionIds.forEach((questionId) => {
    const question = questionById(questionId);
    const answer = session.answers[questionId] || {};
    const selected = [...(answer.selectedIds || [])].sort();
    const expected = [...question.correct_choice_ids].sort();
    const isCorrect = JSON.stringify(selected) === JSON.stringify(expected);
    const answered = selected.length > 0;

    if (!answered) unanswered += 1;
    if (isCorrect) correct += 1;
    if (!byDomain[question.domain_key]) {
      byDomain[question.domain_key] = {
        label: question.domain_label_ja,
        correct: 0,
        total: 0,
      };
    }
    byDomain[question.domain_key].total += 1;
    if (isCorrect) byDomain[question.domain_key].correct += 1;

    if (question.multi_select && answered && !isCorrect) {
      multiSelectMisses += 1;
      if (selected.length !== question.choose_count) wrongCardinality += 1;
    }
    if (!isCorrect && answer.confidenceKey === "confident") confidentWrong += 1;
    if (isCorrect && (answer.confidenceKey === "guess" || answer.confidenceKey === "unsure")) lowConfidenceHits += 1;

    const answerTime = answer.savedAt || answer.touchedAt;
    if (answerTime) {
      if (new Date(answerTime) >= lateWindowStart) {
        lateTotal += 1;
        if (isCorrect) lateCorrect += 1;
      } else {
        earlyTotal += 1;
        if (isCorrect) earlyCorrect += 1;
      }
    }
  });

  const score = Math.round((correct / session.questionIds.length) * 100);
  const weakest = Object.values(byDomain)
    .sort((a, b) => a.correct / a.total - b.correct / b.total)
    .slice(0, 3);
  const lateAccuracy = lateTotal ? lateCorrect / lateTotal : null;
  const earlyAccuracy = earlyTotal ? earlyCorrect / earlyTotal : null;
  const slumpDelta =
    lateAccuracy != null && earlyAccuracy != null ? Number((lateAccuracy - earlyAccuracy).toFixed(3)) : null;

  const recommendations = [];
  if (multiSelectMisses >= 4) {
    recommendations.push(`複数選択 ${multiSelectMisses}問を落としている。まず正答数 ${wrongCardinality}件の外しを止めろ。`);
  }
  if (confidentWrong >= 4) {
    recommendations.push(`自信ありで ${confidentWrong}問落としている。見慣れた用語で雑に決め打ちしている。`);
  }
  if (slumpDelta != null && slumpDelta < -0.12) {
    recommendations.push(`終盤20分で精度が ${Math.round(Math.abs(slumpDelta) * 100)}pt 落ちた。残り25分時点で multi-select を先に回せ。`);
  }
  if (!recommendations.length) {
    recommendations.push(score >= 80 ? "戦略は大崩れしていない。弱点ドメインを磨いて再現性を上げろ。" : "弱点ドメインを回してから再受験。");
  }

  return {
    finishedAt: session.finishedAt,
    score,
    correct,
    total: session.questionIds.length,
    weakest,
    unanswered,
    confidentWrong,
    lowConfidenceHits,
    multiSelectMisses,
    wrongCardinality,
    lateCorrect,
    lateTotal,
    earlyCorrect,
    earlyTotal,
    slumpDelta,
    recommendations,
  };
}

function renderMockResults() {
  const session = currentMockSession();
  if (!session?.summary) return;
  const summary = session.summary;
  const lateLine =
    summary.slumpDelta == null
      ? "終盤20分の十分なサンプルなし"
      : `終盤20分 ${summary.lateCorrect}/${summary.lateTotal} | 前半比 ${summary.slumpDelta >= 0 ? "+" : ""}${Math.round(summary.slumpDelta * 100)}pt`;

  els["mock-results"].innerHTML = `
    <div class="mock-card">
      <strong>模試スコア</strong>
      <div class="mock-score">${summary.score}%</div>
      <div>${summary.correct} / ${summary.total} 問正解</div>
      <div>弱点: ${summary.weakest.map((item) => `${item.label} ${Math.round((item.correct / item.total) * 100)}%`).join(" / ")}</div>
      <div>multi-select misses: ${summary.multiSelectMisses}問 | 選択数ミス ${summary.wrongCardinality}件</div>
      <div>confident-wrong: ${summary.confidentWrong}問 | low-confidence hit: ${summary.lowConfidenceHits}問</div>
      <div>last-20-minute slump: ${lateLine}</div>
      <div>未回答: ${summary.unanswered}問</div>
      <div class="mini-stack">
        ${summary.recommendations.map((line) => `<div class="mini-row"><span>${escapeHtml(line)}</span></div>`).join("")}
      </div>
    </div>
  `;
}

function setMockButtonsDisabled(disabled) {
  els["mock-prev"].disabled = disabled;
  els["mock-save"].disabled = disabled;
  els["mock-next"].disabled = disabled;
}

function shadowQuestionMeta(question) {
  return {
    canonicalId: question.canonical_id || question.id,
    duplicateGroupId: question.duplicate_group_id || null,
    semanticClusterId: question.semantic_cluster_id || null,
    confusionFamily: question.confusion_family || null,
    activePoolScore: backendActivePoolScore(question),
    irtDifficulty: question.irt_difficulty ?? question.base_difficulty ?? null,
    irtDiscrimination: question.irt_discrimination ?? null,
    deltaActive: deltaMetadata(question).active,
  };
}

function shadowLog(type, payload = {}) {
  const entry = {
    type,
    at: nowIso(),
    activePoolSize: state.user ? activeWorkingSetSize() : null,
    ...payload,
  };

  try {
    window.__CSA_SHADOW_LOG__ = [...(window.__CSA_SHADOW_LOG__ || []), entry].slice(-SHADOW_LOG_LIMIT);
    window.localStorage.setItem(SHADOW_STORAGE_KEY, JSON.stringify(window.__CSA_SHADOW_LOG__));
    window.dispatchEvent(new CustomEvent("csa-shadow-log", { detail: entry }));
    if (typeof window.__CSA_SHADOW_HOOK__ === "function") {
      window.__CSA_SHADOW_HOOK__(entry);
    }
  } catch {
    // Shadow logging is best-effort only.
  }
}

function exportShadowLog() {
  const entries = window.__CSA_SHADOW_LOG__ || [];
  const blob = new Blob(entries.map((entry) => `${JSON.stringify(entry)}\n`), {
    type: "application/x-ndjson",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `csa-shadow-log-${new Date().toISOString().replaceAll(":", "-")}.jsonl`;
  anchor.click();
  URL.revokeObjectURL(url);
  shadowLog("shadow_exported", { exportedCount: entries.length });
}
