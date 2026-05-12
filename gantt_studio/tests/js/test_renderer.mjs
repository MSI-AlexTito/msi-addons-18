// Pure-JS test for the renderer's state machine: dirty flags, layout,
// virtual-grid slicing, arrow geometry, edge cases.
//
// The OWL Component is NOT instantiated. We construct instances via
// `Object.create(GanttStudioRenderer.prototype)` and exercise the methods
// (_diffProps, _beforeRender, _sliceVisibleRows) directly. OWL hooks and
// @web/core/virtual_grid_hook are stubbed so the import resolves under Node.

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.resolve(__dirname, "../../static/src/js");
const RENDERER = path.join(SRC_DIR, "gantt_studio_renderer.js");
const UTILS = path.join(SRC_DIR, "gantt_studio_utils.js");

// Stub browser globals that the renderer uses defensively.
// In a real browser these come from the DOM; under Node we provide just
// enough surface area for the unit tests to exercise the state machine.
if (typeof globalThis.requestAnimationFrame === "undefined") {
    globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
}
if (typeof globalThis.document === "undefined") {
    globalThis.document = {
        addEventListener: () => {},
        removeEventListener: () => {},
    };
}

// 1. Temp dir that simulates the Odoo asset bundle
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "gs_renderer_"));

// 2. Stub @odoo/owl
const owlStubPath = path.join(tmpDir, "node_modules", "@odoo", "owl");
fs.mkdirSync(owlStubPath, { recursive: true });
fs.writeFileSync(path.join(owlStubPath, "package.json"),
    JSON.stringify({ name: "@odoo/owl", main: "index.mjs", type: "module" }));
fs.writeFileSync(path.join(owlStubPath, "index.mjs"), `
export class Component { constructor() {} }
export function useRef() { return { el: null }; }
export function useState(s) { return s; }
export function onMounted() {}
export function onWillUnmount() {}
export function onWillRender() {}
export function onWillUpdateProps() {}
`);

// 3. Stub @web/core/virtual_grid_hook
const vghPath = path.join(tmpDir, "node_modules", "@web", "core");
fs.mkdirSync(vghPath, { recursive: true });
fs.writeFileSync(path.join(tmpDir, "node_modules", "@web", "package.json"),
    JSON.stringify({ name: "@web", type: "module" }));
fs.writeFileSync(path.join(vghPath, "virtual_grid_hook.js"), `
export function useVirtualGrid() {
    let _idx = undefined;
    return {
        get rowsIndexes() { return _idx; },
        get columnsIndexes() { return undefined; },
        setRowsHeights(h) {
            if (!h.length) { _idx = []; return; }
            _idx = [0, Math.min(9, h.length - 1)];
        },
        setColumnsWidths() {},
    };
}
`);

// Stub @web/core/py_js/py — only need evaluateBooleanExpr
const pyJsPath = path.join(tmpDir, "node_modules", "@web", "core", "py_js");
fs.mkdirSync(pyJsPath, { recursive: true });
fs.writeFileSync(path.join(pyJsPath, "py.js"), `
// Lightweight Python-expression evaluator for tests. Supports the subset
// we actually use in decoration/disable_drag_drop expressions:
//   - comparison: ==, !=, <, <=, >, >=, in
//   - boolean: and, or, not
//   - identifiers (read from context)
//   - string and number literals
// Falls back to "false" on anything not parseable.
//
// In production this stub is replaced by @web/core/py_js/py.js from Odoo
// which is a full py_js implementation.
export function evaluateBooleanExpr(expr, ctx = {}) {
    if (!expr) return false;
    // Replace Python literals/operators with JS equivalents.
    let js = expr
        .replace(/\\bTrue\\b/g, "true")
        .replace(/\\bFalse\\b/g, "false")
        .replace(/\\bNone\\b/g, "null")
        .replace(/\\band\\b/g, "&&")
        .replace(/\\bor\\b/g, "||")
        .replace(/\\bnot\\b/g, "!");
    // Build a function whose params are the ctx keys.
    try {
        const keys = Object.keys(ctx);
        const vals = keys.map((k) => ctx[k]);
        const fn = new Function(...keys, "return (" + js + ");");
        return Boolean(fn(...vals));
    } catch (e) {
        return false;
    }
}
export function evaluateExpr(expr, ctx = {}) {
    return evaluateBooleanExpr(expr, ctx);
}
`);

