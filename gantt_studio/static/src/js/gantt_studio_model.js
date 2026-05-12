/** @odoo-module **/

import { Model } from "@web/model/model";

/**
 * Data layer for gantt_studio.
 *
 * Responsibilities:
 *   - Fetch records via search_read
 *   - Fetch typed dependencies (Tier 1.1)
 *   - Fetch active baseline lines (Tier 1.4)
 *   - Trigger critical-path computation server-side (Tier 1.2)
 *   - Auto-reschedule writes with dependency cascading (Tier 1.3)
 */
export class GanttStudioModel extends Model {
    setup(params) {
        this.archInfo = params.archInfo;
        this.resModel = params.resModel;
        this.fields = params.fields;
        this.records = [];
        this.dependencies = [];
        this.baselineLines = [];
        this.baselineId = false;
        this.baselineName = "";
        this.criticalRecordIds = new Set();
        this.criticalDependencyIds = new Set();
        this.domain = [];
        this.context = {};
        this.groupBy = [];
        this.orderBy = [];
        // Sprint 3.4 — Resource histogram + overallocations.
        // Lazy: solo se fetchea cuando el user hace toggle.
        this.resourceHistogram = null;       // payload del RPC
        this.overallocatedIds = new Set();   // ids de records con conflicto
    }

    async load(searchParams) {
        this.domain = searchParams.domain || [];
        this.context = searchParams.context || {};
        this.groupBy = (searchParams.groupBy && searchParams.groupBy.length)
            ? searchParams.groupBy
            : (this.archInfo.defaultGroupBy ? [this.archInfo.defaultGroupBy] : []);
        this.orderBy = searchParams.orderBy || [];

        const required = new Set([
            this.archInfo.dateStart,
            this.archInfo.dateStop,
            this.archInfo.barText,
            "display_name",
        ]);
        if (this.archInfo.colorField) required.add(this.archInfo.colorField);
        if (this.archInfo.progress) required.add(this.archInfo.progress);
        for (const f of this.archInfo.fieldsToFetch) required.add(f);
        for (const g of this.groupBy) required.add(g);

        const fields = [...required].filter((f) => f in this.fields);

        this.records = await this.orm.searchRead(
            this.resModel,
            this.domain,
            fields,
            {
                context: this.context,
                order: this.orderBy
                    .map((o) => `${o.name} ${o.asc ? "ASC" : "DESC"}`)
                    .join(", ") || undefined,
                limit: 500,
            }
        );
        const recordIds = this.records.map((r) => r.id);

        // Fetch dependencies (best-effort — if model not installed yet, skip)
        this.dependencies = [];
        if (this.archInfo.showDependencies) {
            try {
                this.dependencies = await this.orm.call(
                    "gantt.studio.dependency",
                    "get_dependencies",
                    [this.resModel, recordIds],
                );
            } catch (e) {
                console.warn("[gantt_studio] could not fetch dependencies", e);
            }
        }

        // Fetch baselines visible (Sprint 3.7 — multi-baseline).
        // Backwards-compat: baselineLines/baselineId/baselineName se
        // mantienen para que la primera capa funcione como antes; el
        // renderer dibuja todas las capas vía `visibleBaselines`.
        this.baselineLines = [];
        this.baselineId = false;
        this.baselineName = "";
        this.visibleBaselines = [];
        if (this.archInfo.baselineSupport && recordIds.length) {
            try {
                const all = await this.orm.call(
                    "gantt.studio.baseline",
                    "get_visible_baselines",
                    [this.resModel, recordIds],
                );
                this.visibleBaselines = all || [];
                // Compat con la 1ra capa (legacy).
                if (this.visibleBaselines.length) {
                    const first = this.visibleBaselines[0];
                    this.baselineLines = first.lines || [];
                    this.baselineId = first.baseline_id || false;
                    this.baselineName = first.baseline_name || "";
                }
            } catch (e) {
                console.warn("[gantt_studio] could not fetch baselines", e);
            }
        }

        // Reset critical path on every reload
        this.criticalRecordIds = new Set();
        this.criticalDependencyIds = new Set();

        this.notify();
    }

