/** @odoo-module **/

import { Component, useState, useSubEnv } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { useService, useBus } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { useModel } from "@web/model/model";
import { useSetupAction } from "@web/search/action_hook";
import { getDefaultConfig } from "@web/views/view";
import { standardViewProps } from "@web/views/standard_view_props";
import { _t } from "@web/core/l10n/translation";
import { exportGanttToPdf } from "./gantt_studio_pdf_export";

const SCALES = ["day", "week", "month", "quarter", "year"];

export class GanttStudioController extends Component {
    static template = "gantt_studio.Controller";
    static components = { Layout };
    static props = {
        ...standardViewProps,
        Model: Function,
        Renderer: Function,
        archInfo: Object,
        buttonTemplate: { type: String, optional: true },
    };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.archInfo = this.props.archInfo;

        this.state = useState({
            scale: this.archInfo.defaultScale,
            criticalPathEnabled: false,
            exportingPdf: false,
            // Sprint 3.1.C.4 — date picker / hotkeys.
            // `goToDateRequest` is a Date|null that the renderer watches
            // via onWillUpdateProps. Each time we want to scroll the
            // gantt, we assign a NEW Date object (object identity changes
            // even if the same calendar date is picked twice → re-scroll).
            goToDateRequest: null,
            // Mirror of the picker's input value (yyyy-mm-dd).
            datePickerInput: this._todayIso(),
        });

        useSubEnv({
            config: {
                ...getDefaultConfig(),
                ...this.env.config,
            },
        });

        this.model = useModel(this.props.Model, {
            archInfo: this.archInfo,
            resModel: this.props.resModel,
            fields: this.props.fields,
        });

        // CRUCIAL: useModel in Odoo 18 does NOT subscribe component renders to
        // model.notify() events. We wire that explicitly here so changes to
        // model.records etc. actually re-render the view.
        useBus(this.model.bus, "update", () => {
            if (window.GANTT_STUDIO_DEBUG) console.log("[gantt_studio] bus update → render");
            this.render(true);
        });

        useSetupAction({
            getLocalState: () => ({
                scale: this.state.scale,
                criticalPathEnabled: this.state.criticalPathEnabled,
            }),
        });

