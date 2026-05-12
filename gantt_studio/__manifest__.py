{
    "name": "Gantt Studio",
    "version": "18.0.1.0.0",
    "summary": "Universal Gantt view for any Odoo model — Community & Enterprise",
    "description": """
Gantt Studio — universal Gantt view
====================================

A model-agnostic Gantt view type ``<gantt_studio>`` that works on any model
having a start date and a stop date. Built in pure OWL — no Vue, no jQuery,
no external CDNs — and designed to coexist peacefully with the native
``<gantt>`` view of Odoo Enterprise.

Highlights
----------

* Works in Community and Enterprise installs (no dependency on ``web_gantt``)
* Pure OWL renderer (SVG) — fast and stylable
* Zoom levels: day / week / month / quarter / year
* Group by any field, color by any field, customizable bar label
* Drag-and-drop to reschedule, drag-resize to change duration
* Click on a bar → open the underlying record's form view
* Designed as the foundation of the Gantt Studio family (Project / MRP / HR
  / Sale add-ons sold separately)

Demo
----

The module ships with a demo view registered on ``project.task`` so you can
verify the installation immediately.
""",
    "author": "MSI",
    "website": "https://www.msi.cl",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": ["web", "project"],
    "data": [
        "security/ir.model.access.csv",
        "views/gantt_studio_views.xml",
        "data/demo_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gantt_studio/static/src/scss/gantt_studio.scss",
            "gantt_studio/static/src/js/gantt_studio_utils.js",
            "gantt_studio/static/src/js/gantt_studio_arch_parser.js",
            "gantt_studio/static/src/js/gantt_studio_model.js",
            "gantt_studio/static/src/js/gantt_studio_renderer.js",
            "gantt_studio/static/src/js/gantt_studio_pdf_export.js",
            "gantt_studio/static/src/js/gantt_studio_controller.js",
            "gantt_studio/static/src/js/gantt_studio_view.js",
            "gantt_studio/static/src/xml/gantt_studio_renderer.xml",
            "gantt_studio/static/src/xml/gantt_studio_controller.xml",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
