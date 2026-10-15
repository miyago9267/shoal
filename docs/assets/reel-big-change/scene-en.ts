/**
 * shoal big change (English): move session store from in-memory to Redis across 6 modules.
 * main -> scout x3 -> researcher x2 -> Plan / plan-critic / Miyago gate
 *      -> 6 slices -> guard -> applier / executor, watcher in background -> verifier.
 * 90x46 portrait grid, 35 s loop @ 30 fps. Adapted from reel-lanes/scene.ts.
 *
 *   bun scene.ts --frame 0,100,230,450,660,800,1000 --strict
 *   bash ~/.claude/skills/term-reels/scripts/render.sh scene.ts
 */
import {
  palette as P, defineScene, runScene,
  text, spans, right, fill, box, hline, connector, progressBar,
  logPane, LogEntry, stamp, span, counter, noise1, strWidth, takeClusters, mix, clamp, padEndW,
} from "/Users/miyago/.claude/skills/term-reels/engine";

const COLS = 90, ROWS = 46, DURATION = 35, SEED = 41;

// lane colors reused from reel-lanes; new roles get their own
const C = {
  you: P.white, main: P.blue, fast: P.green, complex: P.yellow, guard: P.purple, watch: P.cyan, bad: P.red,
  scout: P.orange, research: P.pink, critic: 0xe58cff, verify: 0x4fd6a8, gate: P.yellow,
};
const bright = (c: number) => mix(c, P.white, 0.45);

// ------------------------------------------------------------------ timing table
const T = {
  route: 3.0,
  scoutSend: 3.6, researchSend: 7.8,
  planWrite: [11.8, 13.2] as [number, number],
  critic1: [13.4, 14.6] as [number, number],   // REVISE at [1]
  fix: [15.0, 16.3] as [number, number],       // main adds the rollback step
  critic2: [16.4, 17.6] as [number, number],   // READY at [1]
  gate: [17.8, 19.2] as [number, number],      // approved at [1]
  p1End: 19.8,
  cards: 20.0, labels: 21.0, burst: 21.8,
  guard0: 22.8, guardStep: 0.25,
  watch: [24.2, 30.0] as [number, number],
  verify: [30.2, 31.6] as [number, number],
  integrate: 32.2, green: 33.0,
  fade: DURATION - 0.5,
};

const SCOUTS = [
  { name: "api", x: 3, w: 27, run: [3.8, 6.4], f: ["auth.ts:42 reads sess", "mw.ts:18 writes sid"] },
  { name: "store", x: 31, w: 27, run: [3.8, 7.0], f: ["store.ts:7 global Map", "store.ts:63 clears TTL"] },
  { name: "tests", x: 59, w: 28, run: [3.8, 7.6], f: ["sess.spec:31 mocks Map", "e2e.spec:12 shared state"] },
];
const RESEARCH = [
  { name: "arm experiment", x: 3, w: 41, run: [8.0, 11.0], f: ["hash sess:{sid} + EXPIRE sliding TTL", "Lua atomic touch update"] },
  { name: "arm control", x: 45, w: 42, run: [8.0, 11.6], f: ["TTL drift: old tabs get kicked", "failover loses ~2s of writes"] },
];

interface Slice { id: string; name: string; lane: "fast" | "complex"; role: string; run: [number, number]; }
const SLICES: Slice[] = [
  { id: "S1", name: "api names", lane: "fast", role: "applier", run: [24.6, 27.0] },
  { id: "S2", name: "mw names", lane: "fast", role: "applier", run: [24.6, 27.4] },
  { id: "S3", name: "fix tests", lane: "fast", role: "applier", run: [24.6, 28.0] },
  { id: "S4", name: "config", lane: "fast", role: "applier", run: [24.6, 26.6] },
  { id: "S5", name: "Redis", lane: "complex", role: "executor", run: [24.6, 29.4] },
  { id: "S6", name: "migration", lane: "complex", role: "executor", run: [24.8, 30.0] },
];
const LANE_COLOR = { fast: C.fast, complex: C.complex };
const CARD_X = (i: number) => 3 + 14 * i;
const CARD_W = (i: number) => (i === 5 ? 14 : 13);
const CX = (i: number) => CARD_X(i) + 6;
const PASS_AT = SLICES.map((_, i) => T.guard0 + i * T.guardStep);
const RET_END = (s: Slice) => s.run[1];

