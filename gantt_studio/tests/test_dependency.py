from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import GanttStudioCommon


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioDependency(GanttStudioCommon):

    # ── Validation constraints ────────────────────────────────────────

    def test_01_self_link_forbidden(self):
        with self.assertRaises(ValidationError):
            self.Dep.create({
                "res_model": "project.task",
                "predecessor_id": self.task_a.id,
                "successor_id": self.task_a.id,
                "dep_type": "FS",
            })

    def test_02_unknown_model_forbidden(self):
        with self.assertRaises(ValidationError):
            self.Dep.create({
                "res_model": "no.such.model",
                "predecessor_id": self.task_a.id,
                "successor_id": self.task_b.id,
                "dep_type": "FS",
            })

    def test_03_unique_pair_per_type(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        # Same type → updates lag, does NOT duplicate
        before = self.Dep.search_count([("res_model", "=", "project.task")])
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS", 2.5)
        after = self.Dep.search_count([("res_model", "=", "project.task")])
        self.assertEqual(before, after, "link() should be idempotent per (pred, succ, type)")
        dep = self.Dep.search([
            ("res_model", "=", "project.task"),
            ("predecessor_id", "=", self.task_a.id),
            ("successor_id", "=", self.task_b.id),
            ("dep_type", "=", "FS"),
        ])
        self.assertEqual(dep.lag_days, 2.5, "lag_days should be updated")

    def test_04_different_dep_types_coexist(self):
        # Same (pred, succ) but different types is allowed.
        d1 = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        d2 = self.Dep.link("project.task", self.task_a.id, self.task_b.id, "SS")
        self.assertNotEqual(d1, d2)

    # ── RPC API ───────────────────────────────────────────────────────

    def test_05_get_dependencies_returns_only_touching(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        self.Dep.link("project.task", self.task_b.id, self.task_c.id, "FS")
        # Ask only for A,B → should return both deps that touch B (a→b and b→c)
        rows = self.Dep.get_dependencies("project.task", [self.task_a.id, self.task_b.id])
        ids = {(d["predecessor_id"], d["successor_id"]) for d in rows}
        self.assertIn((self.task_a.id, self.task_b.id), ids)
        self.assertIn((self.task_b.id, self.task_c.id), ids)
        # Now ask only for D (parallel) → should be empty
        rows = self.Dep.get_dependencies("project.task", [self.task_d.id])
        self.assertEqual(rows, [])

    def test_06_get_dependencies_filters_by_model(self):
        # Create a dep on a different model — should not appear when asking
        # for project.task
        self.Dep.link("res.partner", 1, 2, "FS")
        rows = self.Dep.get_dependencies("project.task", [self.task_a.id, self.task_b.id])
        for r in rows:
            self.assertEqual(self.Dep.browse(r["id"]).res_model, "project.task")

    def test_07_unlink_pair(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "SS")
        self.Dep.unlink_pair("project.task", self.task_a.id, self.task_b.id, "FS")
        remaining = self.Dep.search([
            ("res_model", "=", "project.task"),
            ("predecessor_id", "=", self.task_a.id),
            ("successor_id", "=", self.task_b.id),
        ])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining.dep_type, "SS")

    def test_08_unlink_pair_all_types(self):
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "SS")
        self.Dep.unlink_pair("project.task", self.task_a.id, self.task_b.id)
        remaining = self.Dep.search([
            ("res_model", "=", "project.task"),
            ("predecessor_id", "=", self.task_a.id),
            ("successor_id", "=", self.task_b.id),
        ])
        self.assertFalse(remaining)

    def test_09_empty_record_ids_returns_empty(self):
        self.assertEqual(self.Dep.get_dependencies("project.task", []), [])

    def test_10_lag_can_be_negative(self):
        d = self.Dep.create({
            "res_model": "project.task",
            "predecessor_id": self.task_a.id,
            "successor_id": self.task_b.id,
            "dep_type": "FS",
            "lag_days": -1.5,
        })
        self.assertEqual(d.lag_days, -1.5, "Negative lag (lead time) must be allowed")
