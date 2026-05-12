/** @odoo-module **/

import { Component, useRef, useState, onMounted, onWillUnmount } from "@odoo/owl";
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
    measureTextWidth,
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
const HEADER_HEIGHT = 40;
const LEFT_PANEL_WIDTH = 200;

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

        onMounted(() => {
            const today = new Date();
            const range = this._dateRange();
            const px = this._dateToPx(today, range.start);
            if (this.rootRef.el) {
                this.rootRef.el.scrollLeft = Math.max(0, px - 200);
            }
        });
        onWillUnmount(() => this._endDrag());
    }

    // ─────────────────────────────────────────────────────────────────
    _scaleCfg() { return SCALE_CONFIG[this.props.scale] || SCALE_CONFIG.week; }
    _dateRange() {
        return computeDateRange(
            this.props.records,
            this.props.archInfo.dateStart,
            this.props.archInfo.dateStop,
            this.props.scale,
        );
    }
    _dateToPx(date, rangeStart) {
        return dateToPx(date, rangeStart, this.props.scale);
    }
    _pxToMs(px) {
        const cfg = this._scaleCfg();
        return (px / cfg.pxPerUnit) * cfg.unitMs;
    }

    get headerTicks() {
        const cfg = this._scaleCfg();
        const range = this._dateRange();
        const ticks = [];
        for (let t = range.start.getTime(); t <= range.end.getTime(); t += cfg.unitMs) {
            const d = new Date(t);
            ticks.push({ label: cfg.fmt(d), x: this._dateToPx(d, range.start) });
        }
        return ticks;
    }

    get viewportWidth() {
        const range = this._dateRange();
        return Math.max(800, this._dateToPx(range.end, range.start));
    }

    get groupedRecords() {
        return groupRecords(this.props.records, this.props.archInfo.defaultGroupBy);
    }

    /**
     * Compute layout rows:
     *  - "group" rows for group headers
     *  - "bar" rows for records (with x/y/width geometry stored)
     *
     * Also exposes a `barGeoById` map used to draw dependency arrows and
     * baseline ghosts at the exact position of each record.
     */
    get layout() {
        const range = this._dateRange();
        const ds = this.props.archInfo.dateStart;
        const de = this.props.archInfo.dateStop;
        const colorField = this.props.archInfo.colorField;
        const barText = this.props.archInfo.barText;
        const progress = this.props.archInfo.progress;
        const critical = this.props.criticalRecordIds || new Set();
        const baselineMap = new Map(
            (this.props.baselineLines || []).map((l) => [l.record_id, l])
        );
        const rows = [];
        const barGeoById = new Map();
        let rowIdx = 0;
        for (const group of this.groupedRecords) {
            if (group.label) {
                rows.push({ type: "group", rowIdx, label: group.label });
                rowIdx++;
            }
            for (const r of group.records) {
                const start = parseDate(r[ds]);
                const stop = parseDate(r[de]);
                if (!start || !stop) continue;
                const x1 = this._dateToPx(start, range.start);
                const x2 = this._dateToPx(stop, range.start);
                const width = Math.max(4, x2 - x1);
                const y = this.rowY(rowIdx) + 4;
                const height = ROW_HEIGHT - 8;
                const color = colorField ? hashColor(r[colorField]) : PALETTE[rowIdx % PALETTE.length];
                const label = fieldDisplay(r, barText) || `#${r.id}`;
                // ── Label placement (precise Canvas measurement) ──────────
                //  Inside  → centered vertically on the bar (and the bar's
                //            rect covers any dependency arrow underneath).
                //  Outside → positioned BELOW the bar's vertical center so
                //            the FS/SS/FF/SF arrow line (drawn at the bar's
                //            center y) does NOT cross through the text and
                //            give a "strikethrough" look.
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
                // y of the label: inside → bar center; outside → 6px below
                // bar center, which puts the entire glyph below the arrow's
                // horizontal segment (arrow goes at y = bar center).
                const labelY = labelOutside
                    ? y + height / 2 + 6
                    : y + height / 2;
                // Baseline ghost: a faded bar behind the actual one
                let ghost = null;
                const bl = baselineMap.get(r.id);
                if (bl && bl.date_start && bl.date_stop) {
                    const gx1 = this._dateToPx(parseDate(bl.date_start), range.start);
                    const gx2 = this._dateToPx(parseDate(bl.date_stop), range.start);
                    ghost = { x: gx1, width: Math.max(4, gx2 - gx1) };
                }
                const bar = {
                    type: "bar",
                    rowIdx,
                    record: r,
                    x: x1,
                    width,
                    y,
                    height,
                    color,
                    label,          // full text, for the <title> tooltip
                    displayLabel,   // possibly truncated with "…"
                    labelX,
                    labelY,
                    labelOutside,
                    progress: progress != null ? Math.max(0, Math.min(100, r[progress] || 0)) : null,
                    leftLabel: fieldDisplay(r, "display_name"),
                    critical: critical.has(r.id),
                    ghost,
                };
                rows.push(bar);
                barGeoById.set(r.id, { x: x1, y, width, height });
                rowIdx++;
            }
        }
        return { rows, barGeoById };
    }

    get rows() { return this.layout.rows; }

    /** Arrows derived from layout + dependencies. */
    get arrows() {
        const { barGeoById } = this.layout;
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

    get totalHeight() {
        return HEADER_HEIGHT + this.rows.length * (ROW_HEIGHT + ROW_PAD);
    }

    get todayLineX() {
        const range = this._dateRange();
        const today = new Date();
        if (today < range.start || today > range.end) return null;
        return this._dateToPx(today, range.start);
    }

    get leftPanelWidth() { return LEFT_PANEL_WIDTH; }
    get rowHeight() { return ROW_HEIGHT; }
    get rowPad() { return ROW_PAD; }
    get headerHeight() { return HEADER_HEIGHT; }

    rowY(rowIdx) {
        return HEADER_HEIGHT + rowIdx * (ROW_HEIGHT + ROW_PAD);
    }

    // ─────────────────────────────────────────────────────────────────
    // Drag handling
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
        return (row.type === "bar" && this.state.dragId === row.record.id) ? this.state.dragDx : 0;
    }
}