// ------------------------------------------------------------------ counters (one source for stats box, guard box and log)
const passes = (t: number) => PASS_AT.filter((a) => t >= a).length;
const sent = (t: number) => (t >= T.burst ? 6 : 0);
const returned = (t: number) => SLICES.filter((s) => t >= RET_END(s)).length;
const shown = (t: number) => (t < T.cards ? 0 : Math.min(6, Math.floor((t - T.cards) / 0.13) + 1));

const MAIN_STATE: Array<[number, string, number]> = [
  [0, "Idle", P.dim],
  [2.4, "Read request: session store, 6 modules", P.white],
  [T.route, "Decide route = explore_then_plan", C.main],
  [T.scoutSend, "Dispatch scout ×3 in parallel: api / store / tests", C.scout],
  [T.researchSend, "Same batch: researcher ×2, experiment + control", C.research],
  [T.planWrite[0], "Collect evidence, write Plan v1", C.main],
  [T.critic1[0], "Send Plan v1 to plan-critic", C.critic],
  [T.critic1[1], "REVISE: rollback missing, fix Plan", C.bad],
  [T.critic2[0], "Plan v2 re-review", C.critic],
  [T.critic2[1], "READY; data/migration risk, awaiting Miyago approval", C.gate],
  [T.gate[1], "Approved, listing slices", P.green],
  [T.cards + 0.4, "List 6 slices, tag lanes", C.main],
  [T.burst, "Dispatch 6 slices in parallel", C.main],
  [T.guard0, "guard releases them one by one", C.guard],
  [T.watch[0], "Waiting; watcher runs full tests in background", C.watch],
  [T.verify[0], "Dispatch verifier", C.verify],
  [T.integrate, "Integrate 6 slices", C.main],
  [T.green, "All green, done", P.green],
];
const mainState = (t: number) => MAIN_STATE.reduce((cur, e) => (t >= e[0] ? e : cur), MAIN_STATE[0]!);

const PLAN_LINES = [
  "1  Extract SessionStore interface (api / middleware)",
  "2  Add RedisStore adapter, connection via config",
  "3  Migrate: dual-write → switch reads → retire in-memory",
  "4  Tests use a redis test container",
];
const ROLLBACK = "5  Rollback: flag back to in-memory, keep dual-write 1 week";

// ------------------------------------------------------------------ log
const LOG: LogEntry[] = [];
{
  const add = (t: number, tag: string, color: number, msg: string, hot?: boolean) =>
    LOG.push({ t, line: [[stamp(t) + "  ", { fg: P.dim }], [padEndW(tag, 12), { fg: color }], [msg, { fg: hot ? P.white : P.fg }]] });
  add(0.9, "shoal", P.dim, "role routing loaded · guard on");
  add(2.4, "you", C.you, "Move session store from in-memory to Redis", true);
  add(T.route, "main", C.main, "route = explore_then_plan", true);
  add(T.scoutSend, "main", C.main, "Dispatch scout ×3 in parallel · api / store / tests");
  SCOUTS.forEach((s) => add(s.run[1], "scout", C.scout, `${s.name} reported 2 items · ${s.f[0]!.split(" ")[0]}`));
  add(T.researchSend, "main", C.main, "Same batch: researcher ×2 · experiment / control", true);
  add(RESEARCH[0]!.run[1], "researcher", C.research, "experiment · Redis hash + EXPIRE");
  add(RESEARCH[1]!.run[1], "researcher", C.research, "control · TTL drift, failover loses writes");
  add(T.planWrite[0], "main", C.main, "Plan v1 written");
  add(T.critic1[1], "plan-critic", C.critic, "REVISE · rollback missing", true);
  add(T.critic2[0], "main", C.main, "Rollback added, Plan v2 re-review");
  add(T.critic2[1], "plan-critic", C.critic, "READY", true);
  add(T.gate[0], "gate", C.gate, "Miyago approval · data/migration risk trigger");
  add(T.gate[1], "gate", P.green, "Miyago approved", true);
  add(T.burst, "main", C.main, "Dispatch 6 slices in parallel · 4 [fast] 2 [complex]", true);
  SLICES.forEach((s, i) => add(PASS_AT[i]!, "guard", C.guard, `release ${s.id} [${s.lane}]→${s.role} · ${i + 1}/6`, i === 5));
  SLICES.forEach((s) => add(RET_END(s), s.role, LANE_COLOR[s.lane], `${s.id} ${s.name} done`));
  add(T.watch[0], "watcher", C.watch, "full tests in background, main not blocked");
  add(T.watch[1], "watcher", C.watch, "bun test 214/214 passed", true);
  add(T.verify[1], "verifier", C.verify, "CONFIRMED · 214/214 · no Map left", true);
  add(T.integrate, "main", C.main, "Integrate 6 slices");
  add(T.green, "shoal", P.green, "All green · released 6 · blocked 0 · dispatched 6", true);
  LOG.sort((a, b) => a.t - b.t);
}

