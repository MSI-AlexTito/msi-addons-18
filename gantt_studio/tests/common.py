from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class GanttStudioCommon(TransactionCase):
    """Shared fixtures: a small set of project.task records on which we can
    exercise dependencies, CPM, baselines and reschedule end-to-end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env["project.task"]
        cls.Project = cls.env["project.project"]
        cls.Dep = cls.env["gantt.studio.dependency"]
        cls.Baseline = cls.env["gantt.studio.baseline"]
        cls.Planner = cls.env["gantt.studio.planner"]

        cls.project = cls.Project.create({"name": "GS Test Project"})

        # Linear chain A → B → C (FS lag=0), no gap between bars so the
        # dependencies are *binding* and end up on the critical path.
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
        # Parallel short task, off the critical path
        cls.task_d = cls.Task.create({
            "name": "Task D (parallel short)",
            "project_id": cls.project.id,
            "planned_date_begin": datetime(2026, 6, 1, 8, 0),
            "date_deadline": datetime(2026, 6, 2, 17, 0),
        })

        cls.all_task_ids = [cls.task_a.id, cls.task_b.id, cls.task_c.id, cls.task_d.id]
