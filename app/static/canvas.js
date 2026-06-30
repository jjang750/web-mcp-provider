/* MCP Provider — 에디터 캔버스 (디자인팀 예제 기준 + 백엔드 연동)
   전역 함수(onclick): openRun, closeRun, runWorkflow, addTerminal, switchPal, switchRT, autoLayout, alignSel, distribute, pickAuth */
"use strict";

// [진단] 모든 JS 오류를 화면 상단 빨간 배너로 표시
window.addEventListener("error", function (ev) {
  var b = document.createElement("div");
  b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99999;background:#E5484D;color:#fff;font:600 12px/1.4 sans-serif;padding:8px 14px;text-align:center;white-space:pre-wrap";
  b.textContent = "JS 오류: " + (ev.message || "") + "  @ " + (ev.filename || "") + ":" + (ev.lineno || "");
  document.body.appendChild(b);
});


const APP = document.querySelector(".app") || document.querySelector(".editor") || document.body;
const WF_ID = parseInt((APP.getAttribute && APP.getAttribute("data-workflow-id")) || "0", 10);
const container = document.getElementById("drawflow");

let editor = null;
let opsById = {};
const edgeMap = {};
let dirty = false;
let runNo = 1;
let authType = "none";
let runMode = "form";
let addCount = 0;
let selectedIds = new Set();
let wfDescription = null;

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const mlow = (m) => String(m || "get").toLowerCase();

function fatalBanner(msg) {
  document.body.insertAdjacentHTML("afterbegin",
    '<div style="position:fixed;top:0;left:0;right:0;z-index:9999;background:#E5484D;color:#fff;font:600 13px/1.5 sans-serif;padding:10px 16px;text-align:center">' + esc(msg) + "</div>");
}

function toast(msg, kind) {
  const w = document.getElementById("toastWrap");
  if (!w) return;
  const t = document.createElement("div");
  t.className = "toast" + (kind === "fail" ? " fail" : "");
  t.innerHTML = '<span class="ticon">' + (kind === "fail" ? "!" : "✓") + "</span>" + esc(msg);
  w.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 2600);
}

function setDirty(d) {
  dirty = d;
  const chip = document.getElementById("saveChip");
  if (!chip) return;
  chip.innerHTML = '<span class="dot"></span>' + (d ? "저장 안 됨" : "저장됨");
  chip.style.opacity = d ? ".7" : "1";
}

function fallbackCopy(txt, okMsg) {
  try {
    const ta = document.createElement("textarea");
    ta.value = txt == null ? "" : txt;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:-9999px;left:-9999px;opacity:0;";
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    toast(ok ? (okMsg || "복사했습니다") : "복사 실패 — 텍스트를 직접 선택해 복사하세요", ok ? undefined : "fail");
  } catch (e) {
    toast("복사 실패: " + (e && e.message), "fail");
  }
}
function copyText(txt, okMsg) {
  txt = txt == null ? "" : txt;
  if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
    navigator.clipboard.writeText(txt).then(() => toast(okMsg || "복사했습니다")).catch(() => fallbackCopy(txt, okMsg));
  } else {
    fallbackCopy(txt, okMsg);  // http(IP) 등 비보안 컨텍스트 폴백
  }
}
function apiNodeHTML(op) {
  return '<div class="wf-node" data-status="">' +
    '<div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge ' + mlow(op.method) + '">' + esc((op.method || "GET").toUpperCase()) + "</span>" +
    '<span class="path">' + esc(op.path) + "</span></div>" +
    '<div class="title">' + esc(op.summary || op.path) + "</div></div></div>";
}
function terminalHTML(kind) {
  const ico = kind === "start"
    ? '<div style="width:0;height:0;border-top:5px solid transparent;border-bottom:5px solid transparent;border-left:8px solid #fff;margin-left:2px;"></div>'
    : '<div style="width:8px;height:8px;background:#fff;border-radius:2px;"></div>';
  return '<div class="wf-node terminal ' + kind + '"><span class="tico">' + ico + '</span><span class="tlabel">' + (kind === "start" ? "시작" : "종료") + "</span></div>";
}

function seedParams(op) {
  const p = { path: {}, query: {}, header: {}, body: null };
  (op.params_schema || []).forEach((s) => {
    if (["path", "query", "header"].includes(s.in)) {
      const sc = s.schema || {};
      let v = sc.default;
      if (v === undefined && Array.isArray(sc.examples) && sc.examples.length) v = sc.examples[0];
      p[s.in][s.name] = v !== undefined ? v : "";
    }
  });
  return p;
}

function slimOp(op) { return { id: op.id, method: op.method, path: op.path, summary: op.summary || op.path }; }
function addApiNode(op, x, y, params, baseUrl) {
  // Drawflow 가 data 객체의 키로 [df-...] 선택자를 만들므로, $ref 등 특수문자 포함 스키마는 절대 넣지 않는다(슬림 op).
  const data = { op: slimOp(op), params: params || seedParams(op), base_url: baseUrl || null };
  const id = editor.addNode("api", 1, 1, x, y, "api", data, apiNodeHTML(op));
  setDirty(true);
  return id;
}
function addTerminal(kind) {
  const y = 140 + Math.random() * 120, x = kind === "start" ? 60 : 760;
  const id = editor.addNode(kind, kind === "start" ? 0 : 1, kind === "start" ? 1 : 0, x, y, kind, {}, terminalHTML(kind));
  setDirty(true);
  toast((kind === "start" ? "시작" : "종료") + " 노드를 추가했습니다");
  return id;
}

function rtypeOptions(sel) {
  const T = [["auto", "자동"], ["string", "문자열"], ["number", "숫자"], ["boolean", "불리언(true/false)"], ["null", "null"]];
  return T.map((t) => '<option value="' + t[0] + '"' + ((sel || "auto") === t[0] ? " selected" : "") + '>' + t[1] + '</option>').join("");
}
function condSummary(cond) {
  if (!cond || !cond.left) return "조건 미설정";
  const op = cond.op || "truthy";
  if (op === "truthy" || op === "falsy" || op === "exists") return esc(cond.left) + " " + op;
  return esc(cond.left) + " " + esc(op) + " " + esc(cond.right);
}
function conditionHTML(cond) {
  return '<div class="wf-node cond" data-status="">' +
    '<div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge cond-badge">IF</span><span class="path">조건 분기</span></div>' +
    '<div class="title">' + condSummary(cond) + '</div>' +
    '</div></div>';
}
function addConditionNode(x, y, cond) {
  cond = cond || { left: "$.", op: "==", right: "" };
  const id = editor.addNode("condition", 1, 2, x == null ? 360 : x, y == null ? 160 : y, "condition", { params: { condition: cond } }, conditionHTML(cond));
  setDirty(true);
  return id;
}

