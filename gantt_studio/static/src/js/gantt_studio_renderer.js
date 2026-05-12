/** @odoo-module **/

import {
    Component,
    useRef,
    useState,
    onMounted,
    onWillUnmount,
    onWillRender,
    onWillUpdateProps,
} from "@odoo/owl";
import { useVirtualGrid } from "@web/core/virtual_grid_hook";
import {
    SCALE_CONFIG,
    PALETTE,
    parseDate,
    hashColor,
    fieldDisplay,
    dateToPx,
    computeDateRange,
    groupRecords,
    computeArrowPath,
    arrowHeadPoints,
    truncateToWidth,
} from "./gantt_studio_utils";

// Para diagnosticar problemas de drag/render, activar en consola:
// `window.GANTT_STUDIO_DEBUG = true`
function dbg(...args) {
    if (typeof window !== "undefined" && window.GANTT_STUDIO_DEBUG) {
        console.log("[gantt_studio]", ...args);
    }
}

const ROW_HEIGHT = 32;
const ROW_PAD = 4;
const ROW_TOTAL = ROW_HEIGHT + ROW_PAD;
const HEADER_HEIGHT = 40;
const LEFT_PANEL_WIDTH = 200;

/**
 * Gantt Studio renderer.
 *
 * Architecture notes:
 *   - All bars are drawn as SVG (`<rect>`, `<text>`, `<path>`). This is part of
 *     the module's identity and what differentiates us from Enterprise's
 *     `web_gantt` (CSS Grid + divs).
 *   - For datasets > a few dozen rows we use `useVirtualGrid` from
 *     `@web/core/virtual_grid_hook` (Community-compatible) to only emit DOM
 *     nodes for rows whose y-band intersects the viewport (+ buffer).
 *   - Layout / arrows are NOT computed in OWL getters anymore (they ran on
 *     every render which is O(N×deps) and made drag laggy). Instead they live
 *     as plain properties on `this`, populated in `onWillRender` only when
 *     dirty flags say a recompute is needed. The dirty flags are set in
 *     `onWillUpdateProps` by comparing the prop references that come from the
 *     Model layer (the Model creates new array references when data changes
 *     via `_replaceRecord`).
 */