// 4. Copy source files and rewrite imports
fs.cpSync(RENDERER, path.join(tmpDir, "gantt_studio_renderer.js"));
fs.cpSync(UTILS, path.join(tmpDir, "gantt_studio_utils.js"));
for (const f of ["gantt_studio_renderer.js", "gantt_studio_utils.js"]) {
    const p = path.join(tmpDir, f);
    let s = fs.readFileSync(p, "utf-8").replace(/\/\*\*\s*@odoo-module\s*\*\*\//, "");
    s = s.replaceAll('"./gantt_studio_utils"', '"./gantt_studio_utils.js"');
    s = s.replaceAll('"@web/core/virtual_grid_hook"', '"@web/core/virtual_grid_hook.js"');
    s = s.replaceAll('"@web/core/py_js/py"', '"@web/core/py_js/py.js"');
    fs.writeFileSync(p.replace(/\.js$/, ".mjs"), s);
}

// 5. Import
process.chdir(tmpDir);
const mod = await import(path.join(tmpDir, "gantt_studio_renderer.mjs"));
const { GanttStudioRenderer } = mod;

let pass = 0, fail = 0;
function ok(name, cond, extra) {
    if (cond) { console.log("  OK  " + name); pass++; }
    else { console.log("  FAIL " + name + (extra ? " :: " + extra : "")); fail++; }
}
function section(s) { console.log("=".repeat(70)); console.log(s); }

// Helper: build a renderer instance without OWL setup.
function makeRenderer(props, virtualWindow = [0, 9]) {
    const r = Object.create(GanttStudioRenderer.prototype);
    r.props = props;
    // El componente real inicializa state con TODAS las claves; replicamos
    // ese contrato para que los `=== null` no caigan en undefined.
    r.state = {
        dragId: null, dragDx: 0,
        resizeId: null, resizeDx: 0, resizeEdge: null,
        editingId: null, editingValue: "",
        depDragFrom: null, depDragFromEdge: null, depDragTo: null,
        depPopover: null,
        collapsed: new Set(),
    };
    r.rootRef = { el: null };
    r._dirtyRange = true;
    r._dirtyLayout = true;
    r._dirtyArrows = true;
    let _idx = undefined;
    let _heights = [];
    r.virtualGrid = {
        get rowsIndexes() { return _idx; },
        setRowsHeights(h) {
            _heights = h;
            if (!h.length) { _idx = []; return; }
            _idx = [
                Math.min(virtualWindow[0], h.length - 1),
                Math.min(virtualWindow[1], h.length - 1),
            ];
        },
        __setVisibleRange(s, e) { _idx = [s, e]; },
    };
    return r;
}

const archInfo = {
    dateStart: "ds", dateStop: "de", defaultScale: "week",
    defaultGroupBy: null, colorField: null, barText: "name",
    progress: null, fieldsToFetch: [],
    showDependencies: true, showCriticalPath: true,
    autoReschedule: true, baselineSupport: true,
};

const records30 = Array.from({ length: 30 }, (_, i) => ({
    id: i + 1,
    name: `Task ${i + 1}`,
    display_name: `Task ${i + 1}`,
    ds: `2026-05-${String((i % 28) + 1).padStart(2, "0")}`,
    de: `2026-05-${String(Math.min(28, (i % 28) + 3)).padStart(2, "0")}`,
}));

const baseProps = {
    archInfo,
    resModel: "test.model",
    fields: {},
    records: records30,
    dependencies: [
        { id: 100, predecessor_id: 1, successor_id: 2, dep_type: "FS", lag_days: 0 },
        { id: 101, predecessor_id: 2, successor_id: 3, dep_type: "SS", lag_days: 1 },
        { id: 102, predecessor_id: 3, successor_id: 4, dep_type: "FF", lag_days: 0 },
        { id: 103, predecessor_id: 4, successor_id: 5, dep_type: "SF", lag_days: 0 },
    ],
    baselineLines: [],
    baselineId: false,
    criticalRecordIds: new Set([1, 2]),
    criticalDependencyIds: new Set([100]),
    scale: "week",
    criticalPathEnabled: true,
    onBarClick: () => {},
    onBarDrop: () => {},
};

// ─── [1] First render computes everything ──────────────────────────────
section("[1] First render: _beforeRender populates derived state");
const r = makeRenderer(baseProps);
r._beforeRender();
ok("dateRange computed",       !!r.dateRange?.start && !!r.dateRange?.end);
ok("headerTicks is array",     Array.isArray(r.headerTicks) && r.headerTicks.length > 0);
ok("viewportWidth > 800",      r.viewportWidth >= 800);
ok("allRows.length=30",        r.allRows.length === 30);
ok("totalHeight > header",     r.totalHeight > 40);
ok("totalHeight = header + 30×36",
   r.totalHeight === 40 + 30 * 36,
   `got ${r.totalHeight}`);
ok("barGeoById has 30 entries", r.barGeoById.size === 30);
ok("arrows length=4 (one per dep)", r.arrows.length === 4);
ok("FS arrow (id 100) is critical", r.arrows.find((a) => a.id === 100)?.critical === true);
ok("SS arrow (id 101) is NOT critical", r.arrows.find((a) => a.id === 101)?.critical === false);
ok("all 4 dep types produce paths", r.arrows.every((a) => a.d.length > 0));
ok("all 4 dep types produce arrow heads", r.arrows.every((a) => a.head.length > 0));
ok("dirty flags cleared", !r._dirtyRange && !r._dirtyLayout && !r._dirtyArrows);

// ─── [2] Virtualization ────────────────────────────────────────────────
section("[2] Virtualization slices rows to virtualGrid range");
ok("visibleRows.length matches virtual window",
   r.visibleRows.length === 10,
   `expected 10 got ${r.visibleRows.length}`);
ok("first visibleRow has rowIdx=0", r.visibleRows[0].rowIdx === 0);

r.virtualGrid.__setVisibleRange(5, 14);
r._beforeRender();
ok("after scrolling to 5-14: first rowIdx=5", r.visibleRows[0].rowIdx === 5);
ok("after scrolling: 10 visible", r.visibleRows.length === 10);

r.virtualGrid.__setVisibleRange(20, 29);
r._beforeRender();
ok("scroll to end: last rowIdx=29",
   r.visibleRows.at(-1).rowIdx === 29,
   `got ${r.visibleRows.at(-1).rowIdx}`);

// ─── [3] Dirty flags matrix ────────────────────────────────────────────
section("[3] _diffProps dirty flag matrix");
const tests = [
    {
        name: "no change → no flags",
        mutate: (p) => ({ ...p }),
        expect: { range: false, layout: false, arrows: false },
    },
    {
        name: "scale change → all dirty",
        mutate: (p) => ({ ...p, scale: "day" }),
        expect: { range: true, layout: true, arrows: true },
    },
    {
        name: "records change → all dirty",
        mutate: (p) => ({ ...p, records: p.records.slice(0, 5) }),
        expect: { range: true, layout: true, arrows: true },
    },
    {
        name: "deps change → arrows only",
        mutate: (p) => ({ ...p, dependencies: [] }),
        expect: { range: false, layout: false, arrows: true },
    },
    {
        name: "criticalDependencyIds change → arrows only",
        mutate: (p) => ({ ...p, criticalDependencyIds: new Set([101]) }),
        expect: { range: false, layout: false, arrows: true },
    },
    {
        name: "criticalRecordIds change → layout+arrows",
        mutate: (p) => ({ ...p, criticalRecordIds: new Set([5, 6]) }),
        expect: { range: false, layout: true, arrows: true },
    },
    {
        name: "baselineLines change → layout+arrows",
        mutate: (p) => ({ ...p, baselineLines: [{record_id: 1, date_start: "2026-05-01", date_stop: "2026-05-02"}] }),
        expect: { range: false, layout: true, arrows: true },
    },
    {
        name: "criticalPathEnabled toggle → layout+arrows",
        mutate: (p) => ({ ...p, criticalPathEnabled: !p.criticalPathEnabled }),
        expect: { range: false, layout: true, arrows: true },
    },
    {
        name: "archInfo identity change → all dirty",
        mutate: (p) => ({ ...p, archInfo: { ...p.archInfo } }),
        expect: { range: true, layout: true, arrows: true },
    },
];
for (const t of tests) {
    const rt = makeRenderer(baseProps);
    rt._beforeRender();
    rt._diffProps(t.mutate(baseProps));
    ok(t.name, rt._dirtyRange === t.expect.range
            && rt._dirtyLayout === t.expect.layout
            && rt._dirtyArrows === t.expect.arrows,
       `got R=${rt._dirtyRange} L=${rt._dirtyLayout} A=${rt._dirtyArrows}`);
}

// ─── [4] Row keys are stable ──────────────────────────────────────────
section("[4] Stable keys");
const rk = makeRenderer(baseProps);
rk._beforeRender();
const keys = rk.allRows.slice(0, 5).map((row) => row.key);
ok("keys are 'bar_<id>'",
   JSON.stringify(keys) === JSON.stringify(["bar_1","bar_2","bar_3","bar_4","bar_5"]));

// With grouping
const grouped = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, defaultGroupBy: "name" },  // group by name (each unique)
    records: records30.slice(0, 3),
});
grouped._beforeRender();
const groupKeys = grouped.allRows.filter((r) => r.type === "group").map((r) => r.key);
ok("group keys are 'group_<key>'",
   groupKeys.every((k) => k.startsWith("group_")),
   `got ${JSON.stringify(groupKeys)}`);