    /**
     * Toggle critical path computation.
     *
     * We refetch dependencies first so that any deps created since the view
     * was opened are visible. This avoids a common "I just made a dep and
     * CPM says nothing" surprise.
     */
    async toggleCriticalPath(enabled) {
        if (!enabled) {
            this.criticalRecordIds = new Set();
            this.criticalDependencyIds = new Set();
            this.notify();
            return;
        }
        const recordIds = this.records.map((r) => r.id);
        try {
            // 1) Refetch deps so they're current
            if (this.archInfo.showDependencies) {
                this.dependencies = await this.orm.call(
                    "gantt.studio.dependency",
                    "get_dependencies",
                    [this.resModel, recordIds],
                );
            }
            // 2) Compute critical path server-side
            const result = await this.orm.call(
                "gantt.studio.planner",
                "compute_critical_path",
                [this.resModel, recordIds, this.archInfo.dateStart, this.archInfo.dateStop],
            );
            this.criticalRecordIds = new Set(result.critical_record_ids || []);
            this.criticalDependencyIds = new Set(result.critical_dependency_ids || []);
            const total = (result.critical_record_ids || []).length;
            const errCode = result.error;
            if (errCode === "cycle_detected") {
                console.warn("[gantt_studio] critical path: dependency cycle detected — cannot compute");
            } else if (!total) {
                console.info(
                    "[gantt_studio] critical path: 0 records marked critical. " +
                    "This usually means there are no dependencies between the visible records, " +
                    "or all tasks have slack. Deps loaded: " + (this.dependencies || []).length
                );
            } else {
                console.info(`[gantt_studio] critical path: ${total} records, ${(result.critical_dependency_ids || []).length} deps`);
            }
        } catch (e) {
            console.error("[gantt_studio] critical path computation failed", e);
        }
        this.notify();
    }

    /** Persist a single record write — no cascading. */
    async updateRecord(recordId, values) {
        await this.orm.write(this.resModel, [recordId], values);
        this._replaceRecord(recordId, values);
        this.notify();
    }

    /**
     * Sprint 3.2.A — Cambia AMBAS fechas (start + stop) en un solo write.
     * Pensado para el resize de duración via drag-del-borde. No cascadea
     * porque el resize NO mueve la tarea en el tiempo, solo cambia su
     * extensión: las dependencias siguen siendo válidas si lo eran antes.
     *
     * Optimistic update + rollback on RPC error (igual que dragRecord).
     */
    async resizeRecord(recordId, newStart, newStop) {
        const ds = this.archInfo.dateStart;
        const de = this.archInfo.dateStop;
        const current = this.records.find((r) => r.id === recordId);
        if (!current) return;
        const origStart = current[ds];
        const origStop = current[de];
        const startStr = this._fmtIsoSql(newStart);
        const stopStr = this._fmtIsoSql(newStop);
        // 1) optimistic
        this._replaceRecord(recordId, { [ds]: startStr, [de]: stopStr });
        this.notify();
        // 2) persist
        try {
            await this.orm.write(this.resModel, [recordId], {
                [ds]: startStr,
                [de]: stopStr,
            });
        } catch (e) {
            console.error("[gantt_studio] resize persist failed — reverting:", e);
            this._replaceRecord(recordId, { [ds]: origStart, [de]: origStop });
            this.notify();
            throw e;
        }
    }

    /**
     * Drag-and-drop write — applies an *optimistic* local update first so the
     * bar visually settles at the new position immediately, then persists in
     * the background (with optional dependency cascading). Rolls back on
     * server error.
     */
    async dragRecord(recordId, newStart) {
        const ds = this.archInfo.dateStart;
        const de = this.archInfo.dateStop;
        const current = this.records.find((r) => r.id === recordId);
        if (!current) return;

        const origStart = current[ds];
        const origStop = current[de];
        const durationMs = (origStart && origStop)
            ? new Date(origStop).getTime() - new Date(origStart).getTime()
            : 24 * 3600 * 1000;
        const newStartDate = (newStart instanceof Date) ? newStart : new Date(newStart);
        const newStopDate = new Date(newStartDate.getTime() + durationMs);
        const newStartStr = this._fmtIsoSql(newStartDate);
        const newStopStr = this._fmtIsoSql(newStopDate);

        // 1) OPTIMISTIC update + notify
        this._replaceRecord(recordId, { [ds]: newStartStr, [de]: newStopStr });
        this.notify();

        // 2) Persist
        try {
            if (this.archInfo.autoReschedule && (this.dependencies || []).length) {
                const result = await this.orm.call(
                    "gantt.studio.planner",
                    "reschedule_with_dependencies",
                    [this.resModel, recordId, newStartStr, ds, de],
                );
                // The server may have CLAMPED our requested start because the
                // drag would have violated a predecessor constraint. In that
                // case `result.constrained === true` and the dates in
                // `result.updates` are the actual values written.
                const updates = result.updates || [];
                const byId = new Map(updates.map((u) => [u.id, u]));
                this.records = this.records.map((r) => {
                    const u = byId.get(r.id);
                    return u ? { ...r, [ds]: u.date_start, [de]: u.date_stop } : r;
                });
                if (result.constrained) {
                    // surfaced via a custom property the controller can read
                    this._lastDragConstrained = result.constraint_reason ||
                        "Task could not be moved past its predecessor.";
                } else {
                    this._lastDragConstrained = null;
                }
                this.notify();
            } else {
                await this.orm.write(this.resModel, [recordId], {
                    [ds]: newStartStr,
                    [de]: newStopStr,
                });
                this._lastDragConstrained = null;
            }
        } catch (e) {
            console.error("[gantt_studio] persist failed — reverting:", e);
            this._replaceRecord(recordId, { [ds]: origStart, [de]: origStop });
            this.notify();
            throw e;
        }
    }