export class GanttStudioRenderer extends Component {
    static template = "gantt_studio.Renderer";
    static props = {
        archInfo: Object,
        resModel: String,
        fields: Object,
        records: Array,
        dependencies: { type: Array, optional: true },
        baselineLines: { type: Array, optional: true },
        baselineId: { type: [Number, Boolean], optional: true },
        criticalRecordIds: { type: Object, optional: true },
        criticalDependencyIds: { type: Object, optional: true },
        scale: String,
        criticalPathEnabled: { type: Boolean, optional: true },
        onBarClick: Function,
        onBarDrop: Function,
    };
    static defaultProps = {
        dependencies: [],
        baselineLines: [],
        baselineId: false,
        criticalRecordIds: new Set(),
        criticalDependencyIds: new Set(),
        criticalPathEnabled: false,
    };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ dragId: null, dragDx: 0 });

        // ── Dirty flags ────────────────────────────────────────────────
        // Start ALL dirty so the very first render computes everything.
        this._dirtyRange = true;       // date range / header ticks / viewport width
        this._dirtyLayout = true;      // rows[], barGeoById, total height
        this._dirtyArrows = true;      // arrow paths (derived from layout + deps)

        // ── Virtual grid ──────────────────────────────────────────────
        // We render every row as SVG, but only emit DOM nodes for rows in the
        // visible (+ buffered) y-band. `useVirtualGrid` plugs into the scroll
        // listener of `rootRef` and re-renders us when the visible range
        // changes. We use a smallish buffer (0.3) because each row is light
        // weight in SVG; tune up if scroll feels jumpy.
        this.virtualGrid = useVirtualGrid({
            scrollableRef: this.rootRef,
            bufferCoef: 0.3,
            onChange: () => this.render(),
        });

        // OWL 2 lifecycle hooks
        onWillUpdateProps((nextProps) => this._diffProps(nextProps));
        onWillRender(() => this._beforeRender());

        onMounted(() => {
            const today = new Date();
            const range = this.dateRange;
            const px = this._dateToPx(today, range.start);
            if (this.rootRef.el) {
                this.rootRef.el.scrollLeft = Math.max(0, px - 200);
            }
        });
        onWillUnmount(() => this._endDrag());
    }

    // ─────────────────────────────────────────────────────────────────
    // Lifecycle: prop diffing → dirty flags
    // ─────────────────────────────────────────────────────────────────

    _diffProps(next) {
        const prev = this.props;
        // Scale → everything date-related must recompute.
        if (next.scale !== prev.scale) {
            this._dirtyRange = true;
            this._dirtyLayout = true;
            this._dirtyArrows = true;
        }
        // Records identity changes whenever the Model notifies (it always
        // builds a new array). That can affect the date range AND geometry.
        if (next.records !== prev.records) {
            this._dirtyRange = true;
            this._dirtyLayout = true;
            this._dirtyArrows = true;
        }
        // Dependencies / criticals → only arrows need recompute.
        if (
            next.dependencies !== prev.dependencies ||
            next.criticalDependencyIds !== prev.criticalDependencyIds
        ) {
            this._dirtyArrows = true;
        }
        // Critical record set or baseline lines change bar styling, not geometry,
        // so re-derive the layout (cheap — same compute, different flags).
        if (
            next.baselineLines !== prev.baselineLines ||
            next.criticalRecordIds !== prev.criticalRecordIds ||
            next.criticalPathEnabled !== prev.criticalPathEnabled
        ) {
            this._dirtyLayout = true;
            this._dirtyArrows = true;
        }
        // archInfo identity rarely changes after parse, but cheap to check.
        if (next.archInfo !== prev.archInfo) {
            this._dirtyRange = true;
            this._dirtyLayout = true;
            this._dirtyArrows = true;
        }
    }

    _beforeRender() {
        if (this._dirtyRange) {
            this.dateRange = computeDateRange(
                this.props.records,
                this.props.archInfo.dateStart,
                this.props.archInfo.dateStop,
                this.props.scale,
            );
            this.headerTicks = this._computeHeaderTicks();
            this.viewportWidth = Math.max(
                800,
                this._dateToPx(this.dateRange.end, this.dateRange.start),
            );
            this._dirtyRange = false;
        }
        if (this._dirtyLayout) {
            const { rows, barGeoById } = this._computeLayout();
            this.allRows = rows;
            this.barGeoById = barGeoById;
            this.totalHeight = HEADER_HEIGHT + rows.length * ROW_TOTAL;
            // Feed every row's height to the virtual grid. Heights are uniform
            // for now but the API takes a per-row array so we can later expose
            // variable-height rows (e.g. histogram rows in resource leveling).
            this.virtualGrid.setRowsHeights(rows.map(() => ROW_TOTAL));
            this._dirtyLayout = false;
        }
        if (this._dirtyArrows) {
            this.arrows = this._computeArrows();
            this._dirtyArrows = false;
        }
        // Today line — cheap, always recompute.
        this.todayLineX = this._computeTodayLineX();
        // Slice the row array down to what's visible. This is what the OWL
        // template iterates, so the SVG only ever emits DOM for these rows.
        this.visibleRows = this._sliceVisibleRows();
    }

    _sliceVisibleRows() {
        const all = this.allRows || [];
        const indexes = this.virtualGrid.rowsIndexes;
        if (!indexes || !indexes.length) {
            // First mount / no scroll info yet → render everything; the grid
            // hook will fire on next animation frame and trim it.
            return all;
        }
        const [s, e] = indexes;
        return all.slice(s, e + 1);
    }

    // ─────────────────────────────────────────────────────────────────
    // Computations (called from _beforeRender, gated by dirty flags)
    // ─────────────────────────────────────────────────────────────────

    _scaleCfg() { return SCALE_CONFIG[this.props.scale] || SCALE_CONFIG.week; }

    _dateToPx(date, rangeStart) {
        return dateToPx(date, rangeStart, this.props.scale);
    }

    _pxToMs(px) {
        const cfg = this._scaleCfg();
        return (px / cfg.pxPerUnit) * cfg.unitMs;
    }

    _computeHeaderTicks() {
        const cfg = this._scaleCfg();
        const ticks = [];
        for (let t = this.dateRange.start.getTime(); t <= this.dateRange.end.getTime(); t += cfg.unitMs) {
            const d = new Date(t);
            ticks.push({ label: cfg.fmt(d), x: this._dateToPx(d, this.dateRange.start) });
        }
        return ticks;
    }

    _computeTodayLineX() {
        if (!this.dateRange) return null;
        const today = new Date();
        if (today < this.dateRange.start || today > this.dateRange.end) return null;
        return this._dateToPx(today, this.dateRange.start);
    }

    _computeLayout() {
        const range = this.dateRange;
        const ds = this.props.archInfo.dateStart;
        const de = this.props.archInfo.dateStop;
        const colorField = this.props.archInfo.colorField;
        const barText = this.props.archInfo.barText;
        const progress = this.props.archInfo.progress;
        const critical = this.props.criticalRecordIds || new Set();
        const baselineMap = new Map(
            (this.props.baselineLines || []).map((l) => [l.record_id, l])
        );
        const grouped = groupRecords(this.props.records, this.props.archInfo.defaultGroupBy);
        const rows = [];
        const barGeoById = new Map();
        let rowIdx = 0;
        for (const group of grouped) {
            if (group.label) {
                rows.push({
                    type: "group",
                    rowIdx,
                    label: group.label,
                    key: `group_${group.key}`,
                });
                rowIdx++;
            }
            for (const r of group.records) {
                const start = parseDate(r[ds]);
                const stop = parseDate(r[de]);
                if (!start || !stop) continue;
                const x1 = this._dateToPx(start, range.start);
                const x2 = this._dateToPx(stop, range.start);
                const width = Math.max(4, x2 - x1);
                const y = this._rowY(rowIdx) + 4;
                const height = ROW_HEIGHT - 8;
                const color = colorField
                    ? hashColor(r[colorField])
                    : PALETTE[rowIdx % PALETTE.length];
                const label = fieldDisplay(r, barText) || `#${r.id}`;
                // Label placement (canvas-precise measurement). See history
                // for the design rationale; logic unchanged from the previous
                // implementation.
                const PAD_INSIDE = 8;
                const MIN_INSIDE_USEFUL_WIDTH = 30;
                const insideWidth = width - PAD_INSIDE * 2;
                let displayLabel = label;
                let labelOutside = false;
                let labelX;
                if (insideWidth < MIN_INSIDE_USEFUL_WIDTH) {
                    labelOutside = true;
                    labelX = x1 + width + 6;
                } else {
                    labelX = x1 + PAD_INSIDE;
                    displayLabel = truncateToWidth(label, insideWidth);
                    if (!displayLabel) {
                        labelOutside = true;
                        labelX = x1 + width + 6;
                        displayLabel = label;
                    }
                }
                const labelY = labelOutside
                    ? y + height / 2 + 6
                    : y + height / 2;
                let ghost = null;
                const bl = baselineMap.get(r.id);
                if (bl && bl.date_start && bl.date_stop) {
                    const gx1 = this._dateToPx(parseDate(bl.date_start), range.start);
                    const gx2 = this._dateToPx(parseDate(bl.date_stop), range.start);
                    ghost = { x: gx1, width: Math.max(4, gx2 - gx1) };
                }
                rows.push({
                    type: "bar",
                    rowIdx,
                    record: r,
                    key: `bar_${r.id}`,
                    x: x1,
                    width,
                    y,
                    height,
                    color,
                    label,
                    displayLabel,
                    labelX,
                    labelY,
                    labelOutside,
                    progress: progress != null
                        ? Math.max(0, Math.min(100, r[progress] || 0))
                        : null,
                    leftLabel: fieldDisplay(r, "display_name"),
                    critical: critical.has(r.id),
                    ghost,
                });
                barGeoById.set(r.id, { x: x1, y, width, height });
                rowIdx++;
            }
        }
        return { rows, barGeoById };
    }

    _computeArrows() {
        const barGeoById = this.barGeoById;
        if (!barGeoById) return [];
        const critical = this.props.criticalDependencyIds || new Set();
        const out = [];
        for (const dep of this.props.dependencies || []) {
            const from = barGeoById.get(dep.predecessor_id);
            const to = barGeoById.get(dep.successor_id);
            if (!from || !to) continue;
            out.push({
                id: dep.id,
                d: computeArrowPath(from, to, dep.dep_type),
                head: arrowHeadPoints(to, dep.dep_type),
                critical: critical.has(dep.id),
            });
        }
        return out;
    }

    _rowY(rowIdx) {
        return HEADER_HEIGHT + rowIdx * ROW_TOTAL;
    }

    // ─────────────────────────────────────────────────────────────────
    // Template getters (cheap — they only read precomputed fields)
    // ─────────────────────────────────────────────────────────────────

    get leftPanelWidth() { return LEFT_PANEL_WIDTH; }
    get rowHeight() { return ROW_HEIGHT; }
    get headerHeight() { return HEADER_HEIGHT; }
    // Exposed for the XML template (compat with the previous interface).
    rowY(rowIdx) { return this._rowY(rowIdx); }

    // ─────────────────────────────────────────────────────────────────
    // Drag handling (unchanged — interacts with state, not layout cache)
    // ─────────────────────────────────────────────────────────────────

    onBarMouseDown(row, ev) {
        if (row.type !== "bar") return;
        if (ev.button !== 0) return;
        this._dragSeed = {
            recordId: row.record.id,
            origX: row.x,
            startX: ev.clientX,
            origStart: parseDate(row.record[this.props.archInfo.dateStart]),
        };
        this.state.dragId = row.record.id;
        this.state.dragDx = 0;
        this._onMoveBound = this._onDragMove.bind(this);
        this._onUpBound = this._onDragUp.bind(this);
        document.addEventListener("mousemove", this._onMoveBound);
        document.addEventListener("mouseup", this._onUpBound);
        dbg("drag DOWN", {
            recordId: row.record.id,
            origStart: this._dragSeed.origStart?.toISOString(),
        });
        ev.preventDefault();
    }

    _onDragMove(ev) {
        if (!this._dragSeed) return;
        this.state.dragDx = ev.clientX - this._dragSeed.startX;
    }

    _onDragUp(ev) {
        if (!this._dragSeed) return;
        const seed = this._dragSeed;
        const dx = ev.clientX - seed.startX;
        const deltaMs = this._pxToMs(dx);
        const newStart = new Date(seed.origStart.getTime() + deltaMs);
        dbg("drag UP", {
            recordId: seed.recordId, dx, scale: this.props.scale,
            newStart: newStart.toISOString(), isClick: Math.abs(dx) < 4,
        });
        this._endDrag();
        if (Math.abs(dx) < 4) {
            const rec = this.props.records.find((r) => r.id === seed.recordId);
            if (rec) this.props.onBarClick(rec);
            return;
        }
        this.props.onBarDrop(seed.recordId, newStart);
    }

    _endDrag() {
        if (this._onMoveBound) {
            document.removeEventListener("mousemove", this._onMoveBound);
            this._onMoveBound = null;
        }
        if (this._onUpBound) {
            document.removeEventListener("mouseup", this._onUpBound);
            this._onUpBound = null;
        }
        this._dragSeed = null;
        this.state.dragId = null;
        this.state.dragDx = 0;
    }

    /** dx applied to a bar's x while it's being dragged (visual feedback). */
    dragOffsetForBar(row) {
        return (row.type === "bar" && this.state.dragId === row.record.id)
            ? this.state.dragDx
            : 0;
    }
}
