/* ============================================================
   風險分析Demo — front-end logic
   Binds the risk engine's output (risk_report / grouped_report /
   prompts / generated sections) to the wizard UI. Vanilla JS, no build.
   ============================================================ */
"use strict";

// Canonical section order + generated-section (4-x) mapping (see api.py).
const SECTION_ORDER = ["財務結構", "償債能力", "經營效能", "獲利能力", "現金流量"];
const SECTION_TO_NUM = {
  "財務結構": "4-1", "償債能力": "4-2", "經營效能": "4-3",
  "獲利能力": "4-4", "現金流量": "4-5",
};
const STATUS_TEXT = { triggered: "觸發", not_triggered: "未觸發", missing: "缺資料" };

// Canonical upload slots — filename keyword match, falling back to the
// repo's own `財報_<n><label>.html` digit convention, falling back to
// raw pick-order (with a visible warning) since a multi-file <input>
// does not guarantee the browser preserves click order.
const SLOT_DEFS = [
  { field: "file_overview", label: "財務概況", digit: 1, re: /財務概況|概況|overview/i },
  { field: "file_ratio", label: "財務比率", digit: 2, re: /財務比率|比率|ratio/i },
  { field: "file_cashflow", label: "現金流量", digit: 3, re: /現金流量|現金流|cashflow|cash/i },
  { field: "file_equity", label: "淨值調節", digit: 4, re: /淨值調節|淨值|權益|equity/i },
];
const SLOT_MARKS = ["①", "②", "③", "④"];

const STEP_LABELS = ["讀取財報 HTML…", "解析財務科目…", "比對風險指標門檻…", "彙整多期趨勢…", "整理最終報告…"];
const STEP_LABELS_GEN = ["讀取財報 HTML…", "解析財務科目…", "比對風險指標門檻…", "彙整多期趨勢…", "呼叫 LLM 生成敘述…", "整理最終報告…"];

const ICON_INFO_SVG = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v4"/><path d="M12 16h.01"/><circle cx="12" cy="12" r="9"/></svg>';

// ── DOM helpers ────────────────────────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("data-")) node.setAttribute(k, v);
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

function fmtNum(v) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v !== "number") return String(v);
  return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function triggeredCount(entries) {
  let n = 0;
  for (const e of entries || []) for (const t of e.taggings || []) if (t.status === "triggered") n++;
  return n;
}

function orderedSections(data) {
  const keys = new Set([
    ...Object.keys(data.risk_report?.sections || {}),
    ...Object.keys(data.grouped_report || {}),
  ]);
  const ordered = SECTION_ORDER.filter((s) => keys.has(s));
  for (const k of keys) if (!ordered.includes(k)) ordered.push(k);
  return ordered;
}

// ── State ──────────────────────────────────────────────────
const state = {
  stage: "upload",
  tab: "narr",
  slotFiles: [null, null, null, null],
  lastResult: null,
  analyzeTimer: null,
  progressTimer: null,
  // null = unknown (health not loaded); true/false once /api/health resolves.
  hasLlmEnv: null,
};

function setStage(name) {
  state.stage = name;
  $("#stage-upload").hidden = name !== "upload";
  $("#stage-analyzing").hidden = name !== "analyzing";
  $("#stage-done").hidden = name !== "done";
  $("#header-done").hidden = name !== "done";
}

function showError(msg) {
  const banner = $("#error-banner");
  banner.textContent = "分析失敗：" + msg;
  banner.hidden = false;
}

