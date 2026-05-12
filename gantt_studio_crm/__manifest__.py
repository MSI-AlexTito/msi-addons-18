{
    "name": "Gantt Studio — CRM Integration",
    "version": "18.0.1.0.0",
    "summary": "Demo + integration of Gantt Studio for crm.lead",
    "description": """
Gantt Studio — CRM Integration
==============================

Vista demo de Gantt Studio sobre ``crm.lead`` para visualizar el pipeline
comercial como Gantt: cada oportunidad como una barra desde su
``date_open`` (fecha de apertura/asignación) hasta su ``date_deadline``
(cierre esperado), agrupado por etapa, coloreado por responsable.

Demuestra técnicamente que **gantt_studio funciona en cualquier modelo
sin tocar el schema del modelo destino**. Este add-on:

* NO agrega ningún campo a ``crm.lead``.
* NO modifica el modelo ``crm.lead``.
* Solo declara una vista XML y un action/menú.

Las dependencias, baselines y CPM viven en las tablas polimórficas del
core (``gantt.studio.dependency``, ``gantt.studio.baseline``) y se
referencian a las oportunidades por ``(res_model='crm.lead', record_id)``.
""",
    "author": "MSI",
    "website": "https://www.msi.cl",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": ["gantt_studio", "crm"],
    "data": [
        "views/gantt_studio_crm_views.xml",
        "data/demo_action.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
