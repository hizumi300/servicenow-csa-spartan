const DATA_URL = "./data/csa600.json";
const STORAGE_KEY = "csaSpartanState:v1";

const state = {
  dataset: null,
  user: null,
  currentQuestionId: null,
  currentSelections: [],
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
    "drill-mode",
    "domain-filter",
    "drill-status",
    "question-meta",
    "question-card",
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
    const confirmed = window.confirm("学習進捗を全部消す。甘えを捨てるならOK。");
    if (!confirmed) return;
    state.user = defaultUserState();
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
}

function defaultUserState() {
  return {
    version: 1,
    startedAt: null,
    attempts: {},
    mockSession: null,
  };
}

function loadUserState() {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    state.user = defaultUserState();
    return;
  }
  try {
    state.user = { ...defaultUserState(), ...JSON.parse(raw) };
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

function switchView(viewName) {
  els.tabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  els.views.forEach((view) => {
    view.classList.toggle("active", view.id === `view-${viewName}`);
  });
  if (viewName === "mock") {
    renderMock();
  }
}

function renderAll() {
  populateDomainFilter();
  renderHero();
  renderDashboard();
  renderPlan();
  renderDrillControls();
  renderMock();
}

function populateDomainFilter() {
  if (els["domain-filter"].childElementCount > 0) return;
  const options = state.dataset.domains.map((domain) => {
    const option = document.createElement("option");
    option.value = domain.domain_key;
    option.textContent = domain.label_ja;
    return option;
  });
  els["domain-filter"].append(...options);
}

function questionMap() {
  const map = new Map();
  state.dataset.questions.forEach((question) => map.set(question.id, question));
  return map;
}

function attemptRecord(questionId) {
  return state.user.attempts[questionId] || {
    total: 0,
    correct: 0,
    streak: 0,
    dueAt: null,
    history: [],
  };
}

function updateAttempt(questionId, selectedIds, correct) {
  const record = attemptRecord(questionId);
  record.total += 1;
  if (correct) {
    record.correct += 1;
    record.streak += 1;
  } else {
    record.streak = 0;
  }
  record.lastAnswer = selectedIds;
  record.lastResult = correct;
  record.lastSeenAt = new Date().toISOString();
  record.dueAt = spacedDue(correct, record.streak);
  record.history = [...record.history, { at: record.lastSeenAt, correct, selectedIds }].slice(-20);
  state.user.attempts[questionId] = record;
  saveUserState();
}

function spacedDue(correct, streak) {
  const now = Date.now();
  const hour = 60 * 60 * 1000;
  if (!correct) return new Date(now + 15 * 60 * 1000).toISOString();
  if (streak === 1) return new Date(now + 12 * hour).toISOString();
  if (streak === 2) return new Date(now + 24 * hour).toISOString();
  if (streak === 3) return new Date(now + 72 * hour).toISOString();
  return new Date(now + 7 * 24 * hour).toISOString();
}

function reviewedStats() {
  const attempts = Object.values(state.user.attempts);
  return {
    reviewed: attempts.length,
    totalAttempts: attempts.reduce((sum, record) => sum + record.total, 0),
  };
}

function progressByDomain() {
  return state.dataset.domains.map((domain) => {
    const questions = state.dataset.questions.filter((question) => question.domain_key === domain.domain_key);
    let total = 0;
    let correct = 0;
    let reviewed = 0;
    questions.forEach((question) => {
      const record = attemptRecord(question.id);
      total += record.total;
      correct += record.correct;
      if (record.total > 0) reviewed += 1;
    });
    const accuracy = total ? correct / total : 0;
    return {
      ...domain,
      accuracy,
      totalAttempts: total,
      reviewed,
    };
  });
}

function weightedReadiness() {
  return progressByDomain().reduce((sum, domain) => sum + domain.accuracy * domain.weight, 0);
}

function passProbability() {
  const { reviewed } = reviewedStats();
  const coverage = reviewed / state.dataset.meta.curated_count;
  const readiness = weightedReadiness();
  const score = 0.22 + readiness * 0.62 + coverage * 0.16;
  return Math.max(0.18, Math.min(0.98, score));
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

function renderHero() {
  els["stat-curated"].textContent = `${state.dataset.meta.curated_count}`;
  els["stat-days"].textContent = `${state.dataset.plan.days}日`;
  const today = todayPlan();
  els["stat-today"].textContent = `${today.new_questions_target + today.review_questions_target + today.mock_questions}問`;
  els["stat-today-sub"].textContent = today.message;

  const probability = passProbability();
  els["stat-pass"].textContent = `${Math.round(probability * 100)}%`;
  els["stat-pass-sub"].textContent = probability >= 0.75 ? "そのまま殴り切れ" : "まだ甘い。弱点を潰せ";
}

function renderDashboard() {
  const today = todayPlan();
  els["today-badge"].textContent = `Day ${today.day}`;
  els["today-card"].innerHTML = "";
  els["today-card"].appendChild(renderTodayBox(today));

  els["selection-policy"].innerHTML = "";
  state.dataset.selection_policy.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    els["selection-policy"].appendChild(li);
  });

  const progress = progressByDomain();
  const { reviewed } = reviewedStats();
  els["reviewed-count"].textContent = `${reviewed} / ${state.dataset.meta.curated_count}問を着手`;
  els["domain-progress"].innerHTML = "";
  progress.forEach((domain) => {
    els["domain-progress"].appendChild(renderProgressRow(domain));
  });

  renderNextPreview();
}