// ── Bootstrap ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  refreshHealth();
  loadIndustries();
  renderFileChips();

  $("#file-picker").addEventListener("change", (e) => handleFilePick(e.target.files));
  $("#btn-sample").addEventListener("click", onSampleClick);
  $("#btn-analyze").addEventListener("click", onAnalyzeClick);
  $("#btn-export-json").addEventListener("click", openJsonModal);
  $("#btn-reset").addEventListener("click", resetToUpload);

  $("#industry").addEventListener("change", updateAnalyzeButtonState);
  const gen = $("#generate");
  gen.addEventListener("change", () => {
    $("#llm-config").hidden = !gen.checked;
    updateLlmWarning();
    updateAnalyzeButtonState();
  });

  $("#tab-btn-narr").addEventListener("click", () => switchTab("narr"));
  $("#tab-btn-data").addEventListener("click", () => switchTab("data"));
  $("#tab-btn-risk").addEventListener("click", () => switchTab("risk"));

  $("#btn-copy-json").addEventListener("click", copyJson);
  $("#btn-download-json").addEventListener("click", downloadJson);
  $("#btn-close-json").addEventListener("click", closeJsonModal);
  $("#json-modal").addEventListener("click", (e) => {
    if (e.target.id === "json-modal") closeJsonModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#json-modal").hidden) closeJsonModal();
  });
});

async function refreshHealth() {
  const warn = $("#health-warning");
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    state.hasLlmEnv = !!h.has_llm_env;
    const ok = h.status === "ok" && h.has_xlsx;
    warn.hidden = ok;
    if (!ok) warn.textContent = `伺服器資源不完整（${h.status}），分析功能可能無法使用。`;
  } catch {
    state.hasLlmEnv = null; // unknown — don't block generate, let the server decide
    warn.hidden = false;
    warn.textContent = "無法連線至伺服器。";
  }
  updateLlmWarning();
  updateAnalyzeButtonState();
}

// Show the "server has no LLM endpoint" warning only when the user has enabled
// 生成敘述段落 and health has definitively reported the env is unset.
function updateLlmWarning() {
  const show = $("#generate").checked && state.hasLlmEnv === false;
  $("#llm-env-warning").hidden = !show;
}

async function loadIndustries() {
  const sel = $("#industry");
  try {
    const r = await fetch("/api/industries");
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const { industries } = await r.json();
    sel.innerHTML = "";
    sel.appendChild(el("option", { value: "", disabled: true, selected: true, text: "請選擇產業別" }));
    for (const ind of industries) sel.appendChild(el("option", { value: ind, text: ind }));
  } catch (e) {
    sel.innerHTML = "";
    sel.appendChild(el("option", { value: "", disabled: true, selected: true, text: "產業別載入失敗" }));
    console.error("loadIndustries", e);
  }
  updateAnalyzeButtonState();
}

// ── File slot matching ──────────────────────────────────────
function matchSlots(files) {
  const assigned = new Array(SLOT_DEFS.length).fill(null);
  const usedFileIdx = new Set();

  SLOT_DEFS.forEach((slot, si) => {
    for (let fi = 0; fi < files.length; fi++) {
      if (usedFileIdx.has(fi)) continue;
      if (slot.re.test(files[fi].name)) {
        assigned[si] = files[fi];
        usedFileIdx.add(fi);
        break;
      }
    }
  });
  SLOT_DEFS.forEach((slot, si) => {
    if (assigned[si]) return;
    const digitRe = new RegExp(`(^|[^0-9])${slot.digit}([^0-9]|$)`);
    for (let fi = 0; fi < files.length; fi++) {
      if (usedFileIdx.has(fi)) continue;
      if (digitRe.test(files[fi].name)) {
        assigned[si] = files[fi];
        usedFileIdx.add(fi);
        break;
      }
    }
  });
  return assigned.every(Boolean) ? assigned : null;
}

function handleFilePick(fileList) {
  const files = Array.from(fileList || []);
  const note = $("#filelist-note");
  note.hidden = true;

  if (files.length !== 4) {
    state.slotFiles = [null, null, null, null];
    if (files.length > 0) {
      note.hidden = false;
      note.textContent = `請選擇正好 4 個檔案（目前 ${files.length} 個）`;
    }
    renderFileChips();
    updateAnalyzeButtonState();
    return;
  }

  const matched = matchSlots(files);
  if (matched) {
    state.slotFiles = matched;
  } else {
    state.slotFiles = files.slice(0, 4);
    note.hidden = false;
    note.textContent = "檔名未包含可辨識關鍵字，已依選取順序對應 ①②③④，請確認順序是否正確。";
  }
  renderFileChips();
  updateAnalyzeButtonState();
}

