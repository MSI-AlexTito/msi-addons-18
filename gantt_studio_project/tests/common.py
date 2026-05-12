from datetime import datetime

from odoo.tests.common import TransactionCase


class GanttStudioProjectCommon(TransactionCase):
    """Fixtures con 4 project.task: cadena A -> B -> C y una paralela D.

    Las fechas están ajustadas para que las dependencias FS lag=0 entre
    A, B, C sean *binding* (sin float), y D quede afuera de la ruta crítica.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env["project.task"]
        cls.Project = cls.env["project.project"]
        cls.Dep = cls.env["gantt.studio.dependency"]
        cls.Baseline = cls.env["gantt.studio.baseline"]
        cls.Planner = cls.env["gantt.studio.planner"]

        cls.project = cls.Project.create({"name": "GS Project Test"})

        cls.task_a = cls.Task.create({
            "name": "Task A",
            "project_id": cls.project.id,
            "planned_date_begin": datetime(2026, 6, 1, 8, 0),
            "date_deadline": datetime(2026, 6, 3, 17, 0),
        })
        cls.task_b = cls.Task.create({
            "name": "Task B",
            "project_id": cls.project.id,
            "planned_date_begin": datetime(2026, 6, 3, 17, 0),
            "date_deadline": datetime(2026, 6, 5, 17, 0),
        })
        cls.task_c = cls.Task.create({
            "name": "Task C",
            "project_id": cls.project.id,
            "planned_date_begin": datetime(2026, 6, 5, 17, 0),
            "date_deadline": datetime(2026, 6, 7, 17, 0),
        })
        cls.task_d = cls.Task.create({
            "name": "Task D (parallel short)",
            "project_id": cls.project.id,
            "planned_date_begin": datetime(2026, 6, 1, 8, 0),
            "date_deadline": datetime(2026, 6, 2, 17, 0),
        })

        cls.all_task_ids = [cls.task_a.id, cls.task_b.id,
                            cls.task_c.id, cls.task_d.id]