// ─── [5] Layout: bar geometry for first record ──────────────────────────
section("[5] Bar geometry");
const rgeo = makeRenderer(baseProps);
rgeo._beforeRender();
const firstBar = rgeo.allRows.find((row) => row.type === "bar" && row.record.id === 1);
ok("bar has x", typeof firstBar.x === "number");
ok("bar has y >= header", firstBar.y >= 40);
ok("bar has width >= 4 (min)", firstBar.width >= 4);
ok("bar has color (hex)", /^#[0-9a-f]{6}$/i.test(firstBar.color));
ok("bar has label", firstBar.label === "Task 1");
ok("bar has critical=true", firstBar.critical === true);
ok("bar from criticalRecordIds reflects", firstBar.critical);

// ─── [6] Records without dates are skipped ─────────────────────────────
section("[6] Edge: record without dates");
const rND = makeRenderer({
    ...baseProps,
    records: [
        { id: 1, name: "ok", display_name: "ok", ds: "2026-05-01", de: "2026-05-02" },
        { id: 2, name: "missing start", display_name: "x", ds: null, de: "2026-05-05" },
        { id: 3, name: "missing stop", display_name: "y", ds: "2026-05-01", de: null },
    ],
});
rND._beforeRender();
const bars = rND.allRows.filter((row) => row.type === "bar");
ok("only 1 bar (ones with dates skipped)",
   bars.length === 1, `got ${bars.length}`);
ok("the kept bar has id=1", bars[0].record.id === 1);

// ─── [7] Arrows skip when an endpoint is missing ──────────────────────
section("[7] Arrows: missing endpoint");
const rDanglingDep = makeRenderer({
    ...baseProps,
    records: records30.slice(0, 5),
    dependencies: [
        { id: 200, predecessor_id: 1, successor_id: 2, dep_type: "FS", lag_days: 0 },
        { id: 201, predecessor_id: 1, successor_id: 9999, dep_type: "FS", lag_days: 0 }, // succ missing
    ],
});
rDanglingDep._beforeRender();
ok("dangling deps are silently skipped",
   rDanglingDep.arrows.length === 1,
   `got ${rDanglingDep.arrows.length}`);
ok("the surviving arrow is 200", rDanglingDep.arrows[0].id === 200);

// ─── [8] Empty records ────────────────────────────────────────────────
section("[8] Edge: empty records");
const rE = makeRenderer({ ...baseProps, records: [], dependencies: [] });
rE._beforeRender();
ok("allRows empty", rE.allRows.length === 0);
ok("totalHeight=header", rE.totalHeight === 40);
ok("visibleRows empty", rE.visibleRows.length === 0);
ok("arrows empty", rE.arrows.length === 0);

// ─── [9] Today line ───────────────────────────────────────────────────
section("[9] Today line position");
const rT = makeRenderer({
    ...baseProps,
    // Records around today so the today line is within range
    records: [{
        id: 1, name: "t", display_name: "t",
        ds: new Date(Date.now() - 5 * 86400000).toISOString().slice(0, 10),
        de: new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10),
    }],
});
rT._beforeRender();
ok("todayLineX is a number when today ∈ range",
   typeof rT.todayLineX === "number",
   `got ${rT.todayLineX}`);