function switchSummary(sw) {
  const c = (sw && sw.cases) || [];
  return esc((sw && sw.left) || "$.") + " → " + c.length + "개 + default";
}
function switchHTML(sw) {
  return '<div class="wf-node sw" data-status=""><div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge sw-badge">SW</span><span class="path">스위치</span></div>' +
    '<div class="title">' + switchSummary(sw) + '</div></div></div>';
}
function labelSwitchPorts(id, cases) {
  const el = document.getElementById("node-" + id); if (!el) return;
  el.querySelectorAll(".outputs .output").forEach((o, i) => {
    o.querySelectorAll(".port-label").forEach((x) => x.remove());
    const isDef = i >= cases.length;
    const sp = document.createElement("span");
    sp.className = "port-label" + (isDef ? " def" : "");
    sp.textContent = isDef ? "default" : cases[i];
    o.appendChild(sp);
  });
}
function syncSwitchPorts(id, cases) {
  const target = cases.length + 1;
  let cur = Object.keys(editor.drawflow.drawflow.Home.data[id].outputs).length;
  while (cur < target) { editor.addNodeOutput(id); cur++; }
  while (cur > target) { editor.removeNodeOutput(id, "output_" + cur); cur--; }
  labelSwitchPorts(id, cases);
}
function addSwitchNode(x, y, sw) {
  sw = sw || { left: "$.status", cases: ["case1", "case2"] };
  const outs = (sw.cases || []).length + 1;
  const id = editor.addNode("switch", 1, outs, x == null ? 360 : x, y == null ? 160 : y, "switch", { params: { switch: sw } }, switchHTML(sw));
  labelSwitchPorts(id, sw.cases || []);
  setDirty(true);
  return id;
}
function mergeHTML() {
  return '<div class="wf-node mg" data-status=""><div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge mg-badge">MG</span><span class="path">병합</span></div>' +
    '<div class="title">여러 흐름 합류</div></div></div>';
}
function addMergeNode(x, y) {
  const id = editor.addNode("merge", 1, 1, x == null ? 360 : x, y == null ? 160 : y, "merge", {}, mergeHTML());
  setDirty(true);
  return id;
}
function filterHTML(cond) {
  return '<div class="wf-node ft" data-status=""><div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge ft-badge">FT</span><span class="path">필터</span></div>' +
    '<div class="title">' + condSummary(cond) + '</div></div></div>';
}
function addFilterNode(x, y, cond) {
  cond = cond || { left: "$.", op: "truthy", right: "" };
  const id = editor.addNode("filter", 1, 1, x == null ? 360 : x, y == null ? 160 : y, "filter", { params: { condition: cond } }, filterHTML(cond));
  setDirty(true);
  return id;
}
function transformSummary(setmap) {
  const n = (setmap || []).length;
  return n ? n + "개 필드 추출" : "필드 미설정";
}
function transformHTML(setmap) {
  return '<div class="wf-node xf" data-status=""><div class="stripe"></div><div class="nbody">' +
    '<div class="nhead"><span class="badge xf-badge">SET</span><span class="path">변환</span></div>' +
    '<div class="title">' + transformSummary(setmap) + '</div></div></div>';
}
function addTransformNode(x, y, setmap) {
  const id = editor.addNode("transform", 1, 1, x == null ? 360 : x, y == null ? 160 : y, "transform", { params: { setmap: setmap || [] } }, transformHTML(setmap || []));
  setDirty(true);
  return id;
}
function addLogicNode(kind, x, y) {
  if (kind === "branch") { addConditionNode(x, y); toast("조건 분기 노드를 추가했습니다"); }
  else if (kind === "switch") { addSwitchNode(x, y); toast("스위치 노드를 추가했습니다 — 우측에서 케이스를 설정하세요"); }
  else if (kind === "merge") { addMergeNode(x, y); toast("병합 노드를 추가했습니다"); }
  else if (kind === "filter") { addFilterNode(x, y); toast("필터 노드를 추가했습니다 — 우측에서 조건을 설정하세요"); }
  else if (kind === "transform") { addTransformNode(x, y); toast("변환 노드를 추가했습니다 — 우측에서 출력 필드를 정의하세요"); }
}

async function loadOperations() {
  const ops = document.getElementById("paletteOps");
  if (!ops) return;
  try {
    const specs = await fetch("/api/specs").then((r) => r.json());
    if (!specs.length) { ops.innerHTML = '<div class="prop-empty">스펙을 먼저 등록하세요<br>(POST /api/specs/from-url)</div>'; return; }
    const list = await fetch("/api/specs/" + specs[0].id + "/operations").then((r) => r.json());
    opsById = {};
    ops.innerHTML = "";
    list.forEach((op) => {
      opsById[op.id] = op;
      const el = document.createElement("div");
      el.className = "op"; el.draggable = true;
      el.innerHTML = '<span class="grip">⠿</span><div class="meta"><div class="row1">' +
        '<span class="badge ' + mlow(op.method) + '">' + esc(op.method) + '</span>' +
        '<span class="path">' + esc(op.path) + '</span></div>' +
        '<div class="summary">' + esc(op.summary || "") + "</div></div>";
      el.addEventListener("dragstart", (e) => e.dataTransfer.setData("drag", JSON.stringify({ kind: "api", op: op, opId: op.id })));
      el.addEventListener("click", () => {
        addApiNode(op, 140 + (addCount % 6) * 36, 90 + (addCount % 6) * 36);
        addCount++;
        toast("노드를 추가했습니다 — 드래그로 위치를 옮기세요");
      });
      ops.appendChild(el);
    });
    toast("오퍼레이션 " + list.length + "개 로드됨 · Drawflow:" + (typeof Drawflow));
  } catch (e) { ops.innerHTML = '<div class="prop-empty">오퍼레이션 로드 실패: ' + (e && e.message) + '</div>'; }
}
function buildLogicPalette() {
  const lg = document.getElementById("paletteLogic");
  if (!lg) return;
  const LOGIC = [
    ["분기 (IF)", "branch", "조건 true/false 분기"],
    ["스위치 (Switch)", "switch", "값별 다중 분기 (최대 10)"],
    ["병합 (Merge)", "merge", "여러 흐름 합류"],
    ["필터 (Filter)", "filter", "조건 미충족 차단"],
    ["변환 (Set)", "transform", "응답에서 필드 추출/재구성"],
  ];
  const colors = { branch: "var(--logic-branch)", switch: "var(--logic-switch)", merge: "var(--logic-merge)", filter: "var(--logic-filter)", transform: "var(--logic-transform)" };
  lg.innerHTML = LOGIC.map(([name, g, sub]) =>
    '<div class="op" data-logic="' + g + '" draggable="true"><span class="logic-ico" style="background:' + colors[g] + '"></span>' +
    '<div class="logic-meta"><span class="logic-name">' + name + '</span><span class="logic-sub">' + sub + '</span></div></div>').join("");
  lg.querySelectorAll("[data-logic]").forEach((el) => {
    const kind = el.getAttribute("data-logic");
    el.addEventListener("click", () => { addLogicNode(kind, 140 + (addCount % 6) * 36, 90 + (addCount % 6) * 36); addCount++; });
    el.addEventListener("dragstart", (e) => e.dataTransfer.setData("drag", JSON.stringify({ kind: kind })));
  });
}
function switchPal(which) {
  document.querySelectorAll(".tab[data-pal]").forEach((t) => t.classList.toggle("active", t.dataset.pal === which));
  document.getElementById("paletteOps").style.display = which === "ops" ? "flex" : "none";
  document.getElementById("paletteLogic").style.display = which === "logic" ? "flex" : "none";
}

function wireDrop() {
  container.addEventListener("dragover", (e) => e.preventDefault());
  container.addEventListener("drop", (e) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("drag"); if (!raw) return;
    const d = JSON.parse(raw);
    const z = editor.zoom;
    const rect = container.getBoundingClientRect();
    const x = (e.clientX - rect.left - editor.canvas_x) / z;
    const y = (e.clientY - rect.top - editor.canvas_y) / z;
    if (["branch", "switch", "merge", "filter"].indexOf(d.kind) >= 0) { addLogicNode(d.kind, x, y); return; }
    if (d.kind === "condition") { addConditionNode(x, y); return; }
    const op = d.op || opsById[d.opId];
    if (d.kind === "api" && op) addApiNode(op, x, y);
  });
}

