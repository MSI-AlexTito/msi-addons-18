from datetime import datetime

from odoo.tests import tagged

from .common import GanttStudioCommon


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioBaseline(GanttStudioCommon):

    def test_01_snapshot_creates_one_line_per_record(self):
        bid = self.Baseline.snapshot(
            "project.task",
            self.all_task_ids,
            "planned_date_begin",
            "date_deadline",
        )
        baseline = self.Baseline.browse(bid)
        self.assertTrue(baseline.exists())
        self.assertEqual(len(baseline.line_ids), 4)
        self.assertEqual(baseline.line_count, 4)
        self.assertEqual(baseline.res_model, "project.task")

    def test_02_snapshot_with_empty_ids_returns_false(self):
        res = self.Baseline.snapshot(
            "project.task", [], "planned_date_begin", "date_deadline",
        )
        self.assertFalse(res)

    def test_03_snapshot_captures_actual_dates(self):
        bid = self.Baseline.snapshot(
            "project.task",
            [self.task_a.id],
            "planned_date_begin",
            "date_deadline",
        )
        line = self.Baseline.browse(bid).line_ids
        self.assertEqual(line.record_id, self.task_a.id)
        self.assertEqual(line.date_start, datetime(2026, 6, 1, 8, 0))
        self.assertEqual(line.date_stop, datetime(2026, 6, 3, 17, 0))

    def test_04_action_activate_makes_exclusive(self):
        b1 = self.Baseline.browse(self.Baseline.snapshot(
            "project.task", self.all_task_ids, "planned_date_begin", "date_deadline",
        ))
        b2 = self.Baseline.browse(self.Baseline.snapshot(
            "project.task", self.all_task_ids, "planned_date_begin", "date_deadline",
        ))
        b1.action_activate()
        self.assertTrue(b1.is_active)
        b2.action_activate()
        self.assertFalse(b1.is_active, "Activating b2 must deactivate b1")
        self.assertTrue(b2.is_active)

    def test_05_action_activate_per_model_isolation(self):
        # Two baselines on different models must be active independently.
        b_task = self.Baseline.create({"res_model": "project.task"})
        b_partner = self.Baseline.create({"res_model": "res.partner"})
        b_task.action_activate()
        b_partner.action_activate()
        self.assertTrue(b_task.is_active)
        self.assertTrue(b_partner.is_active)

    def test_06_get_active_lines_no_active(self):
        # No active baseline → returns empty stub
        res = self.Baseline.get_active_lines("project.task", self.all_task_ids)
        self.assertEqual(res, {"baseline_id": False, "lines": []})

    def test_07_get_active_lines_filters_by_record_ids(self):
        bid = self.Baseline.snapshot(
            "project.task", self.all_task_ids,
            "planned_date_begin", "date_deadline",
        )
        self.Baseline.browse(bid).action_activate()
        # Ask only for A,B
        res = self.Baseline.get_active_lines("project.task", [self.task_a.id, self.task_b.id])
        self.assertEqual(res["baseline_id"], bid)
        self.assertEqual(len(res["lines"]), 2)
        ids = {l["record_id"] for l in res["lines"]}
        self.assertEqual(ids, {self.task_a.id, self.task_b.id})

    def test_08_action_deactivate(self):
        b = self.Baseline.browse(self.Baseline.snapshot(
            "project.task", self.all_task_ids,
            "planned_date_begin", "date_deadline",
        ))
        b.action_activate()
        b.action_deactivate()
        self.assertFalse(b.is_active)

    def test_09_snapshot_handles_records_without_dates(self):
        # Create a task without dates and make sure snapshot doesn't crash
        no_date = self.Task.create({
            "name": "No-date",
            "project_id": self.project.id,
        })
        bid = self.Baseline.snapshot(
            "project.task", [no_date.id],
            "planned_date_begin", "date_deadline",
        )
        line = self.Baseline.browse(bid).line_ids
        self.assertFalse(line.date_start)
        self.assertFalse(line.date_stop)

    def test_10_baseline_name_defaults(self):
        b = self.Baseline.create({"res_model": "project.task"})
        self.assertIn("Baseline", b.name)
