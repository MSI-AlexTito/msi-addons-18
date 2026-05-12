/** @odoo-module **/

import { Component, useState, useSubEnv } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { useService, useBus } from "@web/core/utils/hooks";
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
    }

    get rendererProps() {
        return {
            archInfo: this.archInfo,
            resModel: this.props.resModel,
            fields: this.props.fields,
            records: this.model.records,
            dependencies: this.model.dependencies,
            baselineLines: this.model.baselineLines,
            baselineId: this.model.baselineId,
            criticalRecordIds: this.model.criticalRecordIds,
            criticalDependencyIds: this.model.criticalDependencyIds,
            criticalPathEnabled: this.state.criticalPathEnabled,
            scale: this.state.scale,
            onBarClick: this.onBarClick.bind(this),
            onBarDrop: this.onBarDrop.bind(this),
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
