/**
 * shoal rigorous path: a security-sensitive change (swap JWT signing, rotate secret).
 * 90x46 portrait grid, 32 s loop @ 30 fps.
 *
 *   bun scene.ts --frame 0,150,480,640,780 --strict
 *   bash ~/.claude/skills/term-reels/scripts/render.sh scene.ts
 */
import {
  palette as P, defineScene, runScene,
  text, spans, right, fill, box, hline, connector, progressBar,
  logPane, LogEntry, stamp, span, noise1, strWidth, takeClusters, mix, clamp, padEndW,
} from "/Users/miyago/.claude/skills/term-reels/engine";

const COLS = 90, ROWS = 46, DURATION = 32, SEED = 41;

const C = {
  you: P.white, main: P.blue, scout: 0x73daca, secrev: P.pink, plan: P.orange, gate: P.white,
  guard: P.purple, fast: P.green, complex: P.yellow, rigorous: P.red, watch: P.cyan,
  verifier: 0xe6d96a, bad: P.red,
};
const bright = (c: number) => mix(c, P.white, 0.45);

// ------------------------------------------------------------------ timing table
const T = {
  task: [1.3, 2.6] as [number, number],
  trigger: 3.0, route: 4.0,
  scout: [4.8, 7.0] as [number, number],
  secrev: [7.0, 10.0] as [number, number],
  find: [8.2, 8.9, 9.6],
  plan: 10.0, critic: [10.8, 12.4] as [number, number],
  gate: 12.8, approve: 13.8,
  send1: 14.6, deny: 15.6,
  resend: 17.2, pass1: 18.2,
  sec1: [19.0, 22.0] as [number, number],
  app: [19.0, 21.2] as [number, number],
  watch: [19.2, 27.6] as [number, number],
  ver1: [22.8, 24.2] as [number, number],   // REFUTED at 24.2
  fixSend: 24.8, fixPass: 25.6,
  fix: [25.6, 27.0] as [number, number],
  ver2: [27.4, 28.6] as [number, number],   // CONFIRMED at 28.6
  integrate: 29.0, green: 29.6,
  fade: DURATION - 0.5,
};

const MAIN_STATE: Array<[number, string, number]> = [
  [0, "待命", P.dim],
  [2.6, "讀需求：換掉 JWT 簽章並輪替 secret", P.white],
  [T.trigger, "安全觸發：碰到 auth 與 secret", C.bad],
  [T.route, "走嚴謹路線", C.rigorous],
  [T.scout[0], "派 scout 找 auth 呼叫點", C.main],
  [T.secrev[0], "派 security-reviewer 唯讀審查", C.main],
  [T.plan, "寫 Plan，送 plan-critic", C.main],
  [T.gate, "Plan READY，等 Miyago 核准", C.gate],
  [T.approve, "已核准，切成 2 個切片", C.main],
  [T.send1, "先派 auth 切片 [complex]→executor", C.complex],
  [T.deny, "guard 擋下，改標 [rigorous]", C.bad],
  [T.resend, "重送 auth，旁支切片 [fast] 平行", C.main],
  [T.pass1, "兩個都放行，等結果", C.fast],
  [T.sec1[1], "auth 切片完成，派 verifier", C.main],
  [T.ver1[1], "verifier 判 REFUTED，派修補", C.bad],
  [T.fixSend, "修補走 [rigorous]→security-executor", C.rigorous],
  [T.fixPass, "guard 放行，等修補", C.fast],
  [T.fix[1], "修補完成，派全新 verifier", C.main],
  [T.ver2[1], "verifier 判 CONFIRMED", C.fast],
  [T.integrate, "整合切片與測試結果", C.main],
  [T.green, "全綠，完成", P.green],
];
const mainState = (t: number) => MAIN_STATE.reduce((cur, e) => (t >= e[0] ? e : cur), MAIN_STATE[0]!);

