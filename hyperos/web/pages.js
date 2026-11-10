/* Hyper OS Creator - pages */
(() => {
  const { get, post, put, del, toast, guard, modal, closeModal, startJob } = App;
  const colorOptions = sel => Screen.NAMES.map((n, i) => `<option value="${i}" ${+sel === i ? "selected" : ""}>${i} · ${n}</option>`).join("");
  const tabs = (names, active) => `<div class="tabs">${names.map(([id, label]) =>
    `<button data-tab="${id}" class="${id === active ? "active" : ""}">${label}</button>`).join("")}</div>`;
  function bindTabs(root, onTab) {
    $$(".tabs [data-tab]", root).forEach(b => {
      b.onclick = () => { $$(".tabs [data-tab]", root).forEach(x => x.classList.toggle("active", x === b)); onTab(b.dataset.tab); };
    });
  }
  const downloadList = items => items.length ? items.map(d => `<div class="item"><div class="grow">
      <div class="title">${esc(d.file)}</div><small>${esc(d.name)} · ${esc(d.version)} · ${human(d.size)} · ${esc(d.date || "")}</small>
      ${d.sha256 ? `<div><small class="mono">sha256 ${esc(d.sha256.slice(0, 24))}…</small></div>` : ""}</div>
      <a class="btn small" href="${fileUrl(d.path)}">Save file</a></div>`).join("") : `<div class="empty">Nothing downloaded yet.</div>`;

  // =========================================================================
  // Home
  // =========================================================================
  App.register("home", async page => {
    const st = await get("/api/status");
    const tools = Object.entries(st.tools);
    page.innerHTML = `
      <div class="card hero" style="padding:28px">
        <h1>Build your own operating system ✨</h1>
        <p class="muted" style="max-width:720px">Hyper OS Creator lets you design a desktop, write a bootloader and kernel,
          download real bootloaders, kernels and Linux ISOs, remix them and share what you make. Everything also works from the command line.</p>
        <div class="row" style="margin-top:14px">
          <button class="primary" id="h-new">+ Create a system</button>
          <a class="btn" href="#/ui">Open the UI editor</a><a class="btn" href="#/code">Open the code editor</a>
          <a class="btn" href="#/resources">Browse resources</a></div>
      </div>
      <div class="cols c3" style="margin-top:14px">
        <div class="card"><small>Systems</small><div class="stat">${st.systems}</div><a href="#/systems">Manage →</a></div>
        <div class="card"><small>Downloads</small><div class="stat">${st.downloads}</div><a href="#/isos">ISOs, kernels, bootloaders →</a></div>
        <div class="card"><small>Installed resources</small><div class="stat">${st.resources}</div><a href="#/resources">Resources →</a></div>
      </div>
      <div class="cols" style="margin-top:14px">
        <div class="card"><h2>Quick start</h2><ol class="steps">
          <li><b>Create a system</b> – give it a name. It boots right away.</li>
          <li><b>Design the desktop</b> in the UI editor – boxes, text, colours.</li>
          <li><b>Add commands</b> or change the boot banner on the system page.</li>
          <li><b>Build &amp; Run</b> – you get a bootable <code>.iso</code> and <code>.img</code>.</li>
          <li><b>Share it</b> as a resource so others can use your work.</li></ol></div>
        <div class="card"><h2>💡 Tip of the moment</h2><p id="h-tip">${esc(st.tip)}</p>
          <button class="small" id="h-tip-next">Another tip</button>
          <h3 style="margin-top:18px">Optional tools on this computer</h3>
          ${tools.map(([n, t]) => `<div class="row" style="margin-bottom:4px"><span class="badge ${t.found ? "ok" : "bad"}">${t.found ? "found" : "missing"}</span>
            <span class="mono">${esc(n)}</span><small>${esc(t.purpose)}</small></div>`).join("")}
          <small>None are required to build systems.</small></div>
      </div>`;
    $("#h-new").onclick = () => newSystemDialog();
    $("#h-tip-next").onclick = async () => { $("#h-tip").textContent = (await get("/api/status")).tip; };
  });

  async function newSystemDialog() {
    const res = await get("/api/resources");
    const templates = res.installed.filter(r => r.type === "system-template");
    modal("Create a new system", `
      <div class="field"><label>Name</label><input id="ns-name" placeholder="e.g. Rocket OS" autofocus></div>
      <div class="field"><label>Start from</label><select id="ns-from"><option value="">The default Hyper OS template</option>
        ${templates.map(t => `<option value="${esc(t.id)}">${esc(t.name)} (resource)</option>`).join("")}</select>
        <small>Get more starting points from <a href="#/resources">Resources</a> (type “system template”).</small></div>
      <div class="row end"><button class="primary" id="ns-go">Create</button></div>`, body => {
      $("#ns-name", body).focus();
      const go = async () => {
        const name = $("#ns-name", body).value.trim();
        if (!name) return toast("Please enter a name", "error");
        const r = await guard(() => post("/api/systems", { name, resource: $("#ns-from", body).value }));
        App.currentSystem.set(r.slug);
        closeModal();
        location.hash = "#/system/" + r.slug;
      };
      $("#ns-go", body).onclick = go;
      $("#ns-name", body).onkeydown = e => { if (e.key === "Enter") go(); };
    });
  }

  // =========================================================================
  // Systems
  // =========================================================================
  App.register("systems", async page => {
    const list = await get("/api/systems");
    page.innerHTML = `<div class="page-head"><div><h1>My Systems</h1><p>Each system is a complete, bootable operating system.</p></div>
      <button class="primary" id="s-new">+ New system</button></div>
      <div class="grid wide" id="s-list">${list.length ? "" : `<div class="card empty">No systems yet – create your first one!</div>`}</div>`;
    $("#s-new").onclick = newSystemDialog;
    const box = $("#s-list");
    for (const s of list) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<canvas class="screen"></canvas><div class="row" style="margin-top:10px"><div class="grow" style="flex:1">
        <div class="title"><b>${esc(s.name)}</b> <small>${esc(s.version)}</small></div><small>${esc(s.description)}</small></div>
        ${s.built ? `<span class="badge ok">built</span>` : `<span class="badge">not built</span>`}</div>
        <div class="row" style="margin-top:10px"><a class="btn small primary" href="#/system/${esc(s.slug)}">Open</a>
        <a class="btn small" href="#/ui/${esc(s.slug)}">UI</a><a class="btn small" href="#/code/${esc(s.slug)}">Code</a></div>`;
      box.appendChild(card);
      get(`/api/systems/${s.slug}`).then(d => Screen.draw($("canvas", card), Screen.render(d.system.ui.elements), { cw: 6, ch: 12 }));
    }
  });

  App.register("system", async (page, slug) => {
    const { system: sys } = await get(`/api/systems/${slug}`);
    App.currentSystem.set(slug);
    const files = await get(`/api/systems/${slug}/files`);
    const asmFiles = files.filter(f => f.name.endsWith(".asm"));
    const fileOpts = sel => asmFiles.map(f => `<option ${f.name === sel ? "selected" : ""}>${esc(f.name)}</option>`).join("");
    const bl = sys.bootloader, kn = sys.kernel, sh = sys.shell;
    page.innerHTML = `
      <div class="page-head"><div><h1>${esc(sys.name)} <small>${esc(sys.version)}</small></h1><p>${esc(sys.description)}</p></div>
        <div class="row"><button id="sy-save">Save</button><button class="primary" id="sy-build">Build</button>
        <button id="sy-run">▶ Run in QEMU</button><button id="sy-more">⋯ More</button></div></div>
      <div class="cols">
        <div>
          <div class="card"><h2>Desktop</h2><canvas class="screen" id="sy-preview"></canvas>
            <div class="row" style="margin-top:10px"><a class="btn" href="#/ui/${esc(slug)}">Edit in UI editor</a>
            <a class="btn" href="#/code/${esc(slug)}">Edit code</a><button id="sy-theme">Apply a resource…</button></div></div>
          <div class="card"><h2>Build output</h2><pre class="log" id="sy-log">Press Build to create your bootable images.</pre>
            <div class="row" style="margin-top:10px" id="sy-dl"></div></div>
        </div>
        <div>
          <div class="card"><h2>General</h2>
            <div class="cols"><div class="field"><label>Name</label><input id="f-name" value="${esc(sys.name)}"></div>
            <div class="field"><label>Version</label><input id="f-version" value="${esc(sys.version)}"></div></div>
            <div class="field"><label>Description</label><input id="f-desc" value="${esc(sys.description)}"></div>
            <div class="field"><label>Author</label><input id="f-author" value="${esc(sys.author || "")}"></div></div>
          <div class="card"><h2>Bootloader</h2>
            <div class="field"><label>Type</label><select id="f-btype">
              <option value="hyperboot">HyperBoot – banner + loads the kernel (recommended)</option>
              <option value="splash">HyperSplash – one-sector splash screen, no kernel</option>
              <option value="custom-asm">Custom – my own NASM code</option></select></div>
            <div id="b-hyper"><div class="field"><label>Boot banner</label><input id="f-banner" maxlength="63" value="${esc(bl.banner || "")}"></div>
              <div class="cols"><div class="field"><label>Text colour</label><select id="f-bfg">${colorOptions(bl.fg ?? 15)}</select></div>
              <div class="field"><label>Background</label><select id="f-bbg">${colorOptions(bl.bg ?? 1)}</select></div></div>
              <label class="check"><input type="checkbox" id="f-wait" ${bl.wait_key ? "checked" : ""}> Wait for a key before starting the kernel</label></div>
            <div id="b-splash"><div class="field"><label>Splash lines (one per line, max ~400 characters total)</label>
              <textarea id="f-splash" rows="4">${esc((bl.lines || []).map(l => l.text).join("\n"))}</textarea></div></div>
            <div id="b-custom"><div class="field"><label>Source file (in src/)</label><select id="f-bsrc">${fileOpts(bl.source)}</select></div>
              <small>Needs NASM. Get started from a template on the <a href="#/bootloaders">Bootloaders</a> page.</small></div></div>
          <div class="card"><h2>Kernel</h2>
            <div class="field"><label>Type</label><select id="f-ktype"><option value="hyperkernel">HyperKernel – desktop + shell (recommended)</option>
              <option value="custom-asm">Custom – my own NASM kernel</option></select></div>
            <div id="k-custom"><div class="field"><label>Source file (in src/)</label><select id="f-ksrc">${fileOpts(kn.source)}</select></div>
              <small>Kernels are loaded at 0x1000:0000. See templates on the <a href="#/kernels">Kernels</a> page.</small></div></div>
          <div class="card"><h2>Shell</h2>
            <div class="cols"><div class="field"><label>Prompt</label><input id="f-prompt" value="${esc(sh.prompt)}"></div>
            <div class="field"><label>Colours</label><div class="row"><select id="f-sfg" style="flex:1">${colorOptions(sh.fg ?? 7)}</select>
              <select id="f-sbg" style="flex:1">${colorOptions(sh.bg ?? 0)}</select></div></div></div>
            <div class="field"><label>Message of the day</label><textarea id="f-motd" rows="2">${esc(sh.motd)}</textarea></div>
            <h3>Custom commands</h3><div id="f-cmds"></div><button class="small" id="f-addcmd">+ Add command</button>
            <p><small>Built-in: help, clear, ver, desktop, echo, mem, time, reboot, halt.</small></p></div>
        </div>
      </div>`;
    const commands = sys.commands.map(c => ({ ...c }));
    const renderCmds = () => {
      $("#f-cmds").innerHTML = commands.map((c, i) => `<div class="row" style="margin-bottom:6px;align-items:flex-start">
        <input data-cn="${i}" value="${esc(c.name)}" placeholder="name" style="width:120px">
        <textarea data-co="${i}" rows="1" placeholder="what it prints" style="flex:1">${esc(c.output)}</textarea>
        <button class="small danger" data-cd="${i}">✕</button></div>`).join("") || `<small>No custom commands yet.</small>`;
      $$("[data-cn]").forEach(e => { e.oninput = () => { commands[e.dataset.cn].name = e.value.replace(/\s/g, "_"); }; });
      $$("[data-co]").forEach(e => { e.oninput = () => { commands[e.dataset.co].output = e.value; }; });
      $$("[data-cd]").forEach(e => { e.onclick = () => { commands.splice(+e.dataset.cd, 1); renderCmds(); }; });
    };
    renderCmds();
    $("#f-addcmd").onclick = () => { commands.push({ name: "", output: "" }); renderCmds(); };
    $("#f-btype").value = bl.type || "hyperboot";
    $("#f-ktype").value = kn.type === "custom-asm" ? "custom-asm" : "hyperkernel";
    const sync = () => {
      const bt = $("#f-btype").value;
      $("#b-hyper").hidden = bt !== "hyperboot"; $("#b-splash").hidden = bt !== "splash"; $("#b-custom").hidden = bt !== "custom-asm";
      $("#k-custom").hidden = $("#f-ktype").value !== "custom-asm";
    };
    $("#f-btype").onchange = sync; $("#f-ktype").onchange = sync; sync();
    Screen.draw($("#sy-preview"), Screen.render(sys.ui.elements));

    const collect = () => {
      const s = JSON.parse(JSON.stringify(sys));
      Object.assign(s, { name: $("#f-name").value.trim() || sys.name, version: $("#f-version").value, description: $("#f-desc").value,
        author: $("#f-author").value });
      const bt = $("#f-btype").value;
      s.bootloader = { ...s.bootloader, type: bt, banner: $("#f-banner").value, fg: +$("#f-bfg").value, bg: +$("#f-bbg").value,
        wait_key: $("#f-wait").checked };
      if (bt === "splash") s.bootloader.lines = $("#f-splash").value.split("\n").filter(Boolean)
        .map((text, i) => ({ x: 4, y: 3 + i * 2, text, fg: +$("#f-bfg").value, bg: +$("#f-bbg").value }));
      if (bt === "custom-asm") s.bootloader.source = $("#f-bsrc").value;
      s.kernel = { ...s.kernel, type: $("#f-ktype").value };
      if (s.kernel.type === "custom-asm") s.kernel.source = $("#f-ksrc").value;
      s.shell = { ...s.shell, prompt: $("#f-prompt").value, motd: $("#f-motd").value, fg: +$("#f-sfg").value, bg: +$("#f-sbg").value };
      s.commands = commands.filter(c => c.name.trim());
      return s;
    };
    const save = () => guard(() => put(`/api/systems/${slug}`, { system: collect() }), "Saved");
    const showResult = r => {
      $("#sy-log").textContent = r.log;
      $("#sy-dl").innerHTML = r.ok ? `<a class="btn small" href="${fileUrl(r.iso)}">⬇ Download .iso</a>
        <a class="btn small" href="${fileUrl(r.image)}">⬇ Download .img</a>
        <small>Kernel ${r.kernel_bytes} bytes · ${r.sectors} sectors</small>` : "";
    };
    $("#sy-save").onclick = save;
    $("#sy-build").onclick = async () => {
      await save();
      $("#sy-log").textContent = "Building…";
      const r = await guard(() => post(`/api/systems/${slug}/build`));
      showResult(r);
      toast(r.ok ? "Build complete – your OS is ready!" : "Build failed – see the log", r.ok ? "ok" : "error");
    };
    $("#sy-run").onclick = async () => { await save(); await post(`/api/systems/${slug}/build`).then(showResult);
      guard(() => post(`/api/systems/${slug}/run`), "QEMU started in a new window"); };
    $("#sy-theme").onclick = () => applyResourceDialog(slug);
    $("#sy-more").onclick = () => modal("More actions", `<div class="stack">
      <button id="m-share">⬡ Share this system as a resource</button>
      <button id="m-dup">⧉ Duplicate system</button>
      <button id="m-json">{ } View system.json</button>
      <button class="danger" id="m-del">🗑 Delete system</button></div>`, body => {
      $("#m-share", body).onclick = () => { closeModal(); location.hash = "#/resources/publish/" + slug; };
      $("#m-json", body).onclick = () => modal("system.json", `<pre class="log" style="max-height:60vh">${esc(JSON.stringify(collect(), null, 2))}</pre>`);
      $("#m-dup", body).onclick = async () => {
        const name = await App.ask("Duplicate system", "Name of the copy", sys.name + " copy");
        if (!name) return;
        const r = await guard(() => post("/api/systems", { name }));
        const copy = collect(); copy.name = name;
        await put(`/api/systems/${r.slug}`, { system: copy });
        location.hash = "#/system/" + r.slug;
      };
      $("#m-del", body).onclick = async () => {
        if (!confirm(`Delete ${sys.name} and all its files?`)) return;
        await guard(() => del(`/api/systems/${slug}`), "Deleted");
        closeModal(); location.hash = "#/systems";
      };
    });
  });

  async function applyResourceDialog(slug) {
    const { installed } = await get("/api/resources");
    const usable = installed.filter(r => r.type !== "system-template");
    modal("Apply a resource", usable.length ? usable.map(r => `<div class="item"><div class="grow"><div class="title">${esc(r.name)}</div>
      <small>${esc(r.type)} · ${esc(r.description)}</small></div><button class="small primary" data-apply="${esc(r.id)}">Apply</button></div>`).join("")
      : `<div class="empty">No resources installed. <a href="#/resources">Browse resources</a> to get themes, layouts and command packs.</div>`, body => {
      $$("[data-apply]", body).forEach(b => {
        b.onclick = async () => {
          const r = await guard(() => post("/api/resources/apply", { id: b.dataset.apply, slug }));
          toast(r.note, "ok"); closeModal(); App.route();
        };
      });
    });
  }
  App.applyResourceDialog = applyResourceDialog;

  // =========================================================================
  // Bootloaders
  // =========================================================================
  App.register("bootloaders", async (page, tab = "get") => {
    page.innerHTML = `<div class="page-head"><div><h1>Bootloaders</h1>
      <p>The first code your computer runs. Download a real one or create your own.</p></div></div>
      ${tabs([["get", "Get from internet"], ["create", "Create custom"], ["code", "Write from code"], ["mine", "My bootloaders"]], tab)}
      <div id="bl-body"></div>`;
    const body = $("#bl-body");
    const show = async t => {
      const data = await get("/api/bootloaders");
      if (t === "get") {
        body.innerHTML = `<div class="grid wide">${data.catalog.map(b => `<div class="card"><h3>${esc(b.name)}</h3>
          <p class="muted">${esc(b.description)}</p><div class="row"><button class="primary small" data-dl="${esc(b.id)}">⬇ Download latest</button>
          <a class="btn small" href="${esc(b.homepage)}" target="_blank" rel="noopener">Website</a></div></div>`).join("")}</div>
          <div class="card" style="margin-top:14px"><h3>Download from any URL</h3><div class="row">
          <input id="bl-url" placeholder="https://example.com/bootloader.tar.xz" style="flex:1"><button id="bl-urlgo">Download</button></div></div>`;
        $$("[data-dl]", body).forEach(b => { b.onclick = () => startJob("/api/bootloaders/download", { id: b.dataset.dl }, () => show("mine")); });
        $("#bl-urlgo").onclick = () => startJob("/api/bootloaders/download", { url: $("#bl-url").value.trim() });
      } else if (t === "create") {
        body.innerHTML = `<div class="cols">
          <div class="card"><h2>HyperBoot loader</h2><p class="muted">Loads a kernel and shows your banner. No tools needed.</p>
            <div class="field"><label>Banner</label><input id="hb-banner" value="Welcome to my OS!" maxlength="63"></div>
            <div class="cols"><div class="field"><label>Text</label><select id="hb-fg">${colorOptions(15)}</select></div>
            <div class="field"><label>Background</label><select id="hb-bg">${colorOptions(1)}</select></div></div>
            <label class="check"><input type="checkbox" id="hb-wait"> Wait for a key</label>
            <div class="field"><label>Name</label><input id="hb-name" value="my-hyperboot"></div>
            <button class="primary" id="hb-go">Generate boot sector</button><div id="hb-out" style="margin-top:10px"></div></div>
          <div class="card"><h2>Splash boot sector</h2><p class="muted">A whole colourful screen in 512 bytes. Boots on its own.</p>
            <canvas class="screen" id="sp-prev"></canvas>
            <div class="field" style="margin-top:10px"><label>Lines of text</label><textarea id="sp-text" rows="4">MY FIRST OS
Booted from a single 512-byte sector!
Press any key to reboot.</textarea></div>
            <div class="cols"><div class="field"><label>Text</label><select id="sp-fg">${colorOptions(14)}</select></div>
            <div class="field"><label>Background</label><select id="sp-bg">${colorOptions(1)}</select></div></div>
            <div class="field"><label>Name</label><input id="sp-name" value="my-splash"></div>
            <button class="primary" id="sp-go">Generate bootable image</button><div id="sp-out" style="margin-top:10px"></div></div></div>`;
        const lines = () => $("#sp-text").value.split("\n").filter(Boolean).map((text, i) => ({ x: 4, y: 3 + i * 2, text, fg: +$("#sp-fg").value, bg: +$("#sp-bg").value }));
        const prev = () => Screen.draw($("#sp-prev"), Screen.render([{ type: "fill", fg: 7, bg: +$("#sp-bg").value },
          ...lines().map(l => ({ type: "text", ...l }))]), { cw: 8, ch: 16 });
        ["sp-text", "sp-fg", "sp-bg"].forEach(id => { $("#" + id).oninput = prev; });
        prev();
        $("#hb-go").onclick = async () => {
          const r = await guard(() => post("/api/bootloaders/hyperboot", { banner: $("#hb-banner").value, fg: +$("#hb-fg").value,
            bg: +$("#hb-bg").value, wait_key: $("#hb-wait").checked, name: $("#hb-name").value }));
          $("#hb-out").innerHTML = `<span class="badge ok">${r.size} bytes</span> <a class="btn small" href="${fileUrl(r.path)}">⬇ boot sector</a>`;
        };
        $("#sp-go").onclick = async () => {
          const r = await guard(() => post("/api/bootloaders/splash", { lines: lines(), fg: +$("#sp-fg").value, bg: +$("#sp-bg").value, name: $("#sp-name").value }));
          $("#sp-out").innerHTML = `<span class="badge ok">${r.size} bytes</span> <a class="btn small" href="${fileUrl(r.image)}">⬇ bootable floppy .img</a>
            <a class="btn small" href="${fileUrl(r.path)}">⬇ raw .bin</a>`;
        };
      } else if (t === "code") {
        body.innerHTML = `<p class="muted">Pick a template, open it in the code editor and make it your own. Building custom code needs NASM
          (${App.status && App.status.tools.nasm.found ? `<span class="badge ok">installed</span>` : `<span class="badge bad">not installed</span>`}).</p>
          <div class="grid wide">${data.templates.map(t => `<div class="card"><h3>${esc(t.name)}</h3><span class="badge accent">${esc(t.difficulty)}</span>
          <p class="muted" style="margin-top:8px">${esc(t.description)}</p><div class="row">
          <button class="small primary" data-use="${esc(t.id)}">Use in a system</button><button class="small" data-view="${esc(t.id)}">View code</button></div></div>`).join("")}</div>`;
        $$("[data-view]", body).forEach(b => { b.onclick = async () => {
          const files = await get(`/api/templates/bootloaders/${b.dataset.view}`);
          modal(b.dataset.view, Object.entries(files).map(([n, c]) => `<h3>${esc(n)}</h3><pre class="log" style="max-height:60vh">${esc(c)}</pre>`).join(""));
        }; });
        $$("[data-use]", body).forEach(b => { b.onclick = () => useTemplateDialog("bootloaders", b.dataset.use); });
      } else {
        body.innerHTML = `<div class="cols"><div class="card"><h2>Downloaded</h2>${downloadList(data.downloaded)}</div>
          <div class="card"><h2>Custom built</h2>${data.custom.length ? data.custom.map(c => `<div class="item"><div class="grow">
          <div class="title">${esc(c.name)}</div><small>${c.size} bytes ${c.has_source ? "· has source" : ""}</small></div>
          <a class="btn small" href="${fileUrl(c.path)}">Save .bin</a></div>`).join("") : `<div class="empty">Nothing yet – try “Create custom”.</div>`}</div></div>`;
      }
    };
    bindTabs(page, t => { history.replaceState(null, "", "#/bootloaders/" + t); show(t); });
    show(tab);
  });

  async function useTemplateDialog(kind, id) {
    const opts = await App.systemOptions(App.currentSystem.get());
    if (!opts) return toast("Create a system first", "error");
    modal("Use template in a system", `<div class="field"><label>System</label><select id="ut-sys">${opts}</select></div>
      <p class="muted">The code is copied into the system's <code>src/</code> folder and the system is switched to use it.</p>
      <div class="row end"><button class="primary" id="ut-go">Use template</button></div>`, body => {
      $("#ut-go", body).onclick = async () => {
        const slug = $("#ut-sys", body).value;
        const r = await guard(() => post(`/api/systems/${slug}/template`, { kind, id }));
        closeModal(); toast("Template copied: " + r.copied, "ok");
        location.hash = `#/code/${slug}/${encodeURIComponent(r.copied.split("/").pop())}`;
      };
    });
  }

  // =========================================================================
  // Kernels
  // =========================================================================
  App.register("kernels", async (page, tab = "get") => {
    page.innerHTML = `<div class="page-head"><div><h1>Kernels</h1><p>The heart of an operating system. Download Linux or create your own kernel.</p></div></div>
      ${tabs([["get", "Get from internet"], ["create", "Create custom"], ["linux", "Custom Linux kernel"], ["mine", "My kernels"]], tab)}<div id="k-body"></div>`;
    const body = $("#k-body");
    const show = async t => {
      const data = await get("/api/kernels");
      if (t === "get") {
        body.innerHTML = `<div class="cols"><div class="card"><h2>Ready-to-boot kernels</h2>
          ${data.prebuilt.map(p => `<div class="item"><div class="grow"><div class="title">${esc(p.name)}</div><small>${esc(p.description)}</small></div>
          <button class="small primary" data-pre="${esc(p.id)}">⬇ Download</button></div>`).join("")}
          <h3 style="margin-top:16px">From any URL</h3><div class="row"><input id="k-url" placeholder="https://…/vmlinuz" style="flex:1"><button id="k-urlgo">Download</button></div></div>
          <div class="card"><h2>Linux source from kernel.org</h2><div id="k-rel"><div class="empty">Loading releases…</div></div></div></div>`;
        $$("[data-pre]", body).forEach(b => { b.onclick = () => startJob("/api/kernels/download", { prebuilt: b.dataset.pre }); });
        $("#k-urlgo").onclick = () => startJob("/api/kernels/download", { url: $("#k-url").value.trim() });
        try {
          const rel = await get("/api/kernels/releases");
          $("#k-rel").innerHTML = `<table class="t"><tr><th>Version</th><th>Type</th><th>Released</th><th></th></tr>${rel.map(r => `<tr>
            <td><b>${esc(r.version)}</b> ${r.latest ? `<span class="badge ok">latest</span>` : ""} ${r.eol ? `<span class="badge bad">EOL</span>` : ""}</td>
            <td>${esc(r.moniker)}</td><td>${esc(r.date)}</td><td><button class="small" data-ver="${esc(r.version)}">⬇ Source</button></td></tr>`).join("")}</table>`;
          $$("[data-ver]", body).forEach(b => { b.onclick = () => startJob("/api/kernels/download", { version: b.dataset.ver }); });
        } catch (e) { $("#k-rel").innerHTML = `<div class="empty">Could not reach kernel.org: ${esc(e.message)}</div>`; }
      } else if (t === "create") {
        body.innerHTML = `<div class="grid wide">${data.templates.map(t => `<div class="card"><h3>${esc(t.name)}</h3>
          <span class="badge accent">${esc(t.difficulty)}</span> ${t.folder ? `<span class="badge">${t.files.length} files</span>` : ""}
          <p class="muted" style="margin-top:8px">${esc(t.description)}</p><div class="row">
          <button class="small primary" data-use="${esc(t.id)}">Use in a system</button><button class="small" data-view="${esc(t.id)}">View code</button></div></div>`).join("")}</div>`;
        $$("[data-view]", body).forEach(b => { b.onclick = async () => {
          const files = await get(`/api/templates/kernels/${b.dataset.view}`);
          modal(b.dataset.view, Object.entries(files).map(([n, c]) => `<h3>${esc(n)}</h3><pre class="log" style="max-height:50vh">${esc(c)}</pre>`).join(""));
        }; });
        $$("[data-use]", body).forEach(b => { b.onclick = () => useTemplateDialog("kernels", b.dataset.use); });
      } else if (t === "linux") {
        const sources = data.downloaded.filter(d => /\.tar\.(xz|gz)$/.test(d.file));
        body.innerHTML = `<div class="cols"><div class="card"><h2>1. Choose features</h2>
          ${Object.entries(data.features).map(([k, label]) => `<label class="check"><input type="checkbox" data-feat="${k}"
            ${["base", "serial", "vga", "virtio", "storage"].includes(k) ? "checked" : ""}> ${esc(label)}</label>`).join("")}
          <div class="field" style="margin-top:10px"><label>Extra options (one CONFIG_…=y per line)</label><textarea id="lx-extra" rows="3"></textarea></div>
          <div class="field"><label>Base configuration</label><select id="lx-base"><option>tinyconfig</option><option>defconfig</option><option>allnoconfig</option></select></div></div>
          <div class="card"><h2>2. Your configuration</h2><pre class="log" id="lx-frag"></pre>
          <h2 style="margin-top:16px">3. Build</h2>
          ${sources.length ? `<div class="field"><label>Linux source (downloaded)</label><select id="lx-src">${sources.map(s => `<option value="${esc(s.path)}">${esc(s.file)}</option>`).join("")}</select></div>
            <button class="primary" id="lx-build">Build kernel</button>` : `<p class="muted">Download a Linux source tarball first (Get from internet tab).</p>`}
          <p><small>Needs make, gcc, flex, bison and bc. Building takes a few minutes with tinyconfig.</small></p>
          <pre class="log" id="lx-log" hidden></pre></div></div>`;
        const feats = () => $$("[data-feat]", body).filter(c => c.checked).map(c => c.dataset.feat);
        const refresh = async () => { $("#lx-frag").textContent = (await post("/api/kernels/config", { features: feats(), extra: $("#lx-extra").value })).config; };
        $$("[data-feat]", body).forEach(c => { c.onchange = refresh; });
        $("#lx-extra").oninput = refresh; refresh();
        if ($("#lx-build")) $("#lx-build").onclick = async () => {
          const job = await startJob("/api/kernels/build-linux", { tarball: $("#lx-src").value, features: feats(), extra: $("#lx-extra").value, base: $("#lx-base").value },
            r => { $("#lx-log").textContent += `\n\nKernel ready: ${r.image}`; });
          $("#lx-log").hidden = false;
          const tick = async () => { const j = await get("/api/jobs/" + job.id); $("#lx-log").textContent = j.message || j.error || "";
            if (j.status === "running") setTimeout(tick, 1500); };
          tick();
        };
      } else {
        body.innerHTML = `<div class="card"><h2>Downloaded kernels</h2>${downloadList(data.downloaded)}
          <p><small>Boot a prebuilt kernel: <code>hyperos kernel run vmlinuz-virt --initrd initramfs-virt</code></small></p></div>`;
      }
    };
    bindTabs(page, t => { history.replaceState(null, "", "#/kernels/" + t); show(t); });
    show(tab);
  });

  // =========================================================================
  // ISOs
  // =========================================================================
  App.register("isos", async (page, tab = "get") => {
    page.innerHTML = `<div class="page-head"><div><h1>ISOs</h1><p>Download Linux distributions, look inside them and build modified versions.</p></div></div>
      ${tabs([["get", "Get from internet"], ["local", "My ISOs"], ["projects", "Modification projects"]], tab)}<div id="i-body"></div>`;
    const body = $("#i-body");
    const show = async t => {
      const data = await get("/api/isos");
      if (t === "get") {
        body.innerHTML = `<div class="grid wide">${data.catalog.map(i => `<div class="card"><h3>${esc(i.name)} <span class="badge">${esc(i.size)}</span></h3>
          <p class="muted">${esc(i.description)}</p><button class="primary small" data-dl="${esc(i.id)}">⬇ Download latest</button></div>`).join("")}</div>
          <div class="card" style="margin-top:14px"><h3>Download from any URL</h3><div class="row"><input id="i-url" placeholder="https://…/image.iso" style="flex:2">
          <input id="i-sha" placeholder="SHA-256 (optional)" style="flex:1"><button id="i-urlgo">Download</button></div></div>`;
        $$("[data-dl]", body).forEach(b => { b.onclick = () => startJob("/api/isos/download", { id: b.dataset.dl }, () => show("local")); });
        $("#i-urlgo").onclick = () => startJob("/api/isos/download", { url: $("#i-url").value.trim(), sha256: $("#i-sha").value.trim() });
      } else if (t === "local") {
        body.innerHTML = `<div class="card">${data.local.length ? data.local.map(i => `<div class="item"><div class="grow">
          <div class="title">${esc(i.file)}</div><small>${esc(i.source)} · ${human(i.size)}</small></div>
          <button class="small" data-insp="${esc(i.path)}">Look inside</button><button class="small primary" data-mod="${esc(i.path)}">Modify</button>
          <a class="btn small" href="${fileUrl(i.path)}">Save</a></div>`).join("") : `<div class="empty">No ISOs yet. Download one or build a system.</div>`}</div>`;
        $$("[data-insp]", body).forEach(b => { b.onclick = () => inspectIso(b.dataset.insp); });
        $$("[data-mod]", body).forEach(b => { b.onclick = async () => {
          const base = b.dataset.mod.split("/").pop().replace(/\.iso$/i, "");
          const name = await App.ask("New modification project", "Project name", base + "-mod");
          if (!name) return;
          const r = await guard(() => post("/api/isos/projects", { name, source: b.dataset.mod }));
          location.hash = "#/isoproject/" + r.name;
        }; });
      } else {
        body.innerHTML = `<div class="card">${data.projects.length ? data.projects.map(p => `<div class="item"><div class="grow">
          <div class="title">${esc(p.name)}</div><small>from ${esc(p.source.split("/").pop())} · ${p.changes.added.length} added · ${p.changes.removed.length} removed</small></div>
          <a class="btn small primary" href="#/isoproject/${esc(p.name)}">Open</a></div>`).join("") : `<div class="empty">No projects. Choose “Modify” on an ISO in My ISOs.</div>`}
          <p><small>Rebuild method: ${data.xorriso ? "xorriso (keeps every boot method)" : "built-in (install xorriso to also keep USB hybrid boot)"}</small></p></div>`;
      }
    };
    bindTabs(page, t => { history.replaceState(null, "", "#/isos/" + t); show(t); });
    show(tab);
  });

  async function inspectIso(path) {
    modal("Inside " + path.split("/").pop(), `<div class="empty">Reading…</div>`);
    const info = await guard(() => post("/api/isos/inspect", { path }));
    $("#modal-body").innerHTML = `<div class="row" style="margin-bottom:10px"><span class="badge">volume ${esc(info.volume_id)}</span>
      <span class="badge">${info.file_count} files</span><span class="badge">${human(info.total_size)}</span>
      ${info.rock_ridge ? `<span class="badge">Rock Ridge</span>` : ""}${info.joliet ? `<span class="badge">Joliet</span>` : ""}
      ${info.boot.map(b => `<span class="badge ok">boot: ${esc(b.platform)} ${esc(b.emulation)}</span>`).join("") || `<span class="badge bad">not bootable</span>`}</div>
      <input id="ins-filter" placeholder="Filter files…" style="margin-bottom:8px"><div class="filetree" id="ins-tree"></div>`;
    const draw = () => {
      const f = $("#ins-filter").value.toLowerCase();
      $("#ins-tree").innerHTML = info.files.filter(x => !f || x.path.toLowerCase().includes(f)).slice(0, 800).map(x =>
        `<div class="fr"><span>${x.dir ? "📁" : "📄"}</span><span class="p">${esc(x.path)}</span><small>${x.dir ? "" : human(x.size)}</small>
         ${!x.dir && x.size < 262144 ? `<button class="small" data-view="${esc(x.path)}">View</button>` : ""}</div>`).join("");
      $$("[data-view]", $("#ins-tree")).forEach(b => { b.onclick = async () => {
        const r = await post("/api/isos/read", { path, inner: b.dataset.view });
        App.modal(b.dataset.view, `<pre class="log" style="max-height:65vh">${esc(r.binary ? "(binary file – hex)\n" + r.text : r.text)}</pre>`);
      }; });
    };
    $("#ins-filter").oninput = draw; draw();
  }

  App.register("isoproject", async (page, name) => {
    const p = await get(`/api/isos/projects/${name}`);
    const removed = new Set(p.changes.removed), added = new Set(p.changes.added);
    page.innerHTML = `<div class="page-head"><div><h1>${esc(p.name)}</h1><p>Modifying ${esc(p.source.split("/").pop())}</p></div>
      <div class="row"><button class="primary" id="ip-build">Build modified ISO</button></div></div>
      <div class="cols"><div class="card"><h2>Files</h2><input id="ip-filter" placeholder="Filter files…" style="margin-bottom:8px">
        <div class="filetree" id="ip-tree"></div></div>
      <div><div class="card"><h2>Add or replace a file</h2>
        <div class="field"><label>Path inside the ISO</label><input id="ip-path" placeholder="/hyperos/hello.txt"></div>
        <div class="field"><label>Upload a file…</label><input type="file" id="ip-file"></div>
        <div class="field"><label>…or type its content</label><textarea id="ip-text" rows="5" placeholder="Hello from my remix!"></textarea></div>
        <button id="ip-add">Add to ISO</button></div>
      <div class="card"><h2>Settings</h2><div class="field"><label>Volume label</label><input id="ip-vol" value="${esc(p.volume_id)}"></div>
        <button class="small" id="ip-volsave">Save</button>
        <h3 style="margin-top:14px">Changes</h3><div class="mono" style="font-size:12px">${[...added].map(a => `<div style="color:var(--ok)">+ ${esc(a)}</div>`).join("")}
        ${[...removed].map(a => `<div style="color:var(--bad)">- ${esc(a)}</div>`).join("") || (added.size ? "" : `<small>No changes yet.</small>`)}</div></div>
      <div class="card"><h2>Result</h2><pre class="log" id="ip-log">Not built yet.</pre><div id="ip-out" class="row" style="margin-top:8px"></div></div></div></div>`;
    const draw = () => {
      const f = $("#ip-filter").value.toLowerCase();
      $("#ip-tree").innerHTML = p.source_info.files.filter(x => !f || x.path.toLowerCase().includes(f)).slice(0, 1000).map(x => {
        const isRem = [...removed].some(r => x.path === r || x.path.startsWith(r + "/"));
        return `<div class="fr ${isRem ? "removed" : ""} ${added.has(x.path) ? "added" : ""}"><span>${x.dir ? "📁" : "📄"}</span><span class="p">${esc(x.path)}</span>
          ${!x.dir && x.size < 262144 ? `<button class="small" data-edit="${esc(x.path)}">Edit</button>` : ""}
          ${isRem ? "" : `<button class="small danger" data-rm="${esc(x.path)}">Remove</button>`}</div>`;
      }).join("");
      $$("[data-rm]", $("#ip-tree")).forEach(b => { b.onclick = async () => { await post(`/api/isos/projects/${name}/remove`, { path: b.dataset.rm }); App.route(); }; });
      $$("[data-edit]", $("#ip-tree")).forEach(b => { b.onclick = async () => {
        const r = await post("/api/isos/read", { path: p.source, inner: b.dataset.edit });
        if (r.binary) return toast("Binary files can be replaced by uploading a new file", "error");
        modal("Edit " + b.dataset.edit, `<textarea id="ed-text" rows="20" class="mono">${esc(r.text)}</textarea>
          <div class="row end" style="margin-top:10px"><button class="primary" id="ed-save">Save change</button></div>`, mb => {
          $("#ed-save", mb).onclick = async () => {
            await guard(() => post(`/api/isos/projects/${name}/file`, { path: b.dataset.edit, text: $("#ed-text", mb).value }), "Change saved");
            closeModal(); App.route();
          };
        });
      }; });
    };
    $("#ip-filter").oninput = draw; draw();
    $("#ip-add").onclick = async () => {
      const path = $("#ip-path").value.trim();
      if (!path) return toast("Enter a path inside the ISO", "error");
      const file = $("#ip-file").files[0];
      let payload = { path, text: $("#ip-text").value };
      if (file) {
        const buf = new Uint8Array(await file.arrayBuffer());
        let bin = ""; for (let i = 0; i < buf.length; i += 32768) bin += String.fromCharCode(...buf.subarray(i, i + 32768));
        payload = { path, data: btoa(bin) };
      }
      await guard(() => post(`/api/isos/projects/${name}/file`, payload), "File added");
      App.route();
    };
    $("#ip-volsave").onclick = () => guard(() => post(`/api/isos/projects/${name}/settings`, { volume_id: $("#ip-vol").value }), "Saved");
    $("#ip-build").onclick = async () => {
      $("#ip-log").textContent = "Building…";
      const job = await startJob(`/api/isos/projects/${name}/build`, {}, r => {
        $("#ip-out").innerHTML = `<a class="btn primary small" href="${fileUrl(r.iso)}">⬇ Download ${esc(r.iso.split("/").pop())}</a>
          <span class="badge">${human(r.size)} · ${esc(r.method)}</span>`;
      });
      const tick = async () => { const j = await get("/api/jobs/" + job.id); $("#ip-log").textContent = j.message || j.error || "…";
        if (j.status === "running") setTimeout(tick, 700); };
      tick();
    };
  });

  // =========================================================================
  // Resources
  // =========================================================================
  App.register("resources", async (page, tab = "browse", arg) => {
    page.innerHTML = `<div class="page-head"><div><h1>Resources</h1><p>Themes, desktop layouts, command packs, code and whole systems – made by you and the community.</p></div></div>
      ${tabs([["browse", "Browse & get"], ["installed", "Installed"], ["publish", "Publish"]], tab)}<div id="r-body"></div>`;
    const body = $("#r-body");
    const meta = await get("/api/resources");
    const typeOpts = sel => Object.entries(meta.types).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${k} – ${esc(v)}</option>`).join("");
    const show = async t => {
      if (t === "browse") {
        body.innerHTML = `<div class="row" style="margin-bottom:14px"><input id="r-q" placeholder="Search resources…" style="flex:2">
          <select id="r-type" style="flex:1"><option value="">All types</option>${typeOpts("")}</select><button class="primary" id="r-go">Search</button></div>
          <div id="r-results"><div class="empty">Searching…</div></div>`;
        const search = async () => {
          const r = await get(`/api/resources/search?q=${encodeURIComponent($("#r-q").value)}&type=${$("#r-type").value}`);
          const have = new Set((await get("/api/resources")).installed.map(x => x.id));
          $("#r-results").innerHTML = (r.results.length ? `<div class="grid wide">${r.results.map(x => `<div class="card"><div class="row">
            <h3 style="margin:0">${esc(x.name)}</h3><span class="spacer"></span><span class="badge accent">${esc(x.type)}</span></div>
            <p class="muted" style="margin:6px 0">${esc(x.description)}</p><small>v${esc(x.version)} · by ${esc(x.author)} · ${esc({ local: "my registry", bundled: "starter pack" }[x.registry] || (() => { try { return new URL(x.registry).host; } catch (e) { return x.registry; } })())}</small>
            <div class="row" style="margin-top:10px">${have.has(x.id) ? `<span class="badge ok">installed</span>` : ""}
            <button class="small primary" data-get="${esc(x.id)}" data-reg="${esc(x.registry)}">${have.has(x.id) ? "Reinstall" : "⬇ Get"}</button></div></div>`).join("")}</div>`
            : `<div class="empty">No resources found.</div>`) + r.errors.map(e => `<p><small>Registry ${esc(e.registry)} unavailable: ${esc(e.error)}</small></p>`).join("");
          $$("[data-get]", body).forEach(b => { b.onclick = async () => {
            await guard(() => post("/api/resources/get", { id: b.dataset.get, registry: b.dataset.reg }), "Installed – apply it from the Installed tab");
            search();
          }; });
        };
        $("#r-go").onclick = search; $("#r-q").onkeydown = e => { if (e.key === "Enter") search(); }; $("#r-type").onchange = search;
        search();
      } else if (t === "installed") {
        const opts = await App.systemOptions(App.currentSystem.get());
        const inst = (await get("/api/resources")).installed;
        body.innerHTML = `<div class="card">${inst.length ? inst.map(x => `<div class="item"><div class="grow"><div class="title">${esc(x.name)}
          <span class="badge accent">${esc(x.type)}</span></div><small>${esc(x.description)} · v${esc(x.version)} · by ${esc(x.author)}</small></div>
          ${x.type === "system-template" ? `<button class="small primary" data-new="${esc(x.id)}">Create system</button>`
          : `<select data-sys="${esc(x.id)}" style="width:160px">${opts}</select><button class="small primary" data-apply="${esc(x.id)}">Apply</button>`}
          <button class="small danger" data-rm="${esc(x.id)}">Remove</button></div>`).join("") : `<div class="empty">Nothing installed yet.</div>`}</div>`;
        $$("[data-apply]", body).forEach(b => { b.onclick = async () => {
          const slug = $(`[data-sys="${b.dataset.apply}"]`, body).value;
          if (!slug) return toast("Create a system first", "error");
          const r = await guard(() => post("/api/resources/apply", { id: b.dataset.apply, slug }));
          toast(`${r.note} → open the system and Build`, "ok");
        }; });
        $$("[data-new]", body).forEach(b => { b.onclick = async () => {
          const name = await App.ask("New system from template", "Name", "My " + b.dataset.new);
          if (!name) return;
          const r = await guard(() => post("/api/resources/new-system", { id: b.dataset.new, name }));
          location.hash = "#/system/" + r.slug;
        }; });
        $$("[data-rm]", body).forEach(b => { b.onclick = async () => { await del("/api/resources/installed/" + b.dataset.rm); show("installed"); }; });
      } else {
        const opts = await App.systemOptions(arg || App.currentSystem.get());
        body.innerHTML = `<div class="cols"><div class="card"><h2>What do you want to share?</h2>
          <div class="field"><label>Source</label><select id="p-src"><option value="system">Something from one of my systems</option>
            <option value="code">Code or text I type here</option><option value="file">A .hyperpkg file</option></select></div>
          <div id="p-sys"><div class="field"><label>System</label><select id="p-slug">${opts}</select></div>
            <div class="field"><label>Share as</label><select id="p-stype"><option value="ui-layout">UI layout (the desktop)</option>
            <option value="theme">Theme (just the colours)</option><option value="command-pack">Command pack</option>
            <option value="system-template">Whole system (template)</option></select></div></div>
          <div id="p-code" hidden><div class="field"><label>Type</label><select id="p-ctype">${typeOpts("snippet")}</select></div>
            <div class="field"><label>File name</label><input id="p-fname" value="snippet.asm"></div>
            <div class="field"><label>Content</label><textarea id="p-content" rows="8" class="mono"></textarea></div></div>
          <div id="p-file" hidden><div class="field"><label>Package</label><input type="file" id="p-pkg" accept=".hyperpkg,.zip"></div></div></div>
          <div class="card"><h2>Details</h2>
          <div class="field"><label>Name</label><input id="p-name" placeholder="Sunset theme"></div>
          <div class="field"><label>Description</label><textarea id="p-desc" rows="2"></textarea></div>
          <div class="cols"><div class="field"><label>Version</label><input id="p-ver" value="1.0.0"></div>
          <div class="field"><label>Tags (comma separated)</label><input id="p-tags" placeholder="retro, blue"></div></div>
          <div class="field"><label>Publish to</label><select id="p-target"><option value="local">My local registry (others can get it from my server)</option>
            ${meta.registries.map(r => `<option value="remote:${esc(r)}">${esc(r)}</option>`).join("")}<option value="file">Just download the package</option></select></div>
          <button class="primary" id="p-go">Publish</button><pre class="log" id="p-out" hidden style="margin-top:10px"></pre></div></div>`;
        const sync = () => { const v = $("#p-src").value; $("#p-sys").hidden = v !== "system"; $("#p-code").hidden = v !== "code"; $("#p-file").hidden = v !== "file"; };
        $("#p-src").onchange = sync;
        $("#p-go").onclick = async () => {
          const target = $("#p-target").value;
          const req = { name: $("#p-name").value, description: $("#p-desc").value, version: $("#p-ver").value, tags: $("#p-tags").value,
            target: target.startsWith("remote:") ? "remote" : target, registry: target.startsWith("remote:") ? target.slice(7) : undefined };
          const src = $("#p-src").value;
          if (src === "system") Object.assign(req, { slug: $("#p-slug").value, type: $("#p-stype").value });
          else if (src === "code") Object.assign(req, { type: $("#p-ctype").value, files: [{ name: $("#p-fname").value, data: $("#p-content").value }] });
          else {
            const f = $("#p-pkg").files[0]; if (!f) return toast("Choose a file", "error");
            const buf = new Uint8Array(await f.arrayBuffer()); let bin = "";
            for (let i = 0; i < buf.length; i += 32768) bin += String.fromCharCode(...buf.subarray(i, i + 32768));
            req.package = btoa(bin);
          }
          if (!req.package && !req.name) return toast("Give your resource a name", "error");
          const r = await guard(() => post("/api/resources/publish", req), "Published!");
          if (r.package) {
            const a = document.createElement("a"); a.href = "data:application/zip;base64," + r.package;
            a.download = (req.name || "resource").toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".hyperpkg"; a.click();
          }
          $("#p-out").hidden = false; $("#p-out").textContent = JSON.stringify({ ...r, package: undefined }, null, 2);
        };
        if (arg) { $("#p-src").value = "system"; $("#p-stype").value = "system-template"; }
        sync();
      }
    };
    bindTabs(page, t => { history.replaceState(null, "", "#/resources/" + t); show(t); });
    show(tab);
  });

  // =========================================================================
  // Suggestions
  // =========================================================================
  App.register("suggestions", async page => {
    page.innerHTML = `<div class="page-head"><div><h1>Feature suggestions</h1><p>Have an idea to make Hyper OS Creator better? Suggest it and vote!</p></div></div>
      <div class="cols"><div class="card"><h2>New suggestion</h2>
        <div class="field"><label>Title</label><input id="sg-title" placeholder="e.g. Mouse support in HyperKernel"></div>
        <div class="field"><label>Details</label><textarea id="sg-desc" rows="4" placeholder="What should it do? Why is it useful?"></textarea></div>
        <div class="cols"><div class="field"><label>Area</label><select id="sg-cat"></select></div>
        <div class="field"><label>Your name (optional)</label><input id="sg-author"></div></div>
        <button class="primary" id="sg-add">Submit suggestion</button></div>
      <div class="card"><div class="row" style="margin-bottom:8px"><h2 style="margin:0">Ideas</h2><span class="spacer"></span>
        <select id="sg-filter" style="width:160px"><option value="">All areas</option></select>
        <select id="sg-sort" style="width:130px"><option value="votes">Most votes</option><option value="new">Newest</option></select></div>
        <div id="sg-list"></div></div></div>`;
    const load = async () => {
      const d = await get(`/api/suggestions?sort=${$("#sg-sort").value}&category=${$("#sg-filter").value}`);
      if (!$("#sg-cat").options.length) {
        $("#sg-cat").innerHTML = d.categories.map(c => `<option>${c}</option>`).join("");
        $("#sg-filter").innerHTML += d.categories.map(c => `<option>${c}</option>`).join("");
      }
      $("#sg-list").innerHTML = d.items.length ? d.items.map(s => `<div class="item" style="align-items:flex-start">
        <div class="vote"><button class="small" data-up="${s.id}" title="Vote up">▲</button><b>${s.votes}</b><button class="small" data-down="${s.id}" title="Vote down">▼</button></div>
        <div class="grow"><div class="title">${esc(s.title)}</div><div class="row" style="margin:4px 0"><span class="badge accent">${esc(s.category)}</span>
        <span class="badge ${s.status === "done" ? "ok" : ""}">${esc(s.status)}</span><small>by ${esc(s.author)} · ${new Date(s.created * 1000).toLocaleDateString()}</small></div>
        ${s.description ? `<p class="muted" style="white-space:pre-wrap">${esc(s.description)}</p>` : ""}
        <div class="row"><button class="small" data-gh="${s.id}">Send to GitHub ↗</button>
        <select class="small" data-st="${s.id}" style="width:130px">${d.statuses.map(x => `<option ${x === s.status ? "selected" : ""}>${x}</option>`).join("")}</select>
        <button class="small danger" data-del="${s.id}">Delete</button></div></div></div>`).join("") : `<div class="empty">No suggestions yet – be the first!</div>`;
      $$("[data-up]").forEach(b => { b.onclick = async () => { await post(`/api/suggestions/${b.dataset.up}/vote`, { delta: 1 }); load(); }; });
      $$("[data-down]").forEach(b => { b.onclick = async () => { await post(`/api/suggestions/${b.dataset.down}/vote`, { delta: -1 }); load(); }; });
      $$("[data-gh]").forEach(b => { b.onclick = async () => window.open((await get(`/api/suggestions/${b.dataset.gh}/github`)).url, "_blank", "noopener"); });
      $$("[data-st]").forEach(s => { s.onchange = () => post(`/api/suggestions/${s.dataset.st}/status`, { status: s.value }).then(load); });
      $$("[data-del]").forEach(b => { b.onclick = async () => { if (confirm("Delete this suggestion?")) { await del(`/api/suggestions/${b.dataset.del}`); load(); } }; });
    };
    $("#sg-sort").onchange = load; $("#sg-filter").onchange = load;
    $("#sg-add").onclick = async () => {
      await guard(() => post("/api/suggestions", { title: $("#sg-title").value, description: $("#sg-desc").value,
        category: $("#sg-cat").value, author: $("#sg-author").value }), "Thanks for your idea!");
      $("#sg-title").value = ""; $("#sg-desc").value = ""; load();
    };
    load();
  });

  // =========================================================================
  // Console (the CLI inside the app)
  // =========================================================================
  App.register("console", async page => {
    page.innerHTML = `<div class="page-head"><div><h1>Console</h1><p>Run Hyper OS Creator commands – the same ones that work in your terminal as <code>hyperos …</code>.</p></div>
      <div class="row"><button class="small" data-ex="system list">system list</button><button class="small" data-ex="tip">tip</button>
      <button class="small" data-ex="doctor">doctor</button><button class="small" data-ex="--help">help</button></div></div>
      <div class="term" id="term"></div><div class="term-input"><span>hyperos&gt;</span><input id="term-in" autocomplete="off" spellcheck="false" placeholder="try: system preview ${esc(App.currentSystem.get() || "my-os")}"></div>`;
    const term = $("#term"), inp = $("#term-in");
    const hist = JSON.parse(localStorage.getItem("hyperos.history") || "[]");
    let hi = hist.length;
    const print = (text, cls = "") => { const d = document.createElement("div"); if (cls) d.className = cls; d.textContent = text; term.appendChild(d); term.scrollTop = term.scrollHeight; };
    print("Hyper OS Creator console. Type 'help' for all commands, 'clear' to clear. Use ↑/↓ for history.");
    const run = async line => {
      line = line.trim(); if (!line) return;
      print("hyperos> " + line, "in");
      hist.push(line); hi = hist.length; localStorage.setItem("hyperos.history", JSON.stringify(hist.slice(-100)));
      if (line === "clear") { term.innerHTML = ""; return; }
      if (line === "help") line = "--help";
      const r = await post("/api/console", { line }).catch(e => ({ output: e.message, code: 1 }));
      print(r.output || "(no output)", r.code ? "err" : "");
    };
    inp.onkeydown = e => {
      if (e.key === "Enter") { run(inp.value); inp.value = ""; }
      else if (e.key === "ArrowUp") { if (hi > 0) inp.value = hist[--hi]; e.preventDefault(); }
      else if (e.key === "ArrowDown") { inp.value = hi < hist.length - 1 ? hist[++hi] : (hi = hist.length, ""); e.preventDefault(); }
    };
    $$("[data-ex]").forEach(b => { b.onclick = () => run(b.dataset.ex); });
    inp.focus();
  });

  // =========================================================================
  // Tips + Settings
  // =========================================================================
  App.register("tips", async page => {
    const d = await get("/api/tips");
    const off = localStorage.getItem("hyperos.tips") === "off";
    page.innerHTML = `<div class="page-head"><div><h1>Tips</h1><p>Little things that make building operating systems easier.</p></div>
      <label class="check"><input type="checkbox" id="tp-on" ${off ? "" : "checked"}> Show a tip on every page</label></div>
      <div class="grid wide">${d.topics.map(t => `<div class="card"><h2 style="text-transform:capitalize">${esc(t)}</h2>
        <ul style="padding-left:18px;margin:0">${d.tips.filter(x => x.topic === t).map(x => `<li style="margin-bottom:6px">${esc(x.tip)}</li>`).join("")}</ul></div>`).join("")}</div>`;
    $("#tp-on").onchange = e => { localStorage.setItem("hyperos.tips", e.target.checked ? "on" : "off"); App.showTip(); };
  });

  App.register("settings", async page => {
    const s = await get("/api/settings");
    const st = await get("/api/status");
    page.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Workspace: <code>${esc(st.workspace)}</code></p></div></div>
      <div class="cols"><div class="card"><h2>You</h2><div class="field"><label>Author name (used when you publish resources)</label>
        <input id="st-author" value="${esc(s.author)}"></div>
        <div class="field"><label>Appearance</label><select id="st-theme"><option value="dark">Dark</option><option value="light">Light</option></select></div>
        <h2 style="margin-top:16px">Resource registries</h2><p class="muted">One URL per line. A registry is a folder with an <code>index.json</code>.
        Friends running <code>hyperos serve --host 0.0.0.0</code> share theirs at <code>http://their-computer:8642/registry</code>.</p>
        <textarea id="st-reg" rows="4" class="mono">${esc(s.registries.join("\n"))}</textarea>
        <div class="field" style="margin-top:12px"><label>GitHub repository for suggestions</label><input id="st-repo" value="${esc(s.suggestions_repo)}"></div>
        <button class="primary" id="st-save">Save settings</button></div>
      <div class="card"><h2>Tools</h2>${Object.entries(st.tools).map(([n, t]) => `<div class="item"><span class="badge ${t.found ? "ok" : "bad"}">${t.found ? "found" : "missing"}</span>
        <div class="grow"><b class="mono">${esc(n)}</b><div><small>${esc(t.purpose)}${t.path ? " · " + esc(t.path) : ""}</small></div></div></div>`).join("")}</div></div>`;
    $("#st-theme").value = localStorage.getItem("hyperos.theme") || "dark";
    $("#st-theme").onchange = e => { localStorage.setItem("hyperos.theme", e.target.value); App.applyTheme(); };
    $("#st-save").onclick = () => guard(() => put("/api/settings", { author: $("#st-author").value, suggestions_repo: $("#st-repo").value,
      registries: $("#st-reg").value.split("\n").map(x => x.trim()).filter(Boolean) }), "Settings saved");
  });
})();
