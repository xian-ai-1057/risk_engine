/* ============================================================
   風險分析Demo — front-end logic
   Binds the risk engine's output (risk_report / grouped_report /
   prompts / generated sections) to the dashboard. Vanilla JS, no build.
   ============================================================ */
"use strict";

// Canonical section order + generated-section (4-x) mapping (see api.py).
const SECTION_ORDER = ["財務結構", "償債能力", "經營效能", "獲利能力", "現金流量"];
const SECTION_TO_NUM = {
  "財務結構": "4-1", "償債能力": "4-2", "經營效能": "4-3",
  "獲利能力": "4-4", "現金流量": "4-5",
};
const STATUS_TEXT = { triggered: "觸發", not_triggered: "未觸發", missing: "缺資料" };
const PERIOD_COLS = [
  ["Current", "當期"], ["Period_2", "前期"], ["Period_3", "前前期"],
];

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

// ── State views ────────────────────────────────────────────
const view = {
  empty:   $("#empty-state"),
  loading: $("#loading-state"),
  error:   $("#error-state"),
  report:  $("#report"),
};
function show(which, msg) {
  for (const k of Object.keys(view)) view[k].hidden = k !== which;
  if (which === "loading" && msg) $("#loading-text").textContent = msg;
}
function showError(msg) {
  view.error.innerHTML = "";
  view.error.appendChild(el("strong", { text: "分析失敗 " }));
  view.error.appendChild(document.createTextNode(msg));
  show("error");
}

// ── Bootstrap ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  refreshHealth();
  loadIndustries();

  const gen = $("#generate");
  gen.addEventListener("change", () => {
    const cfg = $("#llm-config");
    cfg.hidden = !gen.checked;
    for (const id of ["llm_base_url", "llm_model", "llm_api_key"]) {
      $("#" + id).required = gen.checked;
    }
  });

  $("#analyze-form").addEventListener("submit", onAnalyze);
  $("#btn-sample").addEventListener("click", onSample);
});

async function refreshHealth() {
  const box = $("#health");
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    const ok = h.status === "ok" && h.has_xlsx;
    box.className = "topbar__health " + (ok ? "ok" : "bad");
    box.innerHTML = "";
    box.appendChild(el("span", { class: "dot" }));
    box.appendChild(document.createTextNode(ok ? "引擎資源就緒" : "資源不完整"));
  } catch {
    box.className = "topbar__health bad";
    box.textContent = "無法連線";
  }
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
}

// ── Actions ────────────────────────────────────────────────
async function onSample() {
  show("loading", "載入範例資料…");
  try {
    const r = await fetch("/api/sample");
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    renderReport(await r.json());
  } catch (e) {
    showError(e.message);
  }
}