function exportGraph() {
  const data = editor.drawflow.drawflow.Home.data;
  const nodes = [], edges = [];
  Object.keys(data).forEach((id) => {
    const n = data[id], cls = n.class, dd = n.data || {};
    const TYPEMAP = { api: "api_call", start: "start", end: "end", condition: "condition", switch: "switch", merge: "merge", filter: "filter" };
    const type = TYPEMAP[cls] || "transform";
    const LOGICLABEL = { condition: "조건 분기", switch: "스위치", merge: "병합", filter: "필터", transform: "변환" };
    nodes.push({
      id: String(id), type: type,
      label: dd.op ? (dd.op.summary || dd.op.path) : (LOGICLABEL[cls] || null),
      operation_id: dd.op ? dd.op.id : null,
      base_url: dd.base_url || null,
      params: dd.params || {},
      position: { x: n.pos_x, y: n.pos_y },
    });
    Object.keys(n.outputs || {}).forEach((ok) => {
      (n.outputs[ok].connections || []).forEach((c) => {
        const src = String(id), tgt = String(c.node);
        let label = null;
        if (cls === "condition") label = ok === "output_2" ? "false" : "true";
        else if (cls === "switch") {
          const cs = (dd.params && dd.params.switch && dd.params.switch.cases) || [];
          const oi = parseInt(ok.replace("output_", ""), 10) - 1;
          label = oi < cs.length ? cs[oi] : "__default__";
        }
        edges.push({ id: src + "-" + tgt, source: src, target: tgt, data_mapping: edgeMap[src + "->" + tgt] || [], label: label });
      });
    });
  });
  return { nodes, edges };
}

async function saveGraph() {
  const g = exportGraph();
  const body = { nodes: g.nodes, edges: g.edges, name: document.getElementById("wfTitle").textContent.trim() || undefined, description: wfDescription };
  const r = await fetch("/api/workflows/" + WF_ID, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.ok) { setDirty(false); toast("워크플로우가 저장되었습니다"); }
  else toast("저장 실패 — " + r.status, "fail");
  return r.ok;
}

async function loadWorkflow() {
  const wf = await fetch("/api/workflows/" + WF_ID).then((r) => (r.ok ? r.json() : null));
  if (!wf) return;
  document.getElementById("wfTitle").textContent = wf.name || ("워크플로우 #" + WF_ID);
  wfDescription = wf.description || null;
  document.getElementById("wfTitle").title = wfDescription || "";
  document.getElementById("toolName").value = wf.mcp_tool_name || "";
  document.getElementById("mcpGroup").value = wf.mcp_group || "";
  if (wf.mcp_exposed) document.getElementById("mcpToggle").classList.add("on");

  const idMap = {};
  const nodeById = {};
  (wf.nodes || []).forEach((n) => { nodeById[n.id] = n; });
  (wf.nodes || []).forEach((n) => {
    const x = (n.position && n.position.x) || 60, y = (n.position && n.position.y) || 80;
    let live;
    if (n.type === "start" || n.type === "end") {
      live = editor.addNode(n.type, n.type === "start" ? 0 : 1, n.type === "start" ? 1 : 0, x, y, n.type, {}, terminalHTML(n.type));
    } else if (n.type === "api_call") {
      const op = opsById[n.operation_id] || { id: n.operation_id, method: "GET", path: n.label || "", summary: n.label };
      live = editor.addNode("api", 1, 1, x, y, "api", { op: slimOp(op), params: n.params || seedParams(op), base_url: n.base_url || null }, apiNodeHTML(op));
    } else if (n.type === "condition") {
      const cond = (n.params && n.params.condition) || { left: "$.", op: "==", right: "" };
      live = editor.addNode("condition", 1, 2, x, y, "condition", { params: { condition: cond } }, conditionHTML(cond));
    } else if (n.type === "switch") {
      const sw = (n.params && n.params.switch) || { left: "$.status", cases: ["case1", "case2"] };
      live = editor.addNode("switch", 1, (sw.cases || []).length + 1, x, y, "switch", { params: { switch: sw } }, switchHTML(sw));
      labelSwitchPorts(live, sw.cases || []);
    } else if (n.type === "merge") {
      live = editor.addNode("merge", 1, 1, x, y, "merge", {}, mergeHTML());
    } else if (n.type === "filter") {
      const cond = (n.params && n.params.condition) || { left: "$.", op: "truthy", right: "" };
      live = editor.addNode("filter", 1, 1, x, y, "filter", { params: { condition: cond } }, filterHTML(cond));
    } else if (n.type === "transform") {
      const sm = (n.params && n.params.setmap) || [];
      live = editor.addNode("transform", 1, 1, x, y, "transform", { params: { setmap: sm } }, transformHTML(sm));
    } else { return; }
    idMap[n.id] = live;
  });
  (wf.edges || []).forEach((e) => {
    const s = idMap[e.source], t = idMap[e.target];
    if (s == null || t == null) return;
    let outPort = "output_1";
    const sn = nodeById[e.source];
    if (sn && sn.type === "condition") outPort = e.label === "false" ? "output_2" : "output_1";
    else if (sn && sn.type === "switch") {
      const cs = (sn.params && sn.params.switch && sn.params.switch.cases) || [];
      if (e.label === "__default__") outPort = "output_" + (cs.length + 1);
      else { const oi = cs.indexOf(e.label); outPort = "output_" + (oi >= 0 ? oi + 1 : 1); }
    }
    try { editor.addConnection(s, t, outPort, "input_1"); } catch (_) {}
    if (e.data_mapping && e.data_mapping.length) edgeMap[s + "->" + t] = e.data_mapping;
  });
  refreshAlignState();
  setDirty(false);
}