function renderFileChips() {
  const wrap = $("#filelist");
  wrap.innerHTML = "";
  const any = state.slotFiles.some(Boolean);
  $("#filelist-empty").hidden = any;
  SLOT_DEFS.forEach((slot, i) => {
    const f = state.slotFiles[i];
    if (!f) return;
    wrap.appendChild(el("div", { class: "filechip" }, [
      el("span", { class: "filechip__slot", text: SLOT_MARKS[i] }),
      el("span", { class: "filechip__name", text: f.name }),
      el("span", { class: "filechip__check", text: "✓" }),
    ]));
  });
}

function updateAnalyzeButtonState() {
  const allFiles = state.slotFiles.every(Boolean);
  const industryOk = !!$("#industry").value;
  const genChecked = $("#generate").checked;
  // Credentials come from server .env; only block when health has definitively
  // reported the LLM env is missing (unknown/null → let the server decide).
  const llmOk = !genChecked || state.hasLlmEnv !== false;
  $("#btn-analyze").disabled = !(allFiles && industryOk && llmOk);
}

// ── Analyzing-stage animation ───────────────────────────────
function startAnalyzingAnimation(generate) {
  const labels = generate ? STEP_LABELS_GEN : STEP_LABELS;
  let i = 0;
  $("#analyzing-label").textContent = labels[0];
  state.analyzeTimer = setInterval(() => {
    i = (i + 1) % labels.length;
    $("#analyzing-label").textContent = labels[i];
  }, 1800);

  const start = performance.now();
  $("#progress-fill").style.width = "0%";
  state.progressTimer = setInterval(() => {
    const elapsedSec = (performance.now() - start) / 1000;
    const pct = 92 * (1 - Math.exp(-elapsedSec / 8));
    $("#progress-fill").style.width = pct.toFixed(1) + "%";
  }, 200);
}

function stopAnalyzingAnimation() {
  clearInterval(state.analyzeTimer);
  clearInterval(state.progressTimer);
  state.analyzeTimer = null;
  state.progressTimer = null;
}

// ── Actions ────────────────────────────────────────────────
async function onSampleClick() {
  $("#error-banner").hidden = true;
  setStage("analyzing");
  startAnalyzingAnimation(false);
  try {
    const [data] = await Promise.all([
      fetch("/api/sample").then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
      }),
      delay(900),
    ]);
    finishAnalyzing(data);
  } catch (e) {
    stopAnalyzingAnimation();
    setStage("upload");
    showError(e.message);
  }
}

