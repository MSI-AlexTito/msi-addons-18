/** @odoo-module **/

/**
 * Utilidades puras (sin DOM, sin OWL) para la búsqueda dentro del PDF.
 *
 * Diseño: cualquier función expuesta aquí debe ser ejecutable bajo Node
 * para poder testearla sin levantar Odoo ni un navegador.
 */

// Combining diacritical marks (acentos descompuestos por NFD)
const COMBINING_MARKS = /[̀-ͯ]/g;
// Zero-width chars (ZWSP, ZWNJ, ZWJ, BOM)
const ZERO_WIDTH = /[​-‍﻿]/g;

/**
 * Normaliza un texto para búsqueda insensible a mayúsculas y diacríticos.
 *
 * Garantía importante: para textos sin ligaduras ni transformaciones de caja
 * que cambien la longitud (como ß → ss), el resultado tiene la MISMA longitud
 * por carácter que el input, lo que permite mapear índices 1:1 entre
 * normalizado y original.
 *
 * @param {string} s
 * @returns {string}
 */
export function normalizeText(s) {
    return (s || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(COMBINING_MARKS, "")
        .replace(ZERO_WIDTH, "");
}

/**
 * Construye un índice plano de un conjunto de "runs" de texto (típicamente
 * los <span> que genera PDF.js TextLayer). Permite ejecutar búsquedas cuyo
 * match puede cruzar el límite entre runs.
 *
 * @param {Array<{text: string}>} runs
 * @returns {{
 *   text: string,           // texto original concatenado
 *   normalized: string,     // texto normalizado (mismo length que text)
 *   ranges: Array<{start: number, end: number, runIdx: number}>
 * }}
 */
export function buildRunIndex(runs) {
    let text = "";
    let normalized = "";
    const ranges = [];
    runs.forEach((run, runIdx) => {
        const t = run.text || "";
        const start = text.length;
        text += t;
        normalized += normalizeText(t);
        ranges.push({ start, end: text.length, runIdx });
    });
    return { text, normalized, ranges };
}

/**
 * Busca todas las ocurrencias de `query` dentro del texto concatenado.
 *
 * @param {{normalized: string}} index - resultado de buildRunIndex
 * @param {string} query
 * @returns {Array<{start: number, end: number}>}
 */
export function findMatches(index, query) {
    const q = normalizeText((query || "").trim());
    if (!q) return [];
    const matches = [];
    let from = 0;
    while (true) {
        const idx = index.normalized.indexOf(q, from);
        if (idx === -1) break;
        matches.push({ start: idx, end: idx + q.length });
        from = idx + q.length;
    }
    return matches;
}

/**
 * Para un rango (start, end) del texto concatenado, devuelve los sub-rangos
 * correspondientes en cada run involucrado. Permite resaltar un match que
 * cruza el límite entre dos o más spans.
 *
 * @param {{ranges: Array<{start, end, runIdx}>}} index
 * @param {{start: number, end: number}} match
 * @returns {Array<{runIdx: number, localStart: number, localEnd: number}>}
 */
export function splitMatchAcrossRuns(index, match) {
    const out = [];
    for (const r of index.ranges) {
        if (r.end <= match.start) continue;
        if (r.start >= match.end) break;
        const overlapStart = Math.max(match.start, r.start);
        const overlapEnd = Math.min(match.end, r.end);
        out.push({
            runIdx: r.runIdx,
            localStart: overlapStart - r.start,
            localEnd: overlapEnd - r.start,
        });
    }
    return out;
}

/**
 * Aplana matches por página en un array global ordenado.
 *
 * @param {Map<number, Array<{start, end}>>} matchesPerPage
 * @returns {Array<{page: number, start: number, end: number, indexInPage: number}>}
 */
export function flattenMatches(matchesPerPage) {
    const flat = [];
    const pageNums = [...matchesPerPage.keys()].sort((a, b) => a - b);
    for (const page of pageNums) {
        const ms = matchesPerPage.get(page) || [];
        ms.forEach((m, i) => {
            flat.push({ page, start: m.start, end: m.end, indexInPage: i });
        });
    }
    return flat;
}

/**
 * Escapa HTML para insertar texto seguro dentro de innerHTML.
 * @param {string} s
 */
export function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}
