/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { PdfThumbnails } from "./pdf_thumbnails";
import {
    normalizeText,
    buildRunIndex,
    findMatches,
    splitMatchAcrossRuns,
    escapeHtml,
} from "./pdf_search_utils";

const PDFJS_URL = "/web/static/lib/pdfjs/build/pdf.js";
const PDFJS_WORKER_URL = "/web/static/lib/pdfjs/build/pdf.worker.js";
const DEBUG = false; // poner en true para diagnosticar

/**
 * Modo debug visual del TextLayer: tinta los spans de PDF.js en rojo
 * semi-transparente. Útil para verificar si las coincidencias aparecen en
 * "espacios vacíos" porque el PDF tiene texto invisible superpuesto.
 *
 * En la consola del navegador: ejecutar `window.PDF_INLINE_VIEWER_DEBUG = true`
 * y luego cambiar zoom o recargar reporte para verlo activado.
 */
window.PDF_INLINE_VIEWER_DEBUG = window.PDF_INLINE_VIEWER_DEBUG || false;

function log(...args) {
    if (DEBUG) console.log("[pdf_inline_viewer]", ...args);
}
function warn(...args) { console.warn("[pdf_inline_viewer]", ...args); }
function err(...args) { console.error("[pdf_inline_viewer]", ...args); }

let _pdfjsLoadProm = null;

function loadPdfJs() {
    if (window.pdfjsLib?.getDocument) return Promise.resolve(window.pdfjsLib);
    if (_pdfjsLoadProm) return _pdfjsLoadProm;
    _pdfjsLoadProm = (async () => {
        const mod = await import(/* webpackIgnore: true */ PDFJS_URL);
        const pdfjsLib =
            window.pdfjsLib ||
            (mod && mod.getDocument ? mod : null) ||
            (mod && mod.default && mod.default.getDocument ? mod.default : null);
        if (!pdfjsLib || !pdfjsLib.getDocument) {
            throw new Error("PDF.js no expuso getDocument tras import()");
        }
        window.pdfjsLib = pdfjsLib;
        try {
            pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
        } catch (e) {
            warn("loadPdfJs: no se pudo configurar workerSrc", e);
        }
        return pdfjsLib;
    })();
    return _pdfjsLoadProm;
}

export class PdfPreviewDialog extends Component {
    static template = "pdf_inline_viewer.PdfPreviewDialog";
    static components = { Dialog, PdfThumbnails };
    static props = {
        url: String,
        title: { type: String, optional: true },
        action: { type: Object, optional: true },
        watermark: { type: String, optional: true },
        showThumbnails: { type: Boolean, optional: true },
        onDownload: { type: Function, optional: true },
        close: Function,
    };
    static defaultProps = {
        title: "",
        action: {},
        watermark: "",
        showThumbnails: true,
        onDownload: null,
    };

    setup() {
        this.viewerRef = useRef("viewer");        // scroll container
        this.searchInputRef = useRef("searchInput");

        this.state = useState({
            loading: true,
            error: null,
            page: 1,                  // página actualmente visible (para highlight de thumb)
            totalPages: 0,
            scale: 1.2,
            rotation: 0,
            showSidebar: this.props.showThumbnails,
            showSearch: false,
            searchQuery: "",
            searchMatches: [],
            searchIndex: 0,
            searchPending: false,
            isFullscreen: false,
            printing: false,
            needsPassword: false,
            passwordError: false,
        });

        this.pdf = null;
        this.pdfBytes = null;
        this._renderTokens = new Map();        // pageNum -> token (cancelación)
        this._textCache = new Map();
        this._textLayerReady = new Set();      // páginas con TextLayer ya pintado
        this._pendingPassword = null;
        this._pageObserver = null;

        log("setup() llamado. url =", this.props.url, "title =", this.props.title);

        onWillStart(async () => {
            try { await loadPdfJs(); } catch (e) { err("onWillStart: loadPdfJs falló", e); }
        });
        onMounted(() => this._loadPdf());
        onMounted(() => this._bindKeyboardShortcuts());
        onWillUnmount(() => {
            this._unbindKeyboardShortcuts();
            if (this._pageObserver) this._pageObserver.disconnect();
        });

        // Cuando termina la carga o cambia el zoom/rotación, re-render todas
        // las páginas y reconfigura el observer de visibilidad.
        useEffect(
            () => {
                if (!this.pdf || this.state.loading) return;
                if (!this.viewerRef.el) {
                    warn("useEffect: viewerRef.el aún no existe");
                    return;
                }
                log("useEffect: render TODAS las páginas, totalPages=", this.state.totalPages,
                    "scale=", this.state.scale, "rotation=", this.state.rotation);
                this._renderAllPages();
                this._setupVisibilityObserver();
            },
            () => [
                this.state.totalPages,
                this.state.scale,
                this.state.rotation,
                this.state.loading,
            ]
        );
    }