// ------------------------------------------------------------------ guard events (single source for counter, box and log)
const SENDS: Array<[number, number]> = [[T.send1, 1], [T.resend, 2], [T.fixSend, 1]];
const PASSES: Array<[number, number]> = [[T.pass1, 2], [T.fixPass, 1]];
const DENIES: Array<[number, number]> = [[T.deny, 1]];
const tick = (t: number, t0: number, k: number) => (t < t0 ? 0 : Math.min(k, Math.floor((t - t0) / 0.08) + 1));
const sent = (t: number) => SENDS.reduce((a, [t0, k]) => a + tick(t, t0, k), 0);
const sumAt = (t: number, l: Array<[number, number]>) => l.reduce((a, [t0, k]) => a + (t >= t0 ? k : 0), 0);
const passes = (t: number) => sumAt(t, PASSES);
const denies = (t: number) => sumAt(t, DENIES);

const ROLE_ENTER = [T.scout[0], T.secrev[0], T.plan, T.pass1 - 4.2, T.pass1 - 4.2, T.watch[0], T.ver1[0] - 0.4];
const roles = (t: number) => ROLE_ENTER.filter((x) => t >= x).length;

// ------------------------------------------------------------------ log
const LOG: LogEntry[] = [];
{
  const add = (t: number, tag: string, color: number, msg: string, hot?: boolean) =>
    LOG.push({ t, line: [[stamp(t) + "  ", { fg: P.dim }], [padEndW(tag, 19), { fg: color }], [msg, { fg: hot ? P.white : P.fg }]] });
  add(0.9, "shoal", P.dim, "路由載入 · fast / complex / rigorous");
  add(2.7, "你", C.you, "換掉 JWT 簽章並輪替 secret", true);
  add(T.trigger, "shoal", C.bad, "安全觸發 · 改動碰到 auth 與 secret", true);
  add(T.route, "main", C.main, "走嚴謹路線", true);
  add(T.scout[1], "scout", C.scout, "找到 14 處 auth 呼叫點，分布 6 個檔");
  add(T.secrev[1], "security-reviewer", C.secrev, "3 個發現 · 唯讀，沒有改檔", true);
  add(T.plan, "main", C.main, "寫 Plan：換 RS256、雙 key 輪替");
  add(T.critic[1], "plan-critic", C.plan, "READY", true);
  add(T.approve, "Miyago", C.gate, "核准 Plan", true);
  add(T.send1, "main", C.main, "派 auth 切片 [complex]→executor");
  add(T.deny, "guard", C.bad, "擋下 · 安全工作要 [rigorous]→security-executor", true);
  add(T.resend, "main", C.main, "重送 [rigorous]→security-executor · 旁支 [fast]→applier");
  add(T.pass1, "guard", C.guard, "放行 2 · 派出 3 放行 2 擋下 1", true);
  add(T.watch[0], "watcher", C.watch, "背景跑完整測試，main 不用等");
  add(T.sec1[1], "security-executor", C.rigorous, "auth 切片完成 · RS256 與雙 key");
  add(T.ver1[1], "verifier", C.verifier, "REFUTED · 舊 token 驗證路徑仍接受 HS256", true);
  add(T.fixSend, "main", C.main, "派修補 [rigorous]→security-executor");
  add(T.fixPass, "guard", C.guard, "放行 · 派出 4 放行 3 擋下 1", true);
  add(T.fix[1], "security-executor", C.rigorous, "修補完成 · HS256 路徑已移除");
  add(T.watch[1], "watcher", C.watch, "bun test 182/182 通過");
  add(T.ver2[1], "verifier", C.verifier, "CONFIRMED · 全新 context 重驗通過", true);
  add(T.green, "shoal", P.green, "全綠 · 放行 3 擋下 1 · 派工 4", true);
  LOG.sort((a, b) => a.t - b.t);
}

// ------------------------------------------------------------------ helpers
const clock = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const pct = (x: number) => String(Math.round(clamp(x) * 100)).padStart(3) + "%";
const blink = (t: number, k = 0) => Math.floor(t * 4 + k) % 2 === 0;
const stateOf = (t: number, r: [number, number]) => (t < r[0] ? "idle" : t >= r[1] ? "done" : "running");
const edgeFor = (col: number, st: string) => (st === "running" ? mix(P.line, col, 0.85) : st === "done" ? mix(P.line, col, 0.45) : P.line);
const stCol = (col: number, st: string) => (st === "done" ? P.green : st === "running" ? col : P.dim);
const stText = (st: string) => (st === "done" ? "✓ 完成" : st === "running" ? "● 執行中" : "◇ 待命");

