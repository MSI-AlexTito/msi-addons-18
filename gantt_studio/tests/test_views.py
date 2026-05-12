from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioView(TransactionCase):
    """Validation of <gantt_studio> arch and view registration."""

    def test_01_view_type_registered(self):
        sel = dict(self.env["ir.ui.view"]._fields["type"]._description_selection(self.env))
        self.assertIn("gantt_studio", sel)

    def test_02_act_window_view_mode_registered(self):
        sel = dict(self.env["ir.actions.act_window.view"]
                   ._fields["view_mode"]._description_selection(self.env))
        self.assertIn("gantt_studio", sel)

    def test_03_demo_view_loads(self):
        view = self.env.ref("gantt_studio.view_project_task_gantt_studio_demo")
        self.assertEqual(view.type, "gantt_studio")
        self.assertEqual(view.model, "project.task")

    def test_04_demo_action_uses_gantt_studio(self):
        act = self.env.ref("gantt_studio.action_project_task_gantt_studio_demo")
        self.assertIn("gantt_studio", act.view_mode)

    def test_05_valid_arch_accepts_known_attributes(self):
        # Should NOT raise
        self.env["ir.ui.view"].create({
            "name": "Test valid gantt_studio",
            "model": "project.task",
            "type": "gantt_studio",
            "arch": """
                <gantt_studio date_start="planned_date_begin"
                              date_stop="date_deadline"
                              default_scale="month"
                              default_group_by="stage_id"
                              color_field="user_ids"
                              bar_text="name"
                              show_dependencies="true"
                              show_critical_path="true"
                              auto_reschedule="false"
                              baseline_support="true">
                    <field name="name"/>
                </gantt_studio>
            """,
        })

    def test_06_missing_date_start_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "project.task",
                "type": "gantt_studio",
                "arch": """<gantt_studio date_stop="date_deadline"/>""",
            })

    def test_07_missing_date_stop_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "project.task",
                "type": "gantt_studio",
                "arch": """<gantt_studio date_start="planned_date_begin"/>""",
            })

    def test_08_unknown_attribute_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "project.task",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="planned_date_begin"
                                  date_stop="date_deadline"
                                  some_bogus_attr="x"/>
                """,
            })

    def test_09_invalid_scale_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "project.task",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="planned_date_begin"
                                  date_stop="date_deadline"
                                  default_scale="century"/>
                """,
            })

    def test_10_non_field_child_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "project.task",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="planned_date_begin"
                                  date_stop="date_deadline">
                        <not_a_field/>
                    </gantt_studio>
                """,
            })

    def test_11_get_view_info_includes_icon(self):
        info = self.env["ir.ui.view"]._get_view_info()
        self.assertIn("gantt_studio", info)
        self.assertIn("icon", info["gantt_studio"])