async function onAnalyzeClick() {
  const generate = $("#generate").checked;
  const fd = new FormData();
  fd.append("file_overview", state.slotFiles[0]);
  fd.append("file_ratio", state.slotFiles[1]);
  fd.append("file_cashflow", state.slotFiles[2]);
  fd.append("file_equity", state.slotFiles[3]);
  fd.append("industry", $("#industry").value);
  fd.append("customer_id", $("#customer_id").value);
  fd.append("report_date", $("#report_date").value);
  fd.append("generate", generate ? "true" : "false");
  // LLM 端點由伺服器 .env 提供，前端不再傳送金鑰。

  $("#error-banner").hidden = true;
  setStage("analyzing");
  startAnalyzingAnimation(generate);

  try {
    const r = await fetch("/api/analyze", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    finishAnalyzing(data);
  } catch (e) {
    stopAnalyzingAnimation();
    setStage("upload");
    showError(e.message);
  }
}

function finishAnalyzing(data) {
  stopAnalyzingAnimation();
  $("#progress-fill").style.width = "100%";
  state.lastResult = data;
  setTimeout(() => {
    setStage("done");
    renderDone(data);
  }, 200);
}

function resetToUpload() {
  setStage("upload");
  state.slotFiles = [null, null, null, null];
  state.lastResult = null;
  $("#file-picker").value = "";
  $("#filelist-note").hidden = true;
  $("#error-banner").hidden = true;
  renderFileChips();
  updateAnalyzeButtonState();
}

// ── Rendering: done stage ────────────────────────────────────
function renderDone(data) {
  const rr = data.risk_report || {};
  $("#hdr-customer").textContent = data.customer_id || rr.customer_id || "—";
  $("#hdr-date").textContent = data.report_date || rr.report_date || "—";
  $("#hdr-request").textContent = data.request_id || "—";

  const s = rr.summary || {};
  $("#stat-total").textContent = s.total_indicators ?? "—";
  $("#stat-trig").textContent = s.triggered_count ?? "—";
  $("#stat-not").textContent = s.not_triggered_count ?? "—";
  $("#stat-miss").textContent = s.missing_count ?? "—";

  renderNarrTab(data);
  renderDataTab(data);
  renderRiskTab(data);
  switchTab("narr");
}

function switchTab(name) {
  state.tab = name;
  for (const t of ["narr", "data", "risk"]) {
    const isActive = t === name;
    $("#tab-btn-" + t).classList.toggle("is-active", isActive);
    $("#tab-btn-" + t).setAttribute("aria-selected", String(isActive));
    $("#tabpanel-" + t).hidden = !isActive;
  }
}

function renderNarrTab(data) {
  const root = $("#tabpanel-narr");
  root.innerHTML = "";
  const narr = data.narrative_sections || {};
  const risk = data.risk_sections || {};
  const hasNarrative = Object.keys(narr).length;
  const hasRisk = Object.keys(risk).length;

  if (!hasNarrative && !hasRisk) {
    root.appendChild(el("div", { class: "narr-empty" }, [
      el("div", { class: "stage-icon", html: ICON_INFO_SVG }),
      el("div", { class: "narr-empty__title", text: "尚未啟用 LLM 生成敘述段落" }),
      el("p", { class: "narr-empty__sub", text: "請於「進階設定」開啟「呼叫 LLM 生成敘述段落」並填寫端點資訊後重新分析。" }),
    ]));
    return;
  }

  // 整份報告一起呈現：單一文件容器，內部依段落標題分段。每段先敘事、
  // 後風險，兩者接續成文，不標記來源；個別段落無文字時以 placeholder 提示。
  const doc = el("div", { class: "narr-doc" });
  for (const name of orderedSections(data)) {
    const num = SECTION_TO_NUM[name] || name;
    const paras = [];
    if (narr[num]) paras.push(el("p", { class: "narr-doc__text", text: narr[num] }));
    if (risk[num]) paras.push(el("p", { class: "narr-doc__text", text: risk[num] }));
    if (!paras.length) {
      paras.push(el("p", { class: "narr-doc__text narr-doc__text--placeholder", text: "本段落尚未生成內容。" }));
    }
    doc.appendChild(el("section", { class: "narr-doc__section" }, [
      el("h3", { class: "narr-doc__heading" }, [
        el("span", { class: "narr-doc__code", text: num }),
        el("span", { class: "narr-doc__title", text: name }),
      ]),
      ...paras,
    ]));
  }
  root.appendChild(doc);
}

function renderDataTab(data) {
  const root = $("#tabpanel-data");
  root.innerHTML = "";
  const grouped = data.grouped_report || {};
  const sections = orderedSections(data).filter((name) => grouped[name] && Object.keys(grouped[name]).length);

  if (!sections.length) {
    root.appendChild(el("p", { class: "filelist__empty", text: "無財報資料。" }));
    return;
  }

  const grid = el("div", { class: "fin-grid" });
  sections.forEach((name, i) => {
    const wide = sections.length % 2 === 1 && i === sections.length - 1;
    const rows = Object.entries(grouped[name]);
    const card = el("div", { class: "fin-card" + (wide ? " fin-card--wide" : "") }, [
      el("div", { class: "fin-card__head", text: name }),
      el("div", { class: "fin-card__body", role: "table" }, [
        el("div", { class: "fin-row fin-row--head", role: "row" }, [
          el("span", { role: "columnheader", text: "科目" }),
          el("span", { role: "columnheader", text: "當期" }),
          el("span", { role: "columnheader", text: "前期" }),
          el("span", { role: "columnheader", text: "前前期" }),
        ]),
        ...rows.map(([code, row]) => el("div", { class: "fin-row", role: "row" }, [
          el("span", { class: "fin-row__name", role: "cell" }, [
            row.FA_CANME || code,
            el("span", { class: "fin-row__unit", text: row["單位"] || "" }),
          ]),
          el("span", { class: "fin-row__num fin-row__num--cur", role: "cell", text: fmtNum(row.Current) ?? "—" }),
          el("span", { class: "fin-row__num fin-row__num--prev", role: "cell", text: fmtNum(row.Period_2) ?? "—" }),
          el("span", { class: "fin-row__num fin-row__num--prev", role: "cell", text: fmtNum(row.Period_3) ?? "—" }),
        ])),
      ]),
    ]);
    grid.appendChild(card);
  });
  root.appendChild(grid);
}

function renderRiskTab(data) {
  const root = $("#tabpanel-risk");
  root.innerHTML = "";
  const rr = data.risk_report || {};
  const sections = orderedSections(data).filter((name) => (rr.sections?.[name] || []).length);

  if (!sections.length) {
    root.appendChild(el("p", { class: "filelist__empty", text: "無風險判定資料。" }));
    return;
  }

  for (const name of sections) {
    const entries = rr.sections[name] || [];
    const num = SECTION_TO_NUM[name] || name;
    const trig = triggeredCount(entries);

    const card = el("div", { class: "risk-card" });
    card.appendChild(el("div", { class: "risk-card__head" }, [
      el("div", { class: "risk-card__title" }, [
        el("span", { class: "risk-card__code", text: num }), name,
      ]),
      el("div", { class: "risk-card__count" }, [
        "觸發 ", el("b", { text: String(trig) }), ` / ${entries.length}`,
      ]),
    ]));
    const body = el("div", { class: "risk-card__body" });
    for (const e of entries) body.appendChild(renderRiskRow(e));
    card.appendChild(body);
    root.appendChild(card);
  }
}

function renderRiskRow(e) {
  const tpl = $("#tpl-risk-indicator").content.cloneNode(true);
  const row = tpl.querySelector(".risk-row");
  const taggings = e.taggings || [];
  const primary = taggings.find((t) => t.status === "triggered") || taggings[0] || { status: "missing" };
  const status = primary.status || "missing";

  const badge = tpl.querySelector(".status-badge");
  badge.classList.add("status-badge--" + status);
  tpl.querySelector(".status-badge__label").textContent = STATUS_TEXT[status] || status;

  const displayName = e.indicator_name || e.indicator_code || "(未命名指標)";
  tpl.querySelector(".risk-row__name").textContent = displayName;
  tpl.querySelector(".risk-row__cur").textContent = e.current_display || fmtNum(e.current_value) || "—";
  tpl.querySelector(".risk-row__prev").textContent = "前期 " + (e.previous_display || fmtNum(e.previous_value) || "—");

  const detail = tpl.querySelector(".risk-row__detail");
  if (status === "triggered" && primary.threshold) {
    detail.hidden = false;
    tpl.querySelector(".risk-row__threshold").textContent = "門檻 " + primary.threshold;
    tpl.querySelector(".risk-row__desc").textContent = primary.description || "";
  } else {
    detail.remove();
  }
  return row;
}

// ── JSON export modal ────────────────────────────────────────
function openJsonModal() {
  if (!state.lastResult) return;
  $("#json-modal-body").textContent = JSON.stringify(state.lastResult, null, 2);
  $("#json-modal").hidden = false;
}

function closeJsonModal() {
  $("#json-modal").hidden = true;
}

async function copyJson() {
  const btn = $("#btn-copy-json");
  try {
    await navigator.clipboard.writeText($("#json-modal-body").textContent);
    btn.textContent = "已複製 ✓";
  } catch {
    btn.textContent = "複製失敗";
  }
  setTimeout(() => (btn.textContent = "複製"), 1500);
}

function downloadJson() {
  if (!state.lastResult) return;
  const rr = state.lastResult.risk_report || {};
  const name = state.lastResult.customer_id || rr.customer_id || state.lastResult.request_id || "risk_report";
  const blob = new Blob([JSON.stringify(state.lastResult, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: `risk_report_${name}.json` });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
