from odoo import fields, models


class ProjectTask(models.Model):
    """Agrega UN SOLO campo (`planned_date_begin`) a project.task para que
    la vista Gantt Studio funcione en Odoo 18 **Community puro**.

    Coexistencia con `project_enterprise`
    -------------------------------------
    Odoo Enterprise's ``project_enterprise`` declara exactamente este
    mismo campo:

        planned_date_begin = fields.Datetime("Start date", tracking=True)

    Cuando ambos módulos están instalados, Odoo **funde** las dos
    declaraciones en un único campo: como el nombre y el tipo coinciden,
    no hay conflicto de schema, ni de tracking, ni de columna en la BD.

    Esto permite que el cliente:

    * Use **solo Community + gantt_studio_project** — esta clase aporta
      el campo y todo funciona.
    * **Migre a Enterprise** después — la vista, la demo y los datos
      siguen funcionando sin cambios porque el campo se llama igual.
    * O viceversa, **degrade de Enterprise a Community** — los datos
      planificados se conservan; este módulo retoma la propiedad
      del campo y nada se rompe.

    Por qué NO agregar `date_deadline`
    ----------------------------------
    `date_deadline` ya existe nativo en Community en project.task
    (Datetime, "Deadline"). No tiene sentido duplicarlo.
    """

    _inherit = "project.task"

    planned_date_begin = fields.Datetime(
        string="Start date",
        tracking=True,
        index=True,
        help="Fecha planificada de inicio de la tarea (Gantt). En instalaciones "
             "Enterprise este mismo campo lo aporta project_enterprise; ambos "
             "módulos pueden convivir sin conflicto.",
    )
