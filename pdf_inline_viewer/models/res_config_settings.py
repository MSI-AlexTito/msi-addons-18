import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pdf_viewer_enabled = fields.Boolean(
        string="Enable PDF Inline Viewer",
        config_parameter="pdf_inline_viewer.enabled",
        default=True,
    )
    pdf_viewer_watermark = fields.Char(
        string="Watermark text",
        config_parameter="pdf_inline_viewer.watermark",
        help="Text overlaid on the preview. Leave empty to disable.",
    )
    pdf_viewer_watermark_group_id = fields.Many2one(
        "res.groups",
        string="Restrict watermark to group",
        config_parameter="pdf_inline_viewer.watermark_group_id",
        help="If set, only members of this group will see the watermark.",
    )
    pdf_viewer_show_thumbnails = fields.Boolean(
        string="Show thumbnails by default",
        config_parameter="pdf_inline_viewer.show_thumbnails",
        default=True,
    )

    @api.model
    def get_pdf_viewer_config(self):
        """Return viewer settings to the JS client."""
        ICP = self.env["ir.config_parameter"].sudo()
        enabled_raw = ICP.get_param("pdf_inline_viewer.enabled", "True")
        watermark = ICP.get_param("pdf_inline_viewer.watermark", "")
        group_id_raw = ICP.get_param("pdf_inline_viewer.watermark_group_id")
        thumbs_raw = ICP.get_param("pdf_inline_viewer.show_thumbnails", "True")
        show_watermark = bool(watermark)
        if show_watermark and group_id_raw:
            show_watermark = int(group_id_raw) in self.env.user.groups_id.ids
        result = {
            "enabled": enabled_raw == "True",
            "watermark": watermark if show_watermark else "",
            "show_thumbnails": thumbs_raw == "True",
        }
        _logger.debug(
            "get_pdf_viewer_config user=%s -> %s", self.env.user.login, result,
        )
        return result
