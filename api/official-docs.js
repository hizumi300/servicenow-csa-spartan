const fs = require("node:fs");
const path = require("node:path");

const DATASET_PATH = path.join(process.cwd(), "docs", "data", "csa600.json");
const SEARCH_API = "https://www.servicenow.com/docs/api/khub/clustered-search";
const SEARCH_PAGE = "https://www.servicenow.com/docs/search";
const CACHE_TTL_MS = 1000 * 60 * 60 * 6;
const RELEASE_PRIORITY = {
  australia: 6,
  latest: 5,
  zurich: 4,
  yokohama: 3,
  xanadu: 2,
  washingtondc: 1,
};

let datasetCache = null;
let datasetLoadedAt = 0;
const liveCache = new Map();

function json(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(payload));
}

function nowIso() {
  return new Date().toISOString();
}

function normalizeText(value) {
  return String(value || "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeKey(value) {
  return normalizeText(value)
    .toLowerCase()
    .normalize("NFKC");
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function lexicalTokens(value) {
  return normalizeKey(value)
    .replace(/[^a-z0-9\u3040-\u30ff\u3400-\u9fff ]/g, " ")
    .split(/\s+/)
    .filter((token) => token && token.length >= 2);
}

function stripHtml(value) {
  return normalizeText(
    String(value || "")
      .replace(/<span[^>]*class="kwictruncate"[^>]*>.*?<\/span>/gi, "…")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&#39;/g, "'")
      .replace(/&quot;/g, '"')
  );
}

function loadDataset() {
  const stat = fs.statSync(DATASET_PATH);
  if (!datasetCache || stat.mtimeMs > datasetLoadedAt) {
    datasetCache = JSON.parse(fs.readFileSync(DATASET_PATH, "utf-8"));
    datasetLoadedAt = stat.mtimeMs;
  }
  return datasetCache;
}

function conceptLabelJa(tag) {
  const labels = {
    next_experience_unified_navigation: "Next Experience統合ナビ",
    platform_analytics: "Platform Analytics",
    workflow_studio: "Workflow Studio",
    virtual_agent: "Virtual Agent",
    security_center: "Security Center",
    shared_responsibility_model: "Shared Responsibility Model",
    ui_policies: "UI Policies",
    business_rules: "Business Rules",
    importing_data: "Importing Data",
    application_access_control: "Access Control",
  };
  return labels[tag] || tag.replaceAll("_", " ");
}

function englishSearchTerm(term) {
  const raw = normalizeText(term);
  const reverse = new Map([
    ["Next Experience統合ナビ", "next experience unified navigation"],
    ["プラットフォーム概要", "platform overview"],
    ["インスタンス", "instance"],
    ["Platform Analytics", "platform analytics"],
    ["Workflow Studio", "workflow studio"],
    ["Virtual Agent", "virtual agent"],
    ["Security Center", "security center"],
    ["Shared Responsibility Model", "shared responsibility model"],
    ["UI Policies", "ui policies"],
    ["Access Control", "access control"],
  ]);
  return reverse.get(raw) || raw;
}

function queryFromQuestion(question) {
  if (question?.official_doc_evidence?.query) return question.official_doc_evidence.query;
  const basis = question?.doc_basis || {};
  const basisTerms = (basis.basis_terms || []).map(englishSearchTerm);
  const primary = englishSearchTerm(basis.primary_topic || "");
  const secondary = (basis.secondary_topics || []).map(englishSearchTerm);
  const release = (question.current_service_tags || []).slice(0, 2).map((tag) => tag.replaceAll("_", " "));
  const parts = unique([primary, ...secondary, ...basisTerms, ...release]).slice(0, 4);
  return parts.join(" ").trim();
}

function searchRequest(query) {
  return {
    query,
    clusterSortCriterions: [{ key: "family" }],
    metadataFilters: [],
    facets: [{ id: "family" }, { id: "media" }, { id: "product_name" }],
    sort: [],
    sortId: null,
    paging: { page: 1, perPage: 8 },
    keywordMatch: null,
    contentLocale: "en-US",
    virtualField: "EVERYWHERE",
    scope: "DEFAULT",
  };
}

function metadataValues(item) {
  const out = {};
  for (const meta of item.metadata || []) {
    if (!meta?.key) continue;
    out[String(meta.key)] = (meta.values || []).map((value) => normalizeText(value));
  }
  return out;
}

function flattenResults(payload) {
  const rows = [];
  for (const cluster of payload.results || []) {
    for (const entry of cluster.entries || []) {
      const item =
        entry.topic ||
        entry.map ||
        entry.document ||
        entry.unstructuredDocument ||
        entry.htmlPackage ||
        {};
      const metadata = metadataValues(item);
      rows.push({
        type: entry.type || item.editorialType || "unknown",
        title: normalizeText(item.title || ""),
        url: item.readerUrl || item.documentUrl || item.topicUrl || item.url || null,
        excerpt: stripHtml(item.htmlExcerpt || item.excerpt || ""),
        family: (metadata.family || []).map((value) => normalizeKey(value).replaceAll(" ", "")),
        productName: metadata.product_name || [],
        documentType: (metadata["ft:document_type"] || [entry.type || "unknown"])[0],
        updatedOn: (metadata["ft:lastTechChange"] || metadata["ft:lastEdition"] || metadata["ft:lastPublication"] || [null])[0],
      });
    }
  }
  return rows;
}

function scoreCandidate(candidate, query, question) {
  const basisTerms = (question.doc_basis?.basis_terms || []).map((term) => normalizeKey(term));
  const queryTerms = lexicalTokens(query).slice(0, 8);
  const titleKey = normalizeKey(candidate.title);
  const excerptKey = normalizeKey(candidate.excerpt);
  const urlKey = normalizeKey(candidate.url);

  let score = 0;
  if (candidate.family.length) {
    score += Math.max(...candidate.family.map((family) => RELEASE_PRIORITY[family] || 0)) * 9;
  }
  if (candidate.type === "TOPIC") score += 16;
  if (candidate.type === "MAP") score -= 4;
  if (titleKey.includes("api reference") || urlKey.includes("api-reference")) score -= 12;
  if (normalizeKey(query).includes("workflow studio") && titleKey.includes("classic workflow")) score -= 8;

  score += queryTerms.filter((term) => titleKey.includes(term)).length * 6;
  score += queryTerms.filter((term) => excerptKey.includes(term)).length * 2.4;
  score += basisTerms.filter((term) => term && (titleKey.includes(term) || excerptKey.includes(term) || urlKey.includes(term))).length * 4;

  const primary = normalizeKey(question.doc_basis?.primary_topic || "");
  if (primary && titleKey.includes(primary)) score += 12;
  if (candidate.excerpt) score += Math.min(8, candidate.excerpt.length / 42);
  return score;
}

async function searchOfficialDocs(query, question) {
  const response = await fetch(SEARCH_API, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json",
    },
    body: JSON.stringify(searchRequest(query)),
  });
  if (!response.ok) {
    throw new Error(`ServiceNow search failed: ${response.status}`);
  }
  const payload = await response.json();
  const candidates = flattenResults(payload);
  if (!candidates.length) return null;
  const ranked = [...candidates].sort((left, right) => {
    const delta = scoreCandidate(right, query, question) - scoreCandidate(left, query, question);
    if (delta !== 0) return delta;
    return String(left.title).localeCompare(String(right.title));
  });
  const best = ranked[0];
  return {
    source: "vercel-servicenow-live",
    query,
    title: best.title,
    url: best.url || `${SEARCH_PAGE}?q=${encodeURIComponent(query)}`,
    snippet: best.excerpt,
    release_family: best.family[0] || "unknown",
    product_name: best.productName[0] || best.title,
    document_type: best.documentType || best.type,
    updated_on: best.updatedOn,
    score: Number(scoreCandidate(best, query, question).toFixed(2)),
    fetched_at: nowIso(),
    alternatives: ranked.slice(1, 3).filter((item) => item.url).map((item) => ({
      title: item.title,
      url: item.url,
      release_family: item.family[0] || "unknown",
    })),
  };
}

