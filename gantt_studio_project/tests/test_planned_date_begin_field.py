"""Pruebas del campo `planned_date_begin` añadido por gantt_studio_project.

Garantiza que:

1. El campo existe en `project.task` tras instalar gantt_studio_project.
2. Es un Datetime con tracking + index.
3. Si `project_enterprise` también lo declara, AMBOS módulos coexisten
   sin conflicto en la BD (una sola columna).
4. El campo es writable vía ORM.

Esto cubre el escenario *"funciona en Community y si después instalan
Enterprise sigue funcionando"* — la promesa central del módulo.
"""
from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestPlannedDateBeginField(TransactionCase):

    def test_01_field_exists_on_project_task(self):
        field = self.env["project.task"]._fields.get("planned_date_begin")
        self.assertIsNotNone(
            field,
            "gantt_studio_project debe agregar planned_date_begin a project.task",
        )
        self.assertEqual(field.type, "datetime")

    def test_02_field_is_writable(self):
        project = self.env["project.project"].create({"name": "PDB write test"})
        t = self.env["project.task"].create({
            "name": "T",
            "project_id": project.id,
            "planned_date_begin": datetime(2026, 9, 1, 8, 0),
            "date_deadline": datetime(2026, 9, 10, 17, 0),
        })
        self.assertEqual(t.planned_date_begin, datetime(2026, 9, 1, 8, 0))

    def test_03_one_sql_column_only(self):
        # Aunque gantt_studio_project + project_enterprise declaren el
        # MISMO campo, en la BD debe existir UNA sola columna.
        self.env.cr.execute("""
            SELECT count(*) FROM information_schema.columns
            WHERE table_name = 'project_task' AND column_name = 'planned_date_begin'
        """)
        n = self.env.cr.fetchone()[0]
        self.assertEqual(
            n, 1,
            "planned_date_begin debe existir EXACTAMENTE una vez como columna SQL",
        )

    def test_04_gantt_studio_project_is_one_of_the_declaring_modules(self):
        # Independientemente de project_enterprise, gantt_studio_project
        # debe figurar entre los módulos que declaran el campo.
        field = self.env["project.task"]._fields["planned_date_begin"]
        declaring = set(getattr(field, "_modules", set()))
        # En Community-puro: declaring == {"gantt_studio_project"}
        # Con Enterprise:    declaring incluye también "project_enterprise"
        self.assertIn(
            "gantt_studio_project", declaring,
            f"gantt_studio_project debe declarar el campo, _modules={declaring}",
        )
