const state = {
  cases: [],
  filteredCases: [],
  selectedCase: null,
  selectedCaseId: null,
  session: { state: "idle" },
};

const elements = {
  search: document.querySelector("#case-search"),
  filters: {
    violation_type: document.querySelector("#filter-type"),
    app: document.querySelector("#filter-app"),
    tier: document.querySelector("#filter-tier"),
    evidence_state: document.querySelector("#filter-evidence"),
    status: document.querySelector("#filter-status"),
  },
  caseCount: document.querySelector("#case-count"),
  caseList: document.querySelector("#case-list"),
  detailTitle: document.querySelector("#case-detail-title"),
  caseSummary: document.querySelector("#case-summary"),
  detailFields: document.querySelector("#detail-fields"),
  caseMessage: document.querySelector("#case-message"),
  sessionStatus: document.querySelector("#session-status"),
  openVariant: document.querySelector("#open-variant"),
  stopVariant: document.querySelector("#stop-variant"),
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindEvents();
  await loadCases();
  await refreshSession();
  const caseFromUrl = new URLSearchParams(window.location.search).get("case");
  if (caseFromUrl && state.cases.some((item) => item.case_id === caseFromUrl)) {
    await selectCase(caseFromUrl, { updateUrl: false });
  } else if (state.cases.length > 0) {
    await selectCase(state.cases[0].case_id, { updateUrl: false });
  }
}

function bindEvents() {
  elements.search.addEventListener("input", applyFilters);
  Object.values(elements.filters).forEach((filter) => {
    filter.addEventListener("change", applyFilters);
  });
  elements.openVariant.addEventListener("click", openVariant);
  elements.stopVariant.addEventListener("click", stopVariant);
}

async function loadCases() {
  try {
    const data = await requestJson("/api/cases");
    state.cases = data.cases;
    populateFilters();
    applyFilters();
  } catch (error) {
    setMessage(error.message);
    elements.caseCount.textContent = "Could not load cases.";
  }
}

function populateFilters() {
  Object.entries(elements.filters).forEach(([field, select]) => {
    const values = uniqueValues(state.cases.map((item) => item[field]));
    replaceOptions(select, values);
  });
}

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b)),
  );
}

function replaceOptions(select, values) {
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All";
  select.append(all);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

function applyFilters() {
  const query = elements.search.value.trim().toLowerCase();
  state.filteredCases = state.cases.filter((item) => {
    const matchesQuery =
      !query ||
      [
        item.case_id,
        item.short_description,
        item.violation_type,
        item.pattern,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    const matchesFilters = Object.entries(elements.filters).every(
      ([field, select]) => !select.value || item[field] === select.value,
    );
    return matchesQuery && matchesFilters;
  });
  renderCaseList();
}

function renderCaseList() {
  elements.caseList.replaceChildren();
  elements.caseCount.textContent = `${state.filteredCases.length} case${
    state.filteredCases.length === 1 ? "" : "s"
  } shown`;

  state.filteredCases.forEach((item) => {
    const listItem = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "case-row";
    button.setAttribute(
      "aria-current",
      item.case_id === state.selectedCaseId ? "true" : "false",
    );
    button.addEventListener("click", () => selectCase(item.case_id));

    const caseId = document.createElement("span");
    caseId.className = "case-id";
    caseId.textContent = item.case_id;

    const description = document.createElement("span");
    description.textContent = item.short_description;

    const meta = document.createElement("span");
    meta.className = "case-meta";
    meta.textContent = `${item.violation_type} / ${item.tier} / ${item.evidence_state} / ${item.status}`;

    button.append(caseId, description, meta);
    listItem.append(button);
    elements.caseList.append(listItem);
  });
}

async function selectCase(caseId, options = {}) {
  try {
    const data = await requestJson(`/api/cases/${encodeURIComponent(caseId)}`);
    state.selectedCase = data.case;
    state.selectedCaseId = caseId;
    renderDetail();
    renderCaseList();
    if (options.updateUrl !== false) {
      const url = new URL(window.location.href);
      url.searchParams.set("case", caseId);
      window.history.replaceState({}, "", url);
    }
  } catch (error) {
    setMessage(error.message);
  }
}

function renderDetail() {
  const item = state.selectedCase;
  if (!item) {
    return;
  }
  elements.detailTitle.textContent = item.case_id;
  elements.caseSummary.textContent = item.short_description;
  elements.detailFields.replaceChildren();

  const fields = [
    ["Violation type", item.violation_type],
    ["App", item.app],
    ["Status", item.status],
    ["Tier", item.tier],
    ["Evidence state", item.evidence_state],
    ["Pattern", item.pattern],
    ["Profile", item.profile || "(none)"],
    ["Baseline", item.baseline],
    ["Mutation", item.mutation],
    ["Why unambiguous", item.why_unambiguous],
    ["Interaction path", item.interaction_path],
  ];
  fields.forEach(([label, value]) => addDetailField(label, value || ""));
  setMessage(item.launch_error || "");
  updateActionState();
}

function addDetailField(label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  elements.detailFields.append(term, description);
}

async function openVariant() {
  if (!state.selectedCase || !state.selectedCase.launchable) {
    return;
  }
  setMessage("Starting variant...");
  state.session = {
    state: "starting",
    case_id: state.selectedCase.case_id,
    profile: state.selectedCase.profile,
  };
  updateSessionStatus();
  updateActionState();
  try {
    const data = await requestJson("/api/session/open", {
      method: "POST",
      body: JSON.stringify({ case_id: state.selectedCase.case_id }),
    });
    state.session = data.session;
    setMessage("Variant running. Use the visible interaction path for manual review.");
  } catch (error) {
    await refreshSession();
    setMessage(error.message);
  }
  updateSessionStatus();
  updateActionState();
}

async function stopVariant() {
  setMessage("Stopping variant...");
  updateActionState();
  try {
    const data = await requestJson("/api/session/stop", { method: "POST" });
    state.session = data.session;
    setMessage("Variant stopped.");
  } catch (error) {
    setMessage(error.message);
  }
  updateSessionStatus();
  updateActionState();
}

async function refreshSession() {
  try {
    const data = await requestJson("/api/session/status");
    state.session = data.session;
    updateSessionStatus();
    updateActionState();
  } catch (error) {
    setMessage(error.message);
  }
}

function updateSessionStatus() {
  const session = state.session || { state: "idle" };
  if (session.state === "running") {
    elements.sessionStatus.textContent = `Session: running ${session.case_id} (${session.profile})`;
  } else if (session.state === "starting") {
    elements.sessionStatus.textContent = `Session: starting ${session.case_id}`;
  } else if (session.state === "error") {
    elements.sessionStatus.textContent = `Session: error`;
    setMessage(session.message || "The variant session failed.");
  } else {
    elements.sessionStatus.textContent = "Session: idle";
  }
}

function updateActionState() {
  const item = state.selectedCase;
  const sessionState = state.session ? state.session.state : "idle";
  const busy = sessionState === "starting";
  elements.openVariant.disabled = !item || !item.launchable || busy;
  elements.stopVariant.disabled = !["starting", "running", "error"].includes(
    sessionState,
  );
}

function setMessage(message) {
  elements.caseMessage.textContent = message || "";
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const message =
      data && data.error && data.error.message
        ? data.error.message
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return data;
}
