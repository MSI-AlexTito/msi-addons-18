/** @odoo-module **/

/**
 * Pure helpers (no DOM, no OWL) used by the Gantt Studio renderer.
 *
 * Diseño: cualquier función expuesta aquí debe ser ejecutable bajo Node
 * para poder testearla en aislamiento sin Odoo ni un navegador.
 */

export const MS_PER_DAY = 86400000;

export const SCALE_CONFIG = {
    day:     { unitMs: MS_PER_DAY,         pxPerUnit: 80,  fmt: (d) => `${d.getDate()}/${d.getMonth() + 1}` },
    week:    { unitMs: MS_PER_DAY * 7,     pxPerUnit: 140, fmt: (d) => `W${weekNumber(d)} ${d.getFullYear()}` },
    month:   { unitMs: MS_PER_DAY * 30,    pxPerUnit: 180, fmt: (d) => d.toLocaleString("default", { month: "short", year: "2-digit" }) },
    quarter: { unitMs: MS_PER_DAY * 90,    pxPerUnit: 220, fmt: (d) => `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}` },
    year:    { unitMs: MS_PER_DAY * 365,   pxPerUnit: 260, fmt: (d) => `${d.getFullYear()}` },
};

export const PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
];

/** ISO-ish week number for a Date. */
export function weekNumber(d) {
    const onejan = new Date(d.getFullYear(), 0, 1);
    return Math.ceil(((d - onejan) / MS_PER_DAY + onejan.getDay() + 1) / 7);
}

/**
 * Parse a date coming from Odoo (string "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS")
 * or a Date instance. Returns a Date or null.
 */
export function parseDate(s) {
    if (!s) return null;
    if (s instanceof Date) return s;
    if (typeof s === "string") {
        const isoLike = s.replace(" ", "T");
        const withTime = isoLike.includes("T") || isoLike.length > 10
            ? isoLike
            : isoLike + "T00:00:00";
        const d = new Date(withTime);
        return isNaN(d.getTime()) ? null : d;
    }
    return null;
}

/** Deterministic palette pick from any value (used for color encoding). */
export function hashColor(value) {
    if (value === null || value === undefined || value === false) {
        return PALETTE[0];
    }
    const s = typeof value === "string" ? value : JSON.stringify(value);
    let h = 0;
    for (let i = 0; i < s.length; i++) {
        h = (h * 31 + s.charCodeAt(i)) | 0;
    }
    return PALETTE[Math.abs(h) % PALETTE.length];
}

/**
 * Render a single field of an Odoo record into a printable string.
 * - many2one comes as [id, name] → name
 * - false/null/undefined → ""
 * - other → String(...)
 */
export function fieldDisplay(record, fieldName) {
    const v = record[fieldName];
    if (v === undefined || v === null || v === false) return "";
    if (Array.isArray(v)) return v[1] || "";
    return String(v);
}

/** Convert a Date to its pixel offset on the timeline. */
export function dateToPx(date, rangeStart, scale) {
    const cfg = SCALE_CONFIG[scale] || SCALE_CONFIG.week;
    return ((date.getTime() - rangeStart.getTime()) / cfg.unitMs) * cfg.pxPerUnit;
}

/**
 * Computes the {start,end} date range that covers all records for the given
 * start/stop date fields, padded with 2 scale-units of margin on each side.
 *
 * If `records` is empty or has no usable dates → returns ±15 days around today.
 */
export function computeDateRange(records, dateStartField, dateStopField, scale) {
    let min = Infinity;
    let max = -Infinity;
    for (const r of records || []) {
        const s = parseDate(r[dateStartField])?.getTime();
        const e = parseDate(r[dateStopField])?.getTime();
        if (s && s < min) min = s;
        if (e && e > max) max = e;
    }
    if (!isFinite(min) || !isFinite(max)) {
        const now = Date.now();
        return {
            start: new Date(now - MS_PER_DAY * 15),
            end:   new Date(now + MS_PER_DAY * 15),
        };
    }
    const cfg = SCALE_CONFIG[scale] || SCALE_CONFIG.week;
    const margin = cfg.unitMs * 2;
    return {
        start: new Date(Math.floor((min - margin) / cfg.unitMs) * cfg.unitMs),
        end:   new Date(Math.ceil((max + margin) / cfg.unitMs) * cfg.unitMs),
    };
}

