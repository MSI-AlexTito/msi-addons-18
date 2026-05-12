/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";

/**
 * Sidebar de miniaturas.
 *
 * Estrategia: render eager y secuencial al montar el componente y cuando
 * el PDF cambia. Para PDFs grandes (>50 páginas) podríamos volver a lazy
 * con IntersectionObserver, pero hay que esperar al patch del DOM de OWL.
 *
 * Props:
 *  - pdf: instancia PDFDocumentProxy de pdf.js
 *  - currentPage: número de página actual (para highlight)
 *  - onSelectPage: callback(pageNumber)
 */
export class PdfThumbnails extends Component {
    static template = "pdf_inline_viewer.PdfThumbnails";
    static props = {
        pdf: Object,
        currentPage: Number,
        onSelectPage: Function,
    };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ pages: [] });
        this._rendered = new Set();
        this._activeScrollDone = false;

        // Inicializar la lista de páginas y dispararlas a render.
        // Usamos useEffect con totalPages como dep para que el render solo ocurra
        // cuando OWL ya haya patcheado el DOM con los nuevos thumbs.
        useEffect(
            () => {
                if (this.state.pages.length && this.rootRef.el) {
                    this._renderPending();
                }
            },
            () => [this.state.pages.length]
        );

        onMounted(() => this._setupPages());
        onWillUnmount(() => {
            this._rendered.clear();
        });
    }

    _setupPages() {
        const pages = [];
        for (let i = 1; i <= this.props.pdf.numPages; i++) {
            pages.push({ num: i });
        }
        this.state.pages = pages;
    }

    async _renderPending() {
        // Render secuencial — uno tras otro — para no inundar el worker
        for (let i = 1; i <= this.state.pages.length; i++) {
            if (this._rendered.has(i)) continue;
            const wrap = this.rootRef.el.querySelector(`.o_pdf_thumb[data-page="${i}"]`);
            if (!wrap) continue;
            const canvas = wrap.querySelector("canvas");
            if (!canvas) continue;
            this._rendered.add(i);
            await this._renderThumb(i, canvas);
        }
    }

    async _renderThumb(pageNum, canvas) {
        try {
            const page = await this.props.pdf.getPage(pageNum);
            const baseViewport = page.getViewport({ scale: 1 });
            const targetWidth = 130;
            const scale = targetWidth / baseViewport.width;
            const viewport = page.getViewport({ scale });
            const dpr = window.devicePixelRatio || 1;
            canvas.width = Math.floor(viewport.width * dpr);
            canvas.height = Math.floor(viewport.height * dpr);
            canvas.style.width = viewport.width + "px";
            canvas.style.height = viewport.height + "px";
            const ctx = canvas.getContext("2d");
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            await page.render({ canvasContext: ctx, viewport }).promise;
        } catch (e) {
            if (e?.name !== "RenderingCancelledException") {
                console.error("[pdf_inline_viewer] thumb render", pageNum, e);
            }
        }
    }

    onThumbClick(num) {
        this.props.onSelectPage(num);
    }
}