async function loadReturnPreview(opId) {
  const box = document.getElementById("retBox");
  if (!box) return;
  try {
    const r = await fetch("/api/operations/" + opId + "/response-fields");
    if (!r.ok) { box.innerHTML = '<div class="prop-empty">미리보기를 불러오지 못했습니다</div>'; return; }
    const d = await r.json();
    let html = "";
    if (d.fields && d.fields.length) {
      html += '<p class="ret-hint">필드를 클릭하면 JSONPath가 복사됩니다 — 조건/매핑 좌변에 붙여넣어 사용하세요.</p>';
      html += '<div class="ret-fields">' + d.fields.map((f) =>
        '<div class="ret-row" data-path="' + esc(f.path) + '" title="클릭하여 복사"><span class="ret-path">' + esc(f.path) + '</span><span class="ret-type">' + esc(f.type) + (f.required ? " · 필수" : "") + '</span></div>').join("") + '</div>';
    } else if (d.note) {
      html += '<p class="ret-hint">' + esc(d.note) + '</p>';
    }
    if (d.example != null) html += '<div class="sec-label" style="margin-top:12px;">예시 응답</div>' + jsonBlock(d.example);
    box.innerHTML = html || '<div class="prop-empty">표시할 리턴 정보가 없습니다</div>';
    box.querySelectorAll(".ret-row").forEach((row) => row.addEventListener("click", () => {
      const p = row.getAttribute("data-path");
      copyText(p, "복사됨: " + p);
    }));
  } catch (e) { box.innerHTML = '<div class="prop-empty">미리보기 오류: ' + (e && e.message) + '</div>'; }
}
function showProps(id) {
  const node = editor.getNodeFromId(id);
  const empty = document.getElementById("propEmpty"), body = document.getElementById("propBody");
  switchRT("prop");
  if (node.class === "api") {
    const op = node.data.op;
    body.innerHTML =
      '<div class="nhead" style="margin-bottom:14px;"><span class="badge ' + mlow(op.method) + '">' + esc((op.method || "GET").toUpperCase()) + '</span><span style="font-family:var(--font-mono);font-size:11px;color:var(--text-2);">' + esc(op.path) + '</span></div>' +
      '<div class="field"><label>Base URL</label><input id="pBase" value="' + esc(node.data.base_url || "") + '" placeholder="비우면 자동(오퍼레이션→기본값)"></div>' +
      '<div class="field"><label>파라미터 (params JSON)</label><textarea id="pParams" rows="9">' + esc(JSON.stringify(node.data.params || {}, null, 2)) + "</textarea></div>" +
      '<button class="btn btn-secondary" id="pApply">적용</button>' +
      '<div class="sec-label" style="margin-top:16px;">리턴값 미리보기</div><div id="retBox"><div class="prop-empty">불러오는 중…</div></div>';
    empty.style.display = "none"; body.style.display = "block";
    if (op && op.id != null) loadReturnPreview(op.id);
    document.getElementById("pApply").addEventListener("click", () => {
      const nd = editor.drawflow.drawflow.Home.data[id];
      nd.data.base_url = document.getElementById("pBase").value.trim() || null;
      try { nd.data.params = JSON.parse(document.getElementById("pParams").value || "{}"); }
      catch (e) { toast("params JSON 오류: " + e.message, "fail"); return; }
      setDirty(true); toast("적용했습니다");
    });
  } else if (node.class === "condition") {
    const cond = (node.data.params && node.data.params.condition) || { left: "$.", op: "==", right: "" };
    const ops = ["==", "!=", ">", "<", ">=", "<=", "contains", "exists", "truthy", "falsy"];
    body.innerHTML =
      '<div class="sec-label">조건 분기 (IF)</div>' +
      '<p style="font-size:11.5px;color:var(--text-3);margin:0 0 10px;line-height:1.5;">상류 노드 출력 기준 JSONPath로 평가합니다. 참이면 <b>true</b> 포트, 거짓이면 <b>false</b> 포트로 진행합니다.</p>' +
      '<div class="field"><label>좌변 (JSONPath)</label><input id="cLeft" value="' + esc(cond.left || "") + '" placeholder="$.status"></div>' +
      '<div class="field"><label>연산자</label><select id="cOp">' + ops.map((o) => '<option value="' + o + '"' + (o === (cond.op || "==") ? " selected" : "") + '>' + o + '</option>').join("") + '</select></div>' +
      '<div class="field"><label>우변 (리터럴)</label><input id="cRight" value="' + esc(cond.right == null ? "" : cond.right) + '" placeholder="active (exists/truthy/falsy는 불필요)"></div>' +
      '<div class="field"><label>우변 타입</label><select id="cType">' + rtypeOptions(cond.rtype) + '</select></div>' +
      '<button class="btn btn-secondary" id="cApply">적용</button>';
    empty.style.display = "none"; body.style.display = "block";
    document.getElementById("cApply").addEventListener("click", () => {
      const nd = editor.drawflow.drawflow.Home.data[id];
      const c = { left: document.getElementById("cLeft").value.trim(), op: document.getElementById("cOp").value, right: document.getElementById("cRight").value, rtype: document.getElementById("cType").value };
      nd.data.params = nd.data.params || {}; nd.data.params.condition = c;
      const titleEl = document.querySelector("#node-" + id + " .wf-node .title"); if (titleEl) titleEl.textContent = condSummary(c);
      setDirty(true); toast("조건을 적용했습니다");
    });
  } else if (node.class === "switch") {
    const sw = (node.data.params && node.data.params.switch) || { left: "$.status", cases: ["case1", "case2"] };
    const rowsHtml = (sw.cases || []).map((c) => '<div class="case-row"><input class="caseVal" value="' + esc(c) + '"><button class="iconbtn case-del" type="button">✕</button></div>').join("");
    body.innerHTML =
      '<div class="sec-label">스위치 (Switch)</div>' +
      '<p style="font-size:11.5px;color:var(--text-3);margin:0 0 10px;line-height:1.5;">좌변 값(JSONPath)을 케이스와 비교해 일치하는 출력 포트로 분기합니다. 일치 없으면 default 포트. 케이스 최대 10개(포트 순서=목록 순서).</p>' +
      '<div class="field"><label>좌변 (JSONPath)</label><input id="swLeft" value="' + esc(sw.left || "$.") + '" placeholder="$.status"></div>' +
      '<div class="field"><label>케이스</label><div id="caseList">' + rowsHtml + '</div><button class="btn btn-ghost" id="caseAdd" type="button" style="margin-top:6px;">+ 케이스 추가</button></div>' +
      '<button class="btn btn-secondary" id="swApply" type="button">적용</button>';
    empty.style.display = "none"; body.style.display = "block";
    const bindDel = () => body.querySelectorAll(".case-del").forEach((b) => { b.onclick = () => b.parentElement.remove(); });
    bindDel();
    document.getElementById("caseAdd").addEventListener("click", () => {
      const list = document.getElementById("caseList");
      if (list.querySelectorAll(".case-row").length >= 10) { toast("케이스는 최대 10개입니다", "fail"); return; }
      const div = document.createElement("div"); div.className = "case-row";
      div.innerHTML = '<input class="caseVal" value=""><button class="iconbtn case-del" type="button">✕</button>';
      list.appendChild(div); div.querySelector(".case-del").onclick = () => div.remove();
    });
    document.getElementById("swApply").addEventListener("click", () => {
      const left = document.getElementById("swLeft").value.trim() || "$.";
      let cases = [...body.querySelectorAll(".caseVal")].map((i) => i.value.trim()).filter((v) => v !== "");
      if (cases.length > 10) cases = cases.slice(0, 10);
      const nd = editor.drawflow.drawflow.Home.data[id];
      nd.data.params = nd.data.params || {}; nd.data.params.switch = { left: left, cases: cases };
      syncSwitchPorts(id, cases);
      const titleEl = document.querySelector("#node-" + id + " .wf-node .title"); if (titleEl) titleEl.textContent = switchSummary({ left: left, cases: cases });
      setDirty(true); toast("스위치를 적용했습니다");
    });
  } else if (node.class === "filter") {
    const cond = (node.data.params && node.data.params.condition) || { left: "$.", op: "truthy", right: "" };
    const ops = ["==", "!=", ">", "<", ">=", "<=", "contains", "exists", "truthy", "falsy"];
    body.innerHTML =
      '<div class="sec-label">필터 (Filter)</div>' +
      '<p style="font-size:11.5px;color:var(--text-3);margin:0 0 10px;line-height:1.5;">조건이 참이면 통과, 거짓이면 이후 노드를 실행하지 않습니다(걸러짐).</p>' +
      '<div class="field"><label>좌변 (JSONPath)</label><input id="fLeft" value="' + esc(cond.left || "") + '" placeholder="$.status"></div>' +
      '<div class="field"><label>연산자</label><select id="fOp">' + ops.map((o) => '<option value="' + o + '"' + (o === (cond.op || "truthy") ? " selected" : "") + '>' + o + '</option>').join("") + '</select></div>' +
      '<div class="field"><label>우변 (리터럴)</label><input id="fRight" value="' + esc(cond.right == null ? "" : cond.right) + '" placeholder="active"></div>' +
      '<div class="field"><label>우변 타입</label><select id="fType">' + rtypeOptions(cond.rtype) + '</select></div>' +
      '<button class="btn btn-secondary" id="fApply" type="button">적용</button>';
    empty.style.display = "none"; body.style.display = "block";
    document.getElementById("fApply").addEventListener("click", () => {
      const nd = editor.drawflow.drawflow.Home.data[id];
      const c = { left: document.getElementById("fLeft").value.trim(), op: document.getElementById("fOp").value, right: document.getElementById("fRight").value, rtype: document.getElementById("fType").value };
      nd.data.params = nd.data.params || {}; nd.data.params.condition = c;
      const titleEl = document.querySelector("#node-" + id + " .wf-node .title"); if (titleEl) titleEl.textContent = condSummary(c);
      setDirty(true); toast("필터 조건을 적용했습니다");
    });
  } else if (node.class === "transform") {
    const setmap = (node.data.params && node.data.params.setmap) || [];
    const rowH = (f) => '<div class="set-row"><input class="setKey" placeholder="출력 키" value="' + esc(f.key || "") + '"><select class="setMode"><option value="path"' + ((f.mode || "path") === "path" ? " selected" : "") + '>경로</option><option value="literal"' + (f.mode === "literal" ? " selected" : "") + '>고정값</option></select><input class="setVal" placeholder="$.data.x 또는 값" value="' + esc(f.mode === "literal" ? (f.value == null ? "" : f.value) : (f.src || "")) + '"><button class="iconbtn set-del" type="button">✕</button></div>';
    body.innerHTML =
      '<div class="sec-label">변환 (Set)</div>' +
      '<p style="font-size:11.5px;color:var(--text-3);margin:0 0 10px;line-height:1.5;">상류 응답에서 필드를 골라 출력 객체를 만듭니다. <b>경로</b>=JSONPath로 값 복사, <b>고정값</b>=직접 입력. 리턴값 미리보기에서 경로를 복사해 붙여넣으세요.</p>' +
      '<div id="setList">' + setmap.map(rowH).join("") + '</div>' +
      '<button class="btn btn-ghost" id="setAdd" type="button" style="margin-top:6px;">+ 필드 추가</button>' +
      '<button class="btn btn-secondary" id="setApply" type="button" style="margin-left:6px;">적용</button>';
    empty.style.display = "none"; body.style.display = "block";
    body.querySelectorAll(".set-del").forEach((b) => { b.onclick = () => b.parentElement.remove(); });
    document.getElementById("setAdd").addEventListener("click", () => {
      const d = document.createElement("div"); d.className = "set-row";
      d.innerHTML = '<input class="setKey" placeholder="출력 키"><select class="setMode"><option value="path">경로</option><option value="literal">고정값</option></select><input class="setVal" placeholder="$.data.x 또는 값"><button class="iconbtn set-del" type="button">✕</button>';
      document.getElementById("setList").appendChild(d); d.querySelector(".set-del").onclick = () => d.remove();
    });
    document.getElementById("setApply").addEventListener("click", () => {
      const rows = [...body.querySelectorAll(".set-row")].map((r) => {
        const key = r.querySelector(".setKey").value.trim();
        const mode = r.querySelector(".setMode").value;
        const v = r.querySelector(".setVal").value;
        return mode === "literal" ? { key: key, mode: "literal", value: v } : { key: key, mode: "path", src: v.trim() };
      }).filter((f) => f.key);
      const nd = editor.drawflow.drawflow.Home.data[id];
      nd.data.params = nd.data.params || {}; nd.data.params.setmap = rows;
      const titleEl = document.querySelector("#node-" + id + " .wf-node .title"); if (titleEl) titleEl.textContent = transformSummary(rows);
      setDirty(true); toast("변환을 적용했습니다");
    });
  } else if (node.class === "merge") {
    body.innerHTML =
      '<div class="sec-label">병합 (Merge)</div>' +
      '<p style="font-size:12px;color:var(--text-2);line-height:1.5;">여러 상류 노드의 출력을 {노드ID: 출력} 형태로 합쳐 다음 노드로 전달합니다. 입력 포트에 여러 연결을 이어주세요. 스킵된 분기는 제외됩니다.</p>';
    empty.style.display = "none"; body.style.display = "block";
  } else {
    const lbl = node.class === "start" ? "시작" : node.class === "end" ? "종료" : "노드";
    body.innerHTML = '<div class="sec-label">' + lbl + ' 노드</div><p style="font-size:12px;color:var(--text-2);line-height:1.5;">' +
      (node.class === "start" ? "워크플로우의 진입점입니다." : node.class === "end" ? "워크플로우의 종료점입니다." : "설정이 없습니다.") + "</p>";
    empty.style.display = "none"; body.style.display = "block";
  }
}
function hideProps() { document.getElementById("propEmpty").style.display = "block"; document.getElementById("propBody").style.display = "none"; }