/**
 * Group records by a field. Returns an array of { key, label, records }.
 * `groupBy` can be falsy → returns a single anonymous group.
 */
export function groupRecords(records, groupBy) {
    if (!groupBy || !records || !records.length) {
        return [{ key: "__all__", label: "", records: records || [] }];
    }
    const groups = new Map();
    for (const r of records) {
        const raw = r[groupBy];
        const key = Array.isArray(raw) ? raw[0] : (raw === false || raw === null ? "__none__" : raw);
        const label = Array.isArray(raw)
            ? (raw[1] || "—")
            : (raw === false || raw === null ? "—" : String(raw));
        if (!groups.has(key)) groups.set(key, { key, label, records: [] });
        groups.get(key).records.push(r);
    }
    return [...groups.values()];
}

/**
 * Parse a <gantt_studio> arch into an archInfo object.
 *
 * Accepts either:
 *   - a string with the XML arch (legacy / external callers)
 *   - an Element already parsed by Odoo's view machinery (Odoo 18 default;
 *     `view.js` passes `archXmlDoc` which is the documentElement)
 *
 * Required: date_start, date_stop.
 *
 * @param {string|Element} arch
 * @param {{new(): DOMParser}} [ParserCls] — DOMParser constructor; only
 *        needed when `arch` is a string (browser or jsdom).
 */
export function parseGanttStudioArch(arch, ParserCls) {
    let root;
    if (arch && typeof arch === "object" && typeof arch.getAttribute === "function") {
        // Already-parsed Element — common path in Odoo 18 runtime
        root = arch;
    } else if (typeof arch === "string") {
        if (!ParserCls) {
            throw new Error(
                "gantt_studio: ParserCls must be provided when arch is a string"
            );
        }
        const doc = new ParserCls().parseFromString(arch, "text/xml");
        root = doc.documentElement;
    } else {
        throw new Error("gantt_studio: arch must be a string or an Element");
    }

    const dateStart = root.getAttribute("date_start");
    const dateStop = root.getAttribute("date_stop");
    if (!dateStart || !dateStop) {
        throw new Error("gantt_studio: 'date_start' and 'date_stop' are required");
    }
    const defaultScale = root.getAttribute("default_scale") || "week";
    if (!SCALE_CONFIG[defaultScale]) {
        throw new Error(`gantt_studio: invalid default_scale "${defaultScale}"`);
    }
    const defaultGroupBy = root.getAttribute("default_group_by") || null;
    const colorField = root.getAttribute("color_field") || null;
    const barText = root.getAttribute("bar_text") || "display_name";
    const progress = root.getAttribute("progress") || null;
    const formViewId = root.getAttribute("form_view_id");
    const canEdit = root.getAttribute("edit") !== "false";
    const canCreate = root.getAttribute("create") !== "false";
    const canDelete = root.getAttribute("delete") !== "false";
    // Tier 1 toggles (default true for opt-OUT semantics)
    const showDependencies = root.getAttribute("show_dependencies") !== "false";
    const showCriticalPath = root.getAttribute("show_critical_path") !== "false";
    const autoReschedule = root.getAttribute("auto_reschedule") !== "false";
    const baselineSupport = root.getAttribute("baseline_support") !== "false";

    // Sprint 3.1: per-record disable_drag_drop expression + milestone field.
    // `disable_drag_drop` is a Python boolean expression evaluated against
    // each record at render time; if it returns truthy the bar is locked.
    // Empty string / missing → no per-record locking.
    const disableDragDrop = root.getAttribute("disable_drag_drop") || null;
    const milestoneField = root.getAttribute("milestone_field") || null;

    // decoration-<suffix>="<python expr>" — Bootstrap-style conditional
    // styling, identical pattern to Odoo's tree/list views. We collect them
    // into a {success: "expr", danger: "expr", ...} dict here; the renderer
    // evaluates each per record and stacks the resulting CSS classes.
    const decorations = {};
    const decorationSuffixes = ["success", "danger", "warning", "info",
                                "primary", "secondary", "muted"];
    for (const suffix of decorationSuffixes) {
        const expr = root.getAttribute(`decoration-${suffix}`);
        if (expr) decorations[suffix] = expr;
    }

    // <field name="..."/> children
    const fieldsToFetch = [];
    for (const child of root.childNodes) {
        if (child.nodeType === 1 && child.tagName === "field") {
            const name = child.getAttribute("name");
            if (name) fieldsToFetch.push(name);
        }
    }

    return {
        dateStart,
        dateStop,
        defaultScale,
        defaultGroupBy,
        colorField,
        barText,
        progress,
        formViewId: formViewId ? parseInt(formViewId, 10) : null,
        canEdit,
        canCreate,
        canDelete,
        fieldsToFetch,
        showDependencies,
        showCriticalPath,
        autoReschedule,
        baselineSupport,
        disableDragDrop,
        milestoneField,
        decorations,
    };
}

