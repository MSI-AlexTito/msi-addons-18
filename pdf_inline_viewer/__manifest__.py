{
    "name": "PDF Inline Viewer",
    "version": "18.0.1.0.0",
    "summary": "Preview, search and print PDF reports inline — no downloads",
    "description": """
PDF Inline Viewer
=================

Replaces Odoo's default "download-and-open-externally" PDF report flow
with a fast, polished inline viewer based on OWL and PDF.js (already
bundled in Odoo 18 — no external dependencies, no external requests).

Highlights
----------

* Continuous-scroll page viewer with a lazy-loaded thumbnails sidebar
* Accent-insensitive full-text search with live highlighting
    - Yellow for matches, amber for the currently active match
    - Enter / Shift+Enter to step through results
    - Cross-span match detection (handles words split across PDF text runs)
* Print at exact 100% scale — rasterizes pages to the actual paper size
  so browsers don't apply "fit-to-printable-area" reductions
* Smart zoom, rotation, fullscreen, and keyboard shortcuts
* Password-protected PDF support via PDF.js
* Configurable watermark with per-group visibility
* Intercepts not only the Print button but also direct anchor links to
  ``/report/pdf/...``, ``/report/download``, and PDF attachments,
  so any path to a PDF ends in the inline viewer
* Opt-out per report via ``context['pdf_inline_viewer'] = False``

Translated to English (default), Spanish and Chilean Spanish.
""",
    "author": "MSI",
    "website": "https://www.msi.cl",
    "license": "LGPL-3",
    "category": "Tools",
    "depends": ["web", "base_setup"],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pdf_inline_viewer/static/src/scss/pdf_preview.scss",
            "pdf_inline_viewer/static/src/js/pdf_search_utils.js",
            "pdf_inline_viewer/static/src/js/pdf_preview_service.js",
            "pdf_inline_viewer/static/src/js/browser_patches.js",
            "pdf_inline_viewer/static/src/js/pdf_thumbnails.js",
            "pdf_inline_viewer/static/src/js/pdf_preview_dialog.js",
            "pdf_inline_viewer/static/src/xml/pdf_preview_dialog.xml",
            "pdf_inline_viewer/static/src/xml/pdf_thumbnails.xml",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
