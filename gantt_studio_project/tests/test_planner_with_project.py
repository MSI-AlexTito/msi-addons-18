from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import GanttStudioProjectCommon


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestGanttStudioPlannerCPM(GanttStudioProjectCommon):
    """Critical Path Method computation."""

    def test_01_no_records_returns_empty(self):
        res = self.Planner.compute_critical_path(
            "project.task", [], "planned_date_begin", "date_deadline",
        )
        self.assertEqual(res["critical_record_ids"], [])
        self.assertEqual(res["critical_dependency_ids"], [])

    def test_02_no_dependencies_each_record_is_its_own_path(self):
        # Without deps, every task with nonzero duration is its own critical
        # path of length 1. All slack should be 0 trivially.
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, self.task_d.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertIn(self.task_a.id, res["critical_record_ids"])

    def test_03_linear_chain_FS_all_critical(self):
        d_ab = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        d_bc = self.Dep.link("project.task", self.task_b.id, self.task_c.id, "FS")
        res = self.Planner.compute_critical_path(
            "project.task", self.all_task_ids,
            "planned_date_begin", "date_deadline",
        )
        self.assertIn(self.task_a.id, res["critical_record_ids"])
        self.assertIn(self.task_b.id, res["critical_record_ids"])
        self.assertIn(self.task_c.id, res["critical_record_ids"])
        self.assertNotIn(self.task_d.id, res["critical_record_ids"])
        self.assertIn(d_ab, res["critical_dependency_ids"])
        self.assertIn(d_bc, res["critical_dependency_ids"])

    def test_04_cycle_returns_error(self):
        # A → B → A (cycle)
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        self.Dep.link("project.task", self.task_b.id, self.task_a.id, "FS")
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, self.task_b.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertEqual(res.get("error"), "cycle_detected")
        self.assertEqual(res["critical_record_ids"], [])
        self.assertEqual(res["critical_dependency_ids"], [])

    def test_05_records_without_dates_are_skipped(self):
        no_date = self.Task.create({"name": "ND", "project_id": self.project.id})
        # Should not raise and should not include the no-date record
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, no_date.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertNotIn(no_date.id, res["critical_record_ids"])

    def test_06_SS_dependency_binding(self):
        # SS lag=0: B should start when A starts. For the dep to be on the
        # critical path, both endpoints must be critical → both must have
        # zero slack. With our anchored-CPM (project_end = max(ef)) this
        # means both must end at the same moment. Easiest setup: B mirrors
        # A's duration AND start so ef[A] == ef[B] == project_end.
        self.task_b.write({
            "planned_date_begin": self.task_a.planned_date_begin,
            "date_deadline": self.task_a.date_deadline,
        })
        d = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "SS")
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, self.task_b.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertIn(d, res["critical_dependency_ids"])

    def test_07_FF_dependency_binding(self):
        # FF lag=0: B should finish when A finishes.
        self.task_b.write({
            "planned_date_begin": self.task_a.date_deadline - timedelta(days=2),
            "date_deadline": self.task_a.date_deadline,
        })
        d = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FF")
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, self.task_b.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertIn(d, res["critical_dependency_ids"])

    def test_08_FS_with_lag(self):
        # FS lag=1 day: B must start one day after A ends. Set dates to match.
        a_end = self.task_a.date_deadline
        self.task_b.write({
            "planned_date_begin": a_end + timedelta(days=1),
            "date_deadline": a_end + timedelta(days=3),
        })
        d = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS", 1.0)
        res = self.Planner.compute_critical_path(
            "project.task", [self.task_a.id, self.task_b.id],
            "planned_date_begin", "date_deadline",
        )
        self.assertIn(d, res["critical_dependency_ids"])


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestGanttStudioPlannerReschedule(GanttStudioProjectCommon):
    """Auto-reschedule with cascading dependencies + bi-directional clamp."""

    def test_01_invalid_record_raises(self):
        with self.assertRaises(UserError):
            self.Planner.reschedule_with_dependencies(
                "project.task", 9999999, "2026-07-01 08:00:00",
                "planned_date_begin", "date_deadline",
            )

    def test_02_invalid_date_string_raises(self):
        with self.assertRaises(UserError):
            self.Planner.reschedule_with_dependencies(
                "project.task", self.task_a.id, "not-a-date",
                "planned_date_begin", "date_deadline",
            )

    def test_03_no_deps_simple_move(self):
        res = self.Planner.reschedule_with_dependencies(
            "project.task", self.task_d.id, "2026-07-01 08:00:00",
            "planned_date_begin", "date_deadline",
        )
        self.assertFalse(res["constrained"])
        self.task_d.invalidate_recordset()
        self.assertEqual(self.task_d.planned_date_begin, datetime(2026, 7, 1, 8, 0))

    def test_04_cascade_forward(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        self.Dep.link("project.task", self.task_b.id, self.task_c.id, "FS")
        # Push A 5 days forward → B and C should follow.
        # Pasamos respect_calendar=False para validar SOLO la mecánica
        # de cascade lineal sin snap a horario laboral (lo testea
        # test_calendar_awareness.py por separado).
        new_a_start = "2026-06-10 08:00:00"
        res = self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id, new_a_start,
            "planned_date_begin", "date_deadline",
            respect_calendar=False,
        )
        self.assertFalse(res["constrained"])
        ids = {u["id"] for u in res["updates"]}
        self.assertEqual(ids, {self.task_a.id, self.task_b.id, self.task_c.id})

        self.task_a.invalidate_recordset()
        self.task_b.invalidate_recordset()
        self.task_c.invalidate_recordset()
        self.assertEqual(self.task_a.planned_date_begin, datetime(2026, 6, 10, 8, 0))
        # B starts when A ends (FS lag=0)
        self.assertEqual(self.task_b.planned_date_begin, self.task_a.date_deadline)
        self.assertEqual(self.task_c.planned_date_begin, self.task_b.date_deadline)

    def test_05_clamp_when_dragging_before_predecessor(self):
        # B has predecessor A. Try to drag B BEFORE A ends → server clamps.
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        before_a = "2026-05-25 08:00:00"
        res = self.Planner.reschedule_with_dependencies(
            "project.task", self.task_b.id, before_a,
            "planned_date_begin", "date_deadline",
        )
        self.assertTrue(res["constrained"], "Should be clamped")
        self.assertIn("predec", (res["constraint_reason"] or "").lower())

        # B's actual new start must be ≥ A's end
        self.task_b.invalidate_recordset()
        self.assertGreaterEqual(self.task_b.planned_date_begin, self.task_a.date_deadline)

    def test_06_cascade_disabled(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        res = self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id, "2026-06-10 08:00:00",
            "planned_date_begin", "date_deadline", cascade=False,
        )
        # Only A should be in updates
        ids = {u["id"] for u in res["updates"]}
        self.assertEqual(ids, {self.task_a.id})

    def test_07_cascade_preserves_durations(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        orig_b_dur = self.task_b.date_deadline - self.task_b.planned_date_begin
        self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id, "2026-07-01 08:00:00",
            "planned_date_begin", "date_deadline",
            respect_calendar=False,
        )
        self.task_b.invalidate_recordset()
        new_b_dur = self.task_b.date_deadline - self.task_b.planned_date_begin
        self.assertEqual(orig_b_dur, new_b_dur, "Duration of B must be preserved")

    def test_08_cascade_only_pushes_later_never_earlier(self):
        # Make B already AFTER A's new finish — cascade should leave it alone.
        self.task_b.write({
            "planned_date_begin": datetime(2026, 12, 1, 8, 0),
            "date_deadline": datetime(2026, 12, 5, 17, 0),
        })
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        b_before = self.task_b.planned_date_begin
        self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id, "2026-06-15 08:00:00",
            "planned_date_begin", "date_deadline",
        )
        self.task_b.invalidate_recordset()
        self.assertEqual(self.task_b.planned_date_begin, b_before,
                         "B should not be pulled earlier than it already is")

    def test_09_SS_cascade(self):
        # A SS=0 B: B starts when A starts. Move A → B starts at A's new start.
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "SS")
        new_a = datetime(2026, 7, 1, 8, 0)
        self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id, new_a.strftime("%Y-%m-%d %H:%M:%S"),
            "planned_date_begin", "date_deadline",
            respect_calendar=False,
        )
        self.task_b.invalidate_recordset()
        self.assertEqual(self.task_b.planned_date_begin, new_a)