// ─── [10] criticalRecordIds reflected in bars ─────────────────────────
section("[10] Critical highlight in bar.critical");
const rC = makeRenderer({
    ...baseProps,
    criticalRecordIds: new Set([1, 3, 5]),
});
rC._beforeRender();
const c1 = rC.allRows.find((row) => row.type === "bar" && row.record.id === 1);
const c2 = rC.allRows.find((row) => row.type === "bar" && row.record.id === 2);
ok("id=1 is critical", c1.critical === true);
ok("id=2 is NOT critical", c2.critical === false);

// ─── [11] Color field is applied ──────────────────────────────────────
section("[11] colorField");
const rCol = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, colorField: "name" },
});
rCol._beforeRender();
const bar1 = rCol.allRows.find((row) => row.type === "bar" && row.record.id === 1);
const bar2 = rCol.allRows.find((row) => row.type === "bar" && row.record.id === 2);
ok("bars have different colors (name differs)", bar1.color !== bar2.color);

// ─── [12] Progress field ──────────────────────────────────────────────
section("[12] progress field");
const rP = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, progress: "p" },
    records: [
        { id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-05", p: 50 },
        { id: 2, name: "y", display_name: "y", ds: "2026-05-01", de: "2026-05-05", p: 150 },  // clamp
        { id: 3, name: "z", display_name: "z", ds: "2026-05-01", de: "2026-05-05", p: -10 },  // clamp
        { id: 4, name: "w", display_name: "w", ds: "2026-05-01", de: "2026-05-05", p: null },
    ],
});
rP._beforeRender();
const bs = rP.allRows.filter((row) => row.type === "bar");
ok("progress=50 stays 50",         bs.find((b) => b.record.id === 1).progress === 50);
ok("progress=150 clamped to 100",  bs.find((b) => b.record.id === 2).progress === 100);
ok("progress=-10 clamped to 0",    bs.find((b) => b.record.id === 3).progress === 0);
ok("progress=null → 0",            bs.find((b) => b.record.id === 4).progress === 0);

// No progress arch → progress is null
const rNoP = makeRenderer(baseProps);
rNoP._beforeRender();
ok("no progress arch → bar.progress null",
   rNoP.allRows.find((row) => row.type === "bar")?.progress === null);

// ─── [13] Baseline ghost ──────────────────────────────────────────────
section("[13] Baseline ghost");
const rB = makeRenderer({
    ...baseProps,
    baselineLines: [{
        record_id: 1,
        date_start: "2026-05-15",
        date_stop:  "2026-05-20",
    }],
});
rB._beforeRender();
const barB1 = rB.allRows.find((row) => row.type === "bar" && row.record.id === 1);
ok("bar 1 has ghost",       !!barB1.ghost);
ok("ghost has x & width",   typeof barB1.ghost.x === "number" && barB1.ghost.width >= 4);
const barB2 = rB.allRows.find((row) => row.type === "bar" && row.record.id === 2);
ok("bar 2 (no baseline) has no ghost", barB2.ghost === null);

// ─── [14] Sprint 3.1.C.1 — Decorations condicionales ───────────────────
section("[14] Decorations condicionales");
const rDec = makeRenderer({
    ...baseProps,
    archInfo: {
        ...archInfo,
        decorations: {
            success: "is_closed",
            danger:  "priority == '1'",
            warning: "state == '02_changes_requested'",
        },
    },
    records: [
        { id: 1, name: "Done OK", display_name: "x", ds: "2026-05-01", de: "2026-05-05",
          is_closed: true, priority: "0", state: "1_done" },
        { id: 2, name: "Urgent",  display_name: "y", ds: "2026-05-01", de: "2026-05-05",
          is_closed: false, priority: "1", state: "01_in_progress" },
        { id: 3, name: "Changes",  display_name: "z", ds: "2026-05-01", de: "2026-05-05",
          is_closed: false, priority: "0", state: "02_changes_requested" },
        { id: 4, name: "Normal",   display_name: "w", ds: "2026-05-01", de: "2026-05-05",
          is_closed: false, priority: "0", state: "01_in_progress" },
    ],
});
rDec._beforeRender();
const dbars = rDec.allRows.filter((row) => row.type === "bar");
ok("Done has decoration_success",
   dbars.find((b) => b.record.id === 1).decorationClasses.includes("o_gs_bar_decoration_success"));
ok("Urgent has decoration_danger",
   dbars.find((b) => b.record.id === 2).decorationClasses.includes("o_gs_bar_decoration_danger"));
ok("Changes has decoration_warning",
   dbars.find((b) => b.record.id === 3).decorationClasses.includes("o_gs_bar_decoration_warning"));
ok("Normal has NO decoration classes",
   dbars.find((b) => b.record.id === 4).decorationClasses.length === 0);

// Multiple decorations on same record
const rMulti = makeRenderer({
    ...baseProps,
    archInfo: {
        ...archInfo,
        decorations: {
            success: "is_closed",
            primary: "priority == '1'",
        },
    },
    records: [{ id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-05",
                is_closed: true, priority: "1" }],
});
rMulti._beforeRender();
const multiBar = rMulti.allRows.find((row) => row.type === "bar");
ok("stacked decorations: success + primary both apply",
   multiBar.decorationClasses.length === 2 &&
   multiBar.decorationClasses.includes("o_gs_bar_decoration_success") &&
   multiBar.decorationClasses.includes("o_gs_bar_decoration_primary"));

