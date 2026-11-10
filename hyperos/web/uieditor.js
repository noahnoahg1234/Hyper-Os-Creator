/* Hyper OS Creator - visual UI editor for the 80x25 text-mode desktop. */
(() => {
  const CW = 10, CH = 20;
  const ICONS = { fill: "▦", box: "▢", text: "T" };

  App.register("ui", async (page, slug) => {
    slug = slug || App.currentSystem.get();
    const systems = await App.get("/api/systems");
    if (!systems.length) {
      page.innerHTML = `<div class="card empty"><h2>No systems yet</h2><p>Create a system first, then design its desktop here.</p>
        <a class="btn primary" href="#/systems">Go to My Systems</a></div>`;
      return;
    }
    if (!systems.some(s => s.slug === slug)) slug = systems[0].slug;
    App.currentSystem.set(slug);
    const { system } = await App.get(`/api/systems/${slug}`);
    const { installed } = await App.get("/api/resources");
    const layouts = installed.filter(r => r.type === "ui-layout" || r.type === "theme");

    let els = system.ui.elements.map(e => ({ ...e }));
    let sel = els.length > 1 ? 1 : 0, dirty = false;
    const undo = [], redo = [];
    const snapshot = () => { undo.push(JSON.stringify(els)); if (undo.length > 100) undo.shift(); redo.length = 0; dirty = true; };

    page.className = "full";
    page.innerHTML = `
      <div class="page-head" style="margin-bottom:10px"><div><h1>UI Editor</h1><p>Design the desktop your OS shows when it boots.</p></div>
        <div class="row"><select id="u-sys" style="width:200px">${systems.map(s => `<option value="${esc(s.slug)}" ${s.slug === slug ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
        <button id="u-undo" title="Undo (Ctrl+Z)">↶</button><button id="u-redo" title="Redo (Ctrl+Y)">↷</button>
        <button id="u-save" title="Ctrl+S">Save</button><button class="primary" id="u-run">Save, build &amp; run</button></div></div>
      <div class="uie">
        <div class="card"><h3>Add</h3><div class="stack">
          <button data-add="box">▢ Box / window</button><button data-add="text">T Text</button><button data-add="fill">▦ Background fill</button>
          <button data-add="window">🗔 Window with text</button><button data-add="taskbar">▬ Taskbar</button>
          <button data-add="button">⬚ Button</button><button data-add="title">★ Title bar</button></div>
          <h3 style="margin-top:16px">Layers</h3><div class="layers" id="u-layers"></div>
          <div class="row" style="margin-top:8px"><button class="small" id="u-up" title="Move up">▲</button><button class="small" id="u-down" title="Move down">▼</button>
          <button class="small" id="u-dup" title="Duplicate (Ctrl+D)">⧉</button><button class="small danger" id="u-del" title="Delete">🗑</button></div>
          ${layouts.length ? `<h3 style="margin-top:16px">From resources</h3><select id="u-res"><option value="">Apply a layout or theme…</option>
            ${layouts.map(l => `<option value="${esc(l.id)}">${esc(l.name)} (${esc(l.type)})</option>`).join("")}</select>` : ""}
        </div>
        <div><div class="card" style="padding:10px"><div class="uie-canvas-wrap"><canvas class="screen" id="u-canvas"></canvas></div>
          <div class="uie-status"><span id="u-pos">Column –, row –</span><span>Drag to move · drag the ◢ corner to resize · arrows nudge · Del deletes</span></div></div>
          <div class="card"><h3>Boot preview</h3><p class="muted" style="margin:0">After the bootloader banner, your OS draws this screen and waits for a key,
            then opens the shell (prompt <code>${esc(system.shell.prompt)}</code>). Type <code>desktop</code> in the shell to come back.</p></div></div>
        <div class="card" id="u-props"></div>
      </div>`;

    const canvas = $("#u-canvas");
    const draw = () => {
      const ctx = Screen.draw(canvas, Screen.render(els), { cw: CW, ch: CH });
      const el = els[sel];
      if (el && el.type !== "fill") {
        const g = Screen.geometry(el);
        ctx.strokeStyle = "#22d3ee"; ctx.lineWidth = 2; ctx.setLineDash([5, 3]);
        ctx.strokeRect(g.x * CW + 1, g.y * CH + 1, g.w * CW - 2, g.h * CH - 2);
        ctx.setLineDash([]);
        if (el.type === "box") { ctx.fillStyle = "#22d3ee"; ctx.fillRect((g.x + g.w) * CW - 8, (g.y + g.h) * CH - 8, 8, 8); }
      }
    };
    const label = e => e.type === "fill" ? "Background" : e.type === "box" ? `Box ${e.title ? "“" + e.title.trim() + "”" : `${e.w}×${e.h}`}` : `“${e.text}”`;
    const layers = () => {
      $("#u-layers").innerHTML = els.map((e, i) => `<div class="layer ${i === sel ? "sel" : ""}" data-i="${i}">
        <span class="ico">${ICONS[e.type]}</span><span class="nm">${esc(label(e))}</span>
        <span class="swatch" style="width:14px;height:14px;background:${Screen.PALETTE[e.bg ?? 0]}"></span></div>`).join("");
      $$(".layer", $("#u-layers")).forEach(l => { l.onclick = () => { sel = +l.dataset.i; refresh(); }; });
    };
    const swatches = (key, cur, count = 16) => `<div class="swatches">${Screen.PALETTE.slice(0, count).map((c, i) =>
      `<button class="swatch ${i === cur ? "sel" : ""}" style="background:${c}" title="${i} ${Screen.NAMES[i]}" data-k="${key}" data-v="${i}"></button>`).join("")}</div>`;
    const props = () => {
      const e = els[sel], box = $("#u-props");
      if (!e) { box.innerHTML = `<h3>Properties</h3><p class="muted">Select an element.</p>`; return; }
      const num = (k, label, max) => `<div class="field"><label>${label}</label><input type="number" min="0" max="${max}" data-p="${k}" value="${e[k] ?? 0}"></div>`;
      box.innerHTML = `<h3>${ICONS[e.type]} ${e.type === "fill" ? "Background fill" : e.type === "box" ? "Box" : "Text"}</h3>
        ${e.type === "text" ? `<div class="field"><label>Text</label><input data-p="text" value="${esc(e.text)}" maxlength="80"></div>` : ""}
        ${e.type === "box" ? `<div class="field"><label>Title</label><input data-p="title" value="${esc(e.title || "")}" maxlength="76"></div>
          <div class="field"><label>Border</label><select data-p="style">${Object.keys(Screen.STYLES).map(s => `<option ${s === e.style ? "selected" : ""}>${s}</option>`).join("")}</select></div>` : ""}
        ${e.type !== "fill" ? `<div class="cols">${num("x", "Column (x)", 79)}${num("y", "Row (y)", 24)}</div>` : ""}
        ${e.type === "box" ? `<div class="cols">${num("w", "Width", 80)}${num("h", "Height", 25)}</div>` : ""}
        <div class="field"><label>${e.type === "fill" ? "Colour of text drawn on it" : "Text / border colour"}</label>${swatches("fg", e.fg ?? 7)}</div>
        <div class="field"><label>Background</label>${swatches("bg", e.bg ?? 0)}</div>
        ${(e.bg ?? 0) > 7 ? `<small>Bright backgrounds (8–15) may blink on real hardware.</small>` : ""}`;
      $$("[data-p]", box).forEach(inp => {
        inp.onfocus = () => snapshot();
        inp.oninput = () => { e[inp.dataset.p] = inp.type === "number" ? Math.max(0, +inp.value || 0) : inp.value; draw(); layers(); };
        inp.onchange = inp.oninput;
      });
      $$("[data-k]", box).forEach(b => { b.onclick = () => { snapshot(); e[b.dataset.k] = +b.dataset.v; refresh(); }; });
    };
    const refresh = () => { draw(); layers(); props(); };

    const PRESETS = {
      box: () => ({ type: "box", x: 25, y: 7, w: 30, h: 10, fg: 15, bg: 1, style: "single", title: " Window " }),
      text: () => ({ type: "text", x: 30, y: 12, fg: 15, bg: 1, text: "Hello!" }),
      fill: () => ({ type: "fill", fg: 15, bg: 1 }),
      window: () => [{ type: "box", x: 20, y: 6, w: 40, h: 12, fg: 0, bg: 7, style: "double", title: " My App " },
                     { type: "text", x: 23, y: 9, fg: 0, bg: 7, text: "Write something nice here." }],
      taskbar: () => [{ type: "box", x: 0, y: 22, w: 80, h: 3, fg: 0, bg: 7, style: "single", title: "" },
                      { type: "text", x: 2, y: 23, fg: 15, bg: 2, text: " Start " }, { type: "text", x: 70, y: 23, fg: 0, bg: 7, text: "12:00" }],
      button: () => [{ type: "box", x: 34, y: 15, w: 12, h: 3, fg: 15, bg: 2, style: "single", title: "" },
                     { type: "text", x: 38, y: 16, fg: 15, bg: 2, text: "OK" }],
      title: () => [{ type: "box", x: 0, y: 0, w: 80, h: 3, fg: 15, bg: 3, style: "double", title: ` ${system.name} ` }],
    };
    $$("[data-add]").forEach(b => { b.onclick = () => {
      snapshot();
      const items = [].concat(PRESETS[b.dataset.add]());
      if (b.dataset.add === "fill") { els.unshift(items[0]); sel = 0; }
      else { els.push(...items); sel = els.length - items.length; }
      refresh();
    }; });
    const move = d => { const j = sel + d; if (j < 0 || j >= els.length) return; snapshot(); [els[sel], els[j]] = [els[j], els[sel]]; sel = j; refresh(); };
    const dup = () => { if (!els[sel]) return; snapshot(); const c = { ...els[sel] }; if (c.type !== "fill") { c.x = Math.min(79, (c.x || 0) + 2); c.y = Math.min(24, (c.y || 0) + 1); }
      els.splice(sel + 1, 0, c); sel++; refresh(); };
    const remove = () => { if (!els[sel]) return; snapshot(); els.splice(sel, 1); sel = Math.min(sel, els.length - 1); refresh(); };
    $("#u-up").onclick = () => move(-1); $("#u-down").onclick = () => move(1); $("#u-dup").onclick = dup; $("#u-del").onclick = remove;
    const doUndo = () => { if (!undo.length) return; redo.push(JSON.stringify(els)); els = JSON.parse(undo.pop()); sel = Math.min(sel, els.length - 1); refresh(); };
    const doRedo = () => { if (!redo.length) return; undo.push(JSON.stringify(els)); els = JSON.parse(redo.pop()); refresh(); };
    $("#u-undo").onclick = doUndo; $("#u-redo").onclick = doRedo;

    const save = async () => {
      const { system: fresh } = await App.get(`/api/systems/${slug}`);
      fresh.ui = { ...fresh.ui, elements: els };
      await App.guard(() => App.put(`/api/systems/${slug}`, { system: fresh }), "Desktop saved");
      dirty = false;
    };
    $("#u-save").onclick = save;
    $("#u-run").onclick = async () => {
      await save();
      const r = await App.post(`/api/systems/${slug}/build`);
      if (!r.ok) return App.toast("Build failed: " + r.log, "error");
      App.guard(() => App.post(`/api/systems/${slug}/run`), "Built! QEMU is starting…").catch(() => {});
    };
    $("#u-sys").onchange = e => { if (dirty && !confirm("Discard unsaved changes?")) { e.target.value = slug; return; } location.hash = "#/ui/" + e.target.value; };
    if ($("#u-res")) $("#u-res").onchange = async e => {
      if (!e.target.value) return;
      if (dirty) await save();
      const r = await App.guard(() => App.post("/api/resources/apply", { id: e.target.value, slug }));
      App.toast(r.note, "ok"); App.route();
    };

    // ---- mouse interaction
    const cell = ev => {
      const r = canvas.getBoundingClientRect();
      return { x: Math.floor((ev.clientX - r.left) / r.width * 80), y: Math.floor((ev.clientY - r.top) / r.height * 25) };
    };
    const hit = (x, y) => {
      for (let i = els.length - 1; i >= 0; i--) {
        if (els[i].type === "fill") continue;
        const g = Screen.geometry(els[i]);
        if (x >= g.x && x < g.x + g.w && y >= g.y && y < g.y + g.h) return i;
      }
      return els.findIndex(e => e.type === "fill");
    };
    let drag = null;
    canvas.onmousedown = ev => {
      const c = cell(ev);
      const cur = els[sel];
      if (cur && cur.type === "box") {
        const g = Screen.geometry(cur);
        if (c.x === g.x + g.w - 1 && c.y === g.y + g.h - 1) { snapshot(); drag = { mode: "resize", g }; return; }
      }
      const i = hit(c.x, c.y);
      if (i < 0) return;
      sel = i; refresh();
      if (els[i].type !== "fill") { snapshot(); drag = { mode: "move", dx: c.x - (els[i].x || 0), dy: c.y - (els[i].y || 0) }; }
    };
    const onMove = ev => {
      const r = canvas.getBoundingClientRect();
      if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
        const c = cell(ev); $("#u-pos").textContent = `Column ${c.x}, row ${c.y}`;
      }
      if (!drag) return;
      const c = cell(ev), e = els[sel];
      if (drag.mode === "move") {
        const g = Screen.geometry(e);
        e.x = Math.max(0, Math.min(80 - (e.type === "box" ? g.w : 1), c.x - drag.dx));
        e.y = Math.max(0, Math.min(25 - g.h, c.y - drag.dy));
      } else {
        e.w = Math.max(2, Math.min(80 - e.x, c.x - e.x + 1));
        e.h = Math.max(2, Math.min(25 - e.y, c.y - e.y + 1));
      }
      draw(); props();
    };
    const onUp = () => { if (drag) { drag = null; layers(); } };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);

    const onKey = ev => {
      if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || !$("#modal").hidden) return;
      const k = ev.key, ctrl = ev.ctrlKey || ev.metaKey, e = els[sel];
      if (ctrl && k.toLowerCase() === "s") { ev.preventDefault(); save(); }
      else if (ctrl && k.toLowerCase() === "z") { ev.preventDefault(); doUndo(); }
      else if (ctrl && k.toLowerCase() === "y") { ev.preventDefault(); doRedo(); }
      else if (ctrl && k.toLowerCase() === "d") { ev.preventDefault(); dup(); }
      else if (k === "Delete" || k === "Backspace") { ev.preventDefault(); remove(); }
      else if (e && e.type !== "fill" && k.startsWith("Arrow")) {
        ev.preventDefault(); snapshot();
        const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[k];
        e.x = Math.max(0, Math.min(79, (e.x || 0) + d[0])); e.y = Math.max(0, Math.min(24, (e.y || 0) + d[1]));
        refresh();
      }
    };
    document.addEventListener("keydown", onKey);
    const beforeUnload = ev => { if (dirty) { ev.preventDefault(); ev.returnValue = ""; } };
    window.addEventListener("beforeunload", beforeUnload);
    App.cleanup = () => {
      window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp);
      document.removeEventListener("keydown", onKey); window.removeEventListener("beforeunload", beforeUnload);
    };
    refresh();
  });
})();
