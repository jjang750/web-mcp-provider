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
  const LOGIC = [["분기 (IF)", "branch"], ["반복 (Loop)", "loop"], ["병합 (Merge)", "merge"]];
  const colors = { branch: "var(--logic-branch)", loop: "var(--logic-loop)", merge: "var(--logic-merge)" };
  lg.innerHTML = LOGIC.map(([name, g]) =>
    '<div class="op"><span class="logic-ico" style="background:' + colors[g] + '"></span>' +
    '<div class="logic-meta"><span class="logic-name">' + name + '</span><span class="logic-sub">7단계 로드맵</span></div></div>').join("");
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
    const op = d.op || opsById[d.opId];
    if (d.kind === "api" && op) addApiNode(op, x, y);
  });
}

function exportGraph() {
  const data = editor.drawflow.drawflow.Home.data;
  const nodes = [], edges = [];
  Object.keys(data).forEach((id) => {
    const n = data[id], cls = n.class, dd = n.data || {};
    const type = cls === "api" ? "api_call" : (cls === "start" || cls === "end") ? cls : "transform";
    nodes.push({
      id: String(id), type: type,
      label: dd.op ? (dd.op.summary || dd.op.path) : null,
      operation_id: dd.op ? dd.op.id : null,
      base_url: dd.base_url || null,
      params: dd.params || {},
      position: { x: n.pos_x, y: n.pos_y },
    });
    Object.keys(n.outputs || {}).forEach((ok) => {
      (n.outputs[ok].connections || []).forEach((c) => {
        const src = String(id), tgt = String(c.node);
        edges.push({ id: src + "-" + tgt, source: src, target: tgt, data_mapping: edgeMap[src + "->" + tgt] || [] });
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
  (wf.nodes || []).forEach((n) => {
    const x = (n.position && n.position.x) || 60, y = (n.position && n.position.y) || 80;
    let live;
    if (n.type === "start" || n.type === "end") {
      live = editor.addNode(n.type, n.type === "start" ? 0 : 1, n.type === "start" ? 1 : 0, x, y, n.type, {}, terminalHTML(n.type));
    } else if (n.type === "api_call") {
      const op = opsById[n.operation_id] || { id: n.operation_id, method: "GET", path: n.label || "", summary: n.label };
      live = editor.addNode("api", 1, 1, x, y, "api", { op: slimOp(op), params: n.params || seedParams(op), base_url: n.base_url || null }, apiNodeHTML(op));
    } else { return; }
    idMap[n.id] = live;
  });
  (wf.edges || []).forEach((e) => {
    const s = idMap[e.source], t = idMap[e.target];
    if (s == null || t == null) return;
    try { editor.addConnection(s, t, "output_1", "input_1"); } catch (_) {}
    if (e.data_mapping && e.data_mapping.length) edgeMap[s + "->" + t] = e.data_mapping;
  });
  refreshAlignState();
  setDirty(false);
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
      '<button class="btn btn-secondary" id="pApply">적용</button>';
    empty.style.display = "none"; body.style.display = "block";
    document.getElementById("pApply").addEventListener("click", () => {
      const nd = editor.drawflow.drawflow.Home.data[id];
      nd.data.base_url = document.getElementById("pBase").value.trim() || null;
      try { nd.data.params = JSON.parse(document.getElementById("pParams").value || "{}"); }
      catch (e) { toast("params JSON 오류: " + e.message, "fail"); return; }
      setDirty(true); toast("적용했습니다");
    });
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

function openRun() {
  const data = editor.drawflow.drawflow.Home.data;
  const apiIds = Object.keys(data).filter((id) => data[id].class === "api");
  document.getElementById("apiCount").textContent = apiIds.length;
  const form = document.getElementById("runParams");
  if (!apiIds.length) form.innerHTML = '<p style="font-size:12px;color:var(--text-3);">API 노드가 없습니다.</p>';
  else form.innerHTML = apiIds.map((id) => {
    const op = data[id].data.op, params = data[id].data.params || {};
    let rows = "";
    ["path", "query", "header"].forEach((sec) => {
      Object.keys(params[sec] || {}).forEach((k) => {
        rows += '<div class="prow"><label>' + esc(k) + '</label><input data-node="' + id + '" data-sec="' + sec + '" data-key="' + esc(k) + '" value="' + esc(params[sec][k]) + '"></div>';
      });
    });
    if (params.body != null) rows += '<div class="prow"><label>body</label><input data-node="' + id + '" data-sec="body" value="' + esc(typeof params.body === "string" ? params.body : JSON.stringify(params.body)) + '"></div>';
    if (!rows) rows = '<p style="font-size:11px;color:var(--text-3);">파라미터 없음</p>';
    return '<div class="pgroup"><div class="pg-head"><span class="badge ' + mlow(op.method) + '">' + esc((op.method || "GET").toUpperCase()) + '</span><span class="pg-name">' + esc(op.summary || op.path) + "</span></div>" + rows + "</div>";
  }).join("");
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
  return '<div class="code">' + esc(typeof v === "string" ? v : JSON.stringify(v, null, 2)) + "</div>";
}
function buildLog(res) {
  const data = editor.drawflow.drawflow.Home.data;
  const log = document.getElementById("rtLog");
  const failed = res.status !== "success";
  const rows = (res.logs || []).map((l) => {
    const nd = data[l.node_key];
    const name = nd && nd.data.op ? (nd.data.op.summary || nd.data.op.path) : l.node_key;
    const method = nd && nd.data.op ? mlow(nd.data.op.method) : "get";
    let cls = "ok", circle = "var(--success)", icon = "\u2713", code = l.status_code || "200", cc = "var(--success)";
    if (l.status === "failed") { cls = "fail"; circle = "var(--danger)"; icon = "!"; code = (l.error && (String(l.error).match(/\d{3}/) || [])[0]) || "ERR"; cc = "var(--danger)"; }
    else if (l.status === "skipped") { cls = "skip"; circle = "var(--border-strong)"; icon = "\u2013"; code = "\u2014"; cc = "var(--text-3)"; }
    const detail = '<div class="lc-detail">' +
      '<div class="lc-label">INPUT</div>' + jsonBlock(l.input) +
      '<div class="lc-label">OUTPUT</div>' + jsonBlock(l.output) +
      (l.error ? '<div class="lc-label">ERROR</div><div class="err">' + esc(l.error) + "</div>" : "") +
      (l.timestamp ? '<div class="lc-label">TIME</div><div class="code">' + esc(l.timestamp) + "</div>" : "") +
      "</div>";
    return '<div class="logcard ' + cls + '"><div class="lc-head">' +
      '<span class="lc-circle" style="background:' + circle + '">' + icon + "</span>" +
      '<span class="badge ' + method + '">' + (nd && nd.data.op ? esc(nd.data.op.method) : "") + "</span>" +
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

  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  (async function boot() {
    ensureMarkers();
    buildLogicPalette();
    await loadOperations();
    await loadWorkflow();
    refreshAlignState();
  })();
}