// ------------------------------------------------------------------ scene
export const scene = defineScene({
  name: "shoal-security",
  cols: COLS, rows: ROWS, fps: 30, duration: DURATION, seed: SEED,

  frame(t, _f, ctx) {
    const s = ctx.screen();
    const seen = (at: number) => t >= at;
    const inWin = (a: number, b: number) => t >= a && t < b;
    const denyOn = inWin(T.deny, T.resend);
    const flashOn = denyOn && t - T.deny < 1.4 && Math.floor((t - T.deny) * 6) % 2 === 0;

    // ---- title
    if (seen(0.1)) {
      spans(s, 1, 0, [["shoal", { fg: P.white, bold: true }], ["  ·  ", { fg: P.dim }], ["安全敏感的改動，走嚴謹路線", { fg: P.fg }]]);
      right(s, 88, 0, clock(t) + " / " + clock(DURATION), { fg: P.dim });
    }
    if (seen(0.6)) {
      const tag = "安全工作不抄捷徑：唯讀審查、Plan 核准、guard 強制 lane、獨立驗證";
      text(s, 1, 1, takeClusters(tag, Math.floor(span(t, 0.6, 2.4) * 70)), { fg: mix(P.fg, C.rigorous, 0.35) });
    }
    if (seen(0.8)) hline(s, 1, 2, 88, { fg: P.faint });

    // ---- task + guard counter
    if (seen(1.0)) {
      box(s, 3, 3, 56, 3, { border: "rounded", style: { fg: seen(2.7) ? P.white : P.line }, title: [["任務", { fg: C.you, bold: true }]] });
      text(s, 5, 4, takeClusters("換掉 JWT 簽章並輪替 secret", Math.floor(span(t, ...T.task) * 40)), { fg: P.white });
    }
    if (seen(1.2)) {
      box(s, 60, 3, 27, 3, { border: "rounded", style: { fg: P.line }, title: [["guard 計數", { fg: C.guard, bold: true }]] });
      const d = denies(t), p = passes(t);
      spans(s, 62, 4, [
        ["派出 ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
        ["  放行 ", { fg: P.dim }], [String(p), { fg: p ? P.green : P.white, bold: true }],
        ["  擋下 ", { fg: P.dim }], [String(d), { fg: d ? C.bad : P.white, bold: true }],
      ], {}, 24);
    }

    // ---- main (rows 6-10)
    if (seen(1.5)) {
      const [, label, lc] = mainState(t);
      const busy = t > 3 && t < T.green;
      const trig = inWin(T.trigger, T.trigger + 1.0) && Math.floor((t - T.trigger) * 6) % 2 === 0;
      box(s, 3, 6, 84, 5, { border: "rounded", style: { fg: mix(P.line, trig ? C.bad : C.main, 0.65) }, title: [["main", { fg: C.main, bold: true }], [" · 規劃、派工、整合，不碰 auth 檔", { fg: P.dim }]] });
      spans(s, 5, 7, [["●", { fg: t >= T.green ? P.green : P.yellow, dim: busy && blink(t) }], [" " + label, { fg: lc, bold: true }]], {}, 78);
      const mp = clamp(span(t, 2.6, T.green));
      text(s, 5, 8, "進度", { fg: P.dim });
      progressBar(s, 10, 8, 30, mp, { fill: C.main });
      text(s, 41, 8, pct(mp), { fg: C.main, bold: true });
      spans(s, 48, 8, [["已派角色 ", { fg: P.dim }], [String(roles(t)), { fg: P.white, bold: true }], ["/7", { fg: P.dim }]], {}, 38);
      if (seen(T.trigger)) {
        const routed = seen(T.route);
        spans(s, 5, 9, [
          ["觸發 ", { fg: P.dim }], ["[security]", { fg: C.bad, bold: true }], [" auth · secret 變更", { fg: P.fg }],
          ["   →   ", { fg: P.dim }],
          routed ? ["走嚴謹路線 ", { fg: P.white, bold: true }] : ["", {}],
          routed ? ["[rigorous]", { fg: C.rigorous, bold: true }] : ["", {}],
        ], {}, 78);
      }
    }

    // ---- research row (rows 11-15): scout | security-reviewer
    if (seen(T.scout[0])) {
      const st = stateOf(t, T.scout), sp = clamp(span(t, ...T.scout));
      box(s, 3, 11, 30, 5, { border: "single", style: { fg: edgeFor(C.scout, st) }, title: [["scout", { fg: C.scout, bold: true }], [" · 唯讀", { fg: P.dim }]] });
      text(s, 5, 12, "找 auth 呼叫點", { fg: P.fg }, 26);
      progressBar(s, 5, 13, 16, sp, { fill: stCol(C.scout, st) });
      text(s, 22, 13, pct(sp), { fg: stCol(C.scout, st), bold: true });
      text(s, 5, 14, st === "done" ? "✓ 14 處 · 6 個檔" : "● 掃描 " + Math.round(sp * 14) + " 處", { fg: stCol(C.scout, st), bold: true, dim: st === "running" && blink(t) }, 26);
    }
    if (seen(T.secrev[0])) {
      const st = stateOf(t, T.secrev);
      const nf = T.find.filter((x) => t >= x).length;
      box(s, 38, 11, 49, 5, {
        border: "single", style: { fg: edgeFor(C.secrev, st) },
        title: [["security-reviewer", { fg: C.secrev, bold: true }], [" · 唯讀", { fg: P.dim }], [st === "done" ? "  3 個發現" : "  審查中", { fg: stCol(C.secrev, st), bold: true }]],
      });
      const F = [["alg confusion", " · 驗證端未鎖 alg"], ["secret in env log", " · 啟動日誌外洩"], ["missing key rotation window", ""]];
      F.forEach(([a, b], i) => {
        if (i < nf) spans(s, 40, 12 + i, [["▸ ", { fg: C.secrev, bold: true }], [a!, { fg: P.white, bold: true }], [b!, { fg: P.fg }]], {}, 45);
        else text(s, 40, 12 + i, st === "running" && i === nf ? "· · ·" : "", { fg: P.dim });
      });
    }

    // ---- plan row (rows 16-19): plan-critic | Miyago gate
    if (seen(T.plan)) {
      const st = stateOf(t, T.critic), sp = clamp(span(t, ...T.critic));
      const col = C.plan;
      box(s, 3, 16, 52, 4, { border: "single", style: { fg: edgeFor(col, st) }, title: [["plan-critic", { fg: col, bold: true }]] });
      const plan = "Plan：換 RS256 · 雙 key 輪替 · 移除 HS256";
      text(s, 5, 17, takeClusters(plan, Math.floor(span(t, T.plan, T.plan + 0.8) * 44)), { fg: P.white }, 48);
      if (t >= T.critic[0]) {
        progressBar(s, 5, 18, 26, sp, { fill: st === "done" ? P.green : col });
        text(s, 32, 18, pct(sp), { fg: st === "done" ? P.green : col, bold: true });
        if (st === "done") text(s, 38, 18, "✓ READY", { fg: P.green, bold: true });
        else text(s, 38, 18, "● 審 Plan", { fg: col, dim: blink(t) });
      }
      const lit = seen(T.gate), ok = seen(T.approve);
      const glow = lit && !ok && blink(t);
      box(s, 60, 16, 27, 4, {
        border: ok ? "rounded" : "heavy",
        style: { fg: ok ? mix(P.line, P.green, 0.7) : lit ? (glow ? P.white : mix(P.line, C.gate, 0.8)) : P.line },
        title: [["Miyago 核准", { fg: lit ? C.gate : P.dim, bold: true }]],
      });
      if (lit && !ok && glow) fill(s, 61, 17, 25, 2, { bg: mix(P.bg, P.white, 0.14) });
      const gbg = lit && !ok && glow ? { bg: mix(P.bg, P.white, 0.14) } : {};
      text(s, 62, 17, ok ? "✓ 已核准" : lit ? "▲ 等待核准" : "◇ 等 READY", { fg: ok ? P.green : lit ? P.white : P.dim, bold: lit, ...gbg }, 22);
      text(s, 62, 18, ok ? "可以開始動手" : lit ? "Plan 必須先過人" : "", { fg: P.dim, ...gbg }, 22);
    }

    // ---- guard (rows 20-25)
    if (seen(T.approve)) {
      const col = flashOn ? C.bad : denyOn ? mix(P.line, C.bad, 0.7) : mix(P.line, C.guard, 0.8);
      if (flashOn) fill(s, 3, 20, 84, 6, { bg: mix(P.bg, C.bad, 0.3) });
      box(s, 3, 20, 84, 6, { border: "heavy", style: { fg: col }, title: [["GUARD", { fg: flashOn ? C.bad : C.guard, bold: true }], [" · 每次派工都要帶 lane 標籤", { fg: P.dim }]] });
      const bg = flashOn ? { bg: mix(P.bg, C.bad, 0.3) } : {};
      const W = 78;
      if (denyOn) {
        spans(s, 5, 21, [["× 擋下 ", { fg: C.bad, bold: true }], ["auth 切片 ", { fg: P.white, bold: true }], ["[complex]", { fg: C.complex, bold: true }], ["→executor", { fg: P.white }]], bg, W);
        spans(s, 5, 22, [["安全工作要 ", { fg: P.white, bold: true }], ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.white, bold: true }]], bg, W);
      } else if (inWin(T.send1, T.deny)) {
        spans(s, 5, 21, [["● 檢查 ", { fg: C.guard, bold: true }], ["auth 切片 ", { fg: P.white }], ["[complex]", { fg: C.complex, bold: true }], ["→executor", { fg: P.fg }]], bg, W);
        text(s, 5, 22, "比對標籤與任務類型…", { fg: P.dim }, W);
      } else if (inWin(T.resend, T.pass1)) {
        spans(s, 5, 21, [["● 檢查 ", { fg: C.guard, bold: true }], ["auth ", { fg: P.white }], ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }]], bg, W);
        spans(s, 5, 22, [["● 檢查 ", { fg: C.guard, bold: true }], ["文件與設定名 ", { fg: P.white }], ["[fast]", { fg: C.fast, bold: true }], ["→applier", { fg: P.fg }]], bg, W);
      } else if (inWin(T.fixSend, T.fixPass)) {
        spans(s, 5, 21, [["● 檢查 ", { fg: C.guard, bold: true }], ["修補 ", { fg: P.white }], ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }]], bg, W);
        text(s, 5, 22, "舊 token 驗證路徑的修補，一樣走嚴謹", { fg: P.dim }, W);
      } else if (t >= T.fixPass) {
        spans(s, 5, 21, [["● 放行 ", { fg: P.green, bold: true }], ["修補 ", { fg: P.white }], ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }]], bg, W);
        text(s, 5, 22, "累計放行 3 · 擋下 1", { fg: P.dim }, W);
      } else if (t >= T.pass1) {
        spans(s, 5, 21, [["● 放行 ", { fg: P.green, bold: true }], ["auth ", { fg: P.white }], ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }]], bg, W);
        spans(s, 5, 22, [["● 放行 ", { fg: P.green, bold: true }], ["旁支 ", { fg: P.white }], ["[fast]", { fg: C.fast, bold: true }], ["→applier", { fg: P.fg }]], bg, W);
      } else {
        spans(s, 5, 21, [["◇ 待命 ", { fg: P.dim }], ["等 main 派工", { fg: P.dim }]], bg, W);
      }
      spans(s, 5, 23, [
        ["[fast]", { fg: C.fast, bold: true }], ["→applier  ", { fg: P.fg }],
        ["[complex]", { fg: C.complex, bold: true }], ["→executor  ", { fg: P.fg }],
        ["[rigorous]", { fg: C.rigorous, bold: true }], ["→security-executor", { fg: P.fg }],
      ], bg, W);
      const d = denies(t), p = passes(t);
      spans(s, 5, 24, [
        ["放行 ", { fg: P.dim }], [String(p), { fg: p ? P.green : P.white, bold: true }],
        ["   擋下 ", { fg: P.dim }], [String(d), { fg: d ? C.bad : P.white, bold: true }],
        ["   派出 ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
      ], bg, W);
    }

    // ---- lanes (rows 30-34): security-executor | applier | watcher
    if (seen(T.pass1 - 4.2)) {
      const fixing = t >= T.fixPass;
      const r = fixing ? T.fix : T.sec1;
      const st = fixing ? stateOf(t, T.fix) : stateOf(t, T.sec1);
      const sp = clamp(span(t, ...r));
      const done1 = t >= T.sec1[1] && !fixing;
      const col = C.rigorous;
      const shown = fixing ? st : stateOf(t, T.sec1);
      box(s, 3, 30, 34, 5, { border: "single", style: { fg: edgeFor(col, shown === "idle" ? "idle" : fixing && st === "done" ? "done" : st) }, title: [["security-executor", { fg: col, bold: true }]] });
      text(s, 5, 31, "[rigorous]", { fg: col, bold: true });
      text(s, 16, 31, fixing ? "修補 HS256 路徑" : "RS256 · 雙 key 輪替", { fg: P.fg }, 20);
      const c2 = stCol(col, shown);
      progressBar(s, 5, 32, 18, shown === "idle" ? 0 : sp, { fill: c2 });
      text(s, 24, 32, pct(shown === "idle" ? 0 : sp), { fg: c2, bold: true });
      text(s, 5, 33, stText(shown), { fg: c2, bold: shown !== "idle", dim: shown === "running" && blink(t) });
      text(s, 20, 33, shown === "idle" ? "" : "tok " + Math.round((done1 ? 1 : sp) * 640 + 40 * noise1(SEED, t, 5)), { fg: P.dim });
    }
    if (seen(T.pass1 - 4.2)) {
      const st = stateOf(t, T.app), sp = clamp(span(t, ...T.app));
      const col = C.fast, c2 = stCol(col, st);
      box(s, 38, 30, 24, 5, { border: "single", style: { fg: edgeFor(col, st) }, title: [["applier", { fg: col, bold: true }]] });
      text(s, 40, 31, "[fast]", { fg: col, bold: true });
      text(s, 47, 31, "改文件與名稱", { fg: P.fg }, 12);
      progressBar(s, 40, 32, 12, sp, { fill: c2 });
      text(s, 53, 32, pct(sp), { fg: c2, bold: true });
      text(s, 40, 33, stText(st), { fg: c2, bold: st !== "idle", dim: st === "running" && blink(t, 1) });
    }
    if (seen(T.watch[0])) {
      const st = stateOf(t, T.watch), sp = clamp(span(t, ...T.watch));
      const col = C.watch, c2 = stCol(col, st);
      box(s, 63, 30, 24, 5, { border: "single", style: { fg: edgeFor(col, st) }, title: [["watcher", { fg: col, bold: true }], [" · 背景", { fg: P.dim }]] });
      text(s, 65, 31, "bun test 全套", { fg: P.fg }, 20);
      progressBar(s, 65, 32, 12, sp, { fill: c2 });
      text(s, 78, 32, pct(sp), { fg: c2, bold: true });
      const n = Math.round(sp * 182);
      text(s, 65, 33, st === "idle" ? "" : `${String(n).padStart(3)}/182  ${st === "done" ? "✓" : "●"}`, { fg: c2, bold: true, dim: st === "running" && blink(t, 2) });
    }

    // ---- verifier (rows 35-38)
    if (seen(T.ver1[0] - 0.4)) {
      const refuted = inWin(T.ver1[1], T.ver2[0]);
      const confirmed = t >= T.ver2[1];
      const second = t >= T.ver2[0] - 0.4;
      const run = inWin(T.ver1[0], T.ver1[1]) || inWin(T.ver2[0], T.ver2[1]);
      const vc = confirmed ? P.green : refuted ? C.bad : C.verifier;
      const edge = confirmed ? mix(P.line, P.green, 0.8) : refuted ? C.bad : run ? mix(P.line, C.verifier, 0.85) : P.line;
      const flash = refuted && t - T.ver1[1] < 1.2 && Math.floor((t - T.ver1[1]) * 6) % 2 === 0;
      if (flash) fill(s, 3, 35, 84, 4, { bg: mix(P.bg, C.bad, 0.28) });
      const bg = flash ? { bg: mix(P.bg, C.bad, 0.28) } : {};
      box(s, 3, 35, 84, 4, {
        border: refuted || confirmed ? "heavy" : "single", style: { fg: edge },
        title: [["verifier", { fg: C.verifier, bold: true }], [second ? " #2 · 全新 context" : " #1", { fg: P.dim }], [" · 唯讀", { fg: P.dim }]],
      });
      const r: [number, number] = second ? T.ver2 : T.ver1;
      const sp = clamp(span(t, ...r));
      if (refuted) {
        spans(s, 5, 36, [["× REFUTED", { fg: C.bad, bold: true }], ["  不放行，退回修補", { fg: P.fg }]], bg, 78);
        text(s, 5, 37, "舊 token 驗證路徑仍接受 HS256", { fg: P.white, bold: true, ...bg }, 78);
      } else if (confirmed) {
        spans(s, 5, 36, [["✓ CONFIRMED", { fg: P.green, bold: true }], ["  新 context 重驗，簽章與輪替都過", { fg: P.fg }]], bg, 78);
        text(s, 5, 37, "HS256 路徑已移除，雙 key 過渡期生效", { fg: P.dim, ...bg }, 78);
      } else {
        spans(s, 5, 36, [["● 驗證中 ", { fg: C.verifier, bold: true, dim: blink(t) }], [second ? "重驗：舊 token 是否仍被接受" : "對照 Plan 與 3 個發現", { fg: P.fg }]], bg, 78);
        progressBar(s, 5, 37, 40, run ? sp : 0, { fill: C.verifier });
        text(s, 46, 37, pct(run ? sp : 0), { fg: C.verifier, bold: true });
      }
    }

    // ---- connectors: lines first, dots second
    type Conn = { pts: [number, number][]; color: number; on: boolean; at: number; speed?: number; dots?: number; phase?: number };
    const L = (y: number): [number, number][] => [[2, 8], [1, 8], [1, y], [2, y]];
    const conns: Conn[] = [
      { pts: L(13), color: C.scout, on: inWin(T.scout[0] - 0.2, T.scout[0] + 1.0), at: T.scout[0] - 0.2, speed: 0.9, dots: 2 },
      { pts: [[33, 13], [37, 13]], color: C.secrev, on: inWin(T.scout[1], T.scout[1] + 1.0), at: T.scout[1], speed: 1.3, dots: 2 },
      { pts: L(17), color: C.plan, on: inWin(T.plan - 0.2, T.plan + 0.8), at: T.plan - 0.2, speed: 0.9, dots: 2 },
      { pts: [[55, 17], [59, 17]], color: C.gate, on: inWin(T.critic[1], T.gate + 0.4), at: T.critic[1], speed: 1.3, dots: 2 },
      { pts: L(22), color: C.complex, on: inWin(T.send1, T.deny), at: T.send1, speed: 0.9, dots: 2 },
      { pts: L(22), color: C.rigorous, on: inWin(T.resend, T.pass1), at: T.send1, speed: 0.9, dots: 2 },
      { pts: L(22), color: C.fast, on: inWin(T.resend, T.pass1), at: T.send1, speed: 0.9, dots: 2, phase: 0.45 },
      { pts: L(22), color: C.rigorous, on: inWin(T.fixSend, T.fixPass), at: T.send1, speed: 0.9, dots: 2 },
      { pts: [[20, 26], [20, 29]], color: C.rigorous, on: inWin(T.pass1, T.sec1[0] + 0.4) || inWin(T.fixPass, T.fix[0] + 0.6), at: T.pass1 - 4.2, speed: 1.5, dots: 2 },
      { pts: [[49, 26], [49, 29]], color: C.fast, on: inWin(T.pass1, T.app[0] + 0.4), at: T.pass1 - 4.2, speed: 1.5, dots: 2 },
      { pts: [[2, 32], [1, 32], [1, 9], [2, 9]], color: C.rigorous, on: inWin(T.sec1[1], T.sec1[1] + 0.9) || inWin(T.fix[1], T.fix[1] + 0.9), at: T.sec1[1], speed: 0.7, dots: 2 },
      { pts: L(36), color: C.verifier, on: inWin(T.ver1[0] - 0.4, T.ver1[0] + 0.3) || inWin(T.ver2[0] - 0.4, T.ver2[0] + 0.3), at: T.ver1[0] - 0.4, speed: 1.0, dots: 2 },
      { pts: [[87, 32], [88, 32], [88, 8], [87, 8]], color: C.watch, on: inWin(T.watch[1], T.watch[1] + 1.0), at: T.watch[1], speed: 0.7, dots: 2 },
      { pts: [[87, 37], [88, 37], [88, 9], [87, 9]], color: C.bad, on: inWin(T.ver1[1], T.ver1[1] + 0.9), at: T.ver1[1], speed: 0.7, dots: 2 },
      { pts: [[87, 37], [88, 37], [88, 9], [87, 9]], color: P.green, on: inWin(T.ver2[1], T.ver2[1] + 0.9), at: T.ver1[1], speed: 0.7, dots: 2 },
    ];
    for (const draw of ["lines", "dots"] as const) {
      for (const c of conns) {
        if (!seen(c.at)) continue;
        if (draw === "dots" && !c.on) continue;
        connector(s, c.pts, {
          style: { fg: c.on ? mix(P.line, c.color, 0.55) : P.line },
          arrow: "end", draw, t, dots: c.dots ?? 2, speed: c.speed ?? 0.8, phase: c.phase ?? 0,
          dotStyle: { fg: bright(c.color) }, trail: 3,
        });
      }
    }

    // ---- log (rows 39-43)
    if (seen(2.8)) {
      box(s, 1, 39, 88, 5, { border: "single", style: { fg: P.line }, title: [["session log", { fg: P.fg, bold: true }]] });
      logPane(s, 3, 40, 84, 3, LOG, t);
    }

    // ---- prompt / completion line
    if (t < T.green) {
      const full = "shoal 換掉 JWT 簽章並輪替 secret";
      const typed = Math.floor(span(t, 0.3, 1.8) * [...full].length);
      const shown = takeClusters(full, typed);
      spans(s, 1, 44, [["~/app", { fg: C.main }], [" $ ", { fg: P.dim }], [shown, { fg: P.white }]]);
      s.put(1 + 8 + strWidth(shown), 44, typed < [...full].length || Math.floor(t * 2) % 2 === 0 ? "█" : " ", { fg: P.white });
    } else {
      const bg = mix(P.panel, P.green, 0.25);
      fill(s, 1, 44, 88, 1, { bg });
      spans(s, 2, 44, [["● 全綠", { fg: P.green, bold: true }], ["  JWT 已換 RS256 · secret 已輪替 · 182/182 · 驗證 CONFIRMED", { fg: P.white }]], { bg });
    }
    fill(s, 1, 45, 88, 1, { bg: P.panel });
    spans(s, 2, 45, [["lanes ", { fg: P.dim }], ["fast", { fg: C.fast }], [" · ", { fg: P.faint }], ["complex", { fg: C.complex }], [" · ", { fg: P.faint }], ["rigorous", { fg: C.rigorous, bold: true }]], { bg: P.panel });
    right(s, 87, 45, "安全工作只走 rigorous", { fg: P.dim, bg: P.panel });

    // ---- loop outro
    if (t > T.fade) for (const c of s.cells) c.dim = true;
    return s;
  },
});

export default scene;
if (import.meta.main) await runScene(scene);