function showEdgeProps(srcId, tgtId) {
  const key = srcId + "->" + tgtId;
  const empty = document.getElementById("propEmpty"), body = document.getElementById("propBody");
  switchRT("prop");
  body.innerHTML =
    '<div class="sec-label">엣지 데이터 매핑</div>' +
    '<p style="font-size:11.5px;color:var(--text-3);margin:0 0 10px;line-height:1.5;">노드 ' + esc(srcId) + " → " + esc(tgtId) + '. 응답값(JSONPath)을 다음 노드 입력으로 주입합니다. 예: <span class="mono">$.data.dong → query.dong</span></p>' +
    '<div class="field"><label>매핑 (JSON 배열)</label><textarea id="eMaps" rows="6">' + esc(JSON.stringify(edgeMap[key] || [], null, 2)) + "</textarea></div>" +
    '<button class="btn btn-secondary" id="eApply">적용</button>';
  empty.style.display = "none"; body.style.display = "block";
  document.getElementById("eApply").addEventListener("click", () => {
    try { edgeMap[key] = JSON.parse(document.getElementById("eMaps").value || "[]"); }
    catch (e) { toast("매핑 JSON 오류: " + e.message, "fail"); return; }
    setDirty(true); toast("매핑을 적용했습니다");
  });
}

function switchRT(which) {
  document.querySelectorAll(".tab[data-rt]").forEach((t) => t.classList.toggle("active", t.dataset.rt === which));
  // block: 카드가 세로로 정상 스택되도록(flex=가로 배치라 로그가 세로 줄무늬로 깨졌었음)
  document.getElementById("rtProp").style.display = which === "prop" ? "block" : "none";
  document.getElementById("rtLog").style.display = which === "log" ? "block" : "none";
}

