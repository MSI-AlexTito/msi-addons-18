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
import { evaluateBooleanExpr } from "@web/core/py_js/py";
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
        groupBy: { type: Array, optional: true },
        dependencies: { type: Array, optional: true },
        baselineLines: { type: Array, optional: true },
        baselineId: { type: [Number, Boolean], optional: true },
        criticalRecordIds: { type: Object, optional: true },
        criticalDependencyIds: { type: Object, optional: true },
        scale: String,
        criticalPathEnabled: { type: Boolean, optional: true },
        goToDateRequest: { type: [Date, { value: null }], optional: true },
        onBarClick: Function,
        onBarDrop: Function,
    };
    static defaultProps = {
        groupBy: [],
        dependencies: [],
        baselineLines: [],
        baselineId: false,
        criticalRecordIds: new Set(),
        criticalDependencyIds: new Set(),
        criticalPathEnabled: false,
        goToDateRequest: null,
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
            // P1 hardening: Shift+wheel = horizontal scroll (paid Gantt UX).
            // Touch: shift no aplica, los swipes horizontales ya funcionan.
            this._wheelHandler = (ev) => {
                if (!ev.shiftKey || !this.rootRef.el) return;
                ev.preventDefault();
                this.rootRef.el.scrollLeft += ev.deltaY;
            };
            this.rootRef.el?.addEventListener("wheel", this._wheelHandler, { passive: false });
            // P1 hardening: Escape cancela drag.
            this._escHandler = (ev) => {
                if (ev.key === "Escape" && this._dragSeed) this._endDrag();
            };
            document.addEventListener("keydown", this._escHandler);
        });
        onWillUnmount(() => {
            this._endDrag();
            if (this._wheelHandler && this.rootRef.el) {
                this.rootRef.el.removeEventListener("wheel", this._wheelHandler);
            }
            if (this._escHandler) {
                document.removeEventListener("keydown", this._escHandler);
            }
        });
    }

    // ─────────────────────────────────────────────────────────────────
    // Lifecycle: prop diffing → dirty flags
    // ─────────────────────────────────────────────────────────────────

    _diffProps(next) {
        const prev = this.props;
        // Sprint 3.1.C.4 — date picker / hotkeys.
        // When the controller bumps `goToDateRequest`, scroll the gantt
        // so that the requested date is centered in the viewport. We do
        // this here (in onWillUpdateProps) so it runs BEFORE the dirty-
        // flag recompute pass; the layout doesn't actually change.
        if (next.goToDateRequest && next.goToDateRequest !== prev.goToDateRequest) {
            // The new date may be out of the current dateRange. Trigger
            // a range recompute so the renderer can include it. We use
            // queueMicrotask so we read the just-updated dateRange.
            this._dirtyRange = true;
            this._pendingScrollTo = next.goToDateRequest;
        }
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
        // Live groupBy from the search panel → layout must regroup rows.
        // The model recreates this array reference on every load() so a
        // reference compare is enough.
        if (next.groupBy !== prev.groupBy) {
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
            // Bug fix: si hay un scroll pendiente a una fecha fuera del
            // rango de los records, extendemos el rango para incluirla
            // ANTES de calcular el layout.
            if (this._pendingScrollTo) {
                this._expandRangeToInclude(this._pendingScrollTo);
            }
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
        // Sprint 3.1.C.4 — if a date scroll was requested, perform it
        // AFTER the next paint so the SVG width has been laid out.
        if (this._pendingScrollTo) {
            const dt = this._pendingScrollTo;
            this._pendingScrollTo = null;
            // Defer to next frame so the DOM has the new viewportWidth.
            // Defensive: in Node test environments rAF may not exist —
            // fall back to setTimeout. In real browsers this always uses
            // the proper paint-synchronized callback.
            const raf = (typeof requestAnimationFrame !== "undefined")
                ? requestAnimationFrame
                : ((fn) => setTimeout(fn, 16));
            raf(() => this._scrollToDate(dt));
        }
    }

    _scrollToDate(date) {
        if (!this.rootRef.el || !this.dateRange) return;
        const x = this._dateToPx(date, this.dateRange.start);
        // Center the date in the visible viewport
        const viewportW = this.rootRef.el.clientWidth - LEFT_PANEL_WIDTH;
        this.rootRef.el.scrollLeft = Math.max(0, x - viewportW / 2);
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

    /**
     * Bug fix: si el usuario pidió saltar a una fecha que está FUERA del
     * rango de los records cargados, el computeDateRange original devuelve
     * un rango que no incluye esa fecha y el scroll queda clampeado. Esta
     * función extiende el rango para que cubra `extraDate` con margen.
     */
    _expandRangeToInclude(extraDate) {
        if (!this.dateRange || !extraDate) return;
        const cfg = this._scaleCfg();
        const margin = cfg.unitMs * 2;
        const t = extraDate.getTime();
        if (t < this.dateRange.start.getTime()) {
            this.dateRange = {
                start: new Date(Math.floor((t - margin) / cfg.unitMs) * cfg.unitMs),
                end: this.dateRange.end,
            };
            // Re-emit ticks + viewportWidth con el nuevo rango.
            this.headerTicks = this._computeHeaderTicks();
            this.viewportWidth = Math.max(
                800,
                this._dateToPx(this.dateRange.end, this.dateRange.start),
            );
            this._dirtyLayout = true;  // bars need re-compute x positions
        } else if (t > this.dateRange.end.getTime()) {
            this.dateRange = {
                start: this.dateRange.start,
                end: new Date(Math.ceil((t + margin) / cfg.unitMs) * cfg.unitMs),
            };
            this.headerTicks = this._computeHeaderTicks();
            this.viewportWidth = Math.max(
                800,
                this._dateToPx(this.dateRange.end, this.dateRange.start),
            );
            this._dirtyLayout = true;
        }
    }

    _computeTodayLineX() {
        if (!this.dateRange) return null;
        const today = new Date();
        if (today < this.dateRange.start || today > this.dateRange.end) return null;
        return this._dateToPx(today, this.dateRange.start);
    }

    /**
     * Evaluate a Python boolean expression against a record. Used by
     * `decoration-*` and `disable_drag_drop` features (Sprint 3.1).
     *
     * The record dict is used as-is for the eval context — m2o fields
     * come through as `[id, name]` Python-list-like arrays, scalars as
     * scalars, dates as ISO strings (from `searchRead` JSON wire format).
     * Errors in user expressions are logged and treated as `false` so
     * a typo can't crash the renderer.
     */
    _evalRecordExpr(expr, record) {
        if (!expr) return false;
        try {
            return Boolean(evaluateBooleanExpr(expr, record));
        } catch (e) {
            if (typeof window !== "undefined" && window.GANTT_STUDIO_DEBUG) {
                console.warn(`[gantt_studio] expr error "${expr}":`, e.message);
            }
            return false;
        }
    }

    _computeLayout() {
        const range = this.dateRange;
        const ds = this.props.archInfo.dateStart;
        const de = this.props.archInfo.dateStop;
        const colorField = this.props.archInfo.colorField;
        const barText = this.props.archInfo.barText;
        const progress = this.props.archInfo.progress;
        const decorationsArch = this.props.archInfo.decorations || {};
        const disableDragExpr = this.props.archInfo.disableDragDrop;
        const milestoneField = this.props.archInfo.milestoneField;
        const critical = this.props.criticalRecordIds || new Set();
        const baselineMap = new Map(
            (this.props.baselineLines || []).map((l) => [l.record_id, l])
        );
        // Bug fix: agrupado debe respetar lo que el usuario eligió en el
        // search panel (this.props.groupBy). Si no hay groupBy live, caemos
        // al defaultGroupBy del arch. Si tampoco hay, no agrupamos.
        const groupByField = (this.props.groupBy && this.props.groupBy.length)
            ? this.props.groupBy[0]
            : this.props.archInfo.defaultGroupBy;
        const grouped = groupRecords(this.props.records, groupByField);
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
                // Decorations: evaluate each Python expression against the
                // record. Each truthy result becomes a CSS class on the bar.
                const decorationClasses = [];
                for (const suffix in decorationsArch) {
                    if (this._evalRecordExpr(decorationsArch[suffix], r)) {
                        decorationClasses.push(`o_gs_bar_decoration_${suffix}`);
                    }
                }
                // Per-record drag lock.
                const dragDisabled = this._evalRecordExpr(disableDragExpr, r);
                // Sprint 3.1.C.3 — milestone detection.
                // If the configured boolean field is truthy, the record is
                // rendered as a diamond at its `date_start` (date_stop is
                // ignored visually — milestones have no duration). The
                // record's "milestone flag" is read raw from the dict; any
                // truthy value works (True / 1 / non-empty string / m2o).
                const isMilestone = !!(milestoneField && r[milestoneField]);
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
                    decorationClasses,
                    dragDisabled,
                    isMilestone,
                    // Diamond geometry: a square rotated 45° centered at
                    // (x1, y + height/2). We use SVG polygon points so the
                    // template doesn't need to compute trig.
                    milestonePoints: isMilestone
                        ? this._diamondPoints(x1, y + height / 2, height * 0.7)
                        : null,
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

    /**
     * Diamond (rotated square) polygon centered at (cx, cy), with the given
     * vertical extent. Returns an SVG `points` string usable in <polygon>.
     */
    _diamondPoints(cx, cy, size) {
        const half = size / 2;
        return [
            `${cx},${cy - half}`,   // top
            `${cx + half},${cy}`,   // right
            `${cx},${cy + half}`,   // bottom
            `${cx - half},${cy}`,   // left
        ].join(" ");
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
        this._startDrag(row, ev.clientX);
        ev.preventDefault();
    }

    /** P1 hardening: touch entry point — funciona en tablet/móvil. */
    onBarTouchStart(row, ev) {
        if (row.type !== "bar") return;
        if (!ev.touches || ev.touches.length !== 1) return;  // ignore multi-touch
        this._startDrag(row, ev.touches[0].clientX);
        ev.preventDefault();
    }

    _startDrag(row, clientX) {
        // Sprint 3.1: we still register the drag seed when the bar is
        // drag-locked so that a CLICK on it (Δx < 4 px on mouseup) still
        // opens the record form. The seed carries the `dragDisabled` flag
        // and the move/up handlers will skip the actual reposition + RPC.
        this._dragSeed = {
            recordId: row.record.id,
            origX: row.x,
            startX: clientX,
            origStart: parseDate(row.record[this.props.archInfo.dateStart]),
            dragDisabled: !!row.dragDisabled,
        };
        this.state.dragId = row.record.id;
        this.state.dragDx = 0;
        this._onMoveBound = this._onDragMove.bind(this);
        this._onUpBound = this._onDragUp.bind(this);
        this._onTouchMoveBound = (ev) => {
            if (!ev.touches || !ev.touches.length) return;
            this._onDragMove({ clientX: ev.touches[0].clientX });
        };
        this._onTouchEndBound = (ev) => {
            const t = (ev.changedTouches && ev.changedTouches[0]) || null;
            this._onDragUp({ clientX: t ? t.clientX : this._dragSeed.startX });
        };
        document.addEventListener("mousemove", this._onMoveBound);
        document.addEventListener("mouseup", this._onUpBound);
        document.addEventListener("touchmove", this._onTouchMoveBound, { passive: false });
        document.addEventListener("touchend", this._onTouchEndBound);
        document.addEventListener("touchcancel", this._onTouchEndBound);
        dbg("drag DOWN", {
            recordId: row.record.id,
            origStart: this._dragSeed.origStart?.toISOString(),
        });
    }

    _onDragMove(ev) {
        if (!this._dragSeed) return;
        // Drag-locked bars: never move visually; the mousemove only ticks
        // dx for the click-vs-drag heuristic in `_onDragUp`.
        if (this._dragSeed.dragDisabled) return;
        this.state.dragDx = ev.clientX - this._dragSeed.startX;
    }

    _onDragUp(ev) {
        if (!this._dragSeed) return;
        const seed = this._dragSeed;
        const dx = ev.clientX - seed.startX;
        const isClick = Math.abs(dx) < 4;
        dbg("drag UP", {
            recordId: seed.recordId, dx, dragDisabled: seed.dragDisabled,
            scale: this.props.scale, isClick,
        });
        this._endDrag();
        if (isClick) {
            const rec = this.props.records.find((r) => r.id === seed.recordId);
            if (rec) this.props.onBarClick(rec);
            return;
        }
        // Drag-locked: silently swallow the drag (no RPC, no visual move).
        if (seed.dragDisabled) return;
        const deltaMs = this._pxToMs(dx);
        const newStart = new Date(seed.origStart.getTime() + deltaMs);
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
        if (this._onTouchMoveBound) {
            document.removeEventListener("touchmove", this._onTouchMoveBound);
            this._onTouchMoveBound = null;
        }
        if (this._onTouchEndBound) {
            document.removeEventListener("touchend", this._onTouchEndBound);
            document.removeEventListener("touchcancel", this._onTouchEndBound);
            this._onTouchEndBound = null;
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
