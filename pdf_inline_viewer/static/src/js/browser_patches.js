/** @odoo-module **/

/**
 * MSI PDF Preview - Browser patches
 *
 * El handler de `ir.actions.report` no captura todas las rutas de descarga.
 * Quedan fuera:
 *   - clicks en <a href="/report/pdf/..."> y "/web/content/...pdf"
 *   - clicks en <a href="/report/download"> generados por el menú Acciones
 *   - menú de chatter que enlaza a attachments PDF
 *
 * Este archivo añade un interceptor a nivel DOM para capturar esos casos
 * y abrir el visor en su lugar.
 */
import { registry } from "@web/core/registry";
import { PdfPreviewDialog } from "./pdf_preview_dialog";

const PDF_PATH_REGEX = /^\/(report\/pdf|report\/download|web\/content)\b/;

function looksLikePdfUrl(href) {
    if (!href) return false;
    let path;
    try {
        path = new URL(href, window.location.origin).pathname;
    } catch (e) {
        return false;
    }
    if (!PDF_PATH_REGEX.test(path)) return false;
    // /web/content/... solo si termina en .pdf o tiene mimetype pdf en query
    if (path.startsWith("/web/content")) {
        return /\.pdf($|\?)/i.test(href) || /mimetype=application%2Fpdf/i.test(href);
    }
    return true;
}

function extractTitleFromAnchor(anchor) {
    return (
        anchor.getAttribute("title") ||
        anchor.getAttribute("aria-label") ||
        anchor.textContent.trim() ||
        "PDF document"
    );
}

export const pdfPreviewBrowserPatch = {
    dependencies: ["dialog"],
    start(env, { dialog }) {
        function openPreview(href, title) {
            dialog.add(PdfPreviewDialog, {
                url: href,
                title,
                action: { report_name: "external", display_name: title },
                watermark: "",
                showThumbnails: true,
                onDownload: () => {
                    const a = document.createElement("a");
                    a.href = href;
                    a.target = "_blank";
                    a.rel = "noopener";
                    a.dataset.pdfInlineViewer = "skip";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                },
            });
        }

        // Interceptor global de clicks (capture phase) para adelantarnos
        // a los navigators de Odoo.
        function onDocumentClick(ev) {
            if (ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey) {
                return;
            }
            const anchor = ev.target.closest && ev.target.closest("a[href]");
            if (!anchor) return;
            if (anchor.dataset.pdfInlineViewer === "skip") return;
            const href = anchor.getAttribute("href");
            if (!looksLikePdfUrl(href)) return;
            ev.preventDefault();
            ev.stopPropagation();
            openPreview(href, extractTitleFromAnchor(anchor));
        }
        document.addEventListener("click", onDocumentClick, true);
    },
};

registry.category("services").add("pdf_inline_viewer_patch", pdfPreviewBrowserPatch);
