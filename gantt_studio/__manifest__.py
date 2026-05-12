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
* Typed dependencies (FS / SS / FF / SF + lag), polymorphic — no schema
  changes needed on the target model
* CPM (Critical Path Method) with cycle detection
* Auto-reschedule with cascading + bi-directional clamp
* Baselines (snapshot + ghost bars for plan-vs-actual)
* PDF export

Architecture
------------

This module is the **core**. It declares the view type, the polymorphic
``gantt.studio.dependency`` and ``gantt.studio.baseline`` models, the
``gantt.studio.planner`` algorithms, and the OWL renderer. It does NOT
ship a demo view for any specific model — that's the job of the family
of optional integration add-ons:

* ``gantt_studio_project`` — vista demo sobre ``project.task``
* ``gantt_studio_crm``     — vista demo sobre ``crm.lead`` (próximo)
* ``gantt_studio_sale``    — vista demo sobre ``sale.order``
* ``gantt_studio_mrp``     — vista demo sobre ``mrp.production``
* …

Install one of those (or write your own ``<gantt_studio>`` view on the
model of your choice) and the core does the rest. No fields added to
your target model — dependencies, baselines and CPM all live in the
core's own polymorphic tables addressed by ``(res_model, record_id)``.
""",
    "author": "MSI",
    "website": "https://www.msi.cl",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": ["web", "report_xlsx"],
    "data": [
        "security/ir.model.access.csv",
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