// ─────────────────────────────────────────────────────────────────────────
// Tier 1: arrow path computation for dependencies
// ─────────────────────────────────────────────────────────────────────────

/**
 * Compute the SVG path "d" attribute for a dependency arrow between two bars.
 *
 * `from` and `to` are bar geometries: {x, y, width, height}.
 * `depType` ∈ {"FS","SS","FF","SF"}.
 *
 * Strategy: always route the line OUTSIDE both bars by stepping `ELBOW`
 * pixels away from each anchor side, then drawing a 5-segment path:
 *   M anchor1                       ← starts on the predecessor's edge
 *   L outside1 fromY                ← steps away from predecessor
 *   L outside1 midY                 ← vertical, outside both bars
 *   L outside2 midY                 ← horizontal, in the row gutter
 *   L outside2 toY                  ← vertical, outside successor
 *   L anchor2 toY                   ← into the successor's edge
 *
 * This avoids the classic problem of the arrow line cutting through the
 * body of either bar (visible especially in SS / SF where both anchors
 * are on the LEFT side of bars whose body sits to the right of the line).
 */
export function computeArrowPath(from, to, depType) {
    const fromY = from.y + from.height / 2;
    const toY = to.y + to.height / 2;
    const ELBOW = 12;
    const ARROW_GAP = 4;

    let predAnchorX, succAnchorX, predSide, succSide;
    switch (depType) {
        case "FS":
            predAnchorX = from.x + from.width;  predSide = "right";
            succAnchorX = to.x;                  succSide = "left";
            break;
        case "SS":
            predAnchorX = from.x;                predSide = "left";
            succAnchorX = to.x;                  succSide = "left";
            break;
        case "FF":
            predAnchorX = from.x + from.width;  predSide = "right";
            succAnchorX = to.x + to.width;       succSide = "right";
            break;
        case "SF":
            predAnchorX = from.x;                predSide = "left";
            succAnchorX = to.x + to.width;       succSide = "right";
            break;
        default:
            return "";
    }

    // Step "outside" each bar by ELBOW pixels in the anchor direction.
    const predOutsideX = predSide === "left"
        ? predAnchorX - ELBOW
        : predAnchorX + ELBOW;
    const succOutsideX = succSide === "left"
        ? succAnchorX - ELBOW
        : succAnchorX + ELBOW;

    // Mid-Y: half-way between rows. Falls in the gutter for adjacent rows
    // and on the same Y for same-row arrows (degenerate but harmless).
    const midY = (fromY + toY) / 2;

    // Final approach into the successor: stop ARROW_GAP px before the edge
    // so the head polygon has room to render.
    const enterX = succSide === "left"
        ? succAnchorX - ARROW_GAP
        : succAnchorX + ARROW_GAP;

    return [
        `M ${predAnchorX} ${fromY}`,
        `L ${predOutsideX} ${fromY}`,
        `L ${predOutsideX} ${midY}`,
        `L ${succOutsideX} ${midY}`,
        `L ${succOutsideX} ${toY}`,
        `L ${enterX} ${toY}`,
    ].join(" ");
}