function mappedTargets(nodeId) {
  // 이 노드로 들어오는 엣지의 data_mapping 이 채우는 파라미터(sec.key) 집합
  const set = new Set();
  Object.keys(edgeMap).forEach((k) => {
    if (k.endsWith("->" + nodeId)) {
      (edgeMap[k] || []).forEach((m) => {
        let to = (m.to || "").trim().replace(/^\$\./, "").replace(/^params\./, "");
        if (to) set.add(to);
      });
    }
  });
  return set;
}
function hasUpstreamProducer(startId) {
  // 상류(입력 방향)에 데이터 생성 노드(api/transform)가 있으면 true → 그 노드는 직접 입력 불필요
  const data = editor.drawflow.drawflow.Home.data;
  const seen = new Set();
  const stack = [];
  const pushInputs = (nid) => {
    const n = data[nid]; if (!n) return;
    Object.keys(n.inputs || {}).forEach((ik) => {
      (n.inputs[ik].connections || []).forEach((c) => stack.push(String(c.node)));
    });
  };
  pushInputs(startId);
  while (stack.length) {
    const cur = stack.pop();
    if (seen.has(cur)) continue;
    seen.add(cur);
    const n = data[cur];
    if (!n) continue;
    if (n.class === "api" || n.class === "transform") return true;
    pushInputs(cur);
  }
  return false;
}
function openRun() {
  const data = editor.drawflow.drawflow.Home.data;
  const apiIds = Object.keys(data).filter((id) => data[id].class === "api");
  const entryIds = apiIds.filter((id) => !hasUpstreamProducer(id));
  const downstreamCount = apiIds.length - entryIds.length;
  document.getElementById("apiCount").textContent = apiIds.length;
  const form = document.getElementById("runParams");
  if (!apiIds.length) { form.innerHTML = '<p style="font-size:12px;color:var(--text-3);">API 노드가 없습니다.</p>'; }
  else {
  const _note = downstreamCount > 0 ? '<p class="run-note">하류 API ' + downstreamCount + '개는 이전 노드 OUTPUT에서 같은 이름 값을 자동으로 가져옵니다(입력 불필요).</p>' : "";
  const _groups = entryIds.map((id) => {
    const op = data[id].data.op, params = data[id].data.params || {};
    let rows = "";
    const mapped = mappedTargets(id);
    ["path", "query", "header"].forEach((sec) => {
      Object.keys(params[sec] || {}).forEach((k) => {
        if (mapped.has(sec + "." + k)) {
          rows += '<div class="prow"><label>' + esc(k) + '</label><span class="prow-auto">\u2190 이전 노드 데이터로 자동 주입</span></div>';
        } else {
          rows += '<div class="prow"><label>' + esc(k) + '</label><input data-node="' + id + '" data-sec="' + sec + '" data-key="' + esc(k) + '" value="' + esc(params[sec][k]) + '"></div>';
        }
      });
    });
    if (params.body != null) rows += '<div class="prow"><label>body</label><input data-node="' + id + '" data-sec="body" value="' + esc(typeof params.body === "string" ? params.body : JSON.stringify(params.body)) + '"></div>';
    if (!rows) rows = '<p style="font-size:11px;color:var(--text-3);">파라미터 없음</p>';
    return '<div class="pgroup"><div class="pg-head"><span class="badge ' + mlow(op.method) + '">' + esc((op.method || "GET").toUpperCase()) + '</span><span class="pg-name">' + esc(op.summary || op.path) + "</span></div>" + rows + "</div>";
  }).join("");
  form.innerHTML = _note + (_groups || '<p style="font-size:12px;color:var(--text-3);">입력이 필요한 노드가 없습니다 — 바로 실행하세요.</p>');
  }
  document.getElementById("runOverlay").classList.add("show");
}
function closeRun() { document.getElementById("runOverlay").classList.remove("show"); }
function openMeta() {
  const o = document.getElementById("metaOverlay"); if (!o) return;
  document.getElementById("metaName").value = document.getElementById("wfTitle").textContent.trim();
  document.getElementById("metaDesc").value = wfDescription || "";
  o.classList.add("show");
  setTimeout(() => document.getElementById("metaName").focus(), 50);
}
function closeMeta() { const o = document.getElementById("metaOverlay"); if (o) o.classList.remove("show"); }
function saveMeta() {
  const nm = document.getElementById("metaName").value.trim();
  if (nm) document.getElementById("wfTitle").textContent = nm;
  wfDescription = document.getElementById("metaDesc").value.trim();
  document.getElementById("wfTitle").title = wfDescription;
  closeMeta(); setDirty(true);
  toast("정보를 수정했습니다 — 저장하면 반영됩니다");
}
function pickAuth(el) {
  el.parentElement.querySelectorAll(".radio").forEach((r) => r.classList.remove("on"));
  el.classList.add("on");
  authType = el.dataset.auth;
  const w = document.getElementById("authFields");
  if (authType === "bearer") w.innerHTML = '<input id="authToken" type="password" placeholder="Bearer 토큰">';
  else if (authType === "apikey") w.innerHTML = '<div style="display:flex;gap:8px;"><input id="authName" placeholder="헤더명 (X-API-Key)"><input id="authVal" type="password" placeholder="키 값"></div>';
  else w.innerHTML = "";
}

