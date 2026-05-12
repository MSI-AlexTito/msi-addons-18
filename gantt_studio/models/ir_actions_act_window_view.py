from odoo import fields, models


class ActWindowView(models.Model):
    """Allow the new 'gantt_studio' view type to be picked from the
    dropdown when configuring an action's views in debug/Studio mode."""

    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(
        selection_add=[("gantt_studio", "Gantt Studio")],
        ondelete={"gantt_studio": "cascade"},
    )