function renderTodayBox(today) {
  const div = document.createElement("div");
  div.className = "today-box";
  div.innerHTML = `
    <strong>${today.label} | ${today.message}</strong>
    <div>新規 ${today.new_questions_target}問 / 復習 ${today.review_questions_target}問${today.mock_questions ? ` / 模試 ${today.mock_questions}問` : ""}</div>
    <div>想定時間: 約${today.estimated_hours}時間</div>
    <div>重点分野: ${today.domain_split.map((item) => `${domainLabelJa(item.domain_key)} ${item.count}問`).join(" / ") || "復習中心"}</div>
    <div>復習優先: ${today.review_focus.map(domainLabelJa).join(" / ")}</div>
  `;
  return div;
}

function renderProgressRow(domain) {
  const wrap = document.createElement("div");
  wrap.className = "progress-row";
  const accuracy = Math.round(domain.accuracy * 100);
  wrap.innerHTML = `
    <div class="progress-label">
      <span>${domain.label_ja}</span>
      <span>${accuracy}% | ${domain.reviewed}/${domain.actual_count}問</span>
    </div>
    <div class="bar">
      <div class="bar-fill" style="width:${accuracy}%"></div>
    </div>
  `;
  return wrap;
}

function renderNextPreview() {
  const question = nextRecommendedQuestion(currentDomainMode());
  els["next-preview"].innerHTML = "";
  if (!question) {
    els["next-preview"].innerHTML = "<p>出題可能な問題がない。全問終わったなら模試へ行け。</p>";
    return;
  }
  const card = document.createElement("div");
  card.className = "preview-card";
  card.innerHTML = `
    <strong>${question.id} | ${question.domain_label_ja}</strong>
    <div>${question.prompt}</div>
    <div class="muted">選抜理由: ${question.yield_reasons.join(" / ")}</div>
  `;
  els["next-preview"].appendChild(card);
}

function renderDrillControls() {
  const mode = els["drill-mode"].value;
  els["domain-filter"].disabled = mode !== "focus";
  els["drill-status"].textContent = mode === "focus" ? domainLabelJa(els["domain-filter"].value) : "全範囲";
  renderNextPreview();
}

function currentDomainMode() {
  return els["drill-mode"].value === "focus" ? els["domain-filter"].value : null;
}

function nextRecommendedQuestion(domainKey = null) {
  const candidates = state.dataset.questions.filter((question) => !domainKey || question.domain_key === domainKey);
  const ranked = candidates
    .map((question) => ({ question, score: drillPriority(question) }))
    .sort((a, b) => b.score - a.score || a.question.curated_index - b.question.curated_index);
  return ranked[0]?.question || null;
}

function drillPriority(question) {
  const record = attemptRecord(question.id);
  let score = question.yield_score;
  const accuracy = record.total ? record.correct / record.total : 0;
  score += (1 - accuracy) * 28;
  score -= Math.min(record.streak * 3, 9);
  if (record.total === 0) score += 12;
  if (record.dueAt) {
    const due = new Date(record.dueAt).getTime();
    if (due <= Date.now()) score += 20;
    else score -= Math.min(10, (due - Date.now()) / (1000 * 60 * 60 * 6));
  }
  return score;
}

function loadNextDrillQuestion() {
  const question = nextRecommendedQuestion(currentDomainMode());
  if (!question) return;
  state.currentQuestionId = question.id;
  state.currentSelections = [];
  state.hintLevel = 0;
  renderCurrentQuestion();
}

function renderCurrentQuestion() {
  const question = state.dataset.questions.find((item) => item.id === state.currentQuestionId);
  if (!question) {
    els["question-card"].className = "question-card empty";
    els["question-card"].innerHTML = "<p>次の問題を出せ。</p>";
    return;
  }

  els["question-meta"].innerHTML = `
    <span class="pill">${question.id}</span>
    <span class="pill">${question.domain_label_ja}</span>
    <span class="pill">正答数: ${question.choose_count}</span>
    <span class="pill">優先度 ${question.yield_score}</span>
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
  const question = state.dataset.questions.find((item) => item.id === state.currentQuestionId);
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
  const question = state.dataset.questions.find((item) => item.id === state.currentQuestionId);
  if (!question) return;
  state.hintLevel += 1;
  const hintBox = els["hint-box"];
  hintBox.classList.remove("hidden");

  const hints = [];
  hints.push(`ヒント1: 正答は ${question.choose_count} 個。数を外すな。`);
  if (question.topic_tags.length) {
    hints.push(`ヒント2: キーワードは ${question.topic_tags.slice(0, 3).join(" / ")}。`);
  }
  const wrongChoice = question.choices.find((choice) => !question.correct_choice_ids.includes(choice.id));
  if (wrongChoice) {
    hints.push(`ヒント3: ${wrongChoice.id} は切れる可能性が高い。理由を言語化しろ。`);
  }
  hintBox.innerHTML = `<strong>ビシビシヒント</strong><div>${hints.slice(0, state.hintLevel).join("<br>")}</div>`;

  if (state.hintLevel >= 3 && wrongChoice) {
    const button = document.querySelector(`#question-card .choice-button[data-choice-id="${wrongChoice.id}"]`);
    button?.classList.add("eliminated");
  }
}

