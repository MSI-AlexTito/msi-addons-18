{
    "name": "Gantt Studio — Project Integration",
    "version": "18.0.1.0.0",
    "summary": "Demo + integration of Gantt Studio for project.task",
    "description": """
Gantt Studio — Project Integration
===================================

Adds a ready-to-use ``<gantt_studio>`` view on ``project.task`` so users
can validate the Gantt Studio family on Odoo's project module without
writing any XML.

This module is **optional**: ``gantt_studio`` (the core) works on any
model with two date fields, regardless of whether project is installed.
It is shipped here as a demonstration of the polymorphic architecture
and as a convenience for Project users.

For other models, ship a similar tiny add-on:

* ``gantt_studio_crm``  → vista sobre ``crm.lead``
* ``gantt_studio_sale`` → vista sobre ``sale.order``
* ``gantt_studio_mrp``  → vista sobre ``mrp.production``
* …

The core (``gantt_studio``) never depends on these — it just provides the
view type, the polymorphic dependency/baseline models, the planner, and
the OWL renderer.
""",
    "author": "MSI",
    "website": "https://www.msi.cl",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": ["gantt_studio", "project"],
    "data": [
        "views/gantt_studio_project_views.xml",
        "data/demo_action.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
