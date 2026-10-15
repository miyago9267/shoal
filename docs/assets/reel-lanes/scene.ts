/**
 * shoal dispatch lanes: main slices -> guard checks lane label -> applier / executor / security-executor.
 * 90x46 portrait grid, 30 s loop @ 30 fps.
 *
 *   bun scene.ts --frame 0,150,200,300,480,780 --strict
 *   bash ~/.claude/skills/term-reels/scripts/render.sh scene.ts
 */
import {
  palette as P, defineScene, runScene,
  text, spans, right, fill, highlight, box, hline, connector, progressBar,
  logPane, LogEntry, stamp, span, counter, noise1, strWidth, takeClusters, mix, clamp, padEndW,
} from "/Users/miyago/.claude/skills/term-reels/engine";

const COLS = 90, ROWS = 46, DURATION = 30, SEED = 23;

const C = {
  you: P.white, main: P.blue, fast: P.green, complex: P.yellow, rigorous: P.red,
  guard: P.purple, watch: P.cyan, bad: P.red,
};

// ------------------------------------------------------------------ timing table
const T = {
  burst: 5.0,      // all 5 slices leave main at once
  decide1: 6.0,    // guard verdicts on the burst
  resend: 8.0,     // denied slices re-sent with correct labels
  decide2: 9.0,    // guard verdicts on the re-sent slices
  watchA: 16.0, watchB: 25.0,
  watchRet: [25.0, 26.4] as [number, number],
  integrate: 26.4,
  green: 27.0,
  fade: DURATION - 0.5,
};

type Lane = "fast" | "complex" | "rigorous";
interface Slice {
  id: string; name: string; lane: Lane; role: string; cx: number;
  /** first attempt: label sent + verdict. */
  first: { label: string; to: string; deny?: string };
  run: [number, number];
  ret: [number, number];
}
const LANE_COLOR: Record<Lane, number> = { fast: C.fast, complex: C.complex, rigorous: C.rigorous };
const SLICES: Slice[] = [
  { id: "S1", name: "查 login", lane: "fast", role: "applier", cx: 12, first: { label: "[fast]", to: "applier" }, run: [7.0, 11.5], ret: [14.4, 15.8] },
  { id: "S2", name: "改 限額常數", lane: "fast", role: "applier", cx: 28, first: { label: "[fast]", to: "applier" }, run: [7.0, 12.5], ret: [14.4, 15.8] },
  { id: "S3", name: "補 設定檔", lane: "fast", role: "applier", cx: 44, first: { label: "[fast]", to: "executor", deny: "[fast] 不能派 executor，要派 applier" }, run: [10.0, 14.4], ret: [14.4, 15.8] },
  { id: "S4", name: "拆 session", lane: "complex", role: "executor", cx: 60, first: { label: "", to: "executor", deny: "沒有 lane 標籤，必須標 [complex]" }, run: [10.0, 19.0], ret: [19.0, 20.4] },
  { id: "S5", name: "改 token", lane: "rigorous", role: "security-executor", cx: 76, first: { label: "[rigorous]", to: "security-executor" }, run: [7.0, 21.0], ret: [21.0, 22.4] },
];
const denied = (s: Slice) => !!s.first.deny;
/** the time the slice finally clears the guard */
const passAt = (s: Slice) => (denied(s) ? T.decide2 : T.decide1);
const sentAt = (s: Slice) => (denied(s) ? T.resend : T.burst);
const CARD_X = (s: Slice) => s.cx - 7;

const RETURNED_AT = (s: Slice) => s.ret[1];
const MAIN_STATE: Array<[number, string, number]> = [
  [0, "待命", P.dim],
  [2.8, "讀需求，找獨立切片", P.white],
  [3.4, "拆成 5 個互不重疊的切片", C.main],
  [4.7, "替每個切片標 lane", C.main],
  [T.burst, "平行派出 5 個切片", C.main],
  [T.decide1, "guard 擋下 2 個，補標籤", C.bad],
  [T.resend, "重送 S3 S4", C.main],
  [T.decide2, "5 個都放行，等結果", C.fast],
  [T.integrate - 1.4, "等 watcher 的完整測試", C.watch],
  [T.integrate, "整合 5 個切片", C.main],
  [T.green, "全綠，完成", P.green],
];
const mainState = (t: number) => MAIN_STATE.reduce((cur, e) => (t >= e[0] ? e : cur), MAIN_STATE[0]!);

