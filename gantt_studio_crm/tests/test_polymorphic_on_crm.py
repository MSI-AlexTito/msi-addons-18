"""Pruebas end-to-end del flujo Gantt Studio sobre `crm.lead`.

Demuestra que TODO el ciclo (vista + deps tipadas + CPM + reschedule +
baseline) opera sobre CRM **sin agregar ningún campo a crm.lead**. Los
datos auxiliares viven en las tablas polimórficas del core.
"""
from datetime import datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_crm")
class TestGanttStudioOnCrm(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env["crm.lead"]
        cls.Dep = cls.env["gantt.studio.dependency"]
        cls.Baseline = cls.env["gantt.studio.baseline"]
        cls.Planner = cls.env["gantt.studio.planner"]

        # 3 leads que forman una cadena A -> B -> C en el tiempo.
        # Usamos fechas planificadas: date_open (inicio) y date_deadline
        # (cierre esperado). Las creamos con write() en lugar de create()
        # para date_open porque es Datetime "tracking" y a veces se ajusta.
        cls.lead_a = cls.Lead.create({
            "name": "GS CRM Lead A",
            "date_open": datetime(2026, 6, 1, 8, 0),
            "date_deadline": datetime(2026, 6, 10).date(),
        })
        cls.lead_b = cls.Lead.create({
            "name": "GS CRM Lead B",
            "date_open": datetime(2026, 6, 10, 8, 0),
            "date_deadline": datetime(2026, 6, 20).date(),
        })
        cls.lead_c = cls.Lead.create({
            "name": "GS CRM Lead C",
            "date_open": datetime(2026, 6, 20, 8, 0),
            "date_deadline": datetime(2026, 6, 30).date(),
        })

    def test_01_demo_view_loaded_on_crm(self):
        view = self.env.ref("gantt_studio_crm.view_crm_lead_gantt_studio_demo")
        self.assertEqual(view.type, "gantt_studio")
        self.assertEqual(view.model, "crm.lead")

    def test_02_demo_action_uses_view(self):
        act = self.env.ref("gantt_studio_crm.action_crm_lead_gantt_studio_demo")
        self.assertEqual(act.res_model, "crm.lead")
        self.assertIn("gantt_studio", act.view_mode)

    def test_03_no_fields_added_to_crm_lead(self):
        # Este es el test conceptual: si alguna vez alguien agrega un
        # field a crm.lead desde este módulo, esto falla.
        crm_lead_fields = set(self.env["crm.lead"]._fields.keys())
        added_via_gantt_studio_modules = [
            f for f in crm_lead_fields
            if "gantt_studio" in (self.env["crm.lead"]._fields[f]._module or "")
        ]
        self.assertEqual(
            added_via_gantt_studio_modules, [],
            "gantt_studio_* modules MUST NOT add fields to crm.lead "
            "(el modelo polimórfico es el contrato)"
        )

    def test_04_polymorphic_dependency_on_crm_lead(self):
        # Una dep entre dos leads usa exactamente la misma tabla que
        # entre tasks o cualquier otro modelo.
        dep_id = self.Dep.link("crm.lead", self.lead_a.id, self.lead_b.id, "FS", 0.0)
        self.assertTrue(dep_id)
        deps = self.Dep.get_dependencies(
            "crm.lead", [self.lead_a.id, self.lead_b.id]
        )
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["predecessor_id"], self.lead_a.id)
        self.assertEqual(deps[0]["successor_id"], self.lead_b.id)
        self.assertEqual(deps[0]["dep_type"], "FS")

    def test_05_cpm_on_crm_chain(self):
        # CPM completo sobre una cadena de leads CRM. Mismo planner que
        # usamos en project — recibe el modelo como parámetro.
        self.Dep.link("crm.lead", self.lead_a.id, self.lead_b.id, "FS")
        self.Dep.link("crm.lead", self.lead_b.id, self.lead_c.id, "FS")
        res = self.Planner.compute_critical_path(
            "crm.lead",
            [self.lead_a.id, self.lead_b.id, self.lead_c.id],
            "date_open", "date_deadline",
        )
        # Las 3 deberían estar en la ruta crítica (encadenadas sin paralelos)
        self.assertEqual(
            set(res["critical_record_ids"]),
            {self.lead_a.id, self.lead_b.id, self.lead_c.id},
            f"Esperaba las 3 leads críticas, obtuve {res}",
        )

    def test_06_reschedule_with_cascade_on_crm(self):
        # Auto-reschedule: mover el inicio de A → propaga a B y C por la
        # cadena FS.
        self.Dep.link("crm.lead", self.lead_a.id, self.lead_b.id, "FS")
        self.Dep.link("crm.lead", self.lead_b.id, self.lead_c.id, "FS")
        new_start = "2026-07-01 08:00:00"
        res = self.Planner.reschedule_with_dependencies(
            "crm.lead", self.lead_a.id, new_start,
            "date_open", "date_deadline",
        )
        self.assertFalse(res["constrained"])
        ids = {u["id"] for u in res["updates"]}
        self.assertEqual(ids, {self.lead_a.id, self.lead_b.id, self.lead_c.id})

    def test_07_baseline_snapshot_on_crm(self):
        # Snapshot + activar funciona idéntico al de project.
        bid = self.Baseline.snapshot(
            "crm.lead",
            [self.lead_a.id, self.lead_b.id, self.lead_c.id],
            "date_open", "date_deadline",
            name="Plan original CRM",
        )
        b = self.Baseline.browse(bid)
        self.assertEqual(b.res_model, "crm.lead")
        self.assertEqual(len(b.line_ids), 3)
        b.action_activate()
        self.assertTrue(b.is_active)
        ghost = self.Baseline.get_active_lines(
            "crm.lead", [self.lead_a.id, self.lead_b.id]
        )
        self.assertEqual(ghost["baseline_id"], bid)
        self.assertEqual(len(ghost["lines"]), 2)