// ─────────────────────────────────────────────────────────────────────────
// Tier 1.6: precise text width measurement + truncation with ellipsis
// ─────────────────────────────────────────────────────────────────────────

let _measureCtx = null;
function _getMeasureCtx() {
    if (_measureCtx !== null) return _measureCtx;
    // Defensive: any of `document`, `createElement` or `getContext` being
    // unavailable (Node tests, certain headless / stripped-down envs)
    // falls back to the char-width heuristic in `measureTextWidth`.
    if (typeof document === "undefined") return null;
    if (typeof document.createElement !== "function") return null;
    let ctx;
    try {
        const c = document.createElement("canvas");
        if (!c || typeof c.getContext !== "function") return null;
        ctx = c.getContext("2d");
        if (!ctx) return null;
        // MUST match the SCSS rule for .o_gs_bar_label_inside or accuracy drops
        ctx.font = '500 11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    } catch (_) {
        return null;
    }
    _measureCtx = ctx;
    return ctx;
}

/**
 * Measures the rendered pixel width of `text` using a hidden Canvas2D
 * context. Falls back to a 6.5 px/char heuristic when Canvas isn't
 * available (Node + jsdom unit tests).
 */
export function measureTextWidth(text) {
    if (!text) return 0;
    const ctx = _getMeasureCtx();
    if (!ctx) return text.length * 6.5;
    return ctx.measureText(text).width;
}

/**
 * Truncate `text` so it fits within `maxWidth` pixels, appending an
 * ellipsis character. Uses binary search on Canvas-measured widths so
 * the truncation is pixel-accurate for any font/character mix.
 *
 * Returns `""` when not even the ellipsis fits — caller should hide the
 * label or push it outside the bar in that case.
 */
export function truncateToWidth(text, maxWidth, ellipsis = "…") {
    if (!text || maxWidth <= 0) return "";
    if (measureTextWidth(text) <= maxWidth) return text;
    if (measureTextWidth(ellipsis) > maxWidth) return "";
    // Binary search for the largest prefix whose rendered width (plus the
    // ellipsis) still fits in maxWidth.
    let lo = 0;
    let hi = text.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        const candidate = text.slice(0, mid) + ellipsis;
        if (measureTextWidth(candidate) <= maxWidth) lo = mid;
        else hi = mid - 1;
    }
    return lo > 0 ? text.slice(0, lo) + ellipsis : ellipsis;
}

/**
 * Arrow head triangle "points" for the SVG <polygon>.
 *
 * The tip sits on the edge of the successor (`to`) at which the arrow
 * enters. The base of the triangle is on the OPPOSITE side, behind the
 * tip, so the triangle visually points INTO the bar.
 *
 *   ◀── line ──┐
 *              ▶  (tip at successor's left edge, base to its left)
 */
export function arrowHeadPoints(to, depType) {
    const SIZE = 6;
    const y = to.y + to.height / 2;
    let tipX, baseX;
    if (depType === "FS" || depType === "SS") {
        // Enters from the left → tip on left edge, base further LEFT
        tipX = to.x;
        baseX = tipX - SIZE;
    } else {
        // Enters from the right → tip on right edge, base further RIGHT
        tipX = to.x + to.width;
        baseX = tipX + SIZE;
    }
    return [
        `${tipX},${y}`,
        `${baseX},${y - SIZE / 2}`,
        `${baseX},${y + SIZE / 2}`,
    ].join(" ");
}

