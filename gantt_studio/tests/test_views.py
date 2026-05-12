"""Tests del validador del arch `<gantt_studio>`.

El validador del core (`ir_ui_view._validate_tag_gantt_studio`) trabaja
solo a nivel de XML: comprueba presencia/forma de atributos, no que el
modelo destino sea project.task o cualquier otro en particular. Por eso
estos tests crean vistas sobre `res.partner` — un modelo siempre
disponible vía el dep `base`.

Si esto pasa, el módulo se puede instalar y validar arches sin que
project / crm / sale / mrp estén siquiera instalados.
"""
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "gantt_studio")
class TestGanttStudioCoreView(TransactionCase):

    def test_01_view_type_registered(self):
        sel = dict(self.env["ir.ui.view"]._fields["type"]
                   ._description_selection(self.env))
        self.assertIn("gantt_studio", sel)

    def test_02_act_window_view_mode_registered(self):
        sel = dict(self.env["ir.actions.act_window.view"]
                   ._fields["view_mode"]._description_selection(self.env))
        self.assertIn("gantt_studio", sel)

    def test_03_valid_arch_on_arbitrary_model(self):
        # Demuestra que el validador NO requiere campos "date_start" o
        # "date_stop" literales sobre el modelo destino — solo exige que
        # los atributos del arch estén presentes. Usamos res.partner con
        # `create_date` / `write_date` que existen en cualquier modelo.
        self.env["ir.ui.view"].create({
            "name": "Test valid gantt_studio on res.partner",
            "model": "res.partner",
            "type": "gantt_studio",
            "arch": """
                <gantt_studio date_start="create_date"
                              date_stop="write_date"
                              default_scale="month"
                              color_field="user_id"
                              bar_text="name"
                              show_dependencies="true"
                              show_critical_path="true"
                              auto_reschedule="false"
                              baseline_support="true">
                    <field name="name"/>
                </gantt_studio>
            """,
        })

    def test_04_missing_date_start_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "res.partner",
                "type": "gantt_studio",
                "arch": """<gantt_studio date_stop="write_date"/>""",
            })

    def test_05_missing_date_stop_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "res.partner",
                "type": "gantt_studio",
                "arch": """<gantt_studio date_start="create_date"/>""",
            })

    def test_06_unknown_attribute_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "res.partner",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="create_date"
                                  date_stop="write_date"
                                  some_bogus_attr="x"/>
                """,
            })

    def test_07_invalid_scale_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "res.partner",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="create_date"
                                  date_stop="write_date"
                                  default_scale="century"/>
                """,
            })

    def test_08_non_field_child_rejected(self):
        with self.assertRaises(Exception), mute_logger("odoo.addons.base.models.ir_ui_view"):
            self.env["ir.ui.view"].create({
                "name": "bad",
                "model": "res.partner",
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="create_date"
                                  date_stop="write_date">
                        <not_a_field/>
                    </gantt_studio>
                """,
            })

    def test_09_get_view_info_includes_icon(self):
        info = self.env["ir.ui.view"]._get_view_info()
        self.assertIn("gantt_studio", info)
        self.assertIn("icon", info["gantt_studio"])

    def test_10_view_works_on_multiple_models(self):
        # Smoke test final: el MISMO arch funciona sobre cualquier modelo.
        # Es la demostración técnica del modelo-agnosticismo.
        for model in ("res.partner", "res.users", "res.company"):
            self.env["ir.ui.view"].create({
                "name": f"GS test on {model}",
                "model": model,
                "type": "gantt_studio",
                "arch": """
                    <gantt_studio date_start="create_date" date_stop="write_date">
                        <field name="display_name"/>
                    </gantt_studio>
                """,
            })
