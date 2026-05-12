// Pure-JS test suite for gantt_studio_utils.js
//
// Runs under Node (no browser, no Odoo). Stubs the `/** @odoo-module **/`
// pragma and imports the file directly via a temp .mjs.

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "../../static/src/js/gantt_studio_utils.js");

let raw = fs.readFileSync(SRC, "utf-8");
raw = raw.replace(/\/\*\*\s*@odoo-module\s*\*\*\//, "");
const tmp = path.join(os.tmpdir(), `gs_utils_${Date.now()}.mjs`);
fs.writeFileSync(tmp, raw);
const m = await import("file://" + tmp);

const {
    MS_PER_DAY, SCALE_CONFIG, PALETTE,
    weekNumber, parseDate, hashColor, fieldDisplay,
    dateToPx, computeDateRange, groupRecords,
    parseGanttStudioArch, computeArrowPath, arrowHeadPoints,
    measureTextWidth, truncateToWidth,
    buildTree, walkTree, computeRollup,
} = m;

// Try to load xmldom for arch-string tests; skip those if not installed.
let DOMParser = null;
try {
    ({ DOMParser } = await import("@xmldom/xmldom"));
} catch {
    console.warn("⚠️  @xmldom/xmldom not installed — arch-string tests will be skipped");
}

let pass = 0, fail = 0;
function ok(name, cond, extra) {
    if (cond) { console.log("  OK  " + name); pass++; }
    else { console.log("  FAIL " + name + (extra ? " :: " + extra : "")); fail++; }
}

function section(s) {
    console.log("=".repeat(70));
    console.log(s);
}

// ─── [1] Constants & basic primitives ────────────────────────────────
section("[1] Constants & basics");
ok("MS_PER_DAY", MS_PER_DAY === 86400000);
ok("SCALE_CONFIG has 5 scales", Object.keys(SCALE_CONFIG).length === 5);
ok("scales: day, week, month, quarter, year",
   ["day","week","month","quarter","year"].every((s) => s in SCALE_CONFIG));
ok("PALETTE size >= 5", PALETTE.length >= 5);
ok("palette colors are hex", PALETTE.every((c) => /^#[0-9a-f]{6}$/i.test(c)));

// ─── [2] parseDate variations ────────────────────────────────────────
section("[2] parseDate");
ok("date-only string",       parseDate("2026-05-12").getTime() === new Date("2026-05-12T00:00:00").getTime());
ok("datetime string (sp)",   parseDate("2026-05-12 08:30:00").getHours() === 8);
ok("datetime string (T)",    parseDate("2026-05-12T08:30:00").getHours() === 8);
ok("Date instance passthru", parseDate(new Date("2026-05-12")).getTime() === new Date("2026-05-12").getTime());
ok("null → null",            parseDate(null) === null);
ok("undefined → null",       parseDate(undefined) === null);
ok("empty string → null",    parseDate("") === null);
ok("garbage string → null",  parseDate("not-a-date") === null);
ok("malformed iso → null",   parseDate("2026-99-99") === null);

// ─── [3] hashColor determinism ───────────────────────────────────────
section("[3] hashColor");
ok("stable per input",   hashColor("alice") === hashColor("alice"));
ok("different inputs ≠", hashColor("alice") !== hashColor("alicz"));
ok("null → first color", hashColor(null) === PALETTE[0]);
ok("false → first color", hashColor(false) === PALETTE[0]);
ok("undefined → first",   hashColor(undefined) === PALETTE[0]);
ok("array hashable",      typeof hashColor([42, "Hello"]) === "string");
ok("number hashable",     typeof hashColor(42) === "string");

// ─── [4] fieldDisplay ────────────────────────────────────────────────
section("[4] fieldDisplay");
ok("many2one [id,name]",  fieldDisplay({u: [1, "Alice"]}, "u") === "Alice");
ok("m2o with empty name", fieldDisplay({u: [1, ""]}, "u") === "");
ok("false → ''",          fieldDisplay({u: false}, "u") === "");
ok("missing key → ''",    fieldDisplay({}, "u") === "");
ok("number → string",     fieldDisplay({u: 42}, "u") === "42");
ok("bool true → 'true'",  fieldDisplay({u: true}, "u") === "true");

// ─── [5] dateToPx & computeDateRange ─────────────────────────────────
section("[5] dateToPx & computeDateRange");
ok("dateToPx 7d week=140", dateToPx(new Date("2026-05-12"), new Date("2026-05-05"), "week") === 140);
ok("dateToPx 1d day=80",   dateToPx(new Date("2026-05-06"), new Date("2026-05-05"), "day") === 80);
ok("dateToPx month",       dateToPx(new Date("2026-06-04"), new Date("2026-05-05"), "month") === 180);

const rng = computeDateRange(
    [{s: "2026-05-12", e: "2026-05-15"}, {s: "2026-05-20", e: "2026-05-22"}],
    "s", "e", "week");
ok("range encloses min", rng.start.getTime() <= new Date("2026-05-12").getTime());
ok("range encloses max", rng.end.getTime() >= new Date("2026-05-22").getTime());

const emptyRng = computeDateRange([], "s", "e", "week");
const today = Date.now();
ok("empty → ±15d around today",
   Math.abs(emptyRng.start.getTime() - (today - MS_PER_DAY * 15)) < MS_PER_DAY * 30 &&
   Math.abs(emptyRng.end.getTime() - (today + MS_PER_DAY * 15)) < MS_PER_DAY * 30);

const noDateRng = computeDateRange([{s: null, e: null}], "s", "e", "day");
ok("records without dates → today±", isFinite(noDateRng.start.getTime()));

// ─── [6] groupRecords ────────────────────────────────────────────────
section("[6] groupRecords");
const recs = [
    {id: 1, stage: [1, "Todo"]},
    {id: 2, stage: [1, "Todo"]},
    {id: 3, stage: [2, "Done"]},
    {id: 4, stage: false},
    {id: 5, stage: null},
];
const g = groupRecords(recs, "stage");
ok("3 groups (Todo, Done, none)", g.length === 3, `got ${g.length}`);
ok("Todo has 2", g.find((x) => x.key === 1)?.records.length === 2);
ok("__none__ has 2",
   g.find((x) => x.key === "__none__")?.records.length === 2,
   "both false and null go to __none__");
ok("no groupBy → 1 group", groupRecords(recs, null).length === 1);
ok("empty records → 1 empty group",
   groupRecords([], "stage").length === 1 &&
   groupRecords([], "stage")[0].records.length === 0);

const gscalar = groupRecords([{x: "a"}, {x: "b"}, {x: "a"}], "x");
ok("scalar groupby works",
   gscalar.length === 2 && gscalar.find((x) => x.key === "a")?.records.length === 2);

// ─── [7] weekNumber sanity ───────────────────────────────────────────
section("[7] weekNumber");
// Build dates with local-time constructor — `new Date("YYYY-MM-DD")` parses as
// UTC and shifts day in non-UTC timezones, which silently breaks this test.
ok("Jan 1 is week 1",
   weekNumber(new Date(2026, 0, 1)) === 1,
   `got ${weekNumber(new Date(2026, 0, 1))}`);
ok("Dec 31 is week 53-ish",
   weekNumber(new Date(2026, 11, 31)) >= 52,
   `got ${weekNumber(new Date(2026, 11, 31))}`);
ok("mid-year week is in range",
   weekNumber(new Date(2026, 5, 15)) > 1 && weekNumber(new Date(2026, 5, 15)) < 53);

// ─── [8] parseGanttStudioArch ────────────────────────────────────────
section("[8] parseGanttStudioArch");
if (DOMParser) {
    const arch = `<gantt_studio date_start="ds" date_stop="de" default_scale="month"
        default_group_by="stage_id" color_field="user_ids" bar_text="name"
        progress="progress" form_view_id="42" edit="false" create="true"
        delete="false" show_dependencies="false" show_critical_path="true"
        auto_reschedule="false" baseline_support="true">
        <field name="name"/>
        <field name="user_ids"/>
    </gantt_studio>`;
    const info = parseGanttStudioArch(arch, DOMParser);
    ok("dateStart",          info.dateStart === "ds");
    ok("dateStop",           info.dateStop === "de");
    ok("defaultScale",       info.defaultScale === "month");
    ok("defaultGroupBy",     info.defaultGroupBy === "stage_id");
    ok("colorField",         info.colorField === "user_ids");
    ok("barText",            info.barText === "name");
    ok("progress",           info.progress === "progress");
    ok("formViewId is int",  info.formViewId === 42);
    ok("canEdit=false",      info.canEdit === false);
    ok("canCreate=true",     info.canCreate === true);
    ok("canDelete=false",    info.canDelete === false);
    ok("showDependencies=false", info.showDependencies === false);
    ok("showCriticalPath=true",  info.showCriticalPath === true);
    ok("autoReschedule=false",   info.autoReschedule === false);
    ok("baselineSupport=true",   info.baselineSupport === true);
    ok("fieldsToFetch=2",        info.fieldsToFetch.length === 2);
    ok("fields[0]=name",         info.fieldsToFetch[0] === "name");
    ok("fields[1]=user_ids",     info.fieldsToFetch[1] === "user_ids");

    // Defaults
    const minimal = parseGanttStudioArch(
        '<gantt_studio date_start="a" date_stop="b"/>', DOMParser);
    ok("default scale=week",        minimal.defaultScale === "week");
    ok("default barText=display_name", minimal.barText === "display_name");
    ok("opt-out defaults: showDeps=true", minimal.showDependencies === true);
    ok("opt-out defaults: criticalPath=true", minimal.showCriticalPath === true);
    ok("opt-out defaults: autoReschedule=true", minimal.autoReschedule === true);
    ok("opt-out defaults: baseline=true", minimal.baselineSupport === true);
    ok("formViewId default null", minimal.formViewId === null);
    ok("fieldsToFetch default []",  minimal.fieldsToFetch.length === 0);
    // Sprint 3.1 — new arch attributes
    ok("disableDragDrop default null", minimal.disableDragDrop === null);
    ok("milestoneField default null",  minimal.milestoneField === null);
    ok("decorations default empty",
       typeof minimal.decorations === "object" && Object.keys(minimal.decorations).length === 0);

    // Sprint 3.1 — with attributes set
    const sp31 = parseGanttStudioArch(`
        <gantt_studio date_start="a" date_stop="b"
                      disable_drag_drop="state == '1_done'"
                      milestone_field="is_milestone"
                      decoration-success="is_closed"
                      decoration-danger="date_deadline and date_deadline &lt; context_today()"
                      decoration-warning="priority == '1'">
        </gantt_studio>
    `, DOMParser);
    ok("disableDragDrop parsed", sp31.disableDragDrop === "state == '1_done'");
    ok("milestoneField parsed",  sp31.milestoneField === "is_milestone");
    ok("decorations has success", sp31.decorations.success === "is_closed");
    ok("decorations has danger",  sp31.decorations.danger.includes("date_deadline"));
    ok("decorations has warning", sp31.decorations.warning === "priority == '1'");
    ok("decorations count=3",     Object.keys(sp31.decorations).length === 3);

    // Errors
    try {
        parseGanttStudioArch('<gantt_studio date_start="a"/>', DOMParser);
        ok("missing date_stop throws", false);
    } catch (e) {
        ok("missing date_stop throws", /date_start.*date_stop|date_stop/.test(e.message));
    }
    try {
        parseGanttStudioArch('<gantt_studio date_stop="b"/>', DOMParser);
        ok("missing date_start throws", false);
    } catch (e) {
        ok("missing date_start throws", true);
    }
    try {
        parseGanttStudioArch(
            '<gantt_studio date_start="a" date_stop="b" default_scale="century"/>',
            DOMParser);
        ok("invalid scale throws", false);
    } catch (e) {
        ok("invalid scale throws", /century|invalid/i.test(e.message));
    }
    try {
        parseGanttStudioArch(null, DOMParser);
        ok("null arch throws", false);
    } catch (e) {
        ok("null arch throws", true);
    }
    try {
        // String arch but no ParserCls provided
        parseGanttStudioArch('<gantt_studio date_start="a" date_stop="b"/>');
        ok("string without parser throws", false);
    } catch (e) {
        ok("string without parser throws", /ParserCls/.test(e.message));
    }

    // Element form (already parsed)
    const doc = new DOMParser().parseFromString(
        '<gantt_studio date_start="a" date_stop="b"/>', "text/xml");
    const fromEl = parseGanttStudioArch(doc.documentElement);
    ok("Element form works", fromEl.dateStart === "a");
} else {
    console.log("  SKIP — install @xmldom/xmldom in /tmp to enable");
}

// ─── [9] computeArrowPath ────────────────────────────────────────────
section("[9] computeArrowPath");
const from = {x: 100, y: 50, width: 60, height: 20};
const to   = {x: 200, y: 90, width: 60, height: 20};
for (const t of ["FS","SS","FF","SF"]) {
    const p = computeArrowPath(from, to, t);
    ok(`${t}: non-empty path`,        typeof p === "string" && p.length > 0);
    ok(`${t}: starts with M`,         p.startsWith("M "));
    ok(`${t}: has multiple segments`, (p.match(/L /g) || []).length >= 3);
}
ok("invalid type → empty", computeArrowPath(from, to, "??") === "");
ok("identical from=to: still produces path", computeArrowPath(from, from, "FS").length > 0);

// ─── [10] arrowHeadPoints ────────────────────────────────────────────
section("[10] arrowHeadPoints");
const headFS = arrowHeadPoints(to, "FS");
const headSS = arrowHeadPoints(to, "SS");
const headFF = arrowHeadPoints(to, "FF");
const headSF = arrowHeadPoints(to, "SF");
ok("FS: 3 points", headFS.split(" ").length === 3);
ok("SS: 3 points", headSS.split(" ").length === 3);
ok("FF: 3 points", headFF.split(" ").length === 3);
ok("SF: 3 points", headSF.split(" ").length === 3);
ok("FS tip on LEFT edge",  headFS.split(" ")[0].startsWith(`${to.x},`));
ok("SS tip on LEFT edge",  headSS.split(" ")[0].startsWith(`${to.x},`));
ok("FF tip on RIGHT edge", headFF.split(" ")[0].startsWith(`${to.x + to.width},`));
ok("SF tip on RIGHT edge", headSF.split(" ")[0].startsWith(`${to.x + to.width},`));

// ─── [11] measureTextWidth & truncateToWidth ─────────────────────────
section("[11] text measurement");
ok("empty string width=0", measureTextWidth("") === 0);
ok("fallback heuristic 5×6.5",
   Math.abs(measureTextWidth("hello") - 32.5) < 0.01);
ok("truncate fitting unchanged",
   truncateToWidth("Hi", 1000) === "Hi");
ok("truncate ''",  truncateToWidth("", 50) === "");
ok("truncate null", truncateToWidth(null, 50) === "");
ok("negative width", truncateToWidth("foo", -5) === "");
ok("very narrow → ellipsis only or empty",
   truncateToWidth("x", 1) === "");  // less than ellipsis width

const narrow = truncateToWidth("Lorem ipsum dolor sit amet consectetur", 30);
ok("narrow result ends with …", narrow.endsWith("…"));
ok("narrow result strictly shorter than input",
   narrow.length < "Lorem ipsum dolor sit amet consectetur".length);

// ─── [12] Sprint 3.3 — WBS helpers ───────────────────────────────────
section("[12] WBS — buildTree / walkTree / computeRollup");

// Helper para construir records mock con parent_id como m2o array.
const r = (id, name, parentId, s, e) => ({
    id, name, display_name: name,
    parent_id: parentId ? [parentId, `P${parentId}`] : false,
    s, e,
});

// Sin parentField → todos roots.
const flatTree = buildTree([r(1, "a", null, "2026-05-01", "2026-05-02")], null);
ok("sin parentField → todos roots", flatTree.length === 1 && flatTree[0].children.length === 0);

// Arbol simple: 1 (root) → 2 (child) y 3 (root sin hijos)
const records = [
    r(1, "Padre",    null, "2026-05-01", "2026-05-10"),
    r(2, "Hijo",     1,    "2026-05-03", "2026-05-08"),
    r(3, "Solitario", null, "2026-05-05", "2026-05-12"),
];
const tree = buildTree(records, "parent_id");
ok("buildTree: 2 raíces", tree.length === 2);
ok("buildTree: padre tiene 1 hijo",
   tree.find((n) => n.record.id === 1).children.length === 1);
ok("buildTree: hijo está en la rama correcta",
   tree.find((n) => n.record.id === 1).children[0].record.id === 2);
ok("buildTree: solitario sin hijos",
   tree.find((n) => n.record.id === 3).children.length === 0);

// Walk en orden con todo expandido
const walked = walkTree(tree, new Set());
ok("walkTree: 3 entradas (todo expandido)", walked.length === 3);
ok("walkTree: orden padre→hijo→solitario",
   walked[0].record.id === 1
   && walked[1].record.id === 2
   && walked[2].record.id === 3);
ok("walkTree: depth padre=0", walked[0].depth === 0);
ok("walkTree: depth hijo=1", walked[1].depth === 1);
ok("walkTree: hasChildren padre",      walked[0].hasChildren === true);
ok("walkTree: hasChildren hijo=false", walked[1].hasChildren === false);

// Colapsar el padre → solo aparecen padre + solitario
const walkedCollapsed = walkTree(tree, new Set([1]));
ok("walkTree: padre colapsado oculta hijos",
   walkedCollapsed.length === 2 &&
   walkedCollapsed[0].record.id === 1 &&
   walkedCollapsed[1].record.id === 3);

// Hijo de padre faltante → tratado como raíz
const orphan = [
    r(10, "Hijo huérfano", 999, "2026-05-01", "2026-05-05"),  // parent_id=999 no existe
];
const orphanTree = buildTree(orphan, "parent_id");
ok("buildTree: huérfano queda como raíz",
   orphanTree.length === 1 && orphanTree[0].record.id === 10);

// Ciclo: A→B→A. Defensive: B se trata como raíz.
const cycle = [
    r(20, "A", 21, "2026-05-01", "2026-05-05"),
    r(21, "B", 20, "2026-05-01", "2026-05-05"),
];
const cycleTree = buildTree(cycle, "parent_id");
ok("buildTree: ciclo no causa loop infinito (al menos no crash)",
   Array.isArray(cycleTree));

// computeRollup: padre tiene su propio rango más amplio
const node1 = tree.find((n) => n.record.id === 1);
node1.record.s = "2026-05-01";
node1.record.e = "2026-05-10";
// hijo (2): s=2026-05-03 e=2026-05-08
const rollup = computeRollup(node1, "s", "e");
ok("computeRollup: start = min(padre, hijos)",
   rollup.start.getTime() === parseDate("2026-05-01").getTime());
ok("computeRollup: stop = max(padre, hijos)",
   rollup.stop.getTime() === parseDate("2026-05-10").getTime());

// Padre con fechas null → toma del hijo
const node2 = {
    record: { id: 30, s: null, e: null },
    children: [
        { record: { id: 31, s: "2026-05-03", e: "2026-05-08" }, children: [] },
    ],
};
const rollup2 = computeRollup(node2, "s", "e");
ok("computeRollup: padre sin fechas usa rango del hijo",
   rollup2.start.getTime() === parseDate("2026-05-03").getTime() &&
   rollup2.stop.getTime() === parseDate("2026-05-08").getTime());

// Nieto → rollup recursivo
const grandparent = {
    record: { id: 40, s: "2026-05-04", e: "2026-05-06" },
    children: [
        {
            record: { id: 41, s: "2026-05-05", e: "2026-05-05" },
            children: [
                { record: { id: 42, s: "2026-05-01", e: "2026-05-15" }, children: [] },
            ],
        },
    ],
};
const rollupG = computeRollup(grandparent, "s", "e");
ok("computeRollup: recursivo a través de nietos",
   rollupG.start.getTime() === parseDate("2026-05-01").getTime() &&
   rollupG.stop.getTime() === parseDate("2026-05-15").getTime());

// ─── [13] Sprint 3.11 — popup_editor + Sprint 3.9 arch attrs ─────────
section("[13] Sprint 3.11 — popup_editor attribute");
if (DOMParser) {
    // Default: popup_editor ausente → false
    const minPop = parseGanttStudioArch(
        '<gantt_studio date_start="a" date_stop="b"/>', DOMParser);
    ok("popupEditor default false", minPop.popupEditor === false);

    // popup_editor="true" → true
    const withPop = parseGanttStudioArch(
        '<gantt_studio date_start="a" date_stop="b" popup_editor="true"/>', DOMParser);
    ok("popup_editor='true' → true", withPop.popupEditor === true);

    // popup_editor="false" → false (explicit opt-out)
    const noPop = parseGanttStudioArch(
        '<gantt_studio date_start="a" date_stop="b" popup_editor="false"/>', DOMParser);
    ok("popup_editor='false' → false", noPop.popupEditor === false);

    // popup_editor en arch con resto de atributos → no rompe otros
    const fullArch = parseGanttStudioArch(`
        <gantt_studio date_start="ds" date_stop="de"
                      default_scale="month"
                      popup_editor="true"
                      parent_field="parent_id"
                      resource_field="user_ids">
        </gantt_studio>
    `, DOMParser);
    ok("popup_editor=true coexiste con parent_field",
       fullArch.popupEditor === true && fullArch.parentField === "parent_id");
    ok("popup_editor=true coexiste con resource_field",
       fullArch.popupEditor === true && fullArch.resourceField === "user_ids");
    ok("popup_editor preserva defaultScale",
       fullArch.defaultScale === "month");
} else {
    console.log("  SKIP — install @xmldom/xmldom in /tmp to enable");
}

// ─── Summary ─────────────────────────────────────────────────────────
section(`RESULT: ${pass} passed, ${fail} failed`);
fs.unlinkSync(tmp);
process.exit(fail > 0 ? 1 : 0);