    // -------------------------------------------------------------------
    // PDF loading
    // -------------------------------------------------------------------

    async _loadPdf(password) {
        log("_loadPdf: inicio. url =", this.props.url);
        this.state.loading = true;
        this.state.error = null;
        try {
            const pdfjsLib = await loadPdfJs();
            if (!this.pdfBytes) {
                const resp = await fetch(this.props.url, { credentials: "same-origin" });
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                this.pdfBytes = new Uint8Array(await resp.arrayBuffer());
                log("_loadPdf: bytes recibidos =", this.pdfBytes.byteLength);
            }
            const loadingTask = pdfjsLib.getDocument({
                data: this.pdfBytes.slice(0),
                password,
            });
            loadingTask.onPassword = (callback, reason) => {
                this.state.needsPassword = true;
                this.state.passwordError =
                    reason === pdfjsLib.PasswordResponses.INCORRECT_PASSWORD;
                this.state.loading = false;
                this._pendingPassword = callback;
            };
            const pdf = await loadingTask.promise;
            log("_loadPdf: PDF parseado. numPages =", pdf.numPages);
            this.pdf = pdf;
            this.state.totalPages = pdf.numPages;
            this.state.needsPassword = false;
            this.state.passwordError = false;
            this.state.loading = false;
        } catch (e) {
            err("_loadPdf: excepción", e);
            this.state.loading = false;
            this.state.error = e.message || String(e);
        }
    }

    // -------------------------------------------------------------------
    // Rendering (scroll continuo)
    // -------------------------------------------------------------------

    get pageNums() {
        const arr = [];
        for (let i = 1; i <= this.state.totalPages; i++) arr.push(i);
        return arr;
    }

    _getPageCanvas(num) {
        if (!this.viewerRef.el) return null;
        return this.viewerRef.el.querySelector(`canvas[data-page="${num}"]`);
    }

    async _renderAllPages() {
        // Render secuencial para no saturar el worker
        for (let i = 1; i <= this.state.totalPages; i++) {
            this._renderPage(i); // fire & forget, las llamadas se serializan vía tokens
        }
    }

    async _renderPage(num) {
        if (!this.pdf || num < 1 || num > this.pdf.numPages) return;
        const canvas = this._getPageCanvas(num);
        if (!canvas) {
            warn(`_renderPage(${num}): canvas no está en el DOM aún`);
            return;
        }
        const token = (this._renderTokens.get(num) || 0) + 1;
        this._renderTokens.set(num, token);
        this._textLayerReady.delete(num);
        try {
            const page = await this.pdf.getPage(num);
            if (this._renderTokens.get(num) !== token) return; // obsoleto
            const dpr = window.devicePixelRatio || 1;
            const viewport = page.getViewport({
                scale: this.state.scale,
                rotation: this.state.rotation,
            });
            canvas.width = Math.floor(viewport.width * dpr);
            canvas.height = Math.floor(viewport.height * dpr);
            canvas.style.width = viewport.width + "px";
            canvas.style.height = viewport.height + "px";
            const ctx = canvas.getContext("2d");
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            await page.render({ canvasContext: ctx, viewport }).promise;
            if (num === 1) log("_renderPage(1): ✓ render OK", { w: viewport.width, h: viewport.height });
            // Después del canvas, pintamos la capa de texto invisible para
            // soportar selección y resaltado de búsqueda.
            await this._renderTextLayer(num, page, viewport);
            if (this._renderTokens.get(num) !== token) return;
        } catch (e) {
            if (e?.name !== "RenderingCancelledException") {
                err(`_renderPage(${num}): excepción`, e);
            }
        }
    }

