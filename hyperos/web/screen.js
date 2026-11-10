/* Text-mode screen model shared by the UI editor and previews.
 * Mirrors hyperos/system.py (encode_ui/render_desktop) and HyperKernel. */
const Screen = (() => {
  const W = 80, H = 25;
  const PALETTE = ["#000000", "#0000aa", "#00aa00", "#00aaaa", "#aa0000", "#aa00aa", "#aa5500", "#aaaaaa",
                   "#555555", "#5555ff", "#55ff55", "#55ffff", "#ff5555", "#ff55ff", "#ffff55", "#ffffff"];
  const NAMES = ["black", "blue", "green", "cyan", "red", "magenta", "brown", "light gray", "dark gray",
                 "light blue", "light green", "light cyan", "light red", "light magenta", "yellow", "white"];
  // tl, tr, bl, br, horizontal, vertical
  const STYLES = {
    single: ["┌", "┐", "└", "┘", "─", "│"], double: ["╔", "╗", "╚", "╝", "═", "║"],
    block: ["█", "█", "█", "█", "█", "█"], ascii: ["+", "+", "+", "+", "-", "|"], none: [" ", " ", " ", " ", " ", " "],
  };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(Number(v) || 0)));
  const attr = (fg, bg) => ((bg & 15) << 4) | (fg & 15);

  function geometry(el) {
    const x = clamp(el.x, 0, W - 1), y = clamp(el.y, 0, H - 1);
    if (el.type === "box") {
      return { x, y, w: Math.max(2, Math.min(W - x, Math.round(Number(el.w) || 10))),
               h: Math.max(2, Math.min(H - y, Math.round(Number(el.h) || 5))) };
    }
    if (el.type === "text") return { x, y, w: Math.max(1, Math.min(W - x, [...String(el.text || "")].length)), h: 1 };
    return { x: 0, y: 0, w: W, h: H };
  }

  function render(elements) {
    let grid = blank(0x07);
    const put = (x, y, ch, a) => { if (x >= 0 && x < W && y >= 0 && y < H) grid[y][x] = { ch, a }; };
    for (const el of elements || []) {
      const a = attr(el.fg ?? 7, el.bg ?? 0);
      if (el.type === "fill") grid = blank(a);
      else if (el.type === "box") {
        const { x, y, w, h } = geometry(el);
        const s = STYLES[el.style] || STYLES.single;
        for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) {
          let ch;
          if (r === 0) ch = c === 0 ? s[0] : c === w - 1 ? s[1] : s[4];
          else if (r === h - 1) ch = c === 0 ? s[2] : c === w - 1 ? s[3] : s[4];
          else ch = (c === 0 || c === w - 1) ? s[5] : " ";
          put(x + c, y + r, ch, a);
        }
        [...String(el.title || "")].slice(0, Math.max(0, w - 4)).forEach((ch, i) => put(x + 2 + i, y, ch, a));
      } else if (el.type === "text") {
        const { x, y } = geometry(el);
        [...String(el.text || "")].slice(0, W - x).forEach((ch, i) => put(x + i, y, ch, a));
      }
    }
    return grid;
  }

  function blank(a) { return Array.from({ length: H }, () => Array.from({ length: W }, () => ({ ch: " ", a }))); }

  // Box drawing characters are drawn as lines so they connect perfectly.
  const LINES = { "─": "h1", "│": "v1", "┌": "rd1", "┐": "ld1", "└": "ru1", "┘": "lu1",
                  "═": "h2", "║": "v2", "╔": "rd2", "╗": "ld2", "╚": "ru2", "╝": "lu2" };

  function drawGlyph(ctx, ch, px, py, cw, chh, color) {
    const kind = LINES[ch];
    if (ch === "█") { ctx.fillStyle = color; ctx.fillRect(px, py, cw, chh); return; }
    if (!kind) {
      if (ch !== " ") { ctx.fillStyle = color; ctx.fillText(ch, px + cw / 2, py + chh / 2 + 1); }
      return;
    }
    const dbl = kind.endsWith("2"), t = Math.max(1, Math.round(cw / 9)), cx = px + cw / 2, cy = py + chh / 2;
    const offs = dbl ? [-t * 1.5, t * 1.5] : [0];
    ctx.fillStyle = color;
    const hline = (x0, x1, y) => ctx.fillRect(Math.min(x0, x1), y - t / 2, Math.abs(x1 - x0), t);
    const vline = (y0, y1, x) => ctx.fillRect(x - t / 2, Math.min(y0, y1), t, Math.abs(y1 - y0));
    const k = kind.slice(0, -1);
    if (k === "h") offs.forEach(o => hline(px, px + cw, cy + o));
    else if (k === "v") offs.forEach(o => vline(py, py + chh, cx + o));
    else {
      const dx = k.includes("r") ? 1 : -1, dy = k.includes("d") ? 1 : -1, d = dbl ? t * 1.5 : 0;
      const pts = dbl ? [[cx - dx * d, cy - dy * d], [cx + dx * d, cy + dy * d]] : [[cx, cy]];
      for (const [sx, sy] of pts) {
        hline(sx - dx * t / 2, dx > 0 ? px + cw : px, sy);
        vline(sy - dy * t / 2, dy > 0 ? py + chh : py, sx);
      }
    }
  }

  function draw(canvas, grid, opts = {}) {
    const cw = opts.cw || 10, chh = opts.ch || 20;
    if (canvas.width !== W * cw) { canvas.width = W * cw; canvas.height = H * chh; }
    const ctx = canvas.getContext("2d");
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = `${Math.round(chh * 0.8)}px "DejaVu Sans Mono", Consolas, "Courier New", monospace`;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const c = grid[y][x];
      ctx.fillStyle = PALETTE[(c.a >> 4) & 15];
      ctx.fillRect(x * cw, y * chh, cw, chh);
      drawGlyph(ctx, c.ch, x * cw, y * chh, cw, chh, PALETTE[c.a & 15]);
    }
    return ctx;
  }

  return { W, H, PALETTE, NAMES, STYLES, render, draw, geometry, attr };
})();
