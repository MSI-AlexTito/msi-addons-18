/** @odoo-module **/

import { registry } from "@web/core/registry";
import { GanttStudioArchParser } from "./gantt_studio_arch_parser";
import { GanttStudioController } from "./gantt_studio_controller";
import { GanttStudioModel } from "./gantt_studio_model";
import { GanttStudioRenderer } from "./gantt_studio_renderer";

export const ganttStudioView = {
    type: "gantt_studio",
    display_name: "Gantt Studio",
    icon: "fa fa-bars fa-rotate-270",

    ArchParser: GanttStudioArchParser,
    Controller: GanttStudioController,
    Model: GanttStudioModel,
    Renderer: GanttStudioRenderer,

    searchMenuTypes: ["filter", "groupBy", "favorite"],
    buttonTemplate: "gantt_studio.Buttons",

    props: (genericProps, view) => {
        const { ArchParser } = view;
        const archInfo = new ArchParser().parse(genericProps.arch);
        return {
            ...genericProps,
            Model: view.Model,
            Renderer: view.Renderer,
            buttonTemplate: view.buttonTemplate,
            archInfo,
        };
    },
};

registry.category("views").add("gantt_studio", ganttStudioView);
