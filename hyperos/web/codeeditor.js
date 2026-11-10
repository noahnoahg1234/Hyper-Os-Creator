/* Hyper OS Creator - code editor that makes OS coding easier.
 * Syntax highlighting, autocomplete, snippets, instant reference docs,
 * auto-indent, bracket pairing, find/replace and clickable build errors. */
(() => {
  // ------------------------------------------------------------------ language data
  const X86 = {
    mov: "Copy a value: <code>mov dest, src</code>. Example: <code>mov ax, 0x1000</code>",
    int: "Call an interrupt handler, e.g. a BIOS service: <code>int 0x10</code> (video), <code>int 0x13</code> (disk), <code>int 0x16</code> (keyboard).",
    lodsb: "Load the byte at DS:SI into AL and advance SI. Perfect for walking through strings.",
    lodsw: "Load the word at DS:SI into AX and advance SI by 2.",
    stosb: "Store AL at ES:DI and advance DI.", stosw: "Store AX at ES:DI and advance DI by 2. Used to write (char, colour) pairs to VGA memory.",
    movsb: "Copy a byte from DS:SI to ES:DI.", cmpsb: "Compare the bytes at DS:SI and ES:DI.",
    rep: "Repeat the next string instruction CX times: <code>rep stosw</code> fills memory.",
    jmp: "Jump to a label. <code>jmp 0x1000:0</code> is a far jump that also sets CS.",
    je: "Jump if equal (ZF=1). Same as <code>jz</code>.", jz: "Jump if zero (ZF=1).", jne: "Jump if not equal (ZF=0).", jnz: "Jump if not zero.",
    jc: "Jump if the carry flag is set – BIOS calls set it on errors.", jnc: "Jump if no carry (success after BIOS calls).",
    ja: "Jump if above (unsigned >).", jb: "Jump if below (unsigned <).", jae: "Jump if above or equal.", jbe: "Jump if below or equal.",
    jg: "Jump if greater (signed).", jl: "Jump if less (signed).", jcxz: "Jump if CX is zero.",
    cmp: "Compare two values (subtracts without storing) and set flags for a conditional jump.",
    test: "AND two values without storing, sets flags. <code>test al, al</code> checks for zero.",
    call: "Call a subroutine (pushes the return address).", ret: "Return from a subroutine.",
    push: "Push a value on the stack.", pop: "Pop a value from the stack.", pusha: "Push all 16-bit general registers.", popa: "Pop all 16-bit general registers.",
    cli: "Clear the interrupt flag – disable hardware interrupts.", sti: "Set the interrupt flag – enable interrupts.",
    hlt: "Halt the CPU until the next interrupt. Use <code>cli</code> + <code>hlt</code> to stop forever.",
    xor: "Exclusive OR. <code>xor ax, ax</code> is the classic way to set a register to 0.",
    and: "Bitwise AND.", or: "Bitwise OR.", not: "Invert all bits.", inc: "Add 1.", dec: "Subtract 1.", add: "Add.", sub: "Subtract.",
    mul: "Unsigned multiply AX by a value (result in DX:AX).", div: "Unsigned divide DX:AX by a value (AX = quotient, DX = remainder).",
    shl: "Shift bits left (multiply by 2ⁿ).", shr: "Shift bits right (divide by 2ⁿ).",
    loop: "Decrement CX and jump if CX ≠ 0.", in: "Read from an I/O port.", out: "Write to an I/O port.",
    lgdt: "Load the Global Descriptor Table register – needed before entering protected mode.",
    cld: "Clear the direction flag so string instructions move forward.", nop: "Do nothing (1 byte).",
    lea: "Load the address of a memory operand.", movzx: "Move with zero-extension (386+).",
  };
  const DIRECTIVES = {
    org: "Tell NASM where the code will be loaded. Boot sectors use <code>org 0x7C00</code>; HyperBoot kernels use <code>org 0</code>.",
    bits: "Select 16, 32 or 64-bit code: <code>bits 16</code> for real mode.",
    db: "Define bytes: <code>db 'Hello', 0</code>", dw: "Define 16-bit words: <code>dw 0xAA55</code>", dd: "Define 32-bit double words.", dq: "Define 64-bit quad words.",
    times: "Repeat: <code>times 510-($-$$) db 0</code> pads a boot sector.", equ: "Define a constant: <code>KERNEL_SEG equ 0x1000</code>",
    align: "Pad to a multiple: <code>align 16</code>", section: "Start a section (.text, .data, .bss) for ELF output.",
    global: "Export a symbol to the linker.", extern: "Import a symbol from another file.", resb: "Reserve uninitialised bytes (in .bss).",
    incbin: "Include a binary file as data.", "%define": "Define a macro.", "%include": "Include another source file.", "%macro": "Start a multi-line macro.",
  };
  const BIOS = {
    "0x10": "<b>INT 0x10 – video</b><br>AH=0x00 set mode (AL=3 text 80×25)<br>AH=0x01 cursor shape<br>AH=0x02 set cursor (DH row, DL col)<br>AH=0x0E print AL (teletype)<br>AH=0x13 print string with colour",
    "0x13": "<b>INT 0x13 – disk</b><br>AH=0x00 reset<br>AH=0x02 read sectors: AL count, CH cylinder, CL sector, DH head, DL drive, ES:BX buffer<br>AH=0x08 get drive geometry<br>CF=1 on error",
    "0x16": "<b>INT 0x16 – keyboard</b><br>AH=0x00 wait for a key → AL = ASCII, AH = scan code<br>AH=0x01 check for a key (ZF=1 if none)",
    "0x12": "<b>INT 0x12</b> – AX = KB of conventional memory.", "0x15": "<b>INT 0x15</b> – system services (E820 memory map, A20...).",
    "0x19": "<b>INT 0x19</b> – reboot into the bootloader.", "0x1a": "<b>INT 0x1A – clock</b><br>AH=0x02 read RTC time (BCD in CH:CL:DH)",
  };
  const REGS = "al ah ax eax bl bh bx ebx cl ch cx ecx dl dh dx edx si esi di edi bp ebp sp esp cs ds es fs gs ss cr0 cr3 cr4 rax rbx rcx rdx rsi rdi rsp rbp".split(" ");
  const C_KW = "if else for while do switch case default break continue return goto sizeof typedef struct union enum static const volatile extern inline asm __asm__ unsigned signed".split(" ");
  const C_TYPES = "void char short int long float double size_t uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t int64_t bool uintptr_t".split(" ");
  const C_DOCS = { volatile: "Tells the compiler the value can change on its own – needed for hardware memory such as VGA at 0xB8000.",
    __asm__: "Inline assembly: <code>__asm__ volatile (\"hlt\");</code>", uint16_t: "16-bit unsigned integer – one VGA text cell (char + colour)." };

  const SNIPPETS = {
    asm: {
      bootsector: "bits 16\norg 0x7C00\n\nstart:\n    xor ax, ax\n    mov ds, ax\n    mov si, msg\n    call print\n.hang:\n    cli\n    hlt\n    jmp .hang\n\nprint:\n    mov ah, 0x0E\n.next:\n    lodsb\n    test al, al\n    jz .done\n    int 0x10\n    jmp .next\n.done:\n    ret\n\nmsg: db 'Hello!', 13, 10, 0\n\ntimes 510 - ($ - $$) db 0\ndw 0xAA55\n",
      print: "; print the zero terminated string at DS:SI\nprint:\n    mov ah, 0x0E\n.next:\n    lodsb\n    test al, al\n    jz .done\n    int 0x10\n    jmp .next\n.done:\n    ret\n",
      putchar: "mov ah, 0x0E        ; teletype output\nmov al, 'A'\nint 0x10\n",
      readkey: "xor ax, ax\nint 0x16            ; wait for key: al = ASCII, ah = scan code\n",
      cls: "mov ax, 0x0003      ; 80x25 text mode, clears the screen\nint 0x10\n",
      halt: ".hang:\n    cli\n    hlt\n    jmp .hang\n",
      loop: "mov cx, 10\n.again:\n    ; body\n    loop .again\n",
      func: "my_function:\n    pusha\n    ; your code here\n    popa\n    ret\n",
      vga: "push es\nmov ax, 0xB800       ; VGA text memory\nmov es, ax\nmov di, (12 * 80 + 30) * 2 ; row 12, column 30\nmov ax, 0x1F41      ; colour 0x1F, char 'A'\nstosw\npop es\n",
      readdisk: "mov ah, 0x02         ; read sectors\nmov al, 1            ; how many\nmov ch, 0            ; cylinder\nmov cl, 2            ; sector (1 based)\nmov dh, 0            ; head\n; dl = drive (keep the value the BIOS gave you)\nmov bx, 0x1000\nmov es, bx\nxor bx, bx           ; es:bx = buffer\nint 0x13\njc disk_error\n",
      pad: "times 510 - ($ - $$) db 0\ndw 0xAA55\n",
      string: "msg: db 'Hello, world!', 13, 10, 0\n",
    },
    c: {
      main: "void kernel_main(void) {\n    \n}\n", vga: "volatile uint16_t *vga = (uint16_t *)0xB8000;\nvga[0] = (uint16_t)0x1F << 8 | 'A';\n",
      for: "for (int i = 0; i < 10; i++) {\n    \n}\n", halt: "for (;;) __asm__ volatile (\"hlt\");\n",
      outb: "static inline void outb(uint16_t port, uint8_t v) {\n    __asm__ volatile (\"outb %0, %1\" : : \"a\"(v), \"Nd\"(port));\n}\n",
      inb: "static inline uint8_t inb(uint16_t port) {\n    uint8_t v;\n    __asm__ volatile (\"inb %1, %0\" : \"=a\"(v) : \"Nd\"(port));\n    return v;\n}\n",
    },
  };

  const langOf = name => /\.(asm|s|inc|nasm)$/i.test(name) ? "asm" : /\.(c|h|cpp|hpp)$/i.test(name) ? "c" : /\.json$/i.test(name) ? "json" : /makefile|\.mk$/i.test(name) ? "make" : /\.ld$/i.test(name) ? "c" : "text";

  // ------------------------------------------------------------------ highlighter
  const span = (cls, t) => `<span class="tk-${cls}">${esc(t)}</span>`;
  function hlAsm(line) {
    let out = "", i = 0;
    const m = line.match(/^(\s*)([.\w$@]+:)/);
    if (m) { out += esc(m[1]) + span("lbl", m[2]); i = m[0].length; }
    const re = /(;.*$)|('[^']*'?|"[^"]*"?|`[^`]*`?)|(\b0x[0-9a-f]+\b|\b[0-9][0-9a-f]*h\b|\b[01]+b\b|\b\d+\b|\$\$?)|(%?[A-Za-z_.][\w.]*)/gi;
    re.lastIndex = i;
    let last = i, t;
    while ((t = re.exec(line))) {
      out += esc(line.slice(last, t.index));
      if (t[1]) out += span("com", t[1]);
      else if (t[2]) out += span("str", t[2]);
      else if (t[3]) out += span("num", t[3]);
      else {
        const w = t[4].toLowerCase();
        out += X86[w] || /^j[a-z]+$/.test(w) ? span("kw", t[4]) : REGS.includes(w) ? span("reg", t[4])
          : DIRECTIVES[w] || w.startsWith("%") ? span("dir", t[4]) : esc(t[4]);
      }
      last = re.lastIndex;
    }
    return out + esc(line.slice(last));
  }
  function hlC(code) {
    const re = /(\/\*[\s\S]*?\*\/|\/\/.*$)|("(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?)|(^\s*#\s*\w+)|(\b0x[0-9a-f]+\w*\b|\b\d+\w*\b)|([A-Za-z_]\w*)/gim;
    let out = "", last = 0, t;
    while ((t = re.exec(code))) {
      out += esc(code.slice(last, t.index));
      if (t[1]) out += t[1].split("\n").map(x => span("com", x)).join("\n");
      else if (t[2]) out += span("str", t[2]);
      else if (t[3]) out += span("pp", t[3]);
      else if (t[4]) out += span("num", t[4]);
      else out += C_KW.includes(t[5]) ? span("kw", t[5]) : C_TYPES.includes(t[5]) ? span("type", t[5]) : esc(t[5]);
      last = re.lastIndex;
    }
    return out + esc(code.slice(last));
  }
  function hlJson(code) {
    return esc(code).replace(/(&quot;(?:\\.|[^&\\]|&(?!quot;))*?&quot;)(\s*:)?|\b(-?\d+(?:\.\d+)?|true|false|null)\b/g,
      (m, s, colon, n) => s ? `<span class="tk-${colon ? "kw" : "str"}">${s}</span>${colon || ""}` : `<span class="tk-num">${n}</span>`);
  }
  function hlMake(line) {
    if (/^\s*#/.test(line)) return span("com", line);
    const m = line.match(/^([\w.\-%$() ]+)(:)(.*)$/);
    if (m && !line.startsWith("\t")) return span("lbl", m[1]) + m[2] + esc(m[3]);
    return esc(line).replace(/\$\([^)]*\)|\$[@<^]/g, x => `<span class="tk-reg">${x}</span>`);
  }
  function highlight(code, lang, errLines) {
    let html;
    if (lang === "asm") html = code.split("\n").map(hlAsm);
    else if (lang === "c") html = hlC(code).split("\n");
    else if (lang === "json") html = hlJson(code).split("\n");
    else if (lang === "make") html = code.split("\n").map(hlMake);
    else html = code.split("\n").map(esc);
    return html.map((l, i) => errLines.has(i + 1) ? `<span class="ce-line-err">${l || " "}</span>` : l).join("\n") + "\n";
  }

  // ------------------------------------------------------------------ page
  App.register("code", async (page, slug, fileArg) => {
    const systems = await App.get("/api/systems");
    if (!systems.length) {
      page.innerHTML = `<div class="card empty"><h2>No systems yet</h2><p>Create a system first – its source code lives in its <code>src/</code> folder.</p>
        <a class="btn primary" href="#/systems">Go to My Systems</a></div>`;
      return;
    }
    slug = slug || App.currentSystem.get();
    if (!systems.some(s => s.slug === slug)) slug = systems[0].slug;
    App.currentSystem.set(slug);
    page.className = "full";
    page.innerHTML = `
      <div class="ce">
        <div class="ce-side card" style="padding:12px">
          <select id="ce-sys" style="margin-bottom:10px">${systems.map(s => `<option value="${esc(s.slug)}" ${s.slug === slug ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
          <div class="row" style="margin-bottom:6px"><b>Files</b><span class="spacer"></span><button class="small" id="ce-new" title="New file">+ New</button></div>
          <div class="ce-files" id="ce-files"></div>
          <div class="row" style="margin:14px 0 6px"><b>Templates</b></div><div class="ce-files" id="ce-tpl"></div>
        </div>
        <div class="ce-main">
          <div class="ce-bar"><span class="fname" id="ce-fname">–</span><span class="badge" id="ce-lang"></span><span class="badge" id="ce-dirty" hidden>unsaved</span>
            <span class="spacer"></span><button class="small" id="ce-find-btn" title="Ctrl+F">Find</button><button class="small" id="ce-save" title="Ctrl+S">Save</button>
            <button class="small" id="ce-check" title="Ctrl+B">Check / assemble</button><button class="small" id="ce-bootlib" title="Save as a stand-alone boot sector in your library">→ Library</button>
            <button class="small primary" id="ce-build">Build system</button><button class="small" id="ce-run">▶ Run</button></div>
          <div class="ce-find" id="ce-findbar" hidden><input id="ce-q" placeholder="Find"><input id="ce-r" placeholder="Replace with">
            <button class="small" id="ce-fprev">↑</button><button class="small" id="ce-fnext">↓</button><button class="small" id="ce-rep">Replace</button>
            <button class="small" id="ce-repall">All</button><button class="small" id="ce-fclose">✕</button></div>
          <div class="ce-editor"><div class="ce-gutter" id="ce-gutter"></div>
            <div class="ce-area"><pre id="ce-hl"></pre><textarea id="ce-ta" spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off"></textarea>
            <div class="ce-pop" id="ce-pop" hidden></div></div></div>
          <div class="ce-bottom"><div class="tabs" style="margin-bottom:6px"><button data-bt="problems" class="active">Problems</button>
            <button data-bt="output">Output</button><button data-bt="hex">Binary</button><span class="spacer"></span>
            <small id="ce-pos" style="align-self:center">Ln 1, Col 1</small></div>
            <div id="ce-problems" class="log" style="flex:1;overflow:auto"><small class="muted">Press “Check” (Ctrl+B) to assemble and find mistakes.</small></div>
            <pre class="log" id="ce-output" hidden></pre><pre class="log" id="ce-hex" hidden></pre></div>
        </div>
        <div class="ce-ref card" style="padding:12px"><h3>Reference</h3><div id="ce-ref" class="ref-box"><p class="muted">Put the cursor on an instruction,
          register or <code>int</code> number to see what it does.</p></div>
          <h3 style="margin-top:14px">Snippets</h3><p class="muted" style="font-size:12px">Type the name and press Tab, or click to insert.</p><div id="ce-snips"></div>
          <h3 style="margin-top:14px">Shortcuts</h3><div style="font-size:12px" class="muted">Ctrl+Space suggestions · Tab indent/snippet · Shift+Tab outdent ·
          Ctrl+/ comment · Ctrl+S save · Ctrl+B check · Ctrl+F find · Ctrl+D duplicate line</div></div>
      </div>`;

    const ta = $("#ce-ta"), hl = $("#ce-hl"), gutter = $("#ce-gutter"), pop = $("#ce-pop");
    let file = null, lang = "text", saved = "", errLines = new Set(), errors = [];
    let popItems = [], popSel = 0;

    // ---- rendering
    const render = () => {
      hl.innerHTML = highlight(ta.value, lang, errLines);
      const n = ta.value.split("\n").length, cur = ta.value.slice(0, ta.selectionStart).split("\n").length;
      let g = "";
      for (let i = 1; i <= n; i++) g += `<div class="${errLines.has(i) ? "err" : ""} ${i === cur ? "cur" : ""}">${i}</div>`;
      gutter.innerHTML = g;
      syncScroll();
      $("#ce-dirty").hidden = ta.value === saved;
    };
    const syncScroll = () => { hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; gutter.scrollTop = ta.scrollTop; };
    ta.addEventListener("scroll", () => { syncScroll(); pop.hidden = true; });

    const caretInfo = () => {
      const before = ta.value.slice(0, ta.selectionStart), lines = before.split("\n");
      return { line: lines.length, col: lines[lines.length - 1].length + 1 };
    };
    const updateStatus = () => {
      const { line, col } = caretInfo();
      $("#ce-pos").textContent = `Ln ${line}, Col ${col}`;
      const w = wordAt(ta.selectionStart);
      showRef(w);
      $$("div", gutter).forEach((d, i) => d.classList.toggle("cur", i + 1 === line));
    };
    const wordAt = pos => {
      const v = ta.value;
      let s = pos, e = pos;
      while (s > 0 && /[\w.%]/.test(v[s - 1])) s--;
      while (e < v.length && /[\w.%]/.test(v[e])) e++;
      return v.slice(s, e);
    };
    const showRef = word => {
      const w = (word || "").toLowerCase();
      const line = ta.value.slice(0, ta.selectionStart).split("\n").pop() + ta.value.slice(ta.selectionStart).split("\n")[0];
      let html = null;
      const intm = line.match(/\bint\s+(0x[0-9a-f]+|\d+)/i);
      if (intm && (w === "int" || w === intm[1].toLowerCase())) {
        const key = intm[1].toLowerCase().startsWith("0x") ? intm[1].toLowerCase() : "0x" + (+intm[1]).toString(16);
        html = BIOS[key] ? `<div class="ref-word">int ${key}</div><p>${BIOS[key]}</p>` : null;
      }
      if (!html && lang === "asm") {
        if (X86[w]) html = `<div class="ref-word">${esc(w)}</div><p>${X86[w]}</p>`;
        else if (DIRECTIVES[w]) html = `<div class="ref-word">${esc(w)}</div><p>${DIRECTIVES[w]}</p>`;
        else if (REGS.includes(w)) html = `<div class="ref-word">${esc(w)}</div><p>A CPU register.
          ${{ si: "Source index – used by lodsb/movsb.", di: "Destination index – used by stosb/stosw.", cx: "Counter – used by loop and rep.",
             dl: "The BIOS puts the boot drive number here when your boot sector starts.", es: "Extra segment – destination for stosb/stosw.",
             ds: "Data segment – where memory reads come from.", cs: "Code segment.", ss: "Stack segment.", sp: "Stack pointer.",
             ax: "Accumulator – most BIOS calls use AH/AL.", cr0: "Control register 0 – bit 0 turns on protected mode." }[w] || ""}</p>`;
      }
      if (!html && lang === "c" && C_DOCS[word]) html = `<div class="ref-word">${esc(word)}</div><p>${C_DOCS[word]}</p>`;
      if (html) $("#ce-ref").innerHTML = html;
    };

    // ---- editing helpers (execCommand keeps the browser's undo history)
    const insert = text => { ta.focus(); if (!document.execCommand("insertText", false, text)) {
      const s = ta.selectionStart; ta.setRangeText(text, s, ta.selectionEnd, "end"); } render(); };
    const lineRange = () => {
      const v = ta.value, s = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
      let e = v.indexOf("\n", Math.max(ta.selectionEnd - (ta.selectionEnd > ta.selectionStart && v[ta.selectionEnd - 1] === "\n" ? 1 : 0), ta.selectionStart));
      if (e < 0) e = v.length;
      return [s, e];
    };
    const transformLines = fn => {
      const [s, e] = lineRange();
      const text = ta.value.slice(s, e).split("\n").map(fn).join("\n");
      ta.setSelectionRange(s, e);
      insert(text);
      ta.setSelectionRange(s, s + text.length);
    };
    const toggleComment = () => {
      const c = langOf(file || "") === "c" ? "// " : langOf(file || "") === "make" ? "# " : "; ";
      const [s, e] = lineRange();
      const lines = ta.value.slice(s, e).split("\n");
      const all = lines.filter(l => l.trim()).every(l => l.trim().startsWith(c.trim()));
      transformLines(l => all ? l.replace(new RegExp("^(\\s*)" + c.trim().replace(/[/#]/g, "\\$&") + " ?"), "$1") : (l.trim() ? c + l : l));
    };

    // ---- autocomplete
    const candidates = prefix => {
      const p = prefix.toLowerCase(), set = new Map();
      const add = (w, kind) => { if (w.toLowerCase().startsWith(p) && w.toLowerCase() !== p && !set.has(w)) set.set(w, kind); };
      Object.keys(SNIPPETS[lang] || {}).forEach(w => add(w, "snippet"));
      (ta.value.match(/^\s*([A-Za-z_.][\w.]*):/gm) || []).forEach(l => add(l.trim().slice(0, -1), "label"));
      if (lang === "asm") { Object.keys(X86).forEach(w => add(w, "instr")); Object.keys(DIRECTIVES).forEach(w => add(w, "directive")); REGS.forEach(w => add(w, "register")); }
      if (lang === "c") { C_KW.forEach(w => add(w, "keyword")); C_TYPES.forEach(w => add(w, "type")); (ta.value.match(/\b[a-z_]\w{3,}(?=\s*\()/gi) || []).forEach(w => add(w, "function")); }
      return [...set].slice(0, 30);
    };
    const showPop = force => {
      const pos = ta.selectionStart, v = ta.value;
      let s = pos; while (s > 0 && /[\w.%]/.test(v[s - 1])) s--;
      const prefix = v.slice(s, pos);
      if (!force && prefix.length < 2) { pop.hidden = true; return; }
      popItems = candidates(prefix);
      if (!popItems.length) { pop.hidden = true; return; }
      popSel = 0;
      const { line, col } = caretInfo();
      const lh = 21, cw = measureChar();
      pop.style.top = (10 + line * lh - ta.scrollTop + 2) + "px";
      pop.style.left = Math.max(0, 14 + (col - 1 - prefix.length) * cw - ta.scrollLeft) + "px";
      drawPop();
      pop.hidden = false;
      pop.dataset.start = s;
    };
    const drawPop = () => {
      pop.innerHTML = popItems.map(([w, k], i) => `<div class="${i === popSel ? "sel" : ""}" data-i="${i}">${esc(w)}<small>${k}</small></div>`).join("");
      $$("div", pop).forEach(d => { d.onmousedown = ev => { ev.preventDefault(); popSel = +d.dataset.i; acceptPop(); }; });
      const selEl = pop.children[popSel]; if (selEl) selEl.scrollIntoView({ block: "nearest" });
    };
    const acceptPop = () => {
      const [w, kind] = popItems[popSel];
      ta.setSelectionRange(+pop.dataset.start, ta.selectionStart);
      pop.hidden = true;
      if (kind === "snippet") expandSnippet(w, true); else insert(w);
    };
    let charW = 0;
    const measureChar = () => {
      if (charW) return charW;
      const s = document.createElement("span"); s.textContent = "x".repeat(100); s.style.font = getComputedStyle(ta).font;
      s.style.position = "absolute"; s.style.visibility = "hidden"; document.body.appendChild(s);
      charW = s.getBoundingClientRect().width / 100; document.body.removeChild(s); return charW;
    };
    const expandSnippet = (name, selected) => {
      const sn = (SNIPPETS[lang] || {})[name];
      if (!sn) return false;
      if (!selected) ta.setSelectionRange(ta.selectionStart - name.length, ta.selectionStart);
      const indent = (ta.value.slice(0, ta.selectionStart).split("\n").pop().match(/^\s*/) || [""])[0];
      insert(sn.replace(/\n(?!$)/g, "\n" + indent).replace(/\n$/, ""));
      return true;
    };

    // ---- keyboard
    ta.addEventListener("keydown", ev => {
      const ctrl = ev.ctrlKey || ev.metaKey, k = ev.key;
      if (!pop.hidden) {
        if (k === "ArrowDown") { ev.preventDefault(); popSel = (popSel + 1) % popItems.length; drawPop(); return; }
        if (k === "ArrowUp") { ev.preventDefault(); popSel = (popSel - 1 + popItems.length) % popItems.length; drawPop(); return; }
        if (k === "Enter" || k === "Tab") { ev.preventDefault(); acceptPop(); return; }
        if (k === "Escape") { pop.hidden = true; return; }
      }
      if (ctrl && k === " ") { ev.preventDefault(); showPop(true); return; }
      if (ctrl && k.toLowerCase() === "s") { ev.preventDefault(); save(); return; }
      if (ctrl && k.toLowerCase() === "b") { ev.preventDefault(); check(); return; }
      if (ctrl && k.toLowerCase() === "f") { ev.preventDefault(); openFind(); return; }
      if (ctrl && k === "/") { ev.preventDefault(); toggleComment(); return; }
      if (ctrl && k.toLowerCase() === "d") { ev.preventDefault(); const [s, e] = lineRange(); const t = ta.value.slice(s, e);
        ta.setSelectionRange(e, e); insert("\n" + t); return; }
      if (k === "Tab") {
        ev.preventDefault();
        if (ta.selectionStart !== ta.selectionEnd && ta.value.slice(ta.selectionStart, ta.selectionEnd).includes("\n")) {
          transformLines(l => ev.shiftKey ? l.replace(/^( {1,4}|\t)/, "") : "    " + l); return;
        }
        if (ev.shiftKey) { transformLines(l => l.replace(/^( {1,4}|\t)/, "")); return; }
        const w = wordAt(ta.selectionStart);
        if (ta.value.slice(0, ta.selectionStart).endsWith(w) && expandSnippet(w, false)) return;
        insert("    "); return;
      }
      if (k === "Enter" && !ctrl) {
        ev.preventDefault();
        const line = ta.value.slice(0, ta.selectionStart).split("\n").pop();
        let indent = (line.match(/^\s*/) || [""])[0];
        const t = line.trim();
        if (lang === "asm" && /^[\w.]+:$/.test(t)) indent = "    ";
        if ((lang === "c" || lang === "json") && /[{[(]$/.test(t)) {
          const next = ta.value[ta.selectionStart];
          if ("}])".includes(next || "x")) { insert("\n" + indent + "    \n" + indent); ta.setSelectionRange(ta.selectionStart - indent.length - 1, ta.selectionStart - indent.length - 1); return; }
          indent += "    ";
        }
        insert("\n" + indent); return;
      }
      const pairs = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'" };
      if (pairs[k] && !ctrl) {
        const next = ta.value[ta.selectionStart];
        if ((k === '"' || k === "'") && next === k) { ev.preventDefault(); ta.setSelectionRange(ta.selectionStart + 1, ta.selectionStart + 1); return; }
        if (lang === "asm" && k === "'" && /\w/.test(ta.value[ta.selectionStart - 1] || "")) return;
        if (!next || /[\s)\]},;]/.test(next)) {
          ev.preventDefault();
          const sel = ta.value.slice(ta.selectionStart, ta.selectionEnd);
          insert(k + sel + pairs[k]); ta.setSelectionRange(ta.selectionStart - 1, ta.selectionStart - 1); return;
        }
      }
      if (")]}".includes(k) && k && ta.value[ta.selectionStart] === k) { ev.preventDefault(); ta.setSelectionRange(ta.selectionStart + 1, ta.selectionStart + 1); return; }
      if (k === "Backspace" && ta.selectionStart === ta.selectionEnd) {
        const p = ta.value[ta.selectionStart - 1], n = ta.value[ta.selectionStart];
        if (pairs[p] && pairs[p] === n) { ev.preventDefault(); ta.setSelectionRange(ta.selectionStart - 1, ta.selectionStart + 1); insert(""); }
      }
    });
    ta.addEventListener("input", ev => { render(); if (ev.inputType === "insertText" && /[\w.%]/.test(ev.data || "")) showPop(false); else if (ev.inputType !== "insertText") pop.hidden = true; });
    ["click", "keyup"].forEach(t => ta.addEventListener(t, ev => { if (!(t === "keyup" && ["ArrowDown", "ArrowUp"].includes(ev.key) && !pop.hidden)) updateStatus(); }));
    ta.addEventListener("blur", () => setTimeout(() => { pop.hidden = true; }, 150));

    // ---- find & replace
    const openFind = () => { $("#ce-findbar").hidden = false; const s = ta.value.slice(ta.selectionStart, ta.selectionEnd);
      if (s && !s.includes("\n")) $("#ce-q").value = s; $("#ce-q").focus(); $("#ce-q").select(); };
    const find = back => {
      const q = $("#ce-q").value; if (!q) return false;
      const v = ta.value.toLowerCase(), ql = q.toLowerCase();
      let i = back ? v.lastIndexOf(ql, ta.selectionStart - 1) : v.indexOf(ql, ta.selectionEnd);
      if (i < 0) i = back ? v.lastIndexOf(ql) : v.indexOf(ql);
      if (i < 0) { App.toast("Not found"); return false; }
      ta.focus(); ta.setSelectionRange(i, i + q.length);
      const line = ta.value.slice(0, i).split("\n").length;
      ta.scrollTop = Math.max(0, (line - 5) * 21); updateStatus(); return true;
    };
    $("#ce-find-btn").onclick = openFind;
    $("#ce-fnext").onclick = () => find(false); $("#ce-fprev").onclick = () => find(true);
    $("#ce-q").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); find(e.shiftKey); } if (e.key === "Escape") $("#ce-findbar").hidden = true; };
    $("#ce-fclose").onclick = () => { $("#ce-findbar").hidden = true; ta.focus(); };
    $("#ce-rep").onclick = () => { const q = $("#ce-q").value; if (ta.value.slice(ta.selectionStart, ta.selectionEnd).toLowerCase() === q.toLowerCase() && q) insert($("#ce-r").value); find(false); };
    $("#ce-repall").onclick = () => { const q = $("#ce-q").value; if (!q) return;
      const n = ta.value.split(q).length - 1; ta.setSelectionRange(0, ta.value.length); insert(ta.value.split(q).join($("#ce-r").value)); App.toast(`Replaced ${n}`); };

    // ---- bottom panel
    const showBottom = t => { $$("[data-bt]").forEach(b => b.classList.toggle("active", b.dataset.bt === t));
      $("#ce-problems").hidden = t !== "problems"; $("#ce-output").hidden = t !== "output"; $("#ce-hex").hidden = t !== "hex"; };
    $$("[data-bt]").forEach(b => { b.onclick = () => showBottom(b.dataset.bt); });
    const gotoLine = n => {
      const lines = ta.value.split("\n"); let pos = 0;
      for (let i = 0; i < n - 1 && i < lines.length; i++) pos += lines[i].length + 1;
      ta.focus(); ta.setSelectionRange(pos, pos + (lines[n - 1] || "").length);
      ta.scrollTop = Math.max(0, (n - 6) * 21); syncScroll(); updateStatus();
    };
    const showProblems = (list, okText) => {
      errors = list; errLines = new Set(list.filter(e => e.kind !== "warning").map(e => e.line));
      $("#ce-problems").innerHTML = list.length ? list.map((e, i) => `<div class="ce-problem" data-pi="${i}"><span class="k ${esc(e.kind)}">${esc(e.kind)}</span>
        line ${e.line}: ${esc(e.message)}</div>`).join("") : `<span style="color:var(--ok)">✓ ${esc(okText || "No problems found")}</span>`;
      $$("[data-pi]").forEach(d => { d.onclick = () => gotoLine(errors[+d.dataset.pi].line); });
      render();
    };

    // ---- files
    const loadFiles = async () => {
      const files = await App.get(`/api/systems/${slug}/files`);
      $("#ce-files").innerHTML = files.map(f => `<div class="f ${f.name === file ? "sel" : ""}" data-f="${esc(f.name)}">
        <span>${langOf(f.name) === "asm" ? "⚙" : langOf(f.name) === "c" ? "©" : "📄"}</span><span>${esc(f.name)}</span></div>`).join("") || `<small class="muted">No files</small>`;
      $$("[data-f]").forEach(d => { d.onclick = () => openFile(d.dataset.f); });
      return files;
    };
    const openFile = async name => {
      if (file && ta.value !== saved && !confirm("Discard unsaved changes?")) return;
      const r = await App.guard(() => App.get(`/api/systems/${slug}/file?name=${encodeURIComponent(name)}`));
      file = name; lang = langOf(name); saved = r.content;
      ta.value = r.content; ta.scrollTop = 0; ta.setSelectionRange(0, 0);
      $("#ce-fname").textContent = name; $("#ce-lang").textContent = { asm: "NASM assembly", c: "C", json: "JSON", make: "Makefile", text: "Text" }[lang];
      $("#ce-snips").innerHTML = Object.keys(SNIPPETS[lang] || {}).map(s => `<div class="snip" data-s="${s}">${s}</div>`).join("") || `<small class="muted">None for this language.</small>`;
      $$("[data-s]").forEach(d => { d.onclick = () => { ta.focus(); expandSnippet(d.dataset.s, true); }; });
      $("#ce-check").disabled = lang !== "asm"; $("#ce-bootlib").disabled = lang !== "asm";
      showProblems([], "Ready"); loadFiles(); updateStatus();
      history.replaceState(null, "", `#/code/${slug}/${encodeURIComponent(name)}`);
    };
    const save = async () => {
      if (!file) return;
      await App.guard(() => App.put(`/api/systems/${slug}/file`, { name: file, content: ta.value }), "Saved " + file);
      saved = ta.value; render();
    };
    const check = async () => {
      if (lang !== "asm") return App.toast("Only assembly files can be checked here – C kernels build with their Makefile.");
      const r = await App.post("/api/assemble", { source: ta.value });
      $("#ce-output").textContent = r.log;
      if (r.ok) {
        const notes = [];
        if (/org\s+0x7c00/i.test(ta.value)) {
          if (r.size !== 512) notes.push({ line: 1, kind: "warning", message: `a boot sector must be 512 bytes, this is ${r.size}` });
          else if (!r.boot_signature) notes.push({ line: 1, kind: "warning", message: "missing the 0xAA55 boot signature at the end" });
        }
        showProblems(r.errors.concat(notes), `Assembled OK – ${r.size} bytes${r.boot_signature ? " · valid boot sector" : ""}`);
        const hex = r.hex.match(/.{1,32}/g) || [];
        $("#ce-hex").textContent = hex.map((l, i) => (i * 16).toString(16).padStart(4, "0") + "  " + l.match(/../g).join(" ")).join("\n")
          + (r.size > 1024 ? `\n… ${r.size - 1024} more bytes` : "");
      } else { showProblems(r.errors.length ? r.errors : [{ line: 1, kind: "error", message: r.log }]); }
      showBottom("problems");
      return r;
    };
    $("#ce-save").onclick = save; $("#ce-check").onclick = check;
    $("#ce-bootlib").onclick = async () => {
      const r = await App.post("/api/bootloaders/build", { source: ta.value, name: file.replace(/\.\w+$/, "") });
      $("#ce-output").textContent = r.log + (r.warnings ? "\n" + r.warnings.join("\n") : "") + (r.path ? `\nSaved ${r.path}` : "");
      showBottom("output"); App.toast(r.ok ? "Boot sector saved to your library" : "Saved with warnings – see Output", r.ok ? "ok" : "error");
    };
    $("#ce-build").onclick = async () => {
      await save();
      const r = await App.post(`/api/systems/${slug}/build`);
      $("#ce-output").textContent = r.log; showBottom("output");
      if (!r.ok && r.errors && r.errors.length) { showProblems(r.errors); showBottom("problems"); }
      App.toast(r.ok ? "System built!" : "Build failed", r.ok ? "ok" : "error");
      return r;
    };
    $("#ce-run").onclick = async () => { const r = await $("#ce-build").onclick(); if (r && r.ok) App.guard(() => App.post(`/api/systems/${slug}/run`), "QEMU started").catch(() => {}); };
    $("#ce-new").onclick = async () => {
      const name = await App.ask("New file", "File name (e.g. drivers.asm, notes.txt)", "new.asm");
      if (!name) return;
      await App.guard(() => App.put(`/api/systems/${slug}/file`, { name, content: langOf(name) === "asm" ? "; " + name + "\nbits 16\n\n" : "" }));
      await loadFiles(); openFile(name);
    };
    $("#ce-sys").onchange = e => { location.hash = "#/code/" + e.target.value; };

    // templates
    const tpls = [...(await App.get("/api/templates/bootloaders")).map(t => ({ ...t, kind: "bootloaders" })),
                  ...(await App.get("/api/templates/kernels")).map(t => ({ ...t, kind: "kernels" }))];
    $("#ce-tpl").innerHTML = tpls.map((t, i) => `<div class="f" data-t="${i}" title="${esc(t.description)}"><span>${t.kind === "kernels" ? "◎" : "⏻"}</span><span>${esc(t.name)}</span></div>`).join("");
    $$("[data-t]").forEach(d => { d.onclick = async () => {
      const t = tpls[+d.dataset.t];
      if (!confirm(`Copy “${t.name}” into this system${t.folder ? "" : " and use it"}?`)) return;
      const r = await App.guard(() => App.post(`/api/systems/${slug}/template`, { kind: t.kind, id: t.id }));
      await loadFiles();
      const name = t.folder ? `${t.id}/kernel.c` : r.copied;
      file = null; openFile(name);
    }; });

    const files = await loadFiles();
    const first = fileArg && files.some(f => f.name === fileArg) ? fileArg : (files.find(f => f.name === "kernel.asm") || files[0] || {}).name;
    if (first) await openFile(first); else render();
    const beforeUnload = ev => { if (file && ta.value !== saved) { ev.preventDefault(); ev.returnValue = ""; } };
    window.addEventListener("beforeunload", beforeUnload);
    App.cleanup = () => window.removeEventListener("beforeunload", beforeUnload);
  });
})();
