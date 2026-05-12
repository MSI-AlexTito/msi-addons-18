/** @odoo-module **/

import { parseGanttStudioArch } from "./gantt_studio_utils";

/**
 * Parses the <gantt_studio> XML view declaration into a structured archInfo.
 * Thin OO wrapper around `parseGanttStudioArch()` so Odoo's view stack can
 * use `new ArchParser().parse(arch)` (its convention).
 *
 * Pure parsing logic + attribute validation live in `gantt_studio_utils.js`
 * so they can be unit-tested under Node.
 */
export class GanttStudioArchParser {
    parse(arch) {
        return parseGanttStudioArch(arch, DOMParser);
    }
}