async function runWorkflow() {
  const data = editor.drawflow.drawflow.Home.data;
  const apiIds = Object.keys(data).filter((id) => data[id].class === "api");
  if (runMode === "form") {
    document.querySelectorAll("#runParams input[data-node]").forEach((inp) => {
      const nd = data[inp.dataset.node]; if (!nd) return;
      nd.data.params = nd.data.params || { path: {}, query: {}, header: {}, body: null };
      if (inp.dataset.sec === "body") nd.data.params.body = inp.value;
      else { nd.data.params[inp.dataset.sec] = nd.data.params[inp.dataset.sec] || {}; nd.data.params[inp.dataset.sec][inp.dataset.key] = inp.value; }
    });
  }
  let initial = {};
  if (runMode === "json") { try { initial = JSON.parse(document.getElementById("runJson").value || "{}"); } catch (e) { toast("initial_input JSON 오류", "fail"); return; } }
  let auth = null;
  if (authType === "bearer") auth = { type: "bearer", token: (document.getElementById("authToken") || {}).value };
  else if (authType === "apikey") auth = { type: "apikey", name: (document.getElementById("authName") || {}).value, value: (document.getElementById("authVal") || {}).value, location: "header" };

  closeRun();
  if (!apiIds.length) { toast("실행할 API 노드가 없습니다", "fail"); return; }
  if (!(await saveGraph())) return;
  apiIds.forEach((id) => setStatus(id, "running"));

  let res;
  try {
    res = await fetch("/api/workflows/" + WF_ID + "/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ initial_input: initial, auth }) }).then((r) => r.json());
  } catch (e) { toast("실행 요청 실패", "fail"); apiIds.forEach((id) => setStatus(id, "")); return; }

  const statusByNode = {};
  (res.logs || []).forEach((l) => {
    statusByNode[l.node_key] = l.status;
    let code = l.status_code; if (!code && l.error) { const m = String(l.error).match(/\d{3}/); if (m) code = m[0]; }
    const map = { success: "success", failed: "error", skipped: "skipped" };
    const badge = l.status === "success" ? "✓ " + (code || "200") : l.status === "failed" ? "! " + (code || "ERR") : "스킵";
    setStatus(l.node_key, map[l.status] || "", badge);
  });
  colorEdges(statusByNode);
  buildLog(res);
  switchRT("log");
  if (res.status === "success") toast("워크플로우 실행 완료");
  else { const f = (res.logs || []).find((l) => l.status === "failed"); toast("실행 실패 — " + (f ? (f.node_key + " · " + (f.error || "")) : res.status), "fail"); }
}

function setStatus(id, status, badge) {
  const el = document.querySelector("#node-" + id + " .wf-node"); if (!el) return;
  el.setAttribute("data-status", status);
  const head = el.querySelector(".nhead"); if (!head) return;
  const oldS = head.querySelector(".nstatus"), oldSp = head.querySelector(".spinner");
  if (oldS) oldS.remove(); if (oldSp) oldSp.remove();
  if (status === "running") { head.insertAdjacentHTML("beforeend", '<span class="spinner"></span>'); return; }
  if (badge && (status === "success" || status === "error")) {
    const icon = status === "success" ? "✓" : "!";
    const text = badge.replace(/^[✓!]\s*/, "");
    head.insertAdjacentHTML("beforeend", '<span class="nstatus"><span class="scircle">' + icon + "</span>" + esc(text) + "</span>");
  }
}

function colorEdges(statusByNode) {
  const data = editor.drawflow.drawflow.Home.data;
  Object.keys(data).forEach((src) => {
    Object.keys(data[src].outputs || {}).forEach((ok) => {
      (data[src].outputs[ok].connections || []).forEach((c) => {
        const tgt = String(c.node);
        const conn = container.querySelector(".connection.node_out_node-" + src + ".node_in_node-" + tgt);
        if (!conn) return;
        conn.classList.remove("is-success", "is-skip");
        if (statusByNode[tgt] === "skipped") conn.classList.add("is-skip");
        else if (statusByNode[src] === "success") conn.classList.add("is-success");
      });
    });
  });
}

function jsonBlock(v) {
  if (v === undefined || v === null || v === "") return '<div class="code">—</div>';
  const txt = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  return '<div class="codewrap"><button class="codecopy" type="button" title="복사">⧉</button><div class="code">' + esc(txt) + "</div></div>";
}
function buildLog(res) {
  const data = editor.drawflow.drawflow.Home.data;
  const log = document.getElementById("rtLog");
  const failed = res.status !== "success";
  const rows = (res.logs || []).map((l) => {
    const nd = data[l.node_key];
    const NODE_NM = { condition: "조건 분기 (IF)", switch: "스위치 (Switch)", merge: "병합 (Merge)", filter: "필터 (Filter)", start: "시작", end: "종료", transform: "변환" };
    const NODE_TAG = { condition: ["IF", "cond-badge"], switch: ["SW", "sw-badge"], merge: ["MG", "mg-badge"], filter: ["FT", "ft-badge"] };
    let name, badgeHtml;
    if (nd && nd.data && nd.data.op) {
      name = nd.data.op.summary || nd.data.op.path;
      badgeHtml = '<span class="badge ' + mlow(nd.data.op.method) + '">' + esc(nd.data.op.method) + '</span>';
    } else {
      const ncls = nd ? nd.class : "";
      name = NODE_NM[ncls] || l.node_key;
      const tg = NODE_TAG[ncls];
      badgeHtml = tg ? '<span class="badge ' + tg[1] + '">' + tg[0] + '</span>' : '';
    }
    let cls = "ok", circle = "var(--success)", icon = "\u2713", code = l.status_code || "200", cc = "var(--success)";
    if (l.status === "failed") { cls = "fail"; circle = "var(--danger)"; icon = "!"; code = (l.error && (String(l.error).match(/\d{3}/) || [])[0]) || "ERR"; cc = "var(--danger)"; }
    else if (l.status === "skipped") { cls = "skip"; circle = "var(--border-strong)"; icon = "\u2013"; code = "\u2014"; cc = "var(--text-3)"; }
    let logicLine = "";
    const lo = l.output;
    if (lo && typeof lo === "object" && !Array.isArray(lo)) {
      if (lo.branch !== undefined) {
        const ok = lo.branch === "true";
        logicLine = '<div class="lc-label">결과</div><div class="lc-result"><span class="lr-expr">' + esc(lo.expr || "조건") + '</span><span class="lr-arrow">\u2192</span><span class="lr-val ' + (ok ? "t" : "f") + '">' + esc(lo.branch) + '</span></div>';
      } else if (lo.switch !== undefined) {
        logicLine = '<div class="lc-label">결과</div><div class="lc-result"><span class="lr-expr">' + esc((lo.expr || "") + " = " + JSON.stringify(lo.switch)) + '</span><span class="lr-arrow">\u2192</span><span class="lr-val sw">' + esc(lo.matched) + '</span></div>';
      } else if (lo.passed !== undefined) {
        logicLine = '<div class="lc-label">결과</div><div class="lc-result"><span class="lr-expr">' + esc(lo.expr || "필터") + '</span><span class="lr-arrow">\u2192</span><span class="lr-val ' + (lo.passed ? "t" : "f") + '">' + (lo.passed ? "통과" : "차단") + '</span></div>';
      }
    }
    const detail = '<div class="lc-detail">' + logicLine +
      '<div class="lc-label">INPUT</div>' + jsonBlock(l.input) +
      '<div class="lc-label">OUTPUT</div>' + jsonBlock(l.output) +
      (l.error ? '<div class="lc-label">ERROR</div><div class="err">' + esc(l.error) + "</div>" : "") +
      (l.timestamp ? '<div class="lc-label">TIME</div><div class="code">' + esc(l.timestamp) + "</div>" : "") +
      "</div>";
    return '<div class="logcard ' + cls + '"><div class="lc-head">' +
      '<span class="lc-circle" style="background:' + circle + '">' + icon + "</span>" +
      badgeHtml +
      '<span class="lc-name">' + esc(name) + "</span>" +
      '<span class="lc-code" style="color:' + cc + ';margin-left:auto;">' + esc(code) + "</span>" +
      '<span class="lc-toggle">\u25be</span></div>' + detail + "</div>";
  }).join("");
  log.innerHTML = '<div class="log-run" style="margin:-14px -14px 12px;"><div class="run-pill">\uc2e4\ud589 #' + (res.execution_id || runNo++) + '</div><span class="run-time">\ubc29\uae08 \uc804</span>' +
    '<span class="run-status ' + (failed ? "fail" : "ok") + '"><span class="lc-circle" style="background:' + (failed ? "var(--danger)" : "var(--success)") + ';">' + (failed ? "!" : "\u2713") + "</span>" + (failed ? "\uc2e4\ud328" : "\uc131\uacf5") + "</span></div>" +
    (rows || '<div class="prop-empty">\ub85c\uadf8 \uc5c6\uc74c</div>');
  // 카드 펼치기 토글
  log.querySelectorAll(".lc-head").forEach((h) => h.addEventListener("click", () => {
    const d = h.nextElementSibling; if (!d) return;
    d.classList.toggle("open");
    const t = h.querySelector(".lc-toggle"); if (t) t.textContent = d.classList.contains("open") ? "\u25b4" : "\u25be";
  }));

}
function allNodes() { return editor.drawflow.drawflow.Home.data; }
// 선택 노드가 2개 이상이면 그 노드들만, 아니면 전체 노드 대상
function targets() { return selectedIds.size >= 2 ? [...selectedIds].filter((id) => allNodes()[id]) : Object.keys(allNodes()); }
function markSel() {
  document.querySelectorAll("#drawflow .drawflow-node").forEach((el) => el.classList.toggle("multi-sel", selectedIds.has(el.id.replace("node-", ""))));
  const bar = document.getElementById("selBar");
  if (bar) {
    if (selectedIds.size >= 2) { bar.style.display = "flex"; const n = bar.querySelector(".n"); if (n) n.textContent = selectedIds.size; }
    else bar.style.display = "none";
  }
  refreshAlignState();
}
function clearSel() { selectedIds.clear(); markSel(); }
function refreshAlignState() {
  const n = targets().length;
  ["alTop", "alBot", "alLeft", "alRight", "alDistH"].forEach((id) => { const b = document.getElementById(id); if (b) b.disabled = n < 2; });
}
function moveNode(id, x, y) {
  // [GOTCHA #3] CSS 트랜지션 금지 — rAF 로 pos_x/pos_y 직접 트윈하며 매 프레임 updateConnectionNodes
  const nd = allNodes()[id]; if (!nd) return;
  const el = document.getElementById("node-" + id); if (!el) return;
  const sx = nd.pos_x, sy = nd.pos_y, dur = 200, t0 = performance.now();
  const ease = (q) => 1 - Math.pow(1 - q, 3);
  (function step(now) {
    const q = Math.min(1, (now - t0) / dur), k = ease(q);
    nd.pos_x = sx + (x - sx) * k; nd.pos_y = sy + (y - sy) * k;
    el.style.left = nd.pos_x + "px"; el.style.top = nd.pos_y + "px";
    editor.updateConnectionNodes("node-" + id);
    if (q < 1) requestAnimationFrame(step);
    else { nd.pos_x = x; nd.pos_y = y; el.style.left = x + "px"; el.style.top = y + "px"; editor.updateConnectionNodes("node-" + id); }
  })(performance.now());
  setDirty(true);
}
function alignSel(dir) {
  const nodes = allNodes(), ids = targets();
  if (ids.length < 2) { toast("정렬하려면 노드를 2개 이상 선택(Shift+클릭)하세요", "fail"); return; }
  const xs = ids.map((i) => nodes[i].pos_x), ys = ids.map((i) => nodes[i].pos_y);
  if (dir === "top") { const m = Math.min.apply(null, ys); ids.forEach((i) => moveNode(i, nodes[i].pos_x, m)); }
  if (dir === "bottom") { const m = Math.max.apply(null, ys); ids.forEach((i) => moveNode(i, nodes[i].pos_x, m)); }
  if (dir === "left") { const m = Math.min.apply(null, xs); ids.forEach((i) => moveNode(i, m, nodes[i].pos_y)); }
  if (dir === "right") { const m = Math.max.apply(null, xs); ids.forEach((i) => moveNode(i, m, nodes[i].pos_y)); }
  toast((selectedIds.size >= 2 ? "선택한 " + ids.length + "개" : "전체") + " 노드를 정렬했습니다");
}
function distribute(axis) {
  const nodes = allNodes(), ids = targets().sort((a, b) => nodes[a].pos_x - nodes[b].pos_x);
  if (ids.length < 3) { toast("균등 분배는 노드 3개 이상 선택해야 합니다", "fail"); return; }
  const first = nodes[ids[0]].pos_x, last = nodes[ids[ids.length - 1]].pos_x, step = (last - first) / (ids.length - 1);
  ids.forEach((i, k) => moveNode(i, first + step * k, nodes[i].pos_y));
  toast("균등 분배했습니다");
}
function autoLayout() {
  const nodes = allNodes(), ids = Object.keys(nodes);
  if (!ids.length) { toast("정렬할 노드가 없습니다", "fail"); return; }
  const order = ids.sort((a, b) => { const rank = (c) => (c === "start" ? 0 : c === "end" ? 2 : 1); return rank(nodes[a].class) - rank(nodes[b].class) || (+a) - (+b); });
  order.forEach((id, k) => moveNode(id, 80 + k * 240, 200));
  toast("자동 정렬 완료");
}

async function pushExpose() {
  const exposed = document.getElementById("mcpToggle").classList.contains("on");
  const group = document.getElementById("mcpGroup").value.trim() || null;
  const tool_name = document.getElementById("toolName").value.trim() || null;
  await fetch("/api/workflows/" + WF_ID + "/expose", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ exposed, group, tool_name }) });
}

