from odoo.tests.common import TransactionCase


class GanttStudioCoreCommon(TransactionCase):
    """Tests del core sin depender de `project` ni de ningún add-on de
    integración. Usa `res.partner` (siempre instalado vía `base`) como
    modelo arbitrario para ejercitar la naturaleza polimórfica del modelo
    `gantt.studio.dependency` y `gantt.studio.baseline`.

    Los modelos polimórficos guardan solo `res_model` + `<id entero>` y
    validan que `res_model` exista en `env`. No requieren que los records
    tengan ciertas fechas — eso lo prueban tests específicos de integración
    en gantt_studio_project (con project.task), gantt_studio_crm (con
    crm.lead), etc.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Dep = cls.env["gantt.studio.dependency"]
        cls.Baseline = cls.env["gantt.studio.baseline"]
        cls.Planner = cls.env["gantt.studio.planner"]

        # 4 partners para usar como ids de "registros" en las pruebas
        # polimórficas. Ningún test del core inspecciona los datos de estos
        # registros — solo necesitamos ids reales.
        cls.p1 = cls.Partner.create({"name": "GS Core Partner 1"})
        cls.p2 = cls.Partner.create({"name": "GS Core Partner 2"})
        cls.p3 = cls.Partner.create({"name": "GS Core Partner 3"})
        cls.p4 = cls.Partner.create({"name": "GS Core Partner 4"})
        cls.all_ids = [cls.p1.id, cls.p2.id, cls.p3.id, cls.p4.id]
