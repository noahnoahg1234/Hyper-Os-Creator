/* Hyper OS Creator - app core: API client, router, jobs, toasts, tips. */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const human = n => { n = Number(n) || 0; for (const u of ["B", "KB", "MB", "GB"]) { if (n < 1024) return (u === "B" ? n : n.toFixed(1)) + " " + u; n /= 1024; } return n.toFixed(1) + " TB"; };
const fileUrl = path => "/api/file?path=" + encodeURIComponent(path);

const App = (() => {
  const pages = {};
  const PAGE_TOPICS = { home: "start", systems: "start", system: "start", ui: "ui", code: "code", bootloaders: "bootloader",
    kernels: "kernel", isos: "iso", isoproject: "iso", resources: "resources", suggestions: "suggestions", console: "cli" };
  let tipsList = [], currentTopic = "start", status = null;

  async function api(method, path, body) {
    const res = await fetch(path, { method, headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) throw new Error((data && data.error) || `${res.status} ${res.statusText}`);
    return data;
  }
  const get = p => api("GET", p), post = (p, b = {}) => api("POST", p, b), put = (p, b) => api("PUT", p, b), del = p => api("DELETE", p);

  function toast(msg, kind = "") {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.parentNode && el.parentNode.removeChild(el), kind === "error" ? 7000 : 3500);
  }

  async function guard(fn, okMsg) {
    try { const r = await fn(); if (okMsg) toast(okMsg, "ok"); return r; }
    catch (e) { toast(e.message, "error"); throw e; }
  }

  function modal(title, html, onReady) {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = html;
    $("#modal").hidden = false;
    if (onReady) onReady($("#modal-body"));
  }
  function closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; }

  function ask(title, label, value = "") {
    return new Promise(resolve => {
      modal(title, `<div class="field"><label>${esc(label)}</label><input id="pr-in" value="${esc(value)}"></div>
        <div class="row end"><button id="pr-cancel">Cancel</button><button class="primary" id="pr-ok">OK</button></div>`, body => {
        const inp = $("#pr-in", body); inp.focus(); inp.select();
        const done = v => { closeModal(); resolve(v); };
        $("#pr-ok", body).onclick = () => done(inp.value.trim());
        $("#pr-cancel", body).onclick = () => done(null);
        inp.onkeydown = e => { if (e.key === "Enter") done(inp.value.trim()); };
      });
    });
  }

  // ---- background jobs (downloads, builds)
  const watching = new Map();
  function watchJob(job, onDone) {
    watching.set(job.id, { job, onDone });
    renderJobs();
    if (watching.size === 1) setTimeout(pollJobs, 500);
  }
  async function pollJobs() {
    for (const [id, w] of watching) {
      try { w.job = await get("/api/jobs/" + id); } catch (e) { watching.delete(id); continue; }
      if (w.job.status !== "running") {
        watching.delete(id);
        if (w.job.status === "done") { toast(`${w.job.title}: done`, "ok"); if (w.onDone) w.onDone(w.job.result); }
        else toast(`${w.job.title}: ${w.job.error}`, "error");
      }
    }
    renderJobs();
    if (watching.size) setTimeout(pollJobs, 600);
  }
  function renderJobs() {
    $("#jobs").innerHTML = [...watching.values()].map(({ job }) => {
      const pct = job.total ? Math.round(job.done / job.total * 100) : 0;
      return `<div class="job"><div class="row"><b>${esc(job.title)}</b><span class="spacer"></span>
        <button class="small" data-cancel="${job.id}">Cancel</button></div>
        <div class="bar ${job.total ? "" : "indet"}"><div style="width:${pct}%"></div></div>
        <small>${job.total ? `${pct}% · ${human(job.done)} of ${human(job.total)}` : job.done ? human(job.done) : esc((job.message || "working…").split("\n").pop().slice(0, 80))}</small></div>`;
    }).join("");
    $$("[data-cancel]", $("#jobs")).forEach(b => { b.onclick = () => post(`/api/jobs/${b.dataset.cancel}/cancel`); });
  }
  async function startJob(path, body, onDone) {
    const job = await guard(() => post(path, body));
    watchJob(job, onDone);
    return job;
  }

  // ---- tips
  async function loadTips() {
    try { tipsList = (await get("/api/tips")).tips; } catch (e) { tipsList = []; }
  }
  function showTip(topic) {
    currentTopic = topic || currentTopic;
    const hidden = localStorage.getItem("hyperos.tips") === "off";
    $("#tipbar").hidden = hidden || !tipsList.length;
    const pool = tipsList.filter(t => t.topic === currentTopic);
    const list = pool.length ? pool : tipsList;
    if (list.length) $("#tiptext").textContent = list[Math.floor(Math.random() * list.length)].tip;
  }

  // ---- router
  function register(name, fn) { pages[name] = fn; }
  async function route() {
    const [name, ...args] = (location.hash.replace(/^#\/?/, "") || "home").split("/").map(decodeURIComponent);
    const fn = pages[name] || pages.home;
    $$("#nav a").forEach(a => a.classList.toggle("active", a.dataset.page === name ||
      (name === "system" && a.dataset.page === "systems") || (name === "isoproject" && a.dataset.page === "isos")));
    const page = $("#page");
    page.className = "";
    page.innerHTML = `<div class="empty">Loading…</div>`;
    showTip(PAGE_TOPICS[name] || "start");
    if (App.cleanup) { try { App.cleanup(); } catch (e) { /* ignore */ } App.cleanup = null; }
    try { await fn(page, ...args); }
    catch (e) { page.innerHTML = `<div class="card"><h2>Something went wrong</h2><p class="muted">${esc(e.message)}</p></div>`; }
  }

  // remember which system the user is working on
  const currentSystem = {
    get: () => localStorage.getItem("hyperos.system") || "",
    set: slug => localStorage.setItem("hyperos.system", slug),
  };

  async function systemOptions(selected) {
    const list = await get("/api/systems");
    return list.map(s => `<option value="${esc(s.slug)}" ${s.slug === selected ? "selected" : ""}>${esc(s.name)}</option>`).join("");
  }

  function applyTheme() {
    document.documentElement.dataset.theme = localStorage.getItem("hyperos.theme") || "dark";
  }

  async function start() {
    applyTheme();
    $("#modal-close").onclick = closeModal;
    $("#modal").onclick = e => { if (e.target.id === "modal") closeModal(); };
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });
    $("#tipnext").onclick = () => showTip();
    $("#tipclose").onclick = () => { localStorage.setItem("hyperos.tips", "off"); $("#tipbar").hidden = true;
      toast("Tips hidden. Turn them back on from the Tips page."); };
    await loadTips();
    try { status = await get("/api/status"); $("#sidebar-foot").textContent = `v${status.version}`; } catch (e) { /* offline */ }
    window.addEventListener("hashchange", route);
    route();
  }

  return { start, register, api, get, post, put, del, toast, guard, modal, closeModal, ask, startJob, watchJob,
           showTip, loadTips, currentSystem, systemOptions, applyTheme, route, cleanup: null, get status() { return status; } };
})();