// Bad expression doesn't crash
const rBad = makeRenderer({
    ...baseProps,
    archInfo: {
        ...archInfo,
        decorations: { danger: "this_field_doesnt_exist + 999" },
    },
    records: [{ id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-05" }],
});
rBad._beforeRender();
ok("bad expression doesn't crash, returns no class",
   rBad.allRows.find((row) => row.type === "bar").decorationClasses.length === 0);

// ─── [15] Sprint 3.1.C.2 — disable_drag_drop per-record ────────────────
section("[15] disable_drag_drop per-record");
const rLock = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, disableDragDrop: "is_closed" },
    records: [
        { id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-05", is_closed: true },
        { id: 2, name: "y", display_name: "y", ds: "2026-05-01", de: "2026-05-05", is_closed: false },
    ],
});
rLock._beforeRender();
const locked = rLock.allRows.find((row) => row.type === "bar" && row.record.id === 1);
const free   = rLock.allRows.find((row) => row.type === "bar" && row.record.id === 2);
ok("closed bar is dragDisabled",        locked.dragDisabled === true);
ok("open bar is NOT dragDisabled",      free.dragDisabled === false);

// No disable_drag_drop arch attr → all bars are draggable
const rNoLock = makeRenderer(baseProps);
rNoLock._beforeRender();
ok("no disable_drag_drop arch → all dragDisabled=false",
   rNoLock.allRows.filter((row) => row.type === "bar").every((b) => b.dragDisabled === false));

// ─── [16] Sprint 3.1.C.3 — Milestones ──────────────────────────────────
section("[16] Milestones");
const rMile = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, milestoneField: "is_milestone" },
    records: [
        { id: 1, name: "Kickoff",  display_name: "K",  ds: "2026-05-01", de: "2026-05-01",
          is_milestone: true },
        { id: 2, name: "Regular",  display_name: "R",  ds: "2026-05-02", de: "2026-05-04",
          is_milestone: false },
        { id: 3, name: "Go-live",  display_name: "G",  ds: "2026-05-10", de: "2026-05-10",
          is_milestone: true },
    ],
});
rMile._beforeRender();
const mbars = rMile.allRows.filter((row) => row.type === "bar");
ok("Milestone bar 1 is marked isMilestone",
   mbars.find((b) => b.record.id === 1).isMilestone === true);
ok("Regular bar 2 is NOT milestone",
   mbars.find((b) => b.record.id === 2).isMilestone === false);
ok("Milestone has 4-vertex polygon points",
   mbars.find((b) => b.record.id === 1).milestonePoints.split(" ").length === 4);
ok("Regular bar has no milestonePoints",
   mbars.find((b) => b.record.id === 2).milestonePoints === null);

// Without milestone_field arch attr, no bar is ever a milestone
const rNoMile = makeRenderer({
    ...baseProps,
    records: [{ id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-02",
                is_milestone: true }],  // truthy but no milestoneField configured
});
rNoMile._beforeRender();
ok("no milestone_field arch → no record is a milestone",
   rNoMile.allRows.find((row) => row.type === "bar").isMilestone === false);

// ─── [STRESS] Hardening — datasets grandes / extremos ────────────────
section("[STRESS] 1000 records → virtualización cap");
const stressRecords = Array.from({ length: 1000 }, (_, i) => ({
    id: i + 1,
    name: `Stress ${i + 1}`,
    display_name: `Stress ${i + 1}`,
    ds: `2026-${String((i % 12) + 1).padStart(2, "0")}-01`,
    de: `2026-${String((i % 12) + 1).padStart(2, "0")}-15`,
}));
const tBefore = Date.now();
const rStress = makeRenderer({ ...baseProps, records: stressRecords });
rStress._beforeRender();
const tAfter = Date.now();
ok("1000 records computed in < 500ms",
   (tAfter - tBefore) < 500,
   `took ${tAfter - tBefore}ms`);
ok("allRows = 1000",        rStress.allRows.length === 1000);
ok("visibleRows ≤ 10 (virtual window)",
   rStress.visibleRows.length <= 10,
   `got ${rStress.visibleRows.length}`);
ok("totalHeight scales correctly",
   rStress.totalHeight === 40 + 1000 * 36);

section("[STRESS] Zero-width bars (start === stop)");
const rZero = makeRenderer({
    ...baseProps,
    records: [
        { id: 1, name: "Instant", display_name: "I", ds: "2026-05-01", de: "2026-05-01" },
    ],
});
rZero._beforeRender();
const zb = rZero.allRows.find((row) => row.type === "bar");
ok("zero-width bar still has min width >= 4", zb.width >= 4);

section("[STRESS] Records with extreme dates (year 1900, 9999)");
const rExtreme = makeRenderer({
    ...baseProps,
    records: [
        { id: 1, name: "Old", display_name: "X", ds: "1900-01-01", de: "1900-01-10" },
        { id: 2, name: "Future", display_name: "Y", ds: "9999-12-01", de: "9999-12-31" },
    ],
});
rExtreme._beforeRender();
ok("extreme dates produce a valid range",
   rExtreme.dateRange.start.getFullYear() <= 1900 &&
   rExtreme.dateRange.end.getFullYear() >= 9999);
ok("both bars in layout", rExtreme.allRows.filter((row) => row.type === "bar").length === 2);