module.exports = async (req, res) => {
  const dataset = loadDataset();
  const questionId = normalizeText(req.query.questionId || "");
  const rawQuery = normalizeText(req.query.query || "");

  let question = null;
  let query = rawQuery;
  if (questionId) {
    question = (dataset.questions || []).find((item) => item.id === questionId);
    if (!question) {
      return json(res, 404, { error: `unknown questionId: ${questionId}` });
    }
    if (!query) query = queryFromQuestion(question);
  }

  if (!query) {
    return json(res, 400, { error: "questionId or query is required" });
  }

  const cacheKey = `${questionId || "query"}::${normalizeKey(query)}`;
  const cached = liveCache.get(cacheKey);
  const force = String(req.query.force || "") === "1";
  if (!force && cached && Date.now() - cached.at < CACHE_TTL_MS) {
    return json(res, 200, cached.payload);
  }

  try {
    const evidence = await searchOfficialDocs(query, question || { doc_basis: {}, current_service_tags: [] });
    if (!evidence) {
      const fallback = question?.official_doc_evidence || null;
      if (fallback) return json(res, 200, fallback);
      return json(res, 404, { error: "no evidence found" });
    }
    liveCache.set(cacheKey, { at: Date.now(), payload: evidence });
    return json(res, 200, evidence);
  } catch (error) {
    const fallback = question?.official_doc_evidence || null;
    if (fallback) return json(res, 200, fallback);
    return json(res, 502, { error: String(error?.message || error) });
  }
};
