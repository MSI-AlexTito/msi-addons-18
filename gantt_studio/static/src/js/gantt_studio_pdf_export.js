/** @odoo-module **/

/**
 * Export the rendered Gantt to a print-friendly PDF.
 *
 * Strategy:
 *   1. Serialize the .o_gantt_studio_renderer element's SVG + the left panel
 *      to two foreignObject + image steps.
 *   2. Snapshot the visible SVG as a <canvas> at high DPI.
 *   3. Slice the canvas horizontally into A4-landscape pages.
 *   4. Build an HTML document with @page CSS so the browser doesn't rescale.
 *   5. Print it via an off-screen iframe.
 *
 * NOTE: this is an MVP — keeps text-as-bitmap. For selectable-text PDFs we
 * would need a real PDF library; out of scope for Tier 1.
 */

const A4_LANDSCAPE_W_MM = 297;
const A4_LANDSCAPE_H_MM = 210;
const DPI = 150;
const PX_PER_MM = DPI / 25.4;

/** Properties we lift from getComputedStyle into inline style="..." */
const INLINED_SVG_PROPS = [
    "fill", "fill-opacity", "stroke", "stroke-width", "stroke-dasharray",
    "stroke-opacity", "font-size", "font-weight", "font-family",
    "font-style", "text-anchor", "dominant-baseline", "opacity", "color",
    "letter-spacing",
];

/**
 * Clone an SVG and walk every descendant copying getComputedStyle values into
 * inline `style=""` attributes. Necessary because the SCSS rules from the
 * Odoo asset bundle don't follow the serialized SVG once it's wrapped in a
 * blob URL — without this step the rasterized canvas is plain black-on-white.
 */
function cloneWithInlinedStyles(svg) {
    const clone = svg.cloneNode(true);
    const srcAll = [svg, ...svg.querySelectorAll("*")];
    const dstAll = [clone, ...clone.querySelectorAll("*")];
    for (let i = 0; i < srcAll.length; i++) {
        const cs = window.getComputedStyle(srcAll[i]);
        let inline = "";
        for (const prop of INLINED_SVG_PROPS) {
            const v = cs.getPropertyValue(prop);
            if (v && v !== "" && v !== "auto" && v !== "normal" && v !== "none none") {
                inline += `${prop}:${v};`;
            }
        }
        if (inline) dstAll[i].setAttribute("style", inline);
    }
    return clone;
}

/**
 * Rasterize an SVG element (with inlined styles) to a Canvas at 2× pixel
 * density for crispness on print.
 */
async function svgToCanvas(svg) {
    const rect = svg.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const styledClone = cloneWithInlinedStyles(svg);
    // Make sure clone has explicit width/height (some browsers need this)
    styledClone.setAttribute("width", width);
    styledClone.setAttribute("height", height);
    styledClone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const xml = new XMLSerializer().serializeToString(styledClone);
    const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);
    try {
        const img = await new Promise((resolve, reject) => {
            const i = new Image();
            i.onload = () => resolve(i);
            i.onerror = (e) => reject(new Error("Could not rasterize SVG (image load failed)"));
            i.src = url;
        });
        const canvas = document.createElement("canvas");
        const SCALE = 2;
        canvas.width = Math.max(1, Math.ceil(width * SCALE));
        canvas.height = Math.max(1, Math.ceil(height * SCALE));
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "white";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        return canvas;
    } finally {
        URL.revokeObjectURL(url);
    }
}

export async function exportGanttToPdf({ title, renderer }) {
    if (!renderer) throw new Error("exportGanttToPdf: renderer element not found");
    const svg = renderer.querySelector("svg.o_gs_canvas");
    if (!svg) throw new Error("exportGanttToPdf: SVG canvas not found");

    const sourceCanvas = await svgToCanvas(svg);

    // Compute slicing: A4 landscape = 297mm wide × 210mm tall at 150dpi
    const pageWidthPx = Math.floor(A4_LANDSCAPE_W_MM * PX_PER_MM);
    const pageHeightPx = Math.floor(A4_LANDSCAPE_H_MM * PX_PER_MM);
    const totalSliceWidth = sourceCanvas.width;
    const sliceHeight = sourceCanvas.height;

    // Build an HTML doc with each horizontal slice as an <img>
    const imgUrls = [];
    let x = 0;
    while (x < totalSliceWidth) {
        const w = Math.min(pageWidthPx * 2, totalSliceWidth - x); // 2x to match sourceCanvas DPR
        const tile = document.createElement("canvas");
        tile.width = w;
        tile.height = sliceHeight;
        tile.getContext("2d").drawImage(sourceCanvas, -x, 0);
        const blob = await new Promise((r) => tile.toBlob(r, "image/png"));
        imgUrls.push(URL.createObjectURL(blob));
        x += w;
    }

    const safeTitle = (title || "Gantt").replace(/[<>"'&]/g, "");
    const escapedTitle = safeTitle
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>${escapedTitle}</title>
<style>
@page { size: ${A4_LANDSCAPE_W_MM}mm ${A4_LANDSCAPE_H_MM}mm; margin: 8mm; }
html, body { margin: 0; padding: 0; background: white; font-family: system-ui, sans-serif; }
.page { width: ${A4_LANDSCAPE_W_MM - 16}mm; height: ${A4_LANDSCAPE_H_MM - 16}mm;
        page-break-after: always; display: flex; flex-direction: column; }
.page:last-child { page-break-after: auto; }
.page header { font-size: 10px; color: #555; padding-bottom: 4mm;
              border-bottom: 1px solid #ccc; display: flex; justify-content: space-between; }
.page footer { font-size: 9px; color: #888; padding-top: 4mm;
              border-top: 1px solid #ccc; display: flex; justify-content: space-between; }
.page .body { flex: 1; display: flex; align-items: center; justify-content: center; }
.page img { max-width: 100%; max-height: 100%; }
</style>
</head><body>
${imgUrls.map((u, i) => `
<div class="page">
    <header>
        <span><strong>${escapedTitle}</strong></span>
        <span>Page ${i + 1} of ${imgUrls.length}</span>
    </header>
    <div class="body"><img src="${u}" alt="page ${i + 1}"/></div>
    <footer>
        <span>Generated by Gantt Studio</span>
        <span>${new Date().toLocaleString()}</span>
    </footer>
</div>`).join("\n")}
</body></html>`;

    const htmlBlob = new Blob([html], { type: "text/html" });
    const htmlUrl = URL.createObjectURL(htmlBlob);

    let iframe = document.getElementById("gantt_studio_print_iframe");
    if (iframe) iframe.remove();
    iframe = document.createElement("iframe");
    iframe.id = "gantt_studio_print_iframe";
    Object.assign(iframe.style, {
        position: "fixed", right: "0", bottom: "0",
        width: "0", height: "0", border: "0",
    });
    iframe.src = htmlUrl;
    iframe.onload = () => {
        // wait for images to load
        const docImgs = iframe.contentDocument.querySelectorAll("img");
        Promise.all(
            Array.from(docImgs).map((img) =>
                img.complete ? Promise.resolve() : new Promise((r) => { img.onload = img.onerror = r; })
            )
        ).then(() => {
            iframe.contentWindow.focus();
            iframe.contentWindow.print();
            setTimeout(() => {
                imgUrls.forEach((u) => URL.revokeObjectURL(u));
                URL.revokeObjectURL(htmlUrl);
                iframe.remove();
            }, 10000);
        });
    };
    document.body.appendChild(iframe);
}