section("[STRESS] Range extension when goToDate is far outside");
const rExt = makeRenderer({
    ...baseProps,
    records: [
        { id: 1, name: "x", display_name: "x", ds: "2026-05-01", de: "2026-05-05" },
    ],
});
rExt._beforeRender();
const origEnd = rExt.dateRange.end;
const far = new Date(2030, 0, 1);
rExt._diffProps({ ...baseProps, goToDateRequest: far });
rExt._beforeRender();
ok("range was extended past goToDate",
   rExt.dateRange.end.getTime() > origEnd.getTime() &&
   rExt.dateRange.end.getTime() >= far.getTime(),
   `dateRange.end was ${rExt.dateRange.end.toISOString()}`);

section("[STRESS] Drag aborted mid-flight (esc / unmount)");
const rDrag = makeRenderer(baseProps);
rDrag._beforeRender();
const dragBar = rDrag.allRows.find((row) => row.type === "bar");
rDrag._startDrag(dragBar, 100);
ok("after _startDrag, dragSeed is set", rDrag._dragSeed !== null);
ok("after _startDrag, state.dragId set", rDrag.state.dragId === dragBar.record.id);
rDrag._endDrag();
ok("after _endDrag, seed is null", rDrag._dragSeed === null);
ok("after _endDrag, dragId cleared", rDrag.state.dragId === null);

section("[STRESS] groupBy live (search panel override)");
// Sin groupBy en props → usa archInfo.defaultGroupBy.
const rGroupArch = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, defaultGroupBy: null },
    records: [
        { id: 1, name: "a", display_name: "a", ds: "2026-05-01", de: "2026-05-05" },
        { id: 2, name: "b", display_name: "b", ds: "2026-05-01", de: "2026-05-05" },
    ],
});
rGroupArch._beforeRender();
ok("no groupBy anywhere → all in one anon group",
   rGroupArch.allRows.filter((row) => row.type === "group").length === 0);

// Con archInfo.defaultGroupBy="name" → agrupa por nombre.
const rGroupArchSet = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, defaultGroupBy: "name" },
    records: [
        { id: 1, name: "A", display_name: "a", ds: "2026-05-01", de: "2026-05-05" },
        { id: 2, name: "B", display_name: "b", ds: "2026-05-01", de: "2026-05-05" },
    ],
});
rGroupArchSet._beforeRender();
ok("archInfo.defaultGroupBy applies when no live groupBy",
   rGroupArchSet.allRows.filter((row) => row.type === "group").length === 2);

// Con live groupBy del search panel → override.
const rGroupLive = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, defaultGroupBy: "name" },  // sería "name"
    groupBy: ["display_name"],                          // pero el live es display_name
    records: [
        { id: 1, name: "X", display_name: "alfa", ds: "2026-05-01", de: "2026-05-05" },
        { id: 2, name: "X", display_name: "beta", ds: "2026-05-01", de: "2026-05-05" },
    ],
});
rGroupLive._beforeRender();
ok("live groupBy overrides archInfo.defaultGroupBy",
   rGroupLive.allRows.filter((row) => row.type === "group").length === 2,
   "Si tomara 'name' habría 1 grupo (X). Con override 'display_name' hay 2 (alfa/beta)");

// ─── [17] Sprint 3.1.C.4 — _diffProps reacts to goToDateRequest ────────
section("[17] goToDateRequest triggers range + scroll");
const rGoto = makeRenderer(baseProps);
rGoto._beforeRender();  // clear flags
ok("clean state", !rGoto._dirtyRange);

const aDate = new Date(2027, 0, 15);
rGoto._diffProps({ ...baseProps, goToDateRequest: aDate });
ok("goToDateRequest sets _dirtyRange + _pendingScrollTo",
   rGoto._dirtyRange === true && rGoto._pendingScrollTo === aDate);

// Same date object passed twice → no change
rGoto._pendingScrollTo = null;
rGoto._dirtyRange = false;
rGoto.props.goToDateRequest = aDate;  // simulate current state
rGoto._diffProps({ ...baseProps, goToDateRequest: aDate });
ok("same Date reference → no re-scroll",
   rGoto._pendingScrollTo === null);

// Different Date object (even same calendar date) → re-scroll
const aDate2 = new Date(2027, 0, 15);
rGoto._diffProps({ ...baseProps, goToDateRequest: aDate2 });
ok("new Date reference → re-scroll",
   rGoto._pendingScrollTo === aDate2);

// ─── [SP3.2.A] Drag-resize del borde ─────────────────────────────────
section("[SP3.2.A] Drag-resize del borde del bar");
const rResize = makeRenderer({
    ...baseProps,
    onBarResize: () => {},   // habilita la feature
});
rResize._beforeRender();
const resizeBar = rResize.allRows.find((row) => row.type === "bar" && row.record.id === 1);

// Simular resize del borde derecho: arranca, mueve 40px, suelta.
rResize._startResize(resizeBar, "right", 100);
ok("resize seed creado",   rResize._resizeSeed !== null);
ok("state.resizeId asignado", rResize.state.resizeId === resizeBar.record.id);
ok("state.resizeEdge='right'", rResize.state.resizeEdge === "right");

// barGeoForRender debe reflejar el movimiento durante el resize.
rResize._onResizeMove({ clientX: 100 + 40 });
const geoDuringRight = rResize.barGeoForRender(resizeBar);
ok("right resize crece el width",
   geoDuringRight.width > resizeBar.width,
   `width antes=${resizeBar.width} ahora=${geoDuringRight.width}`);
ok("right resize no cambia la x", geoDuringRight.x === resizeBar.x);

rResize._endResize();
ok("_endResize limpia el seed", rResize._resizeSeed === null);

