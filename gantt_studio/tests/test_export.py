"""Tests Sprint 3.9 — export_xlsx.

Ejercita el método `gantt.studio.export.export_xlsx` de forma
polímorfica sobre `res.partner` (siempre instalado). Verifica:
  - Retorna base64 de un xlsx válido (magic PK\\x03\\x04)
  - Ids vacíos devuelven False
  - La hoja "Dependencias" aparece cuando existen deps
  - Funciona con resource_field M2O
  - No revienta con caracteres especiales en nombres (ñ, ü, &, —)
"""
import base64
import zipfile
from io import BytesIO

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioExportXlsx(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Export  = cls.env["gantt.studio.export"]
        cls.Dep     = cls.env["gantt.studio.dependency"]
        cls.Partner = cls.env["res.partner"]

        cls.p1 = cls.Partner.create({"name": "GS Xlsx Partner A"})
        cls.p2 = cls.Partner.create({"name": "GS Xlsx Partner B"})
        cls.p3 = cls.Partner.create({"name": "GS Xlsx Partner C"})
        cls.all_ids = [cls.p1.id, cls.p2.id, cls.p3.id]

        # p1 → p2 (FS), p2 → p3 (FS + 2d lag)
        cls.Dep.create([
            {
                "res_model": "res.partner",
                "predecessor_id": cls.p1.id,
                "successor_id": cls.p2.id,
                "dep_type": "FS",
            },
            {
                "res_model": "res.partner",
                "predecessor_id": cls.p2.id,
                "successor_id": cls.p3.id,
                "dep_type": "FS",
                "lag_days": 2.0,
            },
        ])

    # ── helpers ────────────────────────────────────────────────────────

    def _call(self, record_ids, **kwargs):
        kwargs.setdefault("date_start_field", "create_date")
        kwargs.setdefault("date_stop_field", "write_date")
        return self.Export.export_xlsx("res.partner", record_ids, **kwargs)

    def _assert_xlsx(self, b64, msg=""):
        self.assertIsInstance(b64, str, f"export_xlsx debe retornar str base64 — {msg}")
        self.assertTrue(b64, f"base64 no debe ser vacío — {msg}")
        raw = base64.b64decode(b64)
        self.assertEqual(
            raw[:4], b"PK\x03\x04",
            f"Magic xlsx (ZIP) esperado, got {raw[:4]!r} — {msg}",
        )
        return raw

    def _xlsx_sheet_names(self, b64):
        """Extrae los nombres de hojas del workbook.xml dentro del ZIP xlsx."""
        raw = base64.b64decode(b64)
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
        # Los nombres de hoja aparecen como name="..." en <sheet .../> tags
        import re
        return re.findall(r'<sheet[^>]+name="([^"]+)"', wb_xml)

    # ── tests ──────────────────────────────────────────────────────────

    def test_01_retorna_xlsx_valido(self):
        b64 = self._call(self.all_ids)
        self.assertTrue(b64)
        self._assert_xlsx(b64, "3 partners")

    def test_02_ids_vacios_retornan_false(self):
        self.assertFalse(self._call([]))

    def test_03_hoja_dependencias_presente_cuando_hay_deps(self):
        b64 = self._call(self.all_ids)
        self._assert_xlsx(b64)
        sheets = self._xlsx_sheet_names(b64)
        self.assertIn(
            "Dependencias", sheets,
            f"Se esperaba hoja 'Dependencias'. Hojas encontradas: {sheets}",
        )

    def test_04_sin_deps_no_hay_hoja_dependencias(self):
        b64 = self._call([self.p1.id])
        self._assert_xlsx(b64)
        sheets = self._xlsx_sheet_names(b64)
        self.assertNotIn(
            "Dependencias", sheets,
            "No debe haber hoja Dependencias cuando no hay deps en el subconjunto",
        )

    def test_05_resource_field_m2o(self):
        # user_id existe en res.partner (M2O a res.users); no debe reventar.
        b64 = self._call(self.all_ids, resource_field="user_id")
        self._assert_xlsx(b64, "resource_field M2O")

    def test_06_un_solo_record(self):
        b64 = self._call([self.p1.id])
        self._assert_xlsx(b64, "single record")

    def test_07_caracteres_especiales_en_nombre(self):
        p = self.Partner.create({"name": "Müller & Söhne — España/Türkiye <>&\""})
        b64 = self._call([p.id])
        self._assert_xlsx(b64, "chars especiales")

    def test_08_project_name_custom(self):
        b64 = self._call(self.all_ids, project_name="Mi Proyecto Ñoño")
        self._assert_xlsx(b64, "project_name custom con ñ")

    def test_09_todos_los_tipos_dep_en_xlsx(self):
        p4 = self.Partner.create({"name": "GS Partner D"})
        p5 = self.Partner.create({"name": "GS Partner E"})
        self.Dep.create([
            {"res_model": "res.partner", "predecessor_id": p4.id,
             "successor_id": p5.id, "dep_type": "SS"},
        ])
        b64 = self._call([p4.id, p5.id])
        self._assert_xlsx(b64, "dep SS")
        sheets = self._xlsx_sheet_names(b64)
        self.assertIn("Dependencias", sheets)

    def test_10_lag_negativo_no_revienta(self):
        p6 = self.Partner.create({"name": "GS Partner F"})
        p7 = self.Partner.create({"name": "GS Partner G"})
        self.Dep.create({
            "res_model": "res.partner",
            "predecessor_id": p6.id,
            "successor_id": p7.id,
            "dep_type": "FS",
            "lag_days": -3.0,
        })
        b64 = self._call([p6.id, p7.id])
        self._assert_xlsx(b64, "lag negativo (lead time)")