// ------------------------------------------------------------------ helpers
const clock = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const pct = (x: number) => String(Math.round(clamp(x) * 100)).padStart(3) + "%";
const typed = (str: string, t: number, t0: number, t1: number) => takeClusters(str, Math.floor(span(t, t0, t1) * [...str].length));
const inWin = (t: number, a: number, b: number) => t >= a && t < b;
const blink = (t: number, k = 4, i = 0) => Math.floor(t * k + i) % 2 === 0;
const mkTitle = (txt: string, col: number, extra = "") => [[txt, { fg: col, bold: true }], ...(extra ? [[extra, { fg: P.dim }]] : [])] as any;
const edgeOf = (col: number, on: boolean, done: boolean) => (on ? mix(P.line, col, 0.85) : done ? mix(P.line, col, 0.45) : P.line);

// ------------------------------------------------------------------ scene
export const scene = defineScene({
  name: "shoal-big-change-en",
  cols: COLS, rows: ROWS, fps: 30, duration: DURATION, seed: SEED,

  frame(t, _f, ctx) {
    const s = ctx.screen();
    const seen = (at: number) => t >= at;
    const p1 = t < T.p1End;

    // ---- title + tagline
    if (seen(0.1)) {
      spans(s, 1, 0, [["shoal", { fg: P.white, bold: true }], ["  ·  ", { fg: P.dim }], ["Big cross-module change: explore, plan, approve, build", { fg: P.fg }]]);
      right(s, 88, 0, clock(t) + " / " + clock(DURATION), { fg: P.dim });
    }
    if (seen(0.6)) {
      const tag = "One color per role, one boundary each; risk needs Miyago's approval";
      text(s, 1, 1, takeClusters(tag, Math.floor(span(t, 0.6, 2.4) * 70)), { fg: mix(P.fg, C.main, 0.3) });
    }
    if (seen(0.8)) hline(s, 1, 2, 88, { fg: P.faint });

    // ---- task + guard counter
    if (seen(1.0)) {
      box(s, 3, 3, 58, 3, { border: "rounded", style: { fg: seen(2.4) ? P.white : P.line }, title: [["Task", { fg: C.you, bold: true }]] });
      text(s, 5, 4, typed("Move session store from in-memory to Redis, 6 modules", t, 1.3, 2.4), { fg: P.white }, 54);
    }
    if (seen(1.2)) {
      const flash = PASS_AT.some((a) => t >= a && t < a + 0.15);
      box(s, 62, 3, 25, 3, { border: "rounded", style: { fg: flash ? C.guard : P.line }, title: [["guard count", { fg: C.guard, bold: true }]] });
      const p = passes(t);
      spans(s, 64, 4, [
        ["sent ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
        [" pass ", { fg: P.dim }], [String(p), { fg: p ? P.green : P.white, bold: true }],
        [" block ", { fg: P.dim }], ["0", { fg: P.white, bold: true }],
      ], {}, 22);
    }

    // ---- main
    if (seen(1.5)) {
      const [, label, lc] = mainState(t);
      const busy = t > 2.4 && t < T.green;
      box(s, 3, 6, 84, 5, { border: "rounded", style: { fg: mix(P.line, C.main, 0.6) }, title: [["main", { fg: C.main, bold: true }], [" · slices, decisions, integration; never does the work", { fg: P.dim }]] });
      spans(s, 5, 7, [["●", { fg: t >= T.green ? P.green : P.yellow, dim: busy && blink(t) }], [" " + label, { fg: lc, bold: true }]], {}, 80);
      const mp = clamp(span(t, 2.4, T.green));
      text(s, 5, 8, "prog", { fg: P.dim });
      progressBar(s, 10, 8, 24, mp, { fill: C.main });
      text(s, 35, 8, pct(mp), { fg: C.main, bold: true });
      spans(s, 42, 8, [
        ["slices ", { fg: P.dim }], [String(shown(t)), { fg: P.white, bold: true }], ["/6", { fg: P.dim }],
        ["   back ", { fg: P.dim }], [String(returned(t)), { fg: returned(t) ? P.green : P.white, bold: true }], ["/6", { fg: P.dim }],
      ], {}, 40);
      const planSt: [string, number] =
        t < T.planWrite[0] ? ["—", P.dim] :
        t < T.critic1[0] ? ["v1 draft", P.fg] :
        t < T.critic1[1] ? ["v1 in review", C.critic] :
        t < T.critic2[0] ? ["v1 REVISE", C.bad] :
        t < T.critic2[1] ? ["v2 re-review", C.critic] :
        t < T.gate[1] ? ["v2 READY", P.green] : ["v2 approved", P.green];
      spans(s, 5, 9, [
        ["route ", { fg: P.dim }], [seen(T.route) ? "explore_then_plan" : "—", { fg: seen(T.route) ? C.main : P.dim, bold: true }],
        ["   plan ", { fg: P.dim }], [planSt[0], { fg: planSt[1], bold: true }],
      ], {}, 80);
    }

    // =============================================================== phase 1: explore, plan, approve
    if (p1) {
      // scouts
      SCOUTS.forEach((sc, i) => {
        if (t < T.scoutSend - 0.2 + i * 0.1) return;
        const st = t < sc.run[0] ? 0 : t < sc.run[1] ? 1 : 2;
        const pr = clamp(span(t, sc.run[0], sc.run[1]));
        const col = st === 2 ? P.green : C.scout;
        box(s, sc.x, 15, sc.w, 5, { border: "single", style: { fg: edgeOf(C.scout, st === 1, st === 2) }, title: mkTitle("scout", C.scout, " · " + sc.name) });
        progressBar(s, sc.x + 2, 16, 12, pr, { fill: col });
        text(s, sc.x + 15, 16, pct(pr), { fg: col, bold: true });
        text(s, sc.x + 20, 16, st === 2 ? "✓" : st === 1 ? "●" : "◇", { fg: col, dim: st === 1 && blink(t, 4, i) });
        sc.f.forEach((ln, k) => {
          const a = sc.run[0] + (sc.run[1] - sc.run[0]) * (0.35 + 0.35 * k);
          text(s, sc.x + 2, 17 + k, typed(ln, t, a, a + 0.5), { fg: P.white }, sc.w - 4);
        });
      });
      // researchers
      RESEARCH.forEach((rs, i) => {
        if (t < T.researchSend - 0.2) return;
        const st = t < rs.run[0] ? 0 : t < rs.run[1] ? 1 : 2;
        const pr = clamp(span(t, rs.run[0], rs.run[1]));
        const col = st === 2 ? P.green : C.research;
        box(s, rs.x, 20, rs.w, 5, { border: "single", style: { fg: edgeOf(C.research, st === 1, st === 2) }, title: mkTitle("researcher", C.research, " · " + rs.name) });
        progressBar(s, rs.x + 2, 21, 20, pr, { fill: col });
        text(s, rs.x + 23, 21, pct(pr), { fg: col, bold: true });
        text(s, rs.x + 28, 21, st === 2 ? "✓ done" : st === 1 ? "● searching" : "◇ idle", { fg: col, dim: st === 1 && blink(t, 4, i) });
        rs.f.forEach((ln, k) => {
          const a = rs.run[0] + (rs.run[1] - rs.run[0]) * (0.35 + 0.35 * k);
          text(s, rs.x + 2, 22 + k, typed(ln, t, a, a + 0.5), { fg: P.white }, rs.w - 4);
        });
      });
      // plan
      if (seen(T.planWrite[0] - 0.2)) {
        const v2 = t >= T.fix[0];
        const revise = inWin(t, T.critic1[1], T.critic2[0]);
        box(s, 3, 25, 84, 7, { border: "single", style: { fg: edgeOf(C.main, inWin(t, T.planWrite[0], T.planWrite[1]) || inWin(t, T.fix[0], T.fix[1]), true) }, title: mkTitle(v2 && t >= T.fix[1] ? "Plan v2" : "Plan v1", C.main, " · written by main") });
        PLAN_LINES.forEach((ln, k) => {
          const a = T.planWrite[0] + k * 0.35;
          text(s, 5, 26 + k, typed(ln, t, a, a + 0.35), { fg: P.fg }, 80);
        });
        if (v2) text(s, 5, 30, typed(ROLLBACK, t, T.fix[0], T.fix[1]), { fg: C.gate, bold: true }, 80);
        else if (revise) text(s, 5, 30, blink(t, 3) ? "5  ???" : "", { fg: C.bad, bold: true });
        if (t >= T.fix[0]) text(s, 78, 30, t >= T.fix[1] ? "+ new" : "", { fg: C.gate, bold: true });
      }
      // plan-critic
      if (seen(T.critic1[0] - 0.2)) {
        const rev1 = inWin(t, T.critic1[0], T.critic1[1]), rev2 = inWin(t, T.critic2[0], T.critic2[1]);
        const isRevise = inWin(t, T.critic1[1], T.critic2[0]);
        const isReady = t >= T.critic2[1];
        const col = isRevise ? C.bad : isReady ? P.green : C.critic;
        box(s, 3, 32, 56, 5, { border: "single", style: { fg: isRevise ? mix(P.line, C.bad, 0.8) : edgeOf(C.critic, rev1 || rev2, isReady) }, title: mkTitle("plan-critic", C.critic, " · reviews Plan") });
        const pr = rev1 ? span(t, ...T.critic1) : rev2 ? span(t, ...T.critic2) : 1;
        progressBar(s, 5, 33, 24, pr, { fill: col });
        text(s, 30, 33, pct(pr), { fg: col, bold: true });
        text(s, 36, 33, rev1 || rev2 ? "● reviewing" : isRevise ? "× revise" : "✓ passed", { fg: col, bold: true, dim: (rev1 || rev2) && blink(t) });
        if (isRevise) {
          text(s, 5, 34, "× REVISE", { fg: C.bad, bold: true });
          text(s, 5, 35, "1 issue: no rollback, failed migration is stuck", { fg: P.white }, 52);
        } else if (isReady) {
          text(s, 5, 34, "✓ READY", { fg: P.green, bold: true });
          text(s, 5, 35, "rollback added, risk contained", { fg: P.white }, 52);
        } else {
          text(s, 5, 34, rev2 ? "Re-review v2: check rollback" : "Review v1: scope, order, risk", { fg: P.dim }, 52);
        }
      }
      // Miyago gate
      if (seen(T.gate[0] - 0.1)) {
        const wait = inWin(t, T.gate[0], T.gate[1]), ok = t >= T.gate[1];
        const hot = wait && blink(t, 4);
        if (hot) fill(s, 64, 32, 23, 5, { bg: mix(P.bg, C.gate, 0.22) });
        box(s, 64, 32, 23, 5, { border: "heavy", style: { fg: ok ? P.green : hot ? C.gate : mix(P.line, C.gate, 0.7) }, title: mkTitle("Miyago gate", ok ? P.green : C.gate) });
        const bg = hot ? { bg: mix(P.bg, C.gate, 0.22) } : {};
        text(s, 66, 33, "data/migration", { fg: P.fg }, 19);
        text(s, 66, 34, "risk trigger", { fg: P.fg }, 19);
        text(s, 66, 35, ok ? "✓ approved" : "◆ awaiting you", { fg: ok ? P.green : C.gate, bold: true }, 19);
        void bg;
      }
      // fade the stage out just before phase 2
      if (t > T.p1End - 0.5) for (let y = 15; y < 37; y++) for (let x = 0; x < COLS; x++) s.cells[y * COLS + x]!.dim = true;
    }

    // =============================================================== phase 2: slices, guard, lanes, watcher, verifier
    if (!p1) {
      const n = shown(t);
      // cards
      SLICES.forEach((sl, i) => {
        if (i >= n) return;
        const lc = LANE_COLOR[sl.lane];
        const labelAt = T.labels + i * 0.1;
        let line: string, fg: number, edge: number;
        const st = t < sl.run[0] ? 0 : t < sl.run[1] ? 1 : 2;
        if (st === 2) [line, fg, edge] = ["✓ done", P.green, mix(P.line, P.green, 0.5)];
        else if (st === 1) [line, fg, edge] = ["● running", lc, mix(P.line, lc, 0.7)];
        else if (t >= PASS_AT[i]!) [line, fg, edge] = ["▸ passed", lc, mix(P.line, lc, 0.7)];
        else if (t >= T.burst) [line, fg, edge] = [`[${sl.lane}] ▸`, lc, lc];
        else if (t >= labelAt) [line, fg, edge] = [`[${sl.lane}]`, lc, P.line];
        else [line, fg, edge] = ["untagged", P.dim, P.line];
        const flash = inWin(t, T.burst, T.burst + 0.6) && blink(t, 8);
        if (flash) fill(s, CARD_X(i), 11, CARD_W(i), 4, { bg: mix(P.bg, lc, 0.3) });
        box(s, CARD_X(i), 11, CARD_W(i), 4, { border: "single", style: { fg: edge }, title: [[sl.id, { fg: fg, bold: true }]] });
        text(s, CARD_X(i) + 2, 12, sl.name, { fg: P.white }, CARD_W(i) - 4);
        text(s, CARD_X(i) + 2, 13, line, { fg: fg }, CARD_W(i) - 4);
      });
      // guard
      if (seen(T.cards + 0.3)) {
        const p = passes(t);
        const flash = PASS_AT.some((a) => t >= a && t < a + 0.12);
        const col = flash ? bright(C.guard) : mix(P.line, C.guard, 0.85);
        box(s, 3, 20, 84, 4, { border: "heavy", style: { fg: col }, title: [["GUARD", { fg: C.guard, bold: true }], [" · every dispatch must carry a lane tag", { fg: P.dim }]] });
        if (t < T.burst) spans(s, 5, 21, [["◇ idle ", { fg: P.dim }], ["waiting for main", { fg: P.dim }]], {}, 80);
        else if (p < 6) spans(s, 5, 21, [["● checking each ", { fg: C.guard, bold: true }], ["tag present · role matches lane", { fg: P.fg }]], {}, 80);
        else spans(s, 5, 21, [["● all released ", { fg: P.green, bold: true }], ["6/6 slices tagged, roles match", { fg: P.fg }]], {}, 80);
        spans(s, 5, 22, [
          ["[fast]", { fg: C.fast, bold: true }], ["→applier  ", { fg: P.fg }],
          ["[complex]", { fg: C.complex, bold: true }], ["→executor    ", { fg: P.fg }],
          ["sent ", { fg: P.dim }], [String(sent(t)), { fg: P.white, bold: true }],
          ["  pass ", { fg: P.dim }], [String(p), { fg: p ? P.green : P.white, bold: true }],
          ["  block ", { fg: P.dim }], ["0", { fg: P.white, bold: true }],
        ], {}, 80);
      }
      // lanes
      if (seen(T.cards + 0.5)) {
        const ap = SLICES.slice(0, 4), ex = SLICES.slice(4);
        const stOf = (x: Slice) => (t < x.run[0] ? 0 : t < x.run[1] ? 1 : 2);
        box(s, 3, 29, 56, 6, { border: "single", style: { fg: edgeOf(C.fast, ap.some((x) => stOf(x) === 1), ap.every((x) => stOf(x) === 2)) }, title: mkTitle("applier", C.fast, " · [fast] mechanical renames, config") });
        ap.forEach((x, i) => {
          const y = 30 + i, sp = clamp(span(t, ...x.run)), st = stOf(x);
          const col = st === 2 ? P.green : st === 1 ? C.fast : P.dim;
          text(s, 5, y, x.id, { fg: col, bold: true });
          text(s, 8, y, x.name, { fg: st === 0 ? P.dim : P.white }, 10);
          progressBar(s, 20, y, 18, sp, { fill: col });
          text(s, 39, y, pct(sp), { fg: col, bold: true });
          text(s, 44, y, st === 2 ? "✓" : st === 1 ? "●" : "◇", { fg: col, dim: st === 1 && blink(t, 4, i) });
          text(s, 47, y, st === 0 ? "" : "tok " + Math.round(sp * 210 + 20 * noise1(SEED, t, i + 1)), { fg: P.dim }, 9);
        });
        box(s, 59, 29, 28, 6, { border: "single", style: { fg: edgeOf(C.complex, ex.some((x) => stOf(x) === 1), ex.every((x) => stOf(x) === 2)) }, title: mkTitle("executor", C.complex, " · [complex]") });
        ex.forEach((x, i) => {
          const y = 30 + i * 2, sp = clamp(span(t, ...x.run)), st = stOf(x);
          const col = st === 2 ? P.green : st === 1 ? C.complex : P.dim;
          text(s, 61, y, x.id, { fg: col, bold: true });
          text(s, 64, y, x.name, { fg: st === 0 ? P.dim : P.white }, 10);
          progressBar(s, 75, y, 7, sp, { fill: col });
          text(s, 82, y, pct(sp), { fg: col, bold: true });
          text(s, 61, y + 1, st === 2 ? "✓ done" : st === 1 ? "● running tok " + Math.round(sp * 520 + 40 * noise1(SEED, t, 7 + i)) : "◇ idle", { fg: col, dim: st === 1 && blink(t, 4, i) }, 24);
        });
      }
      // watcher
      if (seen(T.cards + 0.7)) {
        const run = inWin(t, ...T.watch), done = t >= T.watch[1];
        const wp = clamp(span(t, ...T.watch));
        const col = done ? P.green : run ? C.watch : P.dim;
        box(s, 3, 35, 40, 4, { border: "single", style: { fg: run ? mix(P.line, C.watch, 0.8) : done ? mix(P.line, C.watch, 0.4) : P.line }, title: mkTitle("watcher", C.watch, " · background") });
        text(s, 5, 36, "bun test", { fg: P.dim });
        progressBar(s, 14, 36, 12, wp, { fill: col });
        text(s, 27, 36, pct(wp), { fg: col, bold: true });
        const k = done ? 214 : counter(t, T.watch[0], T.watch[1], 0, 214, (x) => x);
        text(s, 32, 36, run || done ? `${String(k).padStart(3)}/214` : "", { fg: P.white, bold: true });
        text(s, 5, 37, done ? "✓ full suite passed" : run ? "● in background, main needn't wait" : "◇ idle", { fg: col, bold: run || done, dim: run && blink(t) }, 36);
      }
      // verifier
      if (seen(T.cards + 0.7)) {
        const run = inWin(t, ...T.verify), done = t >= T.verify[1];
        const col = done ? C.verify : run ? C.verify : P.dim;
        box(s, 43, 35, 44, 4, { border: "single", style: { fg: run ? mix(P.line, C.verify, 0.85) : done ? mix(P.line, C.verify, 0.6) : P.line }, title: mkTitle("verifier", C.verify, " · independent check") });
        text(s, 45, 36, done ? "✓ CONFIRMED" : run ? "● verifying" : "◇ idle", { fg: col, bold: run || done, dim: run && blink(t) }, 40);
        if (done) text(s, 45, 37, "214/214 pass · no Map left in 6 modules", { fg: P.white }, 40);
        else if (run) text(s, 45, 37, "Compare Plan v2 with diff", { fg: P.dim }, 40);
      }
    }

    // ---- connectors: lines first, dots second
    type Conn = { pts: [number, number][]; color: number; on: boolean; at: number; off?: number; speed?: number; dots?: number; trail?: number; reverse?: boolean; arrow?: "end" | "both" };
    const conns: Conn[] = [{ pts: [[31, 3], [31, 4]], color: C.you, on: false, at: 99 }];
    conns.length = 0;
    // phase 1
    SCOUTS.forEach((sc, i) => {
      const cx = sc.x + 13;
      const out = inWin(t, T.scoutSend, T.scoutSend + 1.0), back = inWin(t, sc.run[1], sc.run[1] + 0.8);
      conns.push({ pts: [[cx, 10], [cx, 14]], color: C.scout, on: out || back, at: T.scoutSend - 0.2 + i * 0.1, off: T.p1End, speed: 1.1, dots: 2, trail: 1, reverse: back && !out });
    });
    RESEARCH.forEach((rs, i) => {
      const out = inWin(t, T.researchSend, T.researchSend + 1.1), back = inWin(t, rs.run[1], rs.run[1] + 0.9);
      const pts: [number, number][] = i === 0 ? [[2, 8], [1, 8], [1, 22], [2, 22]] : [[87, 8], [88, 8], [88, 22], [87, 22]];
      conns.push({ pts, color: C.research, on: out || back, at: T.researchSend - 0.2, off: T.p1End, speed: 0.9, dots: 3, trail: 2, reverse: back && !out });
    });
    conns.push({ pts: [[2, 9], [1, 9], [1, 34], [2, 34]], color: C.critic, on: inWin(t, T.critic1[0] - 0.2, T.critic1[0] + 1.0) || inWin(t, T.critic2[0] - 0.2, T.critic2[0] + 1.0), at: T.critic1[0] - 0.2, off: T.p1End, speed: 0.9, dots: 3, trail: 2 });
    conns.push({ pts: [[58, 34], [63, 34]], color: C.gate, on: inWin(t, T.critic2[1], T.critic2[1] + 1.2), at: T.critic2[1], off: T.p1End, speed: 1.0, dots: 2, trail: 1 });
    // phase 2: card -> guard -> lane
    SLICES.forEach((sl, i) => {
      const cx = CX(i), lc = LANE_COLOR[sl.lane];
      conns.push({ pts: [[cx, 15], [cx, 19]], color: lc, on: inWin(t, T.burst, PASS_AT[i]! + 0.2), at: T.cards + 0.3, speed: 1.2, dots: 2, trail: 1 });
      conns.push({ pts: [[cx, 24], [cx, 28]], color: lc, on: inWin(t, PASS_AT[i]!, PASS_AT[i]! + 1.0), at: T.cards + 0.5, speed: 1.2, dots: 2, trail: 1 });
    });
    const anyRet = (xs: Slice[]) => xs.some((x) => inWin(t, RET_END(x), RET_END(x) + 0.8));
    conns.push({ pts: [[2, 32], [1, 32], [1, 9], [2, 9]], color: C.fast, on: anyRet(SLICES.slice(0, 4)), at: 26.0, speed: 0.8, dots: 3, trail: 2 });
    conns.push({ pts: [[87, 32], [88, 32], [88, 9], [87, 9]], color: C.complex, on: anyRet(SLICES.slice(4)), at: 28.6, speed: 0.8, dots: 3, trail: 2 });
    conns.push({ pts: [[2, 37], [1, 37], [1, 8], [2, 8]], color: C.watch, on: inWin(t, T.watch[1], T.watch[1] + 0.9), at: T.watch[0], speed: 0.8, dots: 3, trail: 2 });
    {
      const out = inWin(t, T.verify[0], T.verify[0] + 0.9), back = inWin(t, T.verify[1], T.verify[1] + 0.9);
      conns.push({ pts: [[87, 37], [88, 37], [88, 8], [87, 8]], color: C.verify, on: out || back, at: T.verify[0] - 0.1, speed: 0.8, dots: 3, trail: 2, reverse: out && !back, arrow: "both" });
    }
    for (const draw of ["lines", "dots"] as const) {
      for (const c of conns) {
        if (!seen(c.at) || (c.off !== undefined && t >= c.off)) continue;
        if (draw === "dots" && !c.on) continue;
        connector(s, c.pts, {
          style: { fg: c.on ? mix(P.line, c.color, 0.65) : P.line },
          arrow: c.arrow ?? "end", draw, t, dots: c.dots ?? 2, speed: c.speed ?? 0.9, trail: c.trail ?? 1,
          dotStyle: { fg: bright(c.color) }, reverse: c.reverse ?? false,
        });
      }
    }

    // ---- log
    if (seen(2.4)) {
      box(s, 1, 39, 88, 5, { border: "single", style: { fg: P.line }, title: [["session log", { fg: P.fg, bold: true }]] });
      logPane(s, 3, 40, 84, 3, LOG, t);
    }

    // ---- prompt / completion line
    if (t < T.green) {
      const full = "shoal move session store to Redis";
      const n = Math.floor(span(t, 0.3, 1.8) * [...full].length);
      const sh = takeClusters(full, n);
      spans(s, 1, 44, [["~/app", { fg: C.main }], [" $ ", { fg: P.dim }], [sh, { fg: P.white }]]);
      s.put(9 + strWidth(sh), 44, n < [...full].length || blink(t, 2) ? "█" : " ", { fg: P.white });
    } else {
      const bg = mix(P.panel, P.green, 0.25);
      fill(s, 1, 44, 88, 1, { bg });
      spans(s, 2, 44, [["● all green", { fg: P.green, bold: true }], ["  6 slices merged · pass 6 block 0 · 214/214 · verifier CONFIRMED", { fg: P.white }]], { bg }, 86);
    }
    fill(s, 1, 45, 88, 1, { bg: P.panel });
    spans(s, 2, 45, [
      ["main", { fg: C.main }], [" ", {}], ["scout", { fg: C.scout }], [" ", {}], ["researcher", { fg: C.research }], [" ", {}],
      ["plan-critic", { fg: C.critic }], [" ", {}], ["applier", { fg: C.fast }], [" ", {}], ["executor", { fg: C.complex }], [" ", {}],
      ["guard", { fg: C.guard }], [" ", {}], ["watcher", { fg: C.watch }], [" ", {}], ["verifier", { fg: C.verify }],
    ], { bg: P.panel }, 86);

    // ---- loop outro
    if (t > T.fade) for (const c of s.cells) c.dim = true;
    return s;
  },
});

export default scene;
if (import.meta.main) await runScene(scene);