// ------------------------------------------------------------------ event-derived counters (single source)
const passes = (t: number) => SLICES.filter((s) => t >= passAt(s)).length;
const denies = (t: number) => SLICES.filter((s) => denied(s) && t >= T.decide1).length;
/** dispatches leave in ticks of 0.08 s so the counter visibly ticks. */
const sent = (t: number) => {
  const n = (t0: number, k: number) => (t < t0 ? 0 : Math.min(k, Math.floor((t - t0) / 0.08) + 1));
  return n(T.burst, 5) + n(T.resend, 2);
};
const returned = (t: number) => SLICES.filter((s) => t >= RETURNED_AT(s)).length;

// ------------------------------------------------------------------ log
const LOG: LogEntry[] = [];
{
  const add = (t: number, tag: string, color: number, msg: string, hot?: boolean) =>
    LOG.push({ t, line: [[stamp(t) + "  ", { fg: P.dim }], [padEndW(tag, 11), { fg: color }], [msg, { fg: hot ? P.white : P.fg }]] });
  add(0.9, "shoal", P.dim, "lane 路由載入 · fast / complex / rigorous");
  add(2.7, "你", C.you, "加 rate limit 到 /login，改完要過測試", true);
  add(3.5, "main", C.main, "拆出 5 個互不重疊的切片，每個標 lane");
  add(T.burst, "main", C.main, "一次派出 5 個切片", true);
  add(T.decide1, "guard", C.bad, "擋下 S4 · 沒有 lane 標籤", true);
  add(T.decide1, "guard", C.bad, "擋下 S3 · [fast] 派到 executor", true);
  add(T.decide1, "guard", C.guard, "放行 S1 S2 S5 · 放行 3 擋下 2");
  add(T.resend, "main", C.main, "補標籤重送 S3 → applier · S4 → executor");
  add(T.decide2, "guard", C.guard, "放行 S3 S4 · 放行 5 擋下 2", true);
  add(14.4, "applier", C.fast, "haiku · S1 S2 S3 完成", true);
  add(T.watchA, "watcher", C.watch, "背景跑完整測試一次，不卡 main");
  add(19.0, "executor", C.complex, "S4 完成 · 拆 session", true);
  add(21.0, "security", C.rigorous, "S5 完成 · token 變更", true);
  add(T.watchB, "watcher", C.watch, "bun test 57/57 通過", true);
  add(T.integrate, "main", C.main, "整合 5 個切片的結果");
  add(T.green, "shoal", P.green, "全綠 · 放行 5 · 擋下 2 · 派工 7", true);
  LOG.sort((a, b) => a.t - b.t);
}

// ------------------------------------------------------------------ helpers
const clock = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const pct = (x: number) => String(Math.round(clamp(x) * 100)).padStart(3) + "%";
const sliceP = (s: Slice, t: number) => clamp(span(t, s.run[0], s.run[1]));
const sliceStatus = (s: Slice, t: number) => (t < s.run[0] ? "idle" : t >= s.run[1] ? "done" : "running");
const laneTag = (l: Lane) => `[${l}]`;

/** card state: what the slice shows right now. */
function cardView(s: Slice, t: number): { line: string; fg: number; edge: number; bold?: boolean } {
  const dead = denied(s) && t >= T.decide1 && t < T.resend;
  const lc = LANE_COLOR[s.lane];
  if (dead) return { line: "× 擋下", fg: C.bad, edge: C.bad, bold: true };
  const st = sliceStatus(s, t);
  if (st === "done") return { line: "✓ 完成", fg: P.green, edge: mix(P.line, P.green, 0.5) };
  if (st === "running") return { line: "● 執行中", fg: lc, edge: mix(P.line, lc, 0.7) };
  if (t >= passAt(s)) return { line: "▸ 放行", fg: lc, edge: mix(P.line, lc, 0.7) };
  if (t >= sentAt(s)) return { line: laneTag(s.lane) + " ▸", fg: lc, edge: lc };
  if (t >= T.burst) return { line: s.first.label || "無標籤 ▸", fg: s.first.label ? LANE_COLOR[s.lane] : C.bad, edge: P.fg };
  if (t >= 4.7 + SLICES.indexOf(s) * 0.12) {
    return s.first.label ? { line: s.first.label, fg: lc, edge: P.line } : { line: "忘了標 lane", fg: P.dim, edge: P.line };
  }
  return { line: "待標", fg: P.dim, edge: P.line };
}

