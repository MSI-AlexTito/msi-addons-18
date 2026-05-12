"""Tests del modelo polimórfico `gantt.studio.dependency`.

Se ejercitan contra `res.partner` (en `base`) para evidenciar que el modelo
NO está acoplado a ningún add-on de integración. Si project, crm, sale,
etc. están desinstalados, estos tests siguen pasando.
"""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import GanttStudioCoreCommon


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioDependency(GanttStudioCoreCommon):

    # ── Validation constraints ────────────────────────────────────────

    def test_01_self_link_forbidden(self):
        with self.assertRaises(ValidationError):
            self.Dep.create({
                "res_model": "res.partner",
                "predecessor_id": self.p1.id,
                "successor_id": self.p1.id,
                "dep_type": "FS",
            })

    def test_02_unknown_model_forbidden(self):
        with self.assertRaises(ValidationError):
            self.Dep.create({
                "res_model": "no.such.model",
                "predecessor_id": self.p1.id,
                "successor_id": self.p2.id,
                "dep_type": "FS",
            })

    def test_03_unique_pair_per_type(self):
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        before = self.Dep.search_count([("res_model", "=", "res.partner")])
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS", 2.5)
        after = self.Dep.search_count([("res_model", "=", "res.partner")])
        self.assertEqual(before, after, "link() debe ser idempotente por (pred, succ, type)")
        dep = self.Dep.search([
            ("res_model", "=", "res.partner"),
            ("predecessor_id", "=", self.p1.id),
            ("successor_id", "=", self.p2.id),
            ("dep_type", "=", "FS"),
        ])
        self.assertEqual(dep.lag_days, 2.5, "lag_days debe actualizarse")

    def test_04_different_dep_types_coexist(self):
        d1 = self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        d2 = self.Dep.link("res.partner", self.p1.id, self.p2.id, "SS")
        self.assertNotEqual(d1, d2)

    # ── RPC API ───────────────────────────────────────────────────────

    def test_05_get_dependencies_returns_only_touching(self):
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        self.Dep.link("res.partner", self.p2.id, self.p3.id, "FS")
        rows = self.Dep.get_dependencies("res.partner", [self.p1.id, self.p2.id])
        ids = {(d["predecessor_id"], d["successor_id"]) for d in rows}
        self.assertIn((self.p1.id, self.p2.id), ids)
        self.assertIn((self.p2.id, self.p3.id), ids)
        rows = self.Dep.get_dependencies("res.partner", [self.p4.id])
        self.assertEqual(rows, [])

    def test_06_get_dependencies_filters_by_model(self):
        # Mismo par predecessor/successor en dos modelos distintos: solo
        # se devuelve el que coincide con el filtro de res_model.
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        self.Dep.link("res.users", 1, 2, "FS")
        rows = self.Dep.get_dependencies("res.partner", [self.p1.id, self.p2.id])
        for r in rows:
            self.assertEqual(self.Dep.browse(r["id"]).res_model, "res.partner")

    def test_07_unlink_pair(self):
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "SS")
        self.Dep.unlink_pair("res.partner", self.p1.id, self.p2.id, "FS")
        remaining = self.Dep.search([
            ("res_model", "=", "res.partner"),
            ("predecessor_id", "=", self.p1.id),
            ("successor_id", "=", self.p2.id),
        ])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining.dep_type, "SS")

    def test_08_unlink_pair_all_types(self):
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "SS")
        self.Dep.unlink_pair("res.partner", self.p1.id, self.p2.id)
        remaining = self.Dep.search([
            ("res_model", "=", "res.partner"),
            ("predecessor_id", "=", self.p1.id),
            ("successor_id", "=", self.p2.id),
        ])
        self.assertFalse(remaining)

    def test_09_empty_record_ids_returns_empty(self):
        self.assertEqual(self.Dep.get_dependencies("res.partner", []), [])

    def test_10_lag_can_be_negative(self):
        d = self.Dep.create({
            "res_model": "res.partner",
            "predecessor_id": self.p1.id,
            "successor_id": self.p2.id,
            "dep_type": "FS",
            "lag_days": -1.5,
        })
        self.assertEqual(d.lag_days, -1.5, "Lag negativo (lead time) debe ser permitido")

    def test_11_polymorphic_independence(self):
        # Demuestra que se pueden tener deps en MUCHOS modelos a la vez
        # sin colisión: cada (res_model, pred, succ, type) es independiente
        # y NO requiere agregar campos a esos modelos.
        self.Dep.link("res.partner", self.p1.id, self.p2.id, "FS")
        self.Dep.link("res.users", 1, 2, "FS")
        self.Dep.link("res.partner", self.p2.id, self.p3.id, "SS")
        total = self.Dep.search_count([
            ("res_model", "in", ["res.partner", "res.users"]),
        ])
        self.assertGreaterEqual(total, 3)