    async _renderTextLayer(num, page, viewport) {
        const canvas = this._getPageCanvas(num);
        if (!canvas) return;
        const wrap = canvas.parentElement;
        if (!wrap) return;
        let layer = wrap.querySelector(".o_pdf_text_layer");
        if (!layer) {
            layer = document.createElement("div");
            layer.className = "o_pdf_text_layer";
            wrap.appendChild(layer);
        }
        layer.innerHTML = "";
        layer.style.width = viewport.width + "px";
        layer.style.height = viewport.height + "px";
        layer.style.setProperty("--scale-factor", String(viewport.scale));
        layer.classList.toggle("o_pdf_text_layer_debug", !!window.PDF_INLINE_VIEWER_DEBUG);

        try {
            const textContent = await page.getTextContent();
            const TextLayer = window.pdfjsLib.TextLayer;
            if (!TextLayer) {
                warn("_renderTextLayer: pdfjsLib.TextLayer no disponible");
                return;
            }
            const tl = new TextLayer({
                textContentSource: textContent,
                container: layer,
                viewport,
            });
            await tl.render();
            this._textLayerReady.add(num);
            if (num <= 3 || num === this.state.totalPages) {
                log(`_renderTextLayer(${num}): ${layer.querySelectorAll("span").length} spans,`,
                    "items=", textContent.items.length);
            }
            // Reaplicar highlight de búsqueda si hay query activa
            if (this.state.searchQuery && this.state.searchQuery.trim()) {
                this._applyHighlightToPage(num);
            }
        } catch (e) {
            err(`_renderTextLayer(${num}): excepción`, e);
        }
    }

    // -------------------------------------------------------------------
    // Visibility observer: trackea qué página está activa según scroll
    // -------------------------------------------------------------------

    _setupVisibilityObserver() {
        if (this._pageObserver) this._pageObserver.disconnect();
        if (!this.viewerRef.el) return;
        this._pageObserver = new IntersectionObserver(
            (entries) => {
                // Tomar la entry con mayor intersectionRatio entre las visibles
                let bestNum = null;
                let bestRatio = 0;
                for (const e of entries) {
                    if (e.isIntersecting && e.intersectionRatio > bestRatio) {
                        bestRatio = e.intersectionRatio;
                        bestNum = parseInt(e.target.dataset.page, 10);
                    }
                }
                if (bestNum && bestNum !== this.state.page) {
                    this.state.page = bestNum;
                }
            },
            {
                root: this.viewerRef.el,
                threshold: [0.1, 0.3, 0.5, 0.7],
            }
        );
        for (const c of this.viewerRef.el.querySelectorAll("canvas[data-page]")) {
            this._pageObserver.observe(c);
        }
    }

    // -------------------------------------------------------------------
    // Navigation helpers
    // -------------------------------------------------------------------