// Resize left edge.
rResize._startResize(resizeBar, "left", 100);
rResize._onResizeMove({ clientX: 100 + 30 });
const geoDuringLeft = rResize.barGeoForRender(resizeBar);
ok("left resize mueve la x", geoDuringLeft.x > resizeBar.x);
ok("left resize achica el width", geoDuringLeft.width < resizeBar.width);
rResize._endResize();

// Sin onBarResize, los handles no se rendean (la lógica está en XML
// pero como sanity check confirmamos que la prop por defecto es null).
const rNoResize = makeRenderer({ ...baseProps });   // sin onBarResize
ok("default onBarResize null", rNoResize.props.onBarResize == null);

// Milestones no permiten resize (semánticamente no tienen duración).
const rMilestoneResize = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, milestoneField: "is_milestone" },
    records: [
        { id: 1, name: "m", display_name: "m", ds: "2026-05-01", de: "2026-05-01",
          is_milestone: true },
    ],
    onBarResize: () => {},
});
rMilestoneResize._beforeRender();
const ms = rMilestoneResize.allRows.find((row) => row.type === "bar");
// onResizeMouseDown debe early-return en milestones — no se crea seed.
rMilestoneResize.onResizeMouseDown(ms, "right", { button: 0, preventDefault: () => {}, stopPropagation: () => {} });
ok("milestone NO arranca resize",
   rMilestoneResize._resizeSeed === null || rMilestoneResize._resizeSeed === undefined);

// ─── [SP3.2.B] Edición inline ────────────────────────────────────────
section("[SP3.2.B] Edición inline del nombre");
const rEdit = makeRenderer({
    ...baseProps,
    onBarRename: () => {},
});
rEdit._beforeRender();
const editBar = rEdit.allRows.find((row) => row.type === "bar" && row.record.id === 1);

rEdit.onBarDoubleClick(editBar, { preventDefault: () => {}, stopPropagation: () => {} });
ok("dblclick activa editing", rEdit.state.editingId === editBar.record.id);
ok("editingValue se inicializa con el label",
   rEdit.state.editingValue === editBar.label);

rEdit.onInlineEditInput({ target: { value: "Nuevo nombre" } });
ok("input actualiza editingValue", rEdit.state.editingValue === "Nuevo nombre");

// Enter → commit
let renameCalls = [];
rEdit.props.onBarRename = (id, name) => renameCalls.push({ id, name });
rEdit.onInlineEditKeyDown(editBar, {
    key: "Enter", preventDefault: () => {}, stopPropagation: () => {}
});
ok("Enter dispara onBarRename con el nuevo nombre",
   renameCalls.length === 1 && renameCalls[0].name === "Nuevo nombre");
ok("Enter cierra el modo edición", rEdit.state.editingId === null);

// Esc → cancel (no commit)
renameCalls = [];
rEdit.onBarDoubleClick(editBar, { preventDefault: () => {}, stopPropagation: () => {} });
rEdit.onInlineEditInput({ target: { value: "Otro intento" } });
rEdit.onInlineEditKeyDown(editBar, {
    key: "Escape", preventDefault: () => {}, stopPropagation: () => {}
});
ok("Esc NO dispara onBarRename", renameCalls.length === 0);
ok("Esc cierra el modo edición", rEdit.state.editingId === null);

// Sin onBarRename → dblclick no hace nada
const rNoEdit = makeRenderer(baseProps);
rNoEdit._beforeRender();
const nb = rNoEdit.allRows.find((row) => row.type === "bar");
rNoEdit.onBarDoubleClick(nb, { preventDefault: () => {}, stopPropagation: () => {} });
ok("sin onBarRename, dblclick no entra en edición",
   rNoEdit.state.editingId === null);

// ─── [SP3.2.C] Drag-to-create dep ─────────────────────────────────────
section("[SP3.2.C] Drag-to-create dep + popover");
const rDep = makeRenderer({
    ...baseProps,
    onDepCreate: () => {},
});
rDep._beforeRender();
const fromBar = rDep.allRows.find((row) => row.type === "bar" && row.record.id === 1);

rDep.onDepHandleMouseDown(fromBar, "right", {
    button: 0, clientX: 100, clientY: 50,
    preventDefault: () => {}, stopPropagation: () => {},
});
ok("dep drag arranca", rDep.state.depDragFrom === fromBar.record.id);
ok("dep drag captura edge", rDep.state.depDragFromEdge === "right");

// Simulamos mouseup sobre un bar destino — esto necesita document.elementFromPoint
// que en Node no existe, así que stubeamos.
globalThis.document.elementFromPoint = (x, y) => ({
    closest: (sel) => sel === ".o_gs_bar_group"
        ? { getAttribute: () => "2" }
        : null,
});
rDep._onDepDragUp({ clientX: 200, clientY: 60 });
ok("popover se abre con predId/succId correctos",
   rDep.state.depPopover !== null
   && rDep.state.depPopover.predId === 1
   && rDep.state.depPopover.succId === 2);
ok("popover default depType=FS", rDep.state.depPopover.depType === "FS");
ok("popover default lagDays=0", rDep.state.depPopover.lagDays === 0);

// Cambio de tipo + lag
rDep.onDepPopoverTypeChange({ target: { value: "SS" } });
rDep.onDepPopoverLagChange({ target: { value: "2.5" } });
ok("cambio de tipo",     rDep.state.depPopover.depType === "SS");
ok("cambio de lag", rDep.state.depPopover.lagDays === 2.5);