function submitCurrentQuestion() {
  const question = state.dataset.questions.find((item) => item.id === state.currentQuestionId);
  if (!question) return;
  const userIds = [...state.currentSelections].sort();
  const correctIds = [...question.correct_choice_ids].sort();
  const correct = JSON.stringify(userIds) === JSON.stringify(correctIds);
  updateAttempt(question.id, userIds, correct);

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
    ? "正解。だが再現できなければ意味がない。解説の論理を口で言い直せ。"
    : "不正解。理解が雑な証拠だ。なぜその選択肢を切れなかったか言語化しろ。";
  box.innerHTML = `
    <strong>${correct ? "正解" : "不正解"} | 正答 ${correctIds.join(",")}</strong>
    <div>${coach}</div>
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
  els["plan-summary"].textContent = `平均 ${state.dataset.plan.daily_attempt_target}問/日 | 現実ラインで組んである`;
  els["plan-grid"].innerHTML = "";
  const activeDay = sprintDay();
  state.dataset.plan.schedule.forEach((day) => {
    const card = document.createElement("article");
    card.className = `plan-card ${day.day === activeDay ? "active" : ""}`;
    card.innerHTML = `
      <strong>${day.label}</strong>
      <div>${day.message}</div>
      <div>新規 ${day.new_questions_target} / 復習 ${day.review_questions_target}${day.mock_questions ? ` / 模試 ${day.mock_questions}` : ""}</div>
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
  const selected = [];
  Object.entries(quotas).forEach(([domainKey, count]) => {
    const pool = state.dataset.questions
      .filter((question) => question.domain_key === domainKey)
      .sort((a, b) => drillPriority(b) - drillPriority(a));
    selected.push(...pool.slice(0, count));
  });
  return shuffle(selected).slice(0, 60);
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
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
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

  const qMap = questionMap();
  const currentId = session.questionIds[session.currentIndex];
  const question = qMap.get(currentId);
  const savedAnswer = session.answers[currentId]?.selectedIds || [];
  renderMockQuestion(question, savedAnswer);

  const answered = Object.keys(session.answers).length;
  els["mock-progress"].innerHTML = `
    <span class="pill">${session.currentIndex + 1} / ${session.questionIds.length}</span>
    <span class="pill">回答済み ${answered}</span>
    <span class="pill">${question.domain_label_ja}</span>
  `;
  setMockButtonsDisabled(false);

  if (session.finished) {
    renderMockResults();
  }
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
  session.currentIndex = Math.max(0, Math.min(session.questionIds.length - 1, session.currentIndex + delta));
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
  const qMap = questionMap();
  let correct = 0;
  const byDomain = {};
  session.questionIds.forEach((id) => {
    const question = qMap.get(id);
    const answer = [...(session.answers[id]?.selectedIds || [])].sort();
    const expected = [...question.correct_choice_ids].sort();
    const isCorrect = JSON.stringify(answer) === JSON.stringify(expected);
    if (isCorrect) correct += 1;
    byDomain[question.domain_key] ||= { correct: 0, total: 0, label: question.domain_label_ja };
    byDomain[question.domain_key].total += 1;
    if (isCorrect) byDomain[question.domain_key].correct += 1;
  });
  const score = Math.round((correct / session.questionIds.length) * 100);
  const weakest = Object.values(byDomain).sort((a, b) => a.correct / a.total - b.correct / b.total).slice(0, 3);

  els["mock-results"].innerHTML = `
    <div class="mock-card">
      <strong>模試スコア</strong>
      <div class="mock-score">${score}%</div>
      <div>${correct} / ${session.questionIds.length} 問正解</div>
      <div>弱点: ${weakest.map((item) => `${item.label} ${Math.round((item.correct / item.total) * 100)}%`).join(" / ")}</div>
      <div>${score >= 80 ? "この水準を2回続けろ。合格圏だ。" : "まだ甘い。弱点3分野を周回し直せ。"}</div>
    </div>
  `;
}

function setMockButtonsDisabled(disabled) {
  els["mock-prev"].disabled = disabled;
  els["mock-save"].disabled = disabled;
  els["mock-next"].disabled = disabled;
}

function domainLabelJa(domainKey) {
  const domain = state.dataset.domains.find((item) => item.domain_key === domainKey);
  return domain?.label_ja || domainKey;
}
