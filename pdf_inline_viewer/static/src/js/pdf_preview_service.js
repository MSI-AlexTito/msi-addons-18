/** @odoo-module **/

/**
 * MSI PDF Preview - Action service handler
 *
 * Registra un handler en `ir.actions.report handlers` para interceptar acciones
 * de reporte tipo `qweb-pdf` antes de que Odoo dispare la descarga.
 *
 * El handler abre el Dialog OWL del visor con la URL `/report/pdf/...`.
 */
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { getReportUrl } from "@web/webclient/actions/reports/utils";
import { user } from "@web/core/user";
import { PdfPreviewDialog } from "./pdf_preview_dialog";

let _configCache = null;
let _configProm = null;

async function getConfig(env) {
    if (_configCache) return _configCache;
    if (!_configProm) {
        _configProm = rpc("/web/dataset/call_kw", {
            model: "res.config.settings",
            method: "get_pdf_viewer_config",
            args: [],
            kwargs: {},
        }).catch(() => ({ enabled: true, watermark: "", show_thumbnails: true }));
    }
    _configCache = await _configProm;
    return _configCache;
}

/**
 * Permite invalidar el cache (p.ej. después de cambiar settings).
 */
export function invalidatePdfViewerConfig() {
    _configCache = null;
    _configProm = null;
}

async function pdfPreviewHandler(action, options, env) {
    if (action.report_type !== "qweb-pdf") return false;
    const ctx = action.context || {};
    if (ctx.pdf_inline_viewer === false) return false;
    const config = await getConfig(env);
    if (!config.enabled) return false;

    const url = getReportUrl(action, "pdf", user.context);
    const title = action.display_name || action.name || "Report";

    // Resolver la promesa solo cuando el usuario cierre el dialog. Así el
    // framework dispara `options.onClose` al cierre real (estilo "wizard
    // se cierra después de imprimir"), no al abrir el visor.
    return new Promise((resolve) => {
        env.services.dialog.add(
            PdfPreviewDialog,
            {
                url,
                title,
                action,
                watermark: config.watermark || "",
                showThumbnails: config.show_thumbnails,
                onDownload: () => {
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = (action.report_file || action.report_name) + ".pdf";
                    a.dataset.pdfInlineViewer = "skip"; // no interceptar
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                },
            },
            { onClose: () => resolve(true) }
        );
    });
}

registry
    .category("ir.actions.report handlers")
    .add("pdf_inline_viewer_handler", pdfPreviewHandler, { sequence: 1 });