        // Sprint 3.1.C.4 — keyboard shortcuts (skipped when typing in
        // inputs / textareas, courtesy of the hotkey service's defaults).
        useHotkey("t", () => this.goToToday(), {});
        useHotkey("+", () => this.zoomIn(), {});
        useHotkey("=", () => this.zoomIn(), {});  // unshifted "+" on US layouts
        useHotkey("-", () => this.zoomOut(), {});
    }

    /** Returns the local date in `YYYY-MM-DD` form (input[type=date] value). */
    _todayIso() {
        const d = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    goToToday() {
        this.state.datePickerInput = this._todayIso();
        this.state.goToDateRequest = new Date();
    }

    onDatePickerChange(ev) {
        const v = ev.target.value;
        if (!v) return;
        this.state.datePickerInput = v;
        // Parse as LOCAL date (midnight). `new Date("YYYY-MM-DD")` parses
        // as UTC which shifts a day in negative-offset timezones.
        const [y, m, d] = v.split("-").map(Number);
        this.state.goToDateRequest = new Date(y, m - 1, d);
    }

    zoomIn() {
        const i = SCALES.indexOf(this.state.scale);
        if (i > 0) this.state.scale = SCALES[i - 1];
    }

    zoomOut() {
        const i = SCALES.indexOf(this.state.scale);
        if (i < SCALES.length - 1) this.state.scale = SCALES[i + 1];
    }

    get rendererProps() {
        return {
            archInfo: this.archInfo,
            resModel: this.props.resModel,
            fields: this.props.fields,
            records: this.model.records,
            // Bug fix: el groupBy del search panel debe llegar al renderer.
            // Antes, el renderer agrupaba SIEMPRE por `archInfo.defaultGroupBy`,
            // ignorando la elección del usuario en el menú "Agrupar por".
            groupBy: this.model.groupBy,
            dependencies: this.model.dependencies,
            baselineLines: this.model.baselineLines,
            baselineId: this.model.baselineId,
            criticalRecordIds: this.model.criticalRecordIds,
            criticalDependencyIds: this.model.criticalDependencyIds,
            criticalPathEnabled: this.state.criticalPathEnabled,
            scale: this.state.scale,
            // Sprint 3.1.C.4: cuando cambia esta referencia, el renderer
            // hace scrollLeft a la fecha. La pasamos por valor de prop
            // para mantener el flujo unidireccional (controller → renderer).
            goToDateRequest: this.state.goToDateRequest,
            onBarClick: this.onBarClick.bind(this),
            onBarDrop: this.onBarDrop.bind(this),
            // Sprint 3.2.A: resize de duración. Si el arch deshabilita la
            // edición (archInfo.canEdit === false), no pasamos el handler →
            // los asas del borde no se renderean.
            onBarResize: this.archInfo.canEdit
                ? this.onBarResize.bind(this)
                : null,
            // Sprint 3.2.B: edición inline del nombre. El campo a editar
            // es siempre `name` (el más común). Si tu modelo usa otro,
            // sobreescribe esta vista con un parámetro futuro `name_field`.
            onBarRename: this.archInfo.canEdit
                ? this.onBarRename.bind(this)
                : null,
            // Sprint 3.2.C: crear deps por drag entre bars. Solo si las
            // dependencies están habilitadas en el arch.
            onDepCreate: (this.archInfo.canEdit && this.archInfo.showDependencies)
                ? this.onDepCreate.bind(this)
                : null,
        };
    }

    onBarClick(record) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: record.id,
            views: [[this.archInfo.formViewId || false, "form"]],
            target: "current",
        });
    }

    async onBarDrop(recordId, newStart) {
        try {
            await this.model.dragRecord(recordId, newStart);
            // The planner may have clamped the requested date because it
            // would have violated a predecessor's dependency. Surface that
            // to the user — the bar already snapped to the allowed date.
            if (this.model._lastDragConstrained) {
                this.notification.add(this.model._lastDragConstrained, {
                    type: "warning",
                    title: _t("Move constrained by dependency"),
                });
            }
        } catch (e) {
            console.error("[gantt_studio] drop failed:", e);
            this.notification.add(
                _t("Could not reschedule this task. Reverting to its previous dates."),
                { type: "danger", title: _t("Reschedule failed") },
            );
        }
    }

    /**
     * Sprint 3.2.A — Cambiar la duración de una tarea arrastrando el borde.
     * Difiere de onBarDrop en que aquí cambian AMBAS fechas (start y stop)
     * en un mismo write, así no se dispara la cascada de auto-reschedule
     * (que solo opera sobre date_start). El usuario está extendiendo el
     * trabajo dentro del mismo timeframe, no moviéndolo.
     */
    async onBarResize(recordId, newStart, newStop) {
        try {
            await this.model.resizeRecord(recordId, newStart, newStop);
        } catch (e) {
            console.error("[gantt_studio] resize failed:", e);
            this.notification.add(
                _t("Could not resize this task. Check that the new duration is valid."),
                { type: "danger", title: _t("Resize failed") },
            );
        }
    }

    /**
     * Sprint 3.2.B — Renombrar la tarea desde la edición inline.
     * El campo siempre es `name` (campo natural de project.task,
     * crm.lead, sale.order, casi cualquier modelo Odoo).
     */
    async onBarRename(recordId, newName) {
        try {
            await this.model.updateRecord(recordId, { name: newName });
        } catch (e) {
            console.error("[gantt_studio] rename failed:", e);
            this.notification.add(
                _t("Could not rename this task."),
                { type: "danger", title: _t("Rename failed") },
            );
        }
    }

    /**
     * Sprint 3.2.C — Crear una dependencia tipada via drag entre dos bars.
     * Llama al RPC genérico del modelo polimórfico y recarga deps.
     */
    async onDepCreate(predId, succId, depType, lagDays) {
        try {
            await this.model.createDependency(predId, succId, depType, lagDays);
            this.notification.add(
                _t("Dependency created (%s)").replace("%s", depType),
                { type: "success" },
            );
        } catch (e) {
            console.error("[gantt_studio] dep create failed:", e);
            this.notification.add(
                _t("Could not create the dependency. Check that both records exist."),
                { type: "danger", title: _t("Dependency creation failed") },
            );
        }
    }

    setScale(scale) {
        if (SCALES.includes(scale)) this.state.scale = scale;
    }

    async toggleCriticalPath() {
        this.state.criticalPathEnabled = !this.state.criticalPathEnabled;
        await this.model.toggleCriticalPath(this.state.criticalPathEnabled);
    }

    async saveBaseline() {
        try {
            await this.model.saveBaseline(null);
            this.notification.add(
                _t("Baseline saved. The dashed ghost bars now show the original dates for comparison."),
                {
                    type: "success",
                    title: _t("Plan baseline captured"),
                },
            );
        } catch (e) {
            this.notification.add(_t("Could not save baseline. Please try again."), {
                type: "danger",
            });
        }
    }

    async exportPdf() {
        if (this.state.exportingPdf) return;
        this.state.exportingPdf = true;
        try {
            await exportGanttToPdf({
                title: `Gantt — ${this.props.resModel}`,
                renderer: document.querySelector(".o_gantt_studio_renderer"),
            });
        } catch (e) {
            console.error(e);
            this.notification.add("Could not export PDF", { type: "danger" });
        } finally {
            this.state.exportingPdf = false;
        }
    }

    get scales() { return SCALES; }
    get archCfg() { return this.archInfo; }
}