async function onAnalyze(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const btn = $("#btn-analyze");
  const fd = new FormData(form);
  fd.set("generate", $("#generate").checked ? "true" : "false");

  btn.disabled = true;
  show("loading", $("#generate").checked ? "分析中，並呼叫 LLM 生成敘述…" : "分析中…");
  try {
    const r = await fetch("/api/analyze", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    renderReport(data);
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
  }
}

// ── Rendering ──────────────────────────────────────────────
function orderedSections(data) {
  const keys = new Set([
    ...Object.keys(data.risk_report?.sections || {}),
    ...Object.keys(data.grouped_report || {}),
  ]);
  const ordered = SECTION_ORDER.filter((s) => keys.has(s));
  for (const k of keys) if (!ordered.includes(k)) ordered.push(k);
  return ordered;
}

function renderReport(data) {
  const root = view.report;
  root.innerHTML = "";
  const rr = data.risk_report || {};
  const summary = rr.summary || {};

  root.appendChild(renderMeta(data));
  root.appendChild(renderSummary(summary));

  const sections = orderedSections(data);
  const { tabs, pages } = renderTabs(data, sections);
  root.appendChild(tabs);
  root.appendChild(pages);

  if (data.narrative_sections || data.risk_sections) {
    root.appendChild(renderGenerated(data));
  }
  root.appendChild(renderPrompts(data));

  show("report");
}

function renderMeta(data) {
  const rr = data.risk_report || {};
  const meta = el("div", { class: "report-meta" });
  const add = (label, val) => {
    if (!val && val !== 0) return;
    meta.appendChild(el("span", {}, [label + "：", el("b", { text: String(val) })]));
  };
  add("產業別", data.industry || rr.industry);
  add("客戶", data.customer_id || rr.customer_id);
  add("報告日期", data.report_date || rr.report_date);
  add("規則總數", rr.summary?.total_rules);
  add("request_id", data.request_id);
  return meta;
}

function renderSummary(s) {
  const wrap = el("div", { class: "summary" });
  const cards = [
    ["", "指標項目", s.total_indicators],
    ["stat--warn", "觸發", s.triggered_count],
    ["stat--ok", "未觸發", s.not_triggered_count],
    ["stat--miss", "缺資料", s.missing_count],
  ];
  for (const [cls, cap, num] of cards) {
    wrap.appendChild(el("div", { class: "stat " + cls }, [
      el("div", { class: "stat__num", text: num == null ? "—" : String(num) }),
      el("div", { class: "stat__cap", text: cap }),
    ]));
  }
  return wrap;
}

function triggeredCount(entries) {
  let n = 0;
  for (const e of entries || []) for (const t of e.taggings || []) if (t.status === "triggered") n++;
  return n;
}

function renderTabs(data, sections) {
  const tabs = el("div", { class: "tabs", role: "tablist" });
  const pages = el("div", { class: "tabpages" });
  const rr = data.risk_report || {};

  sections.forEach((name, i) => {
    const entries = rr.sections?.[name] || [];
    const trig = triggeredCount(entries);
    const tab = el("button", { class: "tab" + (i === 0 ? " active" : ""), type: "button" }, [
      name,
      el("span", { class: "tab__count", "data-zero": String(trig === 0), text: String(trig) }),
    ]);
    const page = el("div", { class: "tabpage" + (i === 0 ? " active" : "") });
    page.appendChild(renderSectionBody(name, entries, data.grouped_report?.[name]));

    tab.addEventListener("click", () => {
      $$(".tab", tabs).forEach((t) => t.classList.remove("active"));
      $$(".tabpage", pages).forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      page.classList.add("active");
    });
    tabs.appendChild(tab);
    pages.appendChild(page);
  });
  return { tabs, pages };
}

function renderSectionBody(name, entries, grouped) {
  const frag = document.createDocumentFragment();
  frag.appendChild(el("h3", { class: "section-title" }, [
    name, el("span", { class: "pill", text: `${entries.length} 指標` }),
  ]));

  // Indicator cards
  if (entries.length) {
    frag.appendChild(el("div", { class: "subhead", text: "風險指標判定" }));
    const grid = el("div", { class: "indicators" });
    for (const e of entries) grid.appendChild(renderIndicator(e));
    frag.appendChild(grid);
  } else {
    frag.appendChild(el("p", { class: "empty-note", text: "本段落無風險指標。" }));
  }

  // Trend table
  if (grouped && Object.keys(grouped).length) {
    frag.appendChild(el("div", { class: "subhead", text: "財報數據（多期比較）" }));
    frag.appendChild(renderTrendTable(grouped));
  }
  return frag;
}

function renderIndicator(e) {
  const tpl = $("#tpl-indicator").content.cloneNode(true);
  const card = tpl.querySelector(".indicator");
  const anyTriggered = (e.taggings || []).some((t) => t.status === "triggered");
  if (anyTriggered) card.classList.add("is-triggered");

  const displayName = e.indicator_name || e.indicator_code || "(未命名指標)";
  tpl.querySelector(".indicator__name").textContent = displayName;
  const codeEl = tpl.querySelector(".indicator__code");
  // Only show the formula code line when it adds info beyond the title.
  if (e.indicator_code && e.indicator_code !== displayName) codeEl.textContent = e.indicator_code;
  else codeEl.remove();

  tpl.querySelector(".indicator__num").textContent = e.current_display || fmtNum(e.current_value) || "—";
  tpl.querySelector(".indicator__label").textContent = e.value_label || "";

  const ops = tpl.querySelector(".indicator__operands");
  for (const o of e.operands || []) {
    ops.appendChild(el("span", { class: "operand" }, [
      el("b", { text: o.name || o.code || "" }),
      el("span", { class: "op-period", text: o.period_label || "" }),
      " ", (o.display || fmtNum(o.value) || "—"),
    ]));
  }
  if (!(e.operands || []).length) ops.remove();

  const tags = tpl.querySelector(".indicator__tags");
  for (const t of e.taggings || []) {
    const st = t.status || "missing";
    tags.appendChild(el("div", { class: "tag tag--" + st }, [
      el("span", { class: "badge badge--" + st, text: STATUS_TEXT[st] || st }),
      t.threshold ? el("span", { class: "tag__thresh", text: "門檻 " + t.threshold }) : null,
      t.description ? el("span", { class: "tag__desc", text: t.description }) : null,
    ]));
  }
  if (!(e.taggings || []).length) tags.remove();
  return card;
}

function renderTrendTable(grouped) {
  const wrap = el("div", { class: "table-wrap" });
  const table = el("table", { class: "trend" });
  const thead = el("thead");
  const hrow = el("tr", {}, [
    el("th", { class: "code", text: "代碼" }),
    el("th", { class: "name", text: "會計科目" }),
    el("th", { text: "單位" }),
    ...PERIOD_COLS.map(([, label]) => el("th", { text: label })),
  ]);
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const [code, row] of Object.entries(grouped)) {
    const tds = [
      el("td", { class: "code", text: code }),
      el("td", { class: "name", text: row.FA_CANME || "" }),
      el("td", { text: row["單位"] || "" }),
    ];
    for (const [key] of PERIOD_COLS) {
      const v = fmtNum(row[key]);
      tds.push(el("td", { class: "num" + (v === null ? " na" : "") , text: v === null ? "—" : v }));
    }
    tbody.appendChild(el("tr", {}, tds));
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function renderGenerated(data) {
  const block = el("div", { class: "block" });
  const details = el("details", { class: "disclosure", open: true });
  details.appendChild(el("summary", { text: "LLM 生成敘述段落" }));
  const body = el("div", { class: "disclosure__body" });

  const secs = data.narrative_sections || data.risk_sections || {};
  const source = data.narrative_sections ? "（敘事）" : "（風險）";
  for (const name of SECTION_ORDER) {
    const num = SECTION_TO_NUM[name];
    const txt = (data.narrative_sections && data.narrative_sections[num])
             || (data.risk_sections && data.risk_sections[num]);
    if (!txt) continue;
    body.appendChild(el("div", { class: "narrative-sec" }, [
      el("h5", { text: `${num} ${name}` }),
      el("p", { text: txt }),
    ]));
  }
  if (!body.children.length) {
    // fall back to raw keys if section mapping missed
    for (const [k, v] of Object.entries(secs)) {
      body.appendChild(el("div", { class: "narrative-sec" }, [
        el("h5", { text: k + " " + source }), el("p", { text: String(v) }),
      ]));
    }
  }
  details.appendChild(body);
  block.appendChild(details);
  return block;
}

function renderPrompts(data) {
  const block = el("div", { class: "block" });
  const mk = (title, text) => {
    if (!text) return null;
    const details = el("details", { class: "disclosure" });
    details.appendChild(el("summary", { text: title }));
    const body = el("div", { class: "disclosure__body" });
    const copy = el("button", { class: "copy-btn", type: "button", text: "複製" });
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); copy.textContent = "已複製 ✓"; }
      catch { copy.textContent = "複製失敗"; }
      setTimeout(() => (copy.textContent = "複製"), 1500);
    });
    body.appendChild(copy);
    body.appendChild(el("pre", { class: "prompt-pre", text }));
    details.appendChild(body);
    return details;
  };
  const a = mk("敘事 Prompt（narrative_prompt）", data.narrative_prompt);
  const b = mk("風險 Prompt（risk_prompt）", data.risk_prompt);
  if (a) block.appendChild(a);
  if (b) block.appendChild(b);
  return block.children.length ? block : el("div");
}