    /** Scrollear el viewer hasta una página concreta */
    goToPage(num) {
        const n = Math.max(1, Math.min(this.state.totalPages, num));
        const canvas = this._getPageCanvas(n);
        if (canvas) {
            canvas.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    zoomIn() { this.state.scale = Math.min(4, +(this.state.scale + 0.2).toFixed(2)); }
    zoomOut() { this.state.scale = Math.max(0.3, +(this.state.scale - 0.2).toFixed(2)); }
    zoomReset() { this.state.scale = 1.2; }
    rotate() { this.state.rotation = (this.state.rotation + 90) % 360; }

    toggleSidebar() { this.state.showSidebar = !this.state.showSidebar; }
    toggleSearch() {
        this.state.showSearch = !this.state.showSearch;
        if (this.state.showSearch) {
            Promise.resolve().then(() => this.searchInputRef.el?.focus());
        }
    }

    async toggleFullscreen() {
        const root = this.viewerRef.el?.closest(".modal-dialog") || document.body;
        if (!document.fullscreenElement) {
            await root.requestFullscreen?.();
            this.state.isFullscreen = true;
        } else {
            await document.exitFullscreen?.();
            this.state.isFullscreen = false;
        }
    }

    // -------------------------------------------------------------------
    // Password
    // -------------------------------------------------------------------

    onPasswordSubmit(ev) {
        ev.preventDefault();
        const input = ev.target.querySelector("input[type=password]");
        const pwd = input?.value || "";
        if (this._pendingPassword) {
            this._pendingPassword(pwd);
            this.state.loading = true;
            this.state.needsPassword = false;
        }
    }

    // -------------------------------------------------------------------
    // Search
    // -------------------------------------------------------------------

    /**
     * Construye y cachea el run-index (array de spans con su texto) para una
     * página, usando el TextLayer ya renderizado.
     * Retorna null si la página aún no tiene TextLayer pintado.
     */
    _getPageRunIndex(num) {
        const canvas = this._getPageCanvas(num);
        if (!canvas) return null;
        const layer = canvas.parentElement?.querySelector(".o_pdf_text_layer");
        if (!layer) return null;
        const spans = Array.from(layer.querySelectorAll("span"))
            .filter((s) => s.firstChild && s.firstChild.nodeType === Node.TEXT_NODE);
        const runs = spans.map((s) => ({ text: s.textContent, _span: s }));
        const idx = buildRunIndex(runs);
        idx._spans = spans; // ref a los <span> reales para resaltar
        return idx;
    }

    /**
     * Obtiene el índice de runs CANÓNICO de una página, basado siempre en
     * `getTextContent()` de pdf.js. Es la única fuente de verdad para conteos:
     * los tests E2E muestran 100% paridad con pdftotext, y al usar la misma
     * fuente para todas las páginas evitamos discrepancias entre páginas con
     * TextLayer pintado vs no pintado.
     */
    async _getCanonicalIndex(pageNum) {
        const page = await this.pdf.getPage(pageNum);
        const content = await page.getTextContent();
        return buildRunIndex(content.items.map((it) => ({ text: it.str || "" })));
    }

    async onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        const q = (ev.target.value || "").trim();
        if (!q) {
            this.state.searchMatches = [];
            this.state.searchIndex = 0;
            this._clearAllHighlights();
            return;
        }
        this.state.searchPending = true;
        // Una sola fuente: getTextContent → buildRunIndex → findMatches.
        // matches: array plana global, una entrada por OCURRENCIA real.
        const matches = [];
        for (let i = 1; i <= this.pdf.numPages; i++) {
            const idx = await this._getCanonicalIndex(i);
            const pageMatches = findMatches(idx, q);
            pageMatches.forEach(() => matches.push({ page: i }));
        }
        this.state.searchMatches = matches;
        this.state.searchIndex = 0;
        this.state.searchPending = false;
        log("onSearchInput:", matches.length, "ocurrencias en",
            new Set(matches.map((m) => m.page)).size, "páginas");
        this._applyHighlightsAll();
        if (matches.length) this._scrollToActiveMatch();
    }

    searchNext() {
        if (!this.state.searchMatches.length) return;
        this.state.searchIndex =
            (this.state.searchIndex + 1) % this.state.searchMatches.length;
        this._refreshActiveHighlight();
        this._scrollToActiveMatch();
    }
    searchPrev() {
        if (!this.state.searchMatches.length) return;
        this.state.searchIndex =
            (this.state.searchIndex - 1 + this.state.searchMatches.length) %
            this.state.searchMatches.length;
        this._refreshActiveHighlight();
        this._scrollToActiveMatch();
    }

    /** Limpia la query y oculta el buscador. */
    clearSearch() {
        this.state.searchQuery = "";
        this.state.searchMatches = [];
        this.state.searchIndex = 0;
        this._clearAllHighlights();
        this.state.showSearch = false;
    }

    /** Enter → siguiente, Shift+Enter → anterior. */
    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            if (ev.shiftKey) this.searchPrev();
            else this.searchNext();
        }
    }

    // -------------------------------------------------------------------
    // Highlight helpers (usa pdf_search_utils — testeado en Node)
    // -------------------------------------------------------------------

    _clearAllHighlights() {
        if (!this.viewerRef.el) return;
        for (const layer of this.viewerRef.el.querySelectorAll(".o_pdf_text_layer")) {
            for (const span of layer.querySelectorAll("span")) {
                if (span.querySelector("mark")) {
                    // textContent colapsa el subárbol a un único text node
                    span.textContent = span.textContent;
                }
            }
        }
    }

    _applyHighlightsAll() {
        this._clearAllHighlights();
        if (!(this.state.searchQuery || "").trim()) return;
        for (const num of this._textLayerReady) {
            this._applyHighlightToPage(num);
        }
        this._refreshActiveHighlight();
    }

    /**
     * Resalta todas las ocurrencias en una página. Soporta matches cuyo
     * texto cruza el límite entre spans (lo que evita falsos positivos /
     * highlights pegados en zonas vacías cuando el texto está fragmentado).
     */
    _applyHighlightToPage(num) {
        const idx = this._getPageRunIndex(num);
        if (!idx) return;
        const q = (this.state.searchQuery || "").trim();
        const matches = findMatches(idx, q);
        if (!matches.length) return;

        // Plan de cortes por span: spanIdx → array de [localStart, localEnd]
        const cutsBySpan = new Map();
        for (const m of matches) {
            for (const p of splitMatchAcrossRuns(idx, m)) {
                if (!cutsBySpan.has(p.runIdx)) cutsBySpan.set(p.runIdx, []);
                cutsBySpan.get(p.runIdx).push([p.localStart, p.localEnd]);
            }
        }
        for (const [spanIdx, cuts] of cutsBySpan) {
            const span = idx._spans[spanIdx];
            const text = span.textContent;
            cuts.sort((a, b) => a[0] - b[0]);
            let html = "";
            let cursor = 0;
            for (const [s, e] of cuts) {
                if (s < cursor) continue; // solapamiento improbable
                html += escapeHtml(text.slice(cursor, s));
                html += `<mark class="o_pdf_highlight">${escapeHtml(text.slice(s, e))}</mark>`;
                cursor = e;
            }
            html += escapeHtml(text.slice(cursor));
            span.innerHTML = html;
        }
        log(`_applyHighlightToPage(${num}): ${matches.length} matches en ${cutsBySpan.size} spans`);
    }

    /** Marca el match correspondiente a state.searchIndex como "activo" (naranja). */
    _refreshActiveHighlight() {
        if (!this.viewerRef.el) return;
        // Quitar la clase activa de todos
        for (const m of this.viewerRef.el.querySelectorAll("mark.o_pdf_highlight_active")) {
            m.classList.remove("o_pdf_highlight_active");
        }
        if (!this.state.searchMatches.length) return;
        // El N-ésimo <mark> en orden global del documento es el match activo
        const idx = this.state.searchIndex;
        const allMarks = Array.from(this.viewerRef.el.querySelectorAll(".o_pdf_text_layer mark.o_pdf_highlight"));
        if (idx >= 0 && idx < allMarks.length) {
            allMarks[idx].classList.add("o_pdf_highlight_active");
        }
    }

    _scrollToActiveMatch() {
        if (!this.viewerRef.el) return;
        const m = this.state.searchMatches[this.state.searchIndex];
        if (!m) return;
        // Si el <mark> activo está pintado, scrollearlo. Si no, scrollear la página.
        const active = this.viewerRef.el.querySelector("mark.o_pdf_highlight_active");
        if (active) {
            active.scrollIntoView({ behavior: "smooth", block: "center" });
        } else {
            this.goToPage(m.page);
        }
    }

    // -------------------------------------------------------------------
    // Print
    //
    // Estrategia: renderizamos cada página del PDF como imagen al tamaño
    // exacto del papel (mm). El HTML resultante usa `@page { size: ... mm;
    // margin: 0 }` para que el navegador no tenga nada que escalar — "100%"
    // y "Ajustar a página" producen el mismo resultado.
    //
    // Trade-off: el texto sale rasterizado (no seleccionable en una
    // impresión PDF, pero visualmente idéntico al original).
    // -------------------------------------------------------------------

    async printAll() {
        if (!this.pdf || this.state.printing) return;
        this.state.printing = true;
        const blobUrls = [];
        try {
            const PT_TO_MM = 25.4 / 72;
            const DPI = 150;             // 150 dpi: balance calidad/memoria
            const PX_PER_PT = DPI / 72;
            const pages = [];
            for (let i = 1; i <= this.pdf.numPages; i++) {
                const page = await this.pdf.getPage(i);
                const ptVp = page.getViewport({ scale: 1 });
                const widthMm = +(ptVp.width * PT_TO_MM).toFixed(3);
                const heightMm = +(ptVp.height * PT_TO_MM).toFixed(3);
                const renderVp = page.getViewport({ scale: PX_PER_PT });
                const canvas = document.createElement("canvas");
                canvas.width = Math.floor(renderVp.width);
                canvas.height = Math.floor(renderVp.height);
                const ctx = canvas.getContext("2d");
                await page.render({ canvasContext: ctx, viewport: renderVp }).promise;
                const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
                const url = URL.createObjectURL(blob);
                blobUrls.push(url);
                pages.push({ url, widthMm, heightMm });
            }

            // Asumimos tamaño homogéneo (los reportes Odoo lo son). Si hubiera
            // mezcla, usamos el primero — el resto se ajusta con object-fit.
            const { widthMm, heightMm } = pages[0];
            const imgs = pages
                .map((p) => `<img src="${p.url}" alt=""/>`)
                .join("\n");
            const html = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>${escapeHtml(this.props.title || "PDF")}</title>
<style>
@page { size: ${widthMm}mm ${heightMm}mm; margin: 0; }
html, body { margin: 0; padding: 0; background: white; }
img {
    display: block;
    width: ${widthMm}mm;
    height: ${heightMm}mm;
    page-break-after: always;
    object-fit: contain;
}
img:last-child { page-break-after: auto; }
</style>
</head>
<body>
${imgs}
</body>
</html>`;
            const htmlBlob = new Blob([html], { type: "text/html" });
            const htmlUrl = URL.createObjectURL(htmlBlob);
            blobUrls.push(htmlUrl);

            let iframe = document.getElementById("pdf_inline_viewer_print_iframe");
            if (iframe) iframe.remove();
            iframe = document.createElement("iframe");
            iframe.id = "pdf_inline_viewer_print_iframe";
            Object.assign(iframe.style, {
                position: "fixed", right: "0", bottom: "0",
                width: "0", height: "0", border: "0",
            });
            iframe.src = htmlUrl;

            iframe.onload = async () => {
                // Esperar a que todas las <img> en el iframe estén cargadas
                const idoc = iframe.contentDocument;
                const allImgs = idoc.querySelectorAll("img");
                await Promise.all(
                    Array.from(allImgs).map((img) =>
                        img.complete
                            ? Promise.resolve()
                            : new Promise((r) => { img.onload = img.onerror = r; })
                    )
                );
                try {
                    iframe.contentWindow.focus();
                    iframe.contentWindow.print();
                } catch (e) {
                    err("printAll: print falló", e);
                } finally {
                    this.state.printing = false;
                    // Liberar memoria tras un tiempo prudente (el diálogo de
                    // impresión es modal pero el preview puede tardar).
                    setTimeout(() => {
                        blobUrls.forEach((u) => URL.revokeObjectURL(u));
                        iframe.remove();
                    }, 10000);
                }
            };
            document.body.appendChild(iframe);
        } catch (e) {
            err("printAll: excepción", e);
            blobUrls.forEach((u) => URL.revokeObjectURL(u));
            this.state.printing = false;
        }
    }

    // -------------------------------------------------------------------
    // Download
    // -------------------------------------------------------------------

    onDownload() {
        if (this.props.onDownload) {
            this.props.onDownload();
        } else {
            const a = document.createElement("a");
            a.href = this.props.url;
            a.download = "";
            a.dataset.pdfInlineViewer = "skip";
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
    }

    // -------------------------------------------------------------------
    // Keyboard shortcuts (las flechas dejan al navegador hacer scroll natural)
    // -------------------------------------------------------------------

    _bindKeyboardShortcuts() {
        this._onKeyDown = (ev) => {
            const tag = ev.target.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA") {
                if (ev.key === "Escape" && this.state.showSearch) {
                    this.state.showSearch = false;
                }
                return;
            }
            if (ev.ctrlKey || ev.metaKey) {
                if (ev.key === "f" || ev.key === "F") { ev.preventDefault(); this.toggleSearch(); return; }
                if (ev.key === "p" || ev.key === "P") { ev.preventDefault(); this.printAll(); return; }
                return;
            }
            switch (ev.key) {
                case "Home":
                    ev.preventDefault();
                    this.goToPage(1);
                    break;
                case "End":
                    ev.preventDefault();
                    this.goToPage(this.state.totalPages);
                    break;
                case "+":
                case "=": ev.preventDefault(); this.zoomIn(); break;
                case "-":
                case "_": ev.preventDefault(); this.zoomOut(); break;
                case "0": ev.preventDefault(); this.zoomReset(); break;
                case "r":
                case "R": ev.preventDefault(); this.rotate(); break;
                case "f":
                case "F": ev.preventDefault(); this.toggleFullscreen(); break;
                case "Escape":
                    if (this.state.showSearch) { this.state.showSearch = false; ev.preventDefault(); }
                    break;
            }
        };
        document.addEventListener("keydown", this._onKeyDown);
    }
    _unbindKeyboardShortcuts() {
        document.removeEventListener("keydown", this._onKeyDown);
    }

    // -------------------------------------------------------------------
    // i18n labels
    // -------------------------------------------------------------------

    get labels() {
        return {
            zoomIn: _t("Zoom in"),
            zoomOut: _t("Zoom out"),
            zoomReset: _t("Reset zoom"),
            rotate: _t("Rotate 90°"),
            fullscreen: _t("Fullscreen"),
            search: _t("Search (Ctrl+F)"),
            print: _t("Print (Ctrl+P)"),
            download: _t("Download"),
            sidebar: _t("Toggle thumbnails"),
            loading: _t("Loading PDF…"),
            error: _t("Could not load PDF"),
            password: _t("Password required"),
            wrongPassword: _t("Incorrect password"),
            preparing: _t("Preparing…"),
            searchPlaceholder: _t("Search the document — Enter for next, Shift+Enter for previous"),
            prevMatch: _t("Previous match (Shift+Enter)"),
            nextMatch: _t("Next match (Enter)"),
            clearSearch: _t("Clear and close (Esc)"),
        };
    }
}
