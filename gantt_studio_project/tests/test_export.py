"""Tests para gantt.studio.export (Sprint 3.6).

Verifica que el XML generado es bien-formado y contiene los campos
esperados de MS Project XML 2003.
"""
from xml.etree import ElementTree as ET

from odoo.tests import tagged

from .common import GanttStudioProjectCommon


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestGanttStudioExport(GanttStudioProjectCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Export = cls.env["gantt.studio.export"]
        # 1 cadena de deps para que el XML contenga PredecessorLink.
        cls.Dep.link("project.task", cls.task_a.id, cls.task_b.id, "FS", 0.0)
        cls.Dep.link("project.task", cls.task_b.id, cls.task_c.id, "SS", 1.5)

    # ── XML generation ────────────────────────────────────────────────

    def _parse(self, xml_str):
        """Helper: parsea XML y devuelve root con namespace stripped."""
        # MS Project XML usa namespace, lo limpiamos para asserts simples.
        root = ET.fromstring(xml_str)
        # Strip namespace de todos los tags.
        for el in root.iter():
            if "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        return root

    def test_01_empty_records_returns_empty_xml(self):
        xml = self.Export.export_msproject_xml(
            "project.task", [],
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        self.assertEqual(root.tag, "Project")
        self.assertIsNotNone(root.find("Tasks"))

    def test_02_basic_xml_well_formed(self):
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        self.assertEqual(root.tag, "Project")
        self.assertIsNotNone(root.find("Name"))
        self.assertIsNotNone(root.find("Tasks"))
        self.assertIsNotNone(root.find("Resources"))
        self.assertIsNotNone(root.find("Assignments"))

    def test_03_task_count_matches(self):
        # Las 4 tasks + 1 summary task UID=0 = 5 <Task>.
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        tasks = root.find("Tasks").findall("Task")
        self.assertEqual(len(tasks), len(self.all_task_ids) + 1,
                         "Esperaba N records + 1 summary")

    def test_04_task_has_name_start_finish(self):
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        # Buscamos el Task con Name == "Task A"
        for task in root.find("Tasks").findall("Task"):
            name = task.find("Name")
            if name is not None and name.text == "Task A":
                self.assertIsNotNone(task.find("Start"))
                self.assertIsNotNone(task.find("Finish"))
                self.assertIsNotNone(task.find("Duration"))
                return
        self.fail("Task A no se exportó")

    def test_05_predecessor_links_emitted(self):
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        # B tiene un PredecessorLink hacia A (tipo FS=1)
        # C tiene un PredecessorLink hacia B (tipo SS=3) con LinkLag (1.5d)
        links_found = 0
        for task in root.find("Tasks").findall("Task"):
            for link in task.findall("PredecessorLink"):
                links_found += 1
        self.assertGreaterEqual(links_found, 2, "Faltan PredecessorLink")

    def test_06_predecessor_type_mapping(self):
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
        )
        root = self._parse(xml)
        # Validamos que los Types están en {0,1,2,3} (MSP enum)
        for task in root.find("Tasks").findall("Task"):
            for link in task.findall("PredecessorLink"):
                t = int(link.find("Type").text)
                self.assertIn(t, (0, 1, 2, 3))

    def test_07_resource_field_export_resources(self):
        admin = self.env.ref("base.user_admin")
        self.task_a.user_ids = [(6, 0, [admin.id])]
        self.task_b.user_ids = [(6, 0, [admin.id])]
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
            resource_field="user_ids",
        )
        root = self._parse(xml)
        resources = root.find("Resources").findall("Resource")
        # 1 "Unassigned" + 1 (admin)
        self.assertGreaterEqual(len(resources), 2)
        names = {r.find("Name").text for r in resources if r.find("Name") is not None}
        self.assertTrue(any("Unassigned" in n for n in names))

    def test_08_assignments_emitted(self):
        admin = self.env.ref("base.user_admin")
        self.task_a.user_ids = [(6, 0, [admin.id])]
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids,
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
            resource_field="user_ids",
        )
        root = self._parse(xml)
        assignments = root.find("Assignments").findall("Assignment")
        self.assertGreaterEqual(len(assignments), 1,
            "Esperaba al menos 1 Assignment para la task con user_ids")

    def test_09_wbs_outline_when_parent_field(self):
        # parent_id existe en project.task; creamos un hijo de task_a.
        child = self.Task.create({
            "name": "Subtarea de A",
            "project_id": self.project.id,
            "parent_id": self.task_a.id,
            "planned_date_begin": self.task_a.planned_date_begin,
            "date_deadline": self.task_a.date_deadline,
        })
        xml = self.Export.export_msproject_xml(
            "project.task", self.all_task_ids + [child.id],
            date_start_field="planned_date_begin",
            date_stop_field="date_deadline",
            parent_field="parent_id",
        )
        root = self._parse(xml)
        # Encontramos el outline level del hijo: debería ser 2 (hijo de A
        # que es root level 1) → +1 por la convención = 2.
        found_child = False
        for task in root.find("Tasks").findall("Task"):
            n = task.find("Name")
            if n is not None and n.text == "Subtarea de A":
                outline = task.find("OutlineLevel")
                self.assertIsNotNone(outline)
                self.assertEqual(int(outline.text), 2,
                    f"Outline level del hijo debe ser 2, fue {outline.text}")
                found_child = True
                break
        self.assertTrue(found_child, "Hijo no se exportó")