function ensureMarkers() {
  if (document.getElementById("wf-markers")) return;
  // [GOTCHA #2] 단일 마커 + fill:context-stroke → 화살표 색이 선 색(기본 회색/hover 초록/성공 초록)을 자동 추종
  document.body.insertAdjacentHTML("beforeend",
    '<svg id="wf-markers" width="0" height="0" style="position:absolute" xmlns="http://www.w3.org/2000/svg"><defs>' +
    '<marker id="df-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">' +
    '<path d="M0,0 L8,4.5 L0,9 Z" fill="context-stroke"></path></marker>' +
    "</defs></svg>");
}

if (typeof Drawflow === "undefined") {
  fatalBanner("Drawflow 라이브러리를 불러오지 못했습니다. /static/vendor/drawflow.min.js 경로를 확인하세요.");
} else if (!container) {
  fatalBanner("캔버스(#drawflow)를 찾지 못했습니다. 페이지를 강력 새로고침(Ctrl+F5) 하세요.");
} else {
  editor = new Drawflow(container);
  editor.reroute = true;
  editor.start();

  editor.on("zoom", (z) => { const h = document.getElementById("zoomHint"); if (h) h.textContent = Math.round(z * 100) + "%"; });
  editor.on("nodeSelected", (id) => showProps(id));
  editor.on("nodeUnselected", () => hideProps());
  editor.on("connectionSelected", (c) => showEdgeProps(String(c.output_id), String(c.input_id)));
  editor.on("nodeCreated", refreshAlignState);
  editor.on("nodeRemoved", (id) => { selectedIds.delete(String(id)); markSel(); hideProps(); });
  editor.on("nodeMoved", () => setDirty(true));
  editor.on("connectionCreated", () => setDirty(true));
  editor.on("connectionRemoved", () => setDirty(true));

  wireDrop();

  // 다중 선택: 클릭=단일, Shift+클릭=추가/토글, 빈 캔버스=해제
  container.addEventListener("click", (e) => {
    const nodeEl = e.target.closest(".drawflow-node");
    if (!nodeEl) { if (!e.shiftKey) { selectedIds.clear(); markSel(); } return; }
    const id = nodeEl.id.replace("node-", "");
    if (e.shiftKey) { selectedIds.has(id) ? selectedIds.delete(id) : selectedIds.add(id); }
    else { selectedIds.clear(); selectedIds.add(id); }
    markSel();
  });

  const on = (id, evt, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(evt, fn); };

  on("opSearch", "input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll("#paletteOps .op").forEach((el) => (el.style.display = el.textContent.toLowerCase().includes(q) ? "flex" : "none"));
  });
  on("modeSeg", "click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    runMode = b.dataset.mode;
    document.querySelectorAll("#modeSeg button").forEach((x) => x.classList.toggle("active", x === b));
    document.getElementById("runParams").style.display = runMode === "form" ? "" : "none";
    document.getElementById("runJsonWrap").style.display = runMode === "json" ? "" : "none";
  });
  on("btnSave", "click", saveGraph);
  on("editTitle", "click", openMeta);
  const mo = document.getElementById("metaOverlay");
  if (mo) mo.addEventListener("click", (e) => { if (e.target === mo) closeMeta(); });
  on("zoomIn", "click", () => editor.zoom_in());
  on("zoomOut", "click", () => editor.zoom_out());
  on("themeBtn", "click", () => {
    const html = document.documentElement, dark = html.getAttribute("data-theme") === "dark";
    html.setAttribute("data-theme", dark ? "light" : "dark");
    const ti = document.getElementById("themeIcon"), tl = document.getElementById("themeLabel");
    if (ti) ti.textContent = dark ? "🌗" : "🌙"; if (tl) tl.textContent = dark ? "라이트" : "다크";
    try { localStorage.setItem("mcp-theme", dark ? "light" : "dark"); } catch (e) {}
  });
  if (document.documentElement.getAttribute("data-theme") === "dark") {
    const ti = document.getElementById("themeIcon"), tl = document.getElementById("themeLabel");
    if (ti) ti.textContent = "🌙"; if (tl) tl.textContent = "다크";
  }
  const mcpToggle = document.getElementById("mcpToggle");
  if (mcpToggle) mcpToggle.addEventListener("click", () => { mcpToggle.classList.toggle("on"); pushExpose(); });
  on("toolName", "change", () => { if (mcpToggle && mcpToggle.classList.contains("on")) pushExpose(); });
  on("mcpGroup", "change", () => { if (mcpToggle && mcpToggle.classList.contains("on")) pushExpose(); });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest ? e.target.closest(".codecopy") : null;
    if (!btn) return;
    e.stopPropagation();
    const code = btn.parentElement.querySelector(".code");
    copyText(code ? code.textContent : "", "복사했습니다");
  });

  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  (async function boot() {
    ensureMarkers();
    buildLogicPalette();
    await loadOperations();
    await loadWorkflow();
    refreshAlignState();
  })();
}