// ------------------------------------------------------------------ scene
export const scene = defineScene({
  name: "shoal-lanes",
  cols: COLS, rows: ROWS, fps: 30, duration: DURATION, seed: SEED,

  frame(t, _f, ctx) {
    const s = ctx.screen();
    const seen = (at: number) => t >= at;
    const denyOn = t >= T.decide1 && t < T.resend;
    const flashOn = denyOn && (t - T.decide1) < 1.4 && Math.floor((t - T.decide1) * 6) % 2 === 0;

    // ---- title + tagline
    if (seen(0.1)) {
      spans(s, 1, 0, [["shoal", { fg: P.white, bold: true }], ["  ·  ", { fg: P.dim }], ["切片、平行派工、guard 把關 lane", { fg: P.fg }]]);
      right(s, 88, 0, clock(t) + " / " + clock(DURATION), { fg: P.dim });
    }
    if (seen(0.6)) {
      const tag = "切片互不重疊，派給夠用的最便宜 lane，lane 標籤由 guard 強制";
      text(s, 1, 1, takeClusters(tag, Math.floor(span(t, 0.6, 2.4) * 70)), { fg: mix(P.fg, C.main, 0.3) });
    }
    if (seen(0.8)) hline(s, 1, 2, 88, { fg: P.faint });

    // ---- task + stats (same functions as the guard, so the same frame)
    if (seen(1.0)) {
      box(s, 3, 3, 56, 3, { border: "rounded", style: { fg: seen(2.7) ? P.white : P.line }, title: [["任務", { fg: C.you, bold: true }]] });
      text(s, 5, 4, takeClusters("加 rate limit 到 /login，改完要過測試", Math.floor(span(t, 1.3, 2.7) * 40)), { fg: P.white });
    }
    if (seen(1.2)) {
      box(s, 60, 3, 27, 3, { border: "rounded", style: { fg: P.line }, title: [["guard 計數", { fg: C.guard, bold: true }]] });
      const d = denies(t);
      spans(s, 62, 4, [
        ["派出 ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
        ["  放行 ", { fg: P.dim }], [String(passes(t)), { fg: passes(t) ? P.green : P.white, bold: true }],
        ["  擋下 ", { fg: P.dim }], [String(d), { fg: d ? C.bad : P.white, bold: true }],
      ], {}, 24);
    }

    // ---- main
    if (seen(1.5)) {
      const [, label, lc] = mainState(t);
      const busy = t > 3 && t < T.green;
      box(s, 3, 8, 84, 8, { border: "rounded", style: { fg: mix(P.line, C.main, 0.6) }, title: [["main", { fg: C.main, bold: true }], [" · 只切片與整合，不自己動手", { fg: P.dim }]] });
      spans(s, 5, 9, [["●", { fg: t >= T.green ? P.green : P.yellow, dim: busy && Math.floor(t * 4) % 2 === 0 }], [" " + label, { fg: lc, bold: true }]], {}, 78);
      const mp = clamp(span(t, 3, T.green));
      text(s, 5, 10, "進度", { fg: P.dim });
      progressBar(s, 10, 10, 30, mp, { fill: C.main });
      text(s, 41, 10, pct(mp), { fg: C.main, bold: true });
      spans(s, 48, 10, [
        ["切片 ", { fg: P.dim }], [String(Math.min(5, Math.floor(span(t, 3.4, 4.6) * 5.01))), { fg: P.white, bold: true }], ["/5", { fg: P.dim }],
        ["   回報 ", { fg: P.dim }], [String(returned(t)), { fg: returned(t) ? P.green : P.white, bold: true }], ["/5", { fg: P.dim }],
      ], {}, 38);
      SLICES.forEach((sl, i) => {
        if (t < 3.4 + i * 0.25) return;
        const v = cardView(sl, t);
        const x = CARD_X(sl);
        const dead = denyOn && denied(sl);
        if (dead && flashOn) fill(s, x, 11, 15, 4, { bg: mix(P.bg, C.bad, 0.35) });
        box(s, x, 11, 15, 4, { border: "single", style: { fg: v.edge }, title: [[sl.id, { fg: v.fg, bold: true }]] });
        text(s, x + 2, 12, sl.name, { fg: P.white }, 11);
        text(s, x + 2, 13, v.line, { fg: v.fg, bold: v.bold ?? false }, 11);
      });
    }

    // ---- guard (sits on the dispatch path)
    if (seen(2.0)) {
      const col = flashOn ? C.bad : denyOn ? mix(P.line, C.bad, 0.7) : mix(P.line, C.guard, 0.8);
      if (flashOn) fill(s, 3, 18, 84, 6, { bg: mix(P.bg, C.bad, 0.3) });
      box(s, 3, 18, 84, 6, { border: "heavy", style: { fg: col }, title: [["GUARD", { fg: flashOn ? C.bad : C.guard, bold: true }], [" · 每次派工都要帶 lane 標籤", { fg: P.dim }]] });
      const bg = flashOn ? { bg: mix(P.bg, C.bad, 0.3) } : {};
      if (denyOn) {
        const [a, b] = [SLICES[3]!, SLICES[2]!];
        spans(s, 5, 19, [["× 擋下 ", { fg: C.bad, bold: true }], [a.id + " ", { fg: P.white, bold: true }], [a.first.deny!, { fg: P.white }]], bg, 80);
        spans(s, 5, 20, [["× 擋下 ", { fg: C.bad, bold: true }], [b.id + " ", { fg: P.white, bold: true }], [b.first.deny!, { fg: P.white }]], bg, 80);
      } else if (t >= T.resend && t < T.decide2) {
        spans(s, 5, 19, [["● 檢查重送 ", { fg: C.guard, bold: true }], ["S3 [fast]→applier   S4 [complex]→executor", { fg: P.fg }]], bg, 80);
        text(s, 5, 20, "標籤與 role 相符，放行", { fg: P.dim }, 80);
      } else if (t >= T.burst && t < T.decide1) {
        spans(s, 5, 19, [["● 檢查 5 筆派工 ", { fg: C.guard, bold: true }], ["標籤是否存在 · 是否對應正確 role", { fg: P.fg }]], bg, 80);
      } else if (t >= T.decide2) {
        spans(s, 5, 19, [["● 放行 ", { fg: P.green, bold: true }], ["5/5 切片都帶標籤且 role 相符", { fg: P.fg }]], bg, 80);
      } else {
        spans(s, 5, 19, [["◇ 待命 ", { fg: P.dim }], ["等 main 派工", { fg: P.dim }]], bg, 80);
      }
      // rule legend, always visible
      spans(s, 5, 21, [
        ["[fast]", { fg: C.fast, bold: true }], ["→applier  ", { fg: P.fg }],
        ["[complex]", { fg: C.complex, bold: true }], ["→executor  ", { fg: P.fg }],
        ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }],
      ], bg, 80);
      // counters on the guard itself: identical source as the stats box
      const d = denies(t), p = passes(t);
      spans(s, 5, 22, [
        ["放行 ", { fg: P.dim }], [String(p), { fg: p ? P.green : P.white, bold: true }],
        ["   擋下 ", { fg: P.dim }], [String(d), { fg: d ? C.bad : P.white, bold: true }],
        ["   派出 ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
      ], bg, 80);
    }

    // ---- lanes
    {
      const LY = 26, LH = 8;
      const mkTitle = (id: string, col: number) => [[id, { fg: col, bold: true }]] as any;
      const laneEdge = (col: number, on: boolean, done: boolean) => (on ? mix(P.line, col, 0.8) : done ? mix(P.line, col, 0.4) : P.line);
      const stat = (ss: Slice[]) => ss.map((x) => sliceStatus(x, t));
      // applier
      if (seen(2.2)) {
        const ss = SLICES.filter((x) => x.role === "applier");
        const st = stat(ss);
        const on = st.includes("running"), done = st.every((x) => x === "done");
        box(s, 3, LY, 44, LH, { border: "single", style: { fg: laneEdge(C.fast, on, done) }, title: mkTitle("applier", C.fast) });
        spans(s, 5, LY + 1, [["[fast]", { fg: C.fast, bold: true }], ["  haiku · 最便宜 · 切片最多", { fg: P.fg }]], {}, 40);
        ss.forEach((x, i) => {
          const y = LY + 2 + i, sp = sliceP(x, t), s1 = sliceStatus(x, t);
          const col = s1 === "done" ? P.green : s1 === "running" ? C.fast : P.dim;
          text(s, 5, y, x.id, { fg: col, bold: true });
          text(s, 8, y, x.name, { fg: s1 === "idle" ? P.dim : P.white }, 11);
          progressBar(s, 20, y, 12, sp, { fill: col });
          text(s, 33, y, pct(sp), { fg: col, bold: true });
          text(s, 38, y, s1 === "done" ? "✓" : s1 === "running" ? "●" : "◇", { fg: col, dim: s1 === "running" && Math.floor(t * 4 + i) % 2 === 0 });
        });
        const nd = st.filter((x) => x === "done").length;
        spans(s, 5, LY + 6, [["完成 ", { fg: P.dim }], [`${nd}/3`, { fg: nd === 3 ? P.green : P.white, bold: true }], ["   tok ", { fg: P.dim }], [String(Math.round(ss.reduce((a, x) => a + sliceP(x, t), 0) * 210 + 30 * noise1(SEED, t, 1))), { fg: P.dim }]], {}, 40);
      }
      // executor
      if (seen(2.45)) {
        const x = SLICES[3]!;
        const sp = sliceP(x, t), s1 = sliceStatus(x, t);
        box(s, 47, LY, 15, LH, { border: "single", style: { fg: laneEdge(C.complex, s1 === "running", s1 === "done") }, title: mkTitle("executor", C.complex) });
        text(s, 49, LY + 1, "[complex]", { fg: C.complex, bold: true });
        text(s, 49, LY + 2, "sonnet 多檔", { fg: P.fg }, 12);
        const col = s1 === "done" ? P.green : s1 === "running" ? C.complex : P.dim;
        text(s, 49, LY + 3, x.id, { fg: col, bold: true });
        progressBar(s, 49, LY + 4, 6, sp, { fill: col });
        text(s, 56, LY + 4, pct(sp), { fg: col, bold: true });
        text(s, 49, LY + 5, s1 === "done" ? "✓ 完成" : s1 === "running" ? "● 執行中" : "◇ idle", { fg: col, dim: s1 === "running" && Math.floor(t * 4) % 2 === 0 });
        text(s, 49, LY + 6, s1 === "idle" ? "" : "tok " + Math.round(sp * 520 + 40 * noise1(SEED, t, 3)), { fg: P.dim });
      }
      // security-executor
      if (seen(2.7)) {
        const x = SLICES[4]!;
        const sp = sliceP(x, t), s1 = sliceStatus(x, t);
        box(s, 62, LY, 25, LH, { border: "single", style: { fg: laneEdge(C.rigorous, s1 === "running", s1 === "done") }, title: mkTitle("security-executor", C.rigorous) });
        text(s, 64, LY + 1, "[rigorous]", { fg: C.rigorous, bold: true });
        text(s, 64, LY + 2, "稀有 · auth 與密鑰", { fg: P.fg }, 18);
        const col = s1 === "done" ? P.green : s1 === "running" ? C.rigorous : P.dim;
        text(s, 64, LY + 3, x.id, { fg: col, bold: true });
        progressBar(s, 64, LY + 4, 10, sp, { fill: col });
        text(s, 75, LY + 4, pct(sp), { fg: col, bold: true });
        text(s, 64, LY + 5, s1 === "done" ? "✓ 完成" : s1 === "running" ? "● 執行中" : "◇ idle", { fg: col, dim: s1 === "running" && Math.floor(t * 4 + 1) % 2 === 0 });
        text(s, 64, LY + 6, s1 === "idle" ? "" : "tok " + Math.round(sp * 380 + 40 * noise1(SEED, t, 5)), { fg: P.dim });
      }
    }

    // ---- watcher
    if (seen(3.0)) {
      const run = t >= T.watchA && t < T.watchB, done = t >= T.watchB;
      const wp = clamp(span(t, T.watchA, T.watchB));
      const col = done ? P.green : run ? C.watch : P.dim;
      box(s, 3, 35, 84, 4, { border: "single", style: { fg: run ? mix(P.line, C.watch, 0.75) : done ? mix(P.line, C.watch, 0.35) : P.line }, title: [["watcher", { fg: C.watch, bold: true }]] });
      spans(s, 5, 36, [["haiku · 背景跑完整測試一次 · main 不用等", { fg: P.fg }]], {}, 60);
      text(s, 70, 36, done ? "✓ 完成" : run ? "● 背景中" : "◇ idle", { fg: col, bold: run || done, dim: run && Math.floor(t * 4) % 2 === 0 });
      text(s, 5, 37, "bun test", { fg: P.dim });
      progressBar(s, 14, 37, 44, wp, { fill: col });
      text(s, 59, 37, pct(wp), { fg: col, bold: true });
      const n = done ? 57 : counter(t, T.watchA, T.watchB, 0, 57, (x) => x);
      text(s, 65, 37, run || done ? `${String(n).padStart(2)}/57` : "", { fg: P.white, bold: true });
    }

    // ---- connectors: lines first, dots second
    type Conn = { pts: [number, number][]; color: number; on: boolean; at: number; speed?: number; dots?: number };
    const conns: Conn[] = [
      { pts: [[31, 6], [31, 7]], color: C.you, on: t >= 2.7 && t < 3.6, at: 1.6, speed: 1.2 },
    ];
    const inWin = (a: number, b: number) => t >= a && t < b;
    for (const sl of SLICES) {
      // stage 1: card -> guard. burst for everyone, re-send for the denied ones.
      const win1 = inWin(T.burst, T.decide1) || (denied(sl) && inWin(T.resend, T.decide2));
      const bad1 = denied(sl) && inWin(T.burst, T.decide1);
      conns.push({ pts: [[sl.cx, 16], [sl.cx, 17]], color: bad1 ? C.bad : LANE_COLOR[sl.lane], on: win1, at: 2.4, speed: 1.4, dots: 2 });
      // stage 2: guard -> lane, only after the verdict is pass
      conns.push({ pts: [[sl.cx, 24], [sl.cx, 25]], color: LANE_COLOR[sl.lane], on: inWin(passAt(sl), sl.run[0]), at: 2.4, speed: 1.4, dots: 2 });
    }
    // results back to main: left trunk (applier, watcher), right trunk (executor, security)
    const ret = (a: number, b: number) => inWin(a, b);
    conns.push({ pts: [[2, 30], [1, 30], [1, 12], [2, 12]], color: C.fast, on: ret(14.4, 15.8), at: 14.4, speed: 0.7 });
    conns.push({ pts: [[2, 37], [1, 37], [1, 14], [2, 14]], color: C.watch, on: ret(...T.watchRet), at: T.watchRet[0], speed: 0.7 });
    conns.push({ pts: [[54, 34], [88, 34], [88, 12], [87, 12]], color: C.complex, on: ret(19.0, 20.4), at: 19.0, speed: 0.7 });
    conns.push({ pts: [[87, 30], [88, 30], [88, 14], [87, 14]], color: C.rigorous, on: ret(21.0, 22.4), at: 21.0, speed: 0.7 });
    for (const draw of ["lines", "dots"] as const) {
      for (const c of conns) {
        if (!seen(c.at)) continue;
        if (draw === "dots" && !c.on) continue;
        connector(s, c.pts, {
          style: { fg: c.on ? mix(P.line, c.color, 0.5) : P.line },
          arrow: "end", draw, t, dots: c.dots ?? 1, speed: c.speed ?? 0.6, dotStyle: { fg: c.color }, trail: 2,
        });
      }
    }

    // ---- log
    if (seen(2.8)) {
      box(s, 1, 39, 88, 5, { border: "single", style: { fg: P.line }, title: [["session log", { fg: P.fg, bold: true }]] });
      logPane(s, 3, 40, 84, 3, LOG, t);
    }

    // ---- prompt / completion line
    if (t < T.green) {
      const full = "shoal 加 rate limit 到 /login";
      const typed = Math.floor(span(t, 0.3, 1.8) * [...full].length);
      const shown = takeClusters(full, typed);
      spans(s, 1, 44, [["~/app", { fg: C.main }], [" $ ", { fg: P.dim }], [shown, { fg: P.white }]]);
      s.put(1 + 8 + strWidth(shown), 44, typed < [...full].length || Math.floor(t * 2) % 2 === 0 ? "█" : " ", { fg: P.white });
    } else {
      const bg = mix(P.panel, P.green, 0.25);
      fill(s, 1, 44, 88, 1, { bg });
      spans(s, 2, 44, [["● 全綠", { fg: P.green, bold: true }], ["  5 切片整合完成 · 放行 5 擋下 2 · 57/57 通過", { fg: P.white }]], { bg });
    }
    fill(s, 1, 45, 88, 1, { bg: P.panel });
    spans(s, 2, 45, [["lanes ", { fg: P.dim }], ["fast", { fg: C.fast }], [" · ", { fg: P.faint }], ["complex", { fg: C.complex }], [" · ", { fg: P.faint }], ["rigorous", { fg: C.rigorous }]], { bg: P.panel });
    right(s, 87, 45, "夠用的最便宜 lane", { fg: P.dim, bg: P.panel });

    // ---- loop outro
    if (t > T.fade) for (const c of s.cells) c.dim = true;
    return s;
  },
});

export default scene;
if (import.meta.main) await runScene(scene);
