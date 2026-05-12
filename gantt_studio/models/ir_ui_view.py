from lxml import etree

from odoo import _, fields, models
from odoo.tools import format_list


GANTT_STUDIO_VALID_ATTRIBUTES = {
    "__validate__",          # ir.ui.view implementation detail
    "date_start",
    "date_stop",
    "default_scale",
    "default_group_by",
    "color_field",
    "bar_text",
    "progress",
    "form_view_id",
    "edit",
    "create",
    "delete",
    "string",
    "class",
    "js_class",
    "sample",
    # Tier 1 features ────────────────────────────────────────────────
    "show_dependencies",       # "true"/"false" — draw dep arrows
    "show_critical_path",      # "true"/"false" — enable CPM toggle
    "auto_reschedule",         # "true"/"false" — cascade drag through deps
    "baseline_support",        # "true"/"false" — Save/Activate baseline buttons
}

VALID_SCALES = {"day", "week", "month", "quarter", "year"}


class View(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("gantt_studio", "Gantt Studio")])

    def _validate_tag_gantt_studio(self, node, name_manager, node_info):
        """Validate the structure of a <gantt_studio> view declaration."""
        if not node_info["validate"]:
            return

        attrs = set(node.attrib)
        if "date_start" not in attrs:
            self._raise_view_error(
                _("gantt_studio must have a 'date_start' attribute"), node
            )
        if "date_stop" not in attrs:
            self._raise_view_error(
                _("gantt_studio must have a 'date_stop' attribute"), node
            )

        default_scale = node.get("default_scale")
        if default_scale and default_scale not in VALID_SCALES:
            self._raise_view_error(
                _("Invalid default_scale '%s' in gantt_studio", default_scale), node
            )

        # Children: only <field> allowed (templates support comes in a later sprint)
        for child in node.iterchildren(tag=etree.Element):
            if child.tag != "field":
                self._raise_view_error(
                    _("gantt_studio children must be <field>, got <%s>", child.tag),
                    child,
                )

        remaining = attrs - GANTT_STUDIO_VALID_ATTRIBUTES
        if remaining:
            # format_list espera una list, no un set
            self._raise_view_error(
                _(
                    "Invalid attributes (%(invalid_attributes)s) in gantt_studio. "
                    "Must be in (%(valid_attributes)s)",
                    invalid_attributes=format_list(self.env, sorted(remaining)),
                    valid_attributes=format_list(self.env, sorted(GANTT_STUDIO_VALID_ATTRIBUTES)),
                ),
                node,
            )

    def _get_view_fields(self, view_type, models):
        if view_type == "gantt_studio":
            models[self._name] = list(self._fields.keys())
            return models
        return super()._get_view_fields(view_type, models)

    def _get_view_info(self):
        return {"gantt_studio": {"icon": "fa fa-bars fa-rotate-270"}} | super()._get_view_info()