// Confirm → llama onDepCreate y cierra popover
let createCalls = [];
rDep.props.onDepCreate = (p, s, t, l) => createCalls.push({ p, s, t, l });
rDep.onDepPopoverConfirm();
ok("Crear llama a onDepCreate",
   createCalls.length === 1
   && createCalls[0].p === 1
   && createCalls[0].s === 2
   && createCalls[0].t === "SS"
   && createCalls[0].l === 2.5);
ok("popover se cierra tras Crear", rDep.state.depPopover === null);

// Cancel → cierra popover sin crear
rDep.state.depPopover = { predId: 1, succId: 2, x: 0, y: 0, depType: "FF", lagDays: 0 };
createCalls = [];
rDep.onDepPopoverCancel();
ok("Cancelar NO llama a onDepCreate", createCalls.length === 0);
ok("Cancelar cierra el popover", rDep.state.depPopover === null);

// Drop sobre el mismo bar (predId === succId) NO debe abrir popover
const rSelf = makeRenderer({ ...baseProps, onDepCreate: () => {} });
rSelf._beforeRender();
rSelf.onDepHandleMouseDown(fromBar, "right", {
    button: 0, clientX: 100, clientY: 50,
    preventDefault: () => {}, stopPropagation: () => {},
});
globalThis.document.elementFromPoint = (x, y) => ({
    closest: (sel) => ({ getAttribute: () => "1" }),   // mismo id
});
rSelf._onDepDragUp({ clientX: 110, clientY: 50 });
ok("drop sobre sí mismo NO abre popover", rSelf.state.depPopover === null);

// ─── [SP3.3] WBS jerárquico en el renderer ────────────────────────────
section("[SP3.3] WBS hierarchy");

const wbsRecords = [
    { id: 1, name: "Fase Diseño", display_name: "Fase Diseño",
      parent_id: false,
      ds: "2026-05-01", de: "2026-05-15" },
    { id: 2, name: "Topografía", display_name: "Topografía",
      parent_id: [1, "Fase Diseño"],
      ds: "2026-05-01", de: "2026-05-05" },
    { id: 3, name: "Anteproyecto", display_name: "Anteproyecto",
      parent_id: [1, "Fase Diseño"],
      ds: "2026-05-06", de: "2026-05-15" },
    { id: 4, name: "Solitario", display_name: "Solitario",
      parent_id: false,
      ds: "2026-05-20", de: "2026-05-25" },
];

const rWbs = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, parentField: "parent_id" },
    records: wbsRecords,
});
rWbs._beforeRender();
const wbsBars = rWbs.allRows.filter((row) => row.type === "bar");
ok("WBS: 4 records → 4 bars", wbsBars.length === 4);

const parent = wbsBars.find((b) => b.record.id === 1);
const child1 = wbsBars.find((b) => b.record.id === 2);
const solo = wbsBars.find((b) => b.record.id === 4);

ok("padre marcado como isParent",   parent.isParent === true);
ok("padre depth=0",                  parent.depth === 0);
ok("hijo depth=1",                   child1.depth === 1);
ok("solitario depth=0",              solo.depth === 0);
ok("solitario NO isParent",          solo.isParent === false);

// Padre NO debe ser draggable (es summary).
ok("padre dragDisabled=true (summary)", parent.dragDisabled === true);

// Colapsar padre 1 → solo aparecen padre 1 + solitario 4
rWbs.state.collapsed = new Set([1]);
rWbs._dirtyLayout = true;
rWbs._beforeRender();
const collapsed = rWbs.allRows.filter((row) => row.type === "bar");
ok("colapsado: 2 bars (padre + solitario)",
   collapsed.length === 2 &&
   collapsed.find((b) => b.record.id === 1) &&
   collapsed.find((b) => b.record.id === 4));

// Expandir de nuevo
rWbs.state.collapsed = new Set();
rWbs._dirtyLayout = true;
rWbs._beforeRender();
ok("expandido: 4 bars",
   rWbs.allRows.filter((row) => row.type === "bar").length === 4);

// Toggle via onToggleCollapse mutates set
const rToggle = makeRenderer({
    ...baseProps,
    archInfo: { ...archInfo, parentField: "parent_id" },
    records: wbsRecords,
});
rToggle._beforeRender();
const parentRow = rToggle.allRows.find((row) => row.type === "bar" && row.isParent);
rToggle.onToggleCollapse(parentRow, { preventDefault: () => {}, stopPropagation: () => {} });
ok("toggle agrega al set", rToggle.state.collapsed.has(parentRow.record.id));
ok("toggle marca _dirtyLayout", rToggle._dirtyLayout === true);
rToggle.onToggleCollapse(parentRow, { preventDefault: () => {}, stopPropagation: () => {} });
ok("toggle de nuevo quita del set", !rToggle.state.collapsed.has(parentRow.record.id));

// Sin parent_field configurado → no hay jerarquía
const rNoWbs = makeRenderer({ ...baseProps, records: wbsRecords });
rNoWbs._beforeRender();
const flat = rNoWbs.allRows.filter((row) => row.type === "bar");
ok("sin parent_field: ningún record es isParent",
   flat.every((b) => !b.isParent));

// Rollup: el bar del padre debe envolver el rango de los hijos
ok("rollup: padre.x corresponde a min(start) de hijos",
   parent.x <= child1.x);
// Padre originalmente declarado 01→15. Hijos cubren 01→15. Rollup = 01→15.
// Bar width del padre debe ser >= width de cualquier hijo.
ok("rollup: padre.width envuelve a los hijos",
   parent.width >= child1.width);

// ─── Summary ───────────────────────────────────────────────────────────
section(`RESULT: ${pass} passed, ${fail} failed`);
fs.rmSync(tmpDir, { recursive: true, force: true });
process.exit(fail > 0 ? 1 : 0);
