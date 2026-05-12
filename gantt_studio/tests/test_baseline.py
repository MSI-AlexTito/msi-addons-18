"""Tests del modelo polimórfico `gantt.studio.baseline` y sus líneas.

Como con las dependencias, todo se prueba contra `res.partner` para
mantener el core agnóstico al modelo destino. Para fechas usamos
`create_date` / `write_date` que existen en cualquier modelo de Odoo y
toman valores automáticos al crear el partner.
"""
from datetime import datetime, timedelta

from odoo.tests import tagged

from .common import GanttStudioCoreCommon


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioBaseline(GanttStudioCoreCommon):

    def test_01_snapshot_creates_one_line_per_record(self):
        bid = self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        )
        baseline = self.Baseline.browse(bid)
        self.assertTrue(baseline.exists())
        self.assertEqual(len(baseline.line_ids), 4)
        self.assertEqual(baseline.line_count, 4)
        self.assertEqual(baseline.res_model, "res.partner")

    def test_02_snapshot_with_empty_ids_returns_false(self):
        res = self.Baseline.snapshot(
            "res.partner", [], "create_date", "write_date",
        )
        self.assertFalse(res)

    def test_03_snapshot_captures_dates(self):
        bid = self.Baseline.snapshot(
            "res.partner", [self.p1.id], "create_date", "write_date",
        )
        line = self.Baseline.browse(bid).line_ids
        self.assertEqual(line.record_id, self.p1.id)
        # `create_date` debe estar fijado al crear el partner
        self.assertTrue(line.date_start)
        self.assertTrue(line.date_stop)

    def test_04_action_activate_makes_exclusive(self):
        b1 = self.Baseline.browse(self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        ))
        b2 = self.Baseline.browse(self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        ))
        b1.action_activate()
        self.assertTrue(b1.is_active)
        b2.action_activate()
        self.assertFalse(b1.is_active, "Activar b2 debe desactivar b1")
        self.assertTrue(b2.is_active)

    def test_05_action_activate_per_model_isolation(self):
        # Dos baselines en modelos distintos pueden estar ambas activas.
        b_partner = self.Baseline.create({"res_model": "res.partner"})
        b_users = self.Baseline.create({"res_model": "res.users"})
        b_partner.action_activate()
        b_users.action_activate()
        self.assertTrue(b_partner.is_active)
        self.assertTrue(b_users.is_active)

    def test_06_get_active_lines_no_active(self):
        res = self.Baseline.get_active_lines("res.partner", self.all_ids)
        self.assertEqual(res, {"baseline_id": False, "lines": []})

    def test_07_get_active_lines_filters_by_record_ids(self):
        bid = self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        )
        self.Baseline.browse(bid).action_activate()
        res = self.Baseline.get_active_lines("res.partner", [self.p1.id, self.p2.id])
        self.assertEqual(res["baseline_id"], bid)
        self.assertEqual(len(res["lines"]), 2)
        ids = {l["record_id"] for l in res["lines"]}
        self.assertEqual(ids, {self.p1.id, self.p2.id})

    def test_08_action_deactivate(self):
        b = self.Baseline.browse(self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        ))
        b.action_activate()
        b.action_deactivate()
        self.assertFalse(b.is_active)

    def test_09_baseline_name_defaults(self):
        b = self.Baseline.create({"res_model": "res.partner"})
        self.assertIn("Baseline", b.name)

    def test_10_polymorphic_baseline(self):
        # Una sola tabla `gantt.studio.baseline` puede contener snapshots
        # de muchos modelos distintos. Esto es lo que permite que el módulo
        # se use en proyectos, CRM, ventas, etc. con cero cambios al schema.
        bid_partner = self.Baseline.snapshot(
            "res.partner", self.all_ids, "create_date", "write_date",
        )
        bid_users = self.Baseline.snapshot(
            "res.users", [1], "create_date", "write_date",
        )
        self.assertNotEqual(bid_partner, bid_users)
        self.assertEqual(self.Baseline.browse(bid_partner).res_model, "res.partner")
        self.assertEqual(self.Baseline.browse(bid_users).res_model, "res.users")