    /**
     * Replace the record with id=recordId with a NEW object whose merged
     * fields include `values`. Also replaces the `records` array identity so
     * any framework-level shallow-equality check picks the change up.
     */
    _replaceRecord(recordId, values) {
        let changed = false;
        this.records = this.records.map((r) => {
            if (r.id === recordId) {
                changed = true;
                return { ...r, ...values };
            }
            return r;
        });
        return changed;
    }

    /**
     * Sprint 3.2.C — Crear una dependencia tipada entre dos records via RPC.
     * Refresca la lista de deps localmente y notifica para re-render.
     */
    async createDependency(predId, succId, depType = "FS", lagDays = 0) {
        await this.orm.call(
            "gantt.studio.dependency",
            "link",
            [this.resModel, predId, succId, depType, lagDays],
        );
        // Re-fetch deps de los records cargados así la flecha aparece sin
        // re-cargar todo.
        const recordIds = this.records.map((r) => r.id);
        this.dependencies = await this.orm.call(
            "gantt.studio.dependency",
            "get_dependencies",
            [this.resModel, recordIds],
        );
        this.notify();
    }

    /** Save a baseline snapshot of current records. */
    async saveBaseline(name) {
        const recordIds = this.records.map((r) => r.id);
        const newId = await this.orm.call(
            "gantt.studio.baseline",
            "snapshot",
            [this.resModel, recordIds, this.archInfo.dateStart, this.archInfo.dateStop, name || false],
        );
        // Activate the new baseline so the user sees the ghost bars immediately
        await this.orm.call("gantt.studio.baseline", "action_activate", [[newId]]);
        await this.load({ domain: this.domain, context: this.context, groupBy: this.groupBy });
        return newId;
    }

    /**
     * Sprint 3.4 — fetch del histograma de utilización por recurso.
     * Llamado desde el controller cuando el user toggle el botón
     * "Carga de recursos". `period` = 'day' | 'week' | 'month'.
     */
    async loadResourceHistogram(period = "week") {
        const ds = this.archInfo.dateStart;
        const de = this.archInfo.dateStop;
        const recordIds = this.records.map((r) => r.id);
        if (!recordIds.length) {
            this.resourceHistogram = null;
            this.overallocatedIds = new Set();
            this.notify();
            return;
        }
        // Rango de las records visibles: min(start), max(stop).
        let minDt = null, maxDt = null;
        for (const r of this.records) {
            const s = r[ds];
            const e = r[de];
            if (s && (!minDt || s < minDt)) minDt = s;
            if (e && (!maxDt || e > maxDt)) maxDt = e;
        }
        if (!minDt || !maxDt) {
            this.resourceHistogram = null;
            this.notify();
            return;
        }
        try {
            const histo = await this.orm.call(
                "gantt.studio.resource_load",
                "get_resource_histogram",
                [],
                {
                    res_model: this.resModel,
                    record_ids: recordIds,
                    date_from: minDt,
                    date_to: maxDt,
                    period,
                    resource_field: this.archInfo.resourceField || null,
                    date_start_field: ds,
                    date_stop_field: de,
                },
            );
            this.resourceHistogram = histo;
            // Detectar overallocations
            const overIds = await this.orm.call(
                "gantt.studio.resource_load",
                "detect_overallocations",
                [],
                {
                    res_model: this.resModel,
                    record_ids: recordIds,
                    date_start_field: ds,
                    date_stop_field: de,
                    resource_field: this.archInfo.resourceField || null,
                    threshold: 1.0,
                },
            );
            this.overallocatedIds = new Set(overIds || []);
        } catch (e) {
            console.warn("[gantt_studio] resource histogram failed:", e);
            this.resourceHistogram = null;
            this.overallocatedIds = new Set();
        }
        this.notify();
    }

    /** Sprint 3.4 — limpiar (toggle off). */
    clearResourceHistogram() {
        this.resourceHistogram = null;
        this.overallocatedIds = new Set();
        this.notify();
    }

    /** "YYYY-MM-DD HH:MM:SS" — Odoo's expected datetime format on the wire. */
    _fmtIsoSql(d) {
        if (!d) return false;
        const dt = (d instanceof Date) ? d : new Date(d);
        const pad = (n) => String(n).padStart(2, "0");
        return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}`;
    }
}

GanttStudioModel.services = ["orm"];
