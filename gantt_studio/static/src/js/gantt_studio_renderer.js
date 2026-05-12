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
    buildTree,
    walkTree,
    computeRollup,
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

// Sprint 3.2.A — drag-resize del borde del bar.
// Ancho de los "asas" invisibles a cada lado. Probar valores chicos (6-10)
// para no robar área de drag del centro.
const RESIZE_HANDLE_W = 8;
// Duración mínima permitida al resize (4 horas) — evita zero-width bars
// y que el user accidentalmente colapse el bar a cero por arrastre brusco.
const MIN_DURATION_MS = 4 * 3600 * 1000;

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
        // Sprint 3.2.A — opcional, controller debe pasarlo para que el
        // resize tenga efecto. Si no se pasa, los handles del borde no
        // se renderean (resize deshabilitado).
        onBarResize: { type: Function, optional: true },
        // Sprint 3.2.B — opcional, controller debe pasarlo para que la
        // edición inline tenga efecto. Si no se pasa, el doble-click
        // simplemente NO hace nada (queda el click → open form de siempre).
        onBarRename: { type: Function, optional: true },
        // Sprint 3.2.C — opcional, controller debe pasarlo para habilitar
        // drag-to-create deps. Llama con (predId, succId, type, lagDays).
        onDepCreate: { type: Function, optional: true },
        // Sprint 3.4 — Resource histogram (payload del RPC) y set de ids
        // sobreasignados (highlight rojo en sus bars).
        resourceHistogram: { type: [Object, { value: null }], optional: true },
        overallocatedIds: { type: Object, optional: true },
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
        onBarResize: null,
        onBarRename: null,
        onDepCreate: null,
        resourceHistogram: null,
        overallocatedIds: new Set(),
    };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({
            dragId: null, dragDx: 0,
            // Sprint 3.2.A — resize del borde. resizeEdge ∈ {'left','right'|null}.
            resizeId: null, resizeDx: 0, resizeEdge: null,
            // Sprint 3.2.B — edición inline del nombre.
            editingId: null, editingValue: "",
            // Sprint 3.2.C — drag-to-create deps.
            // `depDragFrom`: id del record predecesor durante el drag.
            // `depDragFromEdge`: 'left' o 'right' del bar de origen.
            // `depDragTo`: {x, y} del cursor (línea fantasma).
            // `depPopover`: si !== null, popover abierto con
            //   {predId, succId, x, y, depType, lagDays}
            depDragFrom: null, depDragFromEdge: null, depDragTo: null,
            depPopover: null,
            // Sprint 3.3 — WBS: ids de nodos colapsados. Mutamos via
            // setState para que OWL detecte el cambio. Default: ningún
            // nodo colapsado (todo expandido).
            collapsed: new Set(),
        });

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
            // P1 hardening: Escape cancela drag y resize en curso.
            this._escHandler = (ev) => {
                if (ev.key !== "Escape") return;
                if (this._dragSeed) this._endDrag();
                if (this._resizeSeed) this._endResize();
            };
            document.addEventListener("keydown", this._escHandler);
        });
        onWillUnmount(() => {
            this._endDrag();
            this._endResize();
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
        // Sprint 3.4 — resource histogram + overallocation set.
        // Layout debe recomputarse para aplicar el highlight rojo en bars.
        if (
            next.resourceHistogram !== prev.resourceHistogram ||
            next.overallocatedIds !== prev.overallocatedIds
        ) {
            this._dirtyLayout = true;
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
        const parentField = this.props.archInfo.parentField;
        const critical = this.props.criticalRecordIds || new Set();
        const overallocated = this.props.overallocatedIds || new Set();
        const baselineMap = new Map(
            (this.props.baselineLines || []).map((l) => [l.record_id, l])
        );

        // Sprint 3.3 — Si hay parent_field, agrupamos via árbol jerárquico
        // PRIMERO y groupBy (si lo hay) se aplica al nivel de raíces.
        // Si NO hay parent_field, mantenemos el flujo plano de antes.
        let grouped;
        if (parentField) {
            const tree = buildTree(this.props.records, parentField);
            const walked = walkTree(tree, this.state.collapsed);
            // Conversión al shape que el resto del código espera: lista
            // ordenada de records con metadata (depth, hasChildren).
            grouped = [{
                key: "__wbs__",
                label: "",
                records: walked.map((w) => ({
                    ...w.record,
                    __depth: w.depth,
                    __hasChildren: w.hasChildren,
                    __isParent: w.hasChildren,
                    __children: w.children,
                })),
            }];
        } else {
            // Bug fix: agrupado debe respetar lo que el usuario eligió en el
            // search panel (this.props.groupBy). Si no hay groupBy live, caemos
            // al defaultGroupBy del arch. Si tampoco hay, no agrupamos.
            const groupByField = (this.props.groupBy && this.props.groupBy.length)
                ? this.props.groupBy[0]
                : this.props.archInfo.defaultGroupBy;
            grouped = groupRecords(this.props.records, groupByField);
        }

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
                // Sprint 3.3 — Si el record es un padre WBS, sus fechas
                // efectivas vienen del ROLLUP (min start / max stop) de
                // toda su descendencia. El padre declara sus propias
                // fechas también, pero el bar visual envuelve a los hijos.
                let start, stop;
                if (r.__isParent && r.__children) {
                    // computeRollup necesita un nodo {record, children}.
                    const rollup = computeRollup(
                        { record: r, children: r.__children },
                        ds, de,
                    );
                    start = rollup.start;
                    stop = rollup.stop;
                } else {
                    start = parseDate(r[ds]);
                    stop = parseDate(r[de]);
                }
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
                // Sprint 3.3 — Los padres WBS no son arrastrables: su bar
                // es un envelope calculado de los hijos. Para mover toda
                // la rama, el user mueve los hijos individualmente (o
                // usaría una feature futura "drag parent → drag chain").
                let dragDisabled = this._evalRecordExpr(disableDragExpr, r);
                if (r.__isParent) dragDisabled = true;
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
                    // Sprint 3.3 — WBS metadata.
                    depth: r.__depth || 0,
                    isParent: !!r.__isParent,
                    isCollapsed: r.__isParent && this.state.collapsed.has(r.id),
                    // Sprint 3.4 — overallocation flag (resource conflict).
                    overallocated: overallocated.has(r.id),
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
            if (!rec) return;
            // Sprint 3.2.B: si la edición inline está habilitada, diferimos
            // el click 250ms para darle chance al dblclick de cancelarlo.
            // Si no hay onBarRename, el click va inmediato (UX sin latencia).
            if (this.props.onBarRename) {
                this._pendingClickTimeout = setTimeout(() => {
                    this._pendingClickTimeout = null;
                    this.props.onBarClick(rec);
                }, 250);
            } else {
                this.props.onBarClick(rec);
            }
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

    // ─────────────────────────────────────────────────────────────────
    // Sprint 3.2.A — Drag-resize del borde del bar
    // ─────────────────────────────────────────────────────────────────

    /** Empieza el resize cuando el user toca un handle de borde.
     * `edge` es 'left' o 'right'. */
    onResizeMouseDown(row, edge, ev) {
        if (row.type !== "bar") return;
        if (ev.button !== 0) return;
        if (!this.props.onBarResize) return;        // resize deshabilitado
        if (row.dragDisabled) return;               // bar bloqueado
        if (row.isMilestone) return;                // milestones no tienen duración
        this._startResize(row, edge, ev.clientX);
        ev.preventDefault();
        ev.stopPropagation();   // que el mousedown del bar no dispare drag
    }

    /** Variante touch del resize. */
    onResizeTouchStart(row, edge, ev) {
        if (row.type !== "bar") return;
        if (!ev.touches || ev.touches.length !== 1) return;
        if (!this.props.onBarResize) return;
        if (row.dragDisabled || row.isMilestone) return;
        this._startResize(row, edge, ev.touches[0].clientX);
        ev.preventDefault();
        ev.stopPropagation();
    }

    _startResize(row, edge, clientX) {
        this._resizeSeed = {
            recordId: row.record.id,
            edge,
            startX: clientX,
            origX: row.x,
            origWidth: row.width,
            origStart: parseDate(row.record[this.props.archInfo.dateStart]),
            origStop: parseDate(row.record[this.props.archInfo.dateStop]),
        };
        this.state.resizeId = row.record.id;
        this.state.resizeEdge = edge;
        this.state.resizeDx = 0;

        this._onResizeMoveBound = this._onResizeMove.bind(this);
        this._onResizeUpBound = this._onResizeUp.bind(this);
        this._onResizeTouchMoveBound = (ev) => {
            if (!ev.touches || !ev.touches.length) return;
            this._onResizeMove({ clientX: ev.touches[0].clientX });
        };
        this._onResizeTouchEndBound = (ev) => {
            const t = (ev.changedTouches && ev.changedTouches[0]) || null;
            this._onResizeUp({ clientX: t ? t.clientX : this._resizeSeed.startX });
        };
        document.addEventListener("mousemove", this._onResizeMoveBound);
        document.addEventListener("mouseup", this._onResizeUpBound);
        document.addEventListener("touchmove", this._onResizeTouchMoveBound, { passive: false });
        document.addEventListener("touchend", this._onResizeTouchEndBound);
        document.addEventListener("touchcancel", this._onResizeTouchEndBound);
        dbg("resize START", { recordId: row.record.id, edge, origWidth: row.width });
    }

    _onResizeMove(ev) {
        if (!this._resizeSeed) return;
        let dx = ev.clientX - this._resizeSeed.startX;
        // Clamp para no permitir colapsar el bar bajo el ancho minimo durante
        // el arrastre. El ancho efectivo durante resize es:
        //   right edge:  origWidth + dx
        //   left edge:   origWidth - dx (porque la x crece y la barra
        //                                pierde ancho equivalente)
        const minWidthPx = this._dateToPx(
            new Date(0 + MIN_DURATION_MS), new Date(0)
        );
        if (this._resizeSeed.edge === "right") {
            if (this._resizeSeed.origWidth + dx < minWidthPx) {
                dx = minWidthPx - this._resizeSeed.origWidth;
            }
        } else {
            if (this._resizeSeed.origWidth - dx < minWidthPx) {
                dx = this._resizeSeed.origWidth - minWidthPx;
            }
        }
        this.state.resizeDx = dx;
    }

    _onResizeUp(ev) {
        if (!this._resizeSeed) return;
        const seed = this._resizeSeed;
        const dx = this.state.resizeDx;   // ya clamped al minimo
        const deltaMs = this._pxToMs(dx);
        let newStart = seed.origStart;
        let newStop = seed.origStop;
        if (seed.edge === "right") {
            newStop = new Date(seed.origStop.getTime() + deltaMs);
        } else {
            newStart = new Date(seed.origStart.getTime() + deltaMs);
        }
        // Defensive: aseguramos que stop > start con al menos MIN_DURATION.
        if (newStop.getTime() - newStart.getTime() < MIN_DURATION_MS) {
            if (seed.edge === "right") {
                newStop = new Date(newStart.getTime() + MIN_DURATION_MS);
            } else {
                newStart = new Date(newStop.getTime() - MIN_DURATION_MS);
            }
        }
        dbg("resize END", {
            recordId: seed.recordId, edge: seed.edge,
            origStart: seed.origStart.toISOString(),
            origStop: seed.origStop.toISOString(),
            newStart: newStart.toISOString(),
            newStop: newStop.toISOString(),
        });
        this._endResize();
        // Solo dispara onBarResize si hubo cambio real (clamp pudo dejar dx=0).
        if (Math.abs(dx) >= 1 && this.props.onBarResize) {
            this.props.onBarResize(seed.recordId, newStart, newStop);
        }
    }

    _endResize() {
        if (this._onResizeMoveBound) {
            document.removeEventListener("mousemove", this._onResizeMoveBound);
            this._onResizeMoveBound = null;
        }
        if (this._onResizeUpBound) {
            document.removeEventListener("mouseup", this._onResizeUpBound);
            this._onResizeUpBound = null;
        }
        if (this._onResizeTouchMoveBound) {
            document.removeEventListener("touchmove", this._onResizeTouchMoveBound);
            this._onResizeTouchMoveBound = null;
        }
        if (this._onResizeTouchEndBound) {
            document.removeEventListener("touchend", this._onResizeTouchEndBound);
            document.removeEventListener("touchcancel", this._onResizeTouchEndBound);
            this._onResizeTouchEndBound = null;
        }
        this._resizeSeed = null;
        this.state.resizeId = null;
        this.state.resizeEdge = null;
        this.state.resizeDx = 0;
    }

    /**
     * Geometría visual de la barra mientras se resize. Devuelve {x, width}.
     * Si no hay resize en curso para esta fila, devuelve las originales.
     */
    barGeoForRender(row) {
        if (row.type !== "bar" || this.state.resizeId !== row.record.id) {
            return { x: row.x, width: row.width };
        }
        const dx = this.state.resizeDx;
        if (this.state.resizeEdge === "right") {
            return { x: row.x, width: Math.max(4, row.width + dx) };
        } else {
            return { x: row.x + dx, width: Math.max(4, row.width - dx) };
        }
    }

    /** Constants exposed to the template. */
    get resizeHandleW() { return RESIZE_HANDLE_W; }

    // ─────────────────────────────────────────────────────────────────
    // Sprint 3.2.B — Edición inline del nombre
    // ─────────────────────────────────────────────────────────────────

    onBarDoubleClick(row, ev) {
        if (row.type !== "bar") return;
        if (!this.props.onBarRename) return;        // feature deshabilitada
        if (row.dragDisabled) return;               // bar locked
        ev.preventDefault();
        ev.stopPropagation();
        // Cancela el click diferido del 1er release (el flujo de Odoo
        // sería: 1er click → abrir form. Lo evitamos al detectar dblclick).
        if (this._pendingClickTimeout) {
            clearTimeout(this._pendingClickTimeout);
            this._pendingClickTimeout = null;
        }
        this.state.editingId = row.record.id;
        this.state.editingValue = row.label;
        // Foco al input después del próximo render (cuando el <input>
        // ya existe en el DOM).
        if (typeof setTimeout !== "undefined") {
            setTimeout(() => {
                const el = document.querySelector(
                    ".o_gs_inline_edit_input[data-record-id='" + row.record.id + "']"
                );
                if (el) {
                    el.focus();
                    el.select();
                }
            }, 0);
        }
    }

    onInlineEditInput(ev) {
        this.state.editingValue = ev.target.value;
    }

    onInlineEditKeyDown(row, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this._commitInlineEdit(row);
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this._cancelInlineEdit();
        }
    }

    onInlineEditBlur(row) {
        // Blur sin Enter explícito = commit (UX común; si el user no
        // quería guardar usa Esc). Si la edición ya fue cerrada por
        // Enter/Esc en keydown, _commitInlineEdit es no-op porque
        // editingId === null.
        if (this.state.editingId !== null) {
            this._commitInlineEdit(row);
        }
    }

    _commitInlineEdit(row) {
        const newName = (this.state.editingValue || "").trim();
        const old = row.label;
        this.state.editingId = null;
        this.state.editingValue = "";
        // No-op si no cambió o el nombre quedó vacío (mantenemos el viejo).
        if (!newName || newName === old) return;
        try {
            this.props.onBarRename(row.record.id, newName);
        } catch (e) {
            console.error("[gantt_studio] rename failed:", e);
        }
    }

    _cancelInlineEdit() {
        this.state.editingId = null;
        this.state.editingValue = "";
    }

    // ─────────────────────────────────────────────────────────────────
    // Sprint 3.2.C — Drag-to-create dependencies con popover
    // ─────────────────────────────────────────────────────────────────

    /**
     * Inicia el dibujado de una dependencia desde el handle "+" de un bar.
     * El handle vive en bordes left/right del bar (= anchor de la futura
     * dep tipada). `edge` es 'left' (anchor SS o SF) o 'right' (anchor FS
     * o FF) — el tipo final se elige en el popover.
     */
    onDepHandleMouseDown(row, edge, ev) {
        if (row.type !== "bar") return;
        if (ev.button !== 0) return;
        if (!this.props.onDepCreate) return;        // feature deshabilitada
        if (row.isMilestone) return;                // semánticamente complejo, lo dejamos
        ev.preventDefault();
        ev.stopPropagation();
        this.state.depDragFrom = row.record.id;
        this.state.depDragFromEdge = edge;
        // Punto inicial del cursor — se actualiza con onDepDragMove.
        this.state.depDragTo = this._eventPointInSvg(ev.clientX, ev.clientY);

        this._depDragMoveBound = (mv) => {
            this.state.depDragTo = this._eventPointInSvg(mv.clientX, mv.clientY);
        };
        this._depDragUpBound = (up) => this._onDepDragUp(up);
        document.addEventListener("mousemove", this._depDragMoveBound);
        document.addEventListener("mouseup", this._depDragUpBound);
    }

    _onDepDragUp(ev) {
        const fromId = this.state.depDragFrom;
        // Cerramos el modo "drag de dep" siempre, haya drop válido o no.
        if (this._depDragMoveBound) {
            document.removeEventListener("mousemove", this._depDragMoveBound);
            this._depDragMoveBound = null;
        }
        if (this._depDragUpBound) {
            document.removeEventListener("mouseup", this._depDragUpBound);
            this._depDragUpBound = null;
        }
        this.state.depDragFrom = null;
        this.state.depDragFromEdge = null;
        this.state.depDragTo = null;

        // Buscamos sobre qué bar cayó el mouseup.
        const dropEl = document.elementFromPoint(ev.clientX, ev.clientY);
        const targetGroup = dropEl?.closest?.(".o_gs_bar_group");
        // Cada <g class="o_gs_bar_group"> lleva un atributo data-record-id
        // que ponemos en el template para identificarlo en mouseup.
        const succId = targetGroup
            ? parseInt(targetGroup.getAttribute("data-record-id"), 10)
            : NaN;
        if (!fromId || !succId || succId === fromId) return;

        // Abre popover en la posición del drop.
        this.state.depPopover = {
            predId: fromId,
            succId,
            x: ev.clientX,
            y: ev.clientY,
            depType: "FS",   // default
            lagDays: 0,
        };
    }

    /** Pone el cliente XY en coordenadas SVG (canvas relativo). */
    _eventPointInSvg(clientX, clientY) {
        if (!this.rootRef.el) return { x: clientX, y: clientY };
        const rect = this.rootRef.el.getBoundingClientRect();
        return {
            x: clientX - rect.left + this.rootRef.el.scrollLeft - LEFT_PANEL_WIDTH,
            y: clientY - rect.top + this.rootRef.el.scrollTop,
        };
    }

    /**
     * Línea fantasma desde el anchor del predecesor hasta el cursor.
     * Solo se llama desde la plantilla cuando hay drag activo.
     */
    depGhostPath() {
        const fromId = this.state.depDragFrom;
        if (!fromId || !this.state.depDragTo) return "";
        const fromGeo = this.barGeoById?.get(fromId);
        if (!fromGeo) return "";
        const ax = this.state.depDragFromEdge === "right"
            ? fromGeo.x + fromGeo.width
            : fromGeo.x;
        const ay = fromGeo.y + fromGeo.height / 2;
        const tx = this.state.depDragTo.x;
        const ty = this.state.depDragTo.y;
        return `M ${ax} ${ay} L ${tx} ${ty}`;
    }

    onDepPopoverTypeChange(ev) {
        if (this.state.depPopover) this.state.depPopover.depType = ev.target.value;
    }
    onDepPopoverLagChange(ev) {
        if (this.state.depPopover) {
            const v = parseFloat(ev.target.value);
            this.state.depPopover.lagDays = isNaN(v) ? 0 : v;
        }
    }
    onDepPopoverConfirm() {
        const p = this.state.depPopover;
        if (!p || !this.props.onDepCreate) {
            this.state.depPopover = null;
            return;
        }
        try {
            this.props.onDepCreate(p.predId, p.succId, p.depType, p.lagDays);
        } catch (e) {
            console.error("[gantt_studio] dep create failed:", e);
        }
        this.state.depPopover = null;
    }
    onDepPopoverCancel() {
        this.state.depPopover = null;
    }

    // ─────────────────────────────────────────────────────────────────
    // Sprint 3.3 — WBS expand/collapse
    // ─────────────────────────────────────────────────────────────────

    /** Toggle del estado expandido/colapsado de un nodo padre. */
    onToggleCollapse(row, ev) {
        if (!row.isParent) return;
        ev.preventDefault();
        ev.stopPropagation();
        // Mutamos en lugar de reasignar el Set; OWL detecta el cambio
        // mediante useState. Reasignamos por las dudas para forzar
        // detección si alguna implementación lo requiere.
        const next = new Set(this.state.collapsed);
        if (next.has(row.record.id)) {
            next.delete(row.record.id);
        } else {
            next.add(row.record.id);
        }
        this.state.collapsed = next;
        // Layout cambia (filas hijas aparecen/desaparecen).
        this._dirtyLayout = true;
        this._dirtyArrows = true;
    }
}
