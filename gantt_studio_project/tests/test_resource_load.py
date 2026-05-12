"""Tests para gantt.studio.resource_load (Sprint 3.4).

Se ejercitan contra project.task porque tiene user_ids (M2M) nativo
en Community. La detección automática de resource_field encuentra
"user_ids" como primer candidato.
"""
from datetime import datetime, timedelta

from odoo.tests import tagged

from .common import GanttStudioProjectCommon


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestGanttStudioResourceLoad(GanttStudioProjectCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ResourceLoad = cls.env["gantt.studio.resource_load"]
        # Asignamos los 4 tasks comunes al mismo user para forzar overlap.
        admin = cls.env.ref("base.user_admin")
        cls.task_a.user_ids = [(6, 0, [admin.id])]
        cls.task_b.user_ids = [(6, 0, [admin.id])]
        cls.task_c.user_ids = [(6, 0, [admin.id])]
        cls.task_d.user_ids = [(6, 0, [admin.id])]
        cls.user_admin_id = admin.id

    def test_01_detect_resource_field_user_ids(self):
        name, desc = self.ResourceLoad._detect_resource_field("project.task")
        self.assertEqual(name, "user_ids")
        self.assertIsNotNone(desc)

    def test_02_detect_resource_field_returns_none_for_unrelated_model(self):
        # `res.lang` no tiene ninguno de los candidatos (user_ids, user_id,
        # resource_id, employee_id, workcenter_id). Nota: res.partner tiene
        # user_ids cuando `crm` o `portal` están instalados, así que NO sirve
        # para este test.
        name, desc = self.ResourceLoad._detect_resource_field("res.lang")
        self.assertIsNone(name)
        self.assertIsNone(desc)

    def test_03_histogram_empty_when_no_records(self):
        h = self.ResourceLoad.get_resource_histogram(
            "project.task", [],
            datetime(2026, 6, 1).isoformat(),
            datetime(2026, 6, 15).isoformat(),
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        self.assertEqual(h["resources"], [])

    def test_04_histogram_basic_shape(self):
        h = self.ResourceLoad.get_resource_histogram(
            "project.task", self.all_task_ids,
            datetime(2026, 5, 28).isoformat(),
            datetime(2026, 6, 15).isoformat(),
            period="week",
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        self.assertEqual(h["period"], "week")
        self.assertTrue(h["buckets"])
        self.assertEqual(h["resource_field"], "user_ids")
        # Hay al menos un recurso (admin), con datos por bucket.
        self.assertTrue(h["resources"])
        admin = next((r for r in h["resources"] if r["id"] == self.user_admin_id), None)
        self.assertIsNotNone(admin)
        self.assertEqual(len(admin["data"]), len(h["buckets"]))

    def test_05_overallocation_detection(self):
        # A, B, C son secuenciales (no overlap). D es paralela a A (overlap).
        # Si todas están asignadas al mismo user con default 8h/día, los
        # buckets donde overlap A+D tienen >8h → ratio > 1 → conflict.
        over = self.ResourceLoad.detect_overallocations(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
            resource_field="user_ids",
            threshold=1.0,
        )
        # Esperamos al menos task_a y task_d (paralelas, mismo user).
        self.assertIn(self.task_a.id, over,
                      "Task A debería detectarse como sobreasignada (overlap con D)")
        self.assertIn(self.task_d.id, over,
                      "Task D debería detectarse como sobreasignada (overlap con A)")

    def test_06_no_overallocation_when_threshold_high(self):
        # Threshold absurdamente alto → nada sobreasignado.
        over = self.ResourceLoad.detect_overallocations(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
            resource_field="user_ids",
            threshold=10.0,
        )
        self.assertEqual(over, [])

    def test_07_returns_empty_for_model_without_resource(self):
        # res.lang no tiene user_ids/user_id/etc. → payload vacío.
        lang = self.env["res.lang"].search([], limit=1)
        h = self.ResourceLoad.get_resource_histogram(
            "res.lang", [lang.id],
            datetime(2026, 6, 1).isoformat(),
            datetime(2026, 6, 15).isoformat(),
            date_start_field="create_date",
            date_stop_field="write_date",
        )
        self.assertEqual(h["resources"], [])
        self.assertIsNone(h["resource_field"])

    def test_08_buckets_iterate_correctly(self):
        h = self.ResourceLoad.get_resource_histogram(
            "project.task", self.all_task_ids,
            datetime(2026, 6, 1).isoformat(),
            datetime(2026, 6, 8).isoformat(),
            period="day",
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        # 7 días → 7 buckets
        self.assertEqual(len(h["buckets"]), 7)

    def test_09_resource_field_explicit_override(self):
        # Pasamos resource_field explícitamente; debe respetarlo aunque
        # también exista uno alternativo.
        h = self.ResourceLoad.get_resource_histogram(
            "project.task", self.all_task_ids,
            datetime(2026, 6, 1).isoformat(),
            datetime(2026, 6, 15).isoformat(),
            resource_field="user_ids",
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        self.assertEqual(h["resource_field"], "user_ids")
