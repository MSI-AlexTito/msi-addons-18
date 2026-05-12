"""Tests para validar la integración de la vista sobre project.task.

El validador del arch vive en `gantt_studio` y se prueba en su propia suite
contra `res.partner`. Aquí confirmamos que la vista demo embebida en este
módulo se carga correctamente y que el action queda enlazada a ella.
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestGanttStudioProjectViews(TransactionCase):

    def test_01_demo_view_loaded(self):
        view = self.env.ref(
            "gantt_studio_project.view_project_task_gantt_studio_demo"
        )
        self.assertEqual(view.type, "gantt_studio")
        self.assertEqual(view.model, "project.task")

    def test_02_demo_action_uses_view(self):
        act = self.env.ref(
            "gantt_studio_project.action_project_task_gantt_studio_demo"
        )
        self.assertIn("gantt_studio", act.view_mode)
        self.assertEqual(act.res_model, "project.task")

    def test_03_menu_present(self):
        menu = self.env.ref("gantt_studio_project.menu_gantt_studio_demo")
        self.assertEqual(menu.action.id, self.env.ref(
            "gantt_studio_project.action_project_task_gantt_studio_demo"
        ).id)
