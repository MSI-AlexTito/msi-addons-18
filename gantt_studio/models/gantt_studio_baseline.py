from odoo import _, api, fields, models


class GanttStudioBaseline(models.Model):
    """A frozen snapshot of a plan at a given time, for plan-vs-actual comparison."""

    _name = "gantt.studio.baseline"
    _description = "Gantt Studio Baseline"
    _order = "create_date desc"

    name = fields.Char(required=True, default=lambda self: self._default_name())
    res_model = fields.Char(string="Model", required=True, index=True)
    line_ids = fields.One2many(
        "gantt.studio.baseline.line", "baseline_id", string="Snapshot lines"
    )
    line_count = fields.Integer(compute="_compute_line_count", string="Records")
    is_active = fields.Boolean(
        default=False,
        help="The active baseline is the one shown as ghost bars in the Gantt.",
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for b in self:
            b.line_count = len(b.line_ids)

    def _default_name(self):
        return _("Baseline %s") % fields.Datetime.now().strftime("%Y-%m-%d %H:%M")

    # ----------------------------------------------------------------------
    # RPC API
    # ----------------------------------------------------------------------

    @api.model
    def snapshot(self, res_model, record_ids, date_start_field, date_stop_field, name=None):
        """Create a new baseline with a snapshot of the given records."""
        if not record_ids:
            return False
        records = self.env[res_model].browse(record_ids)
        baseline = self.create({
            "res_model": res_model,
            "name": name or self._default_name(),
        })
        line_vals = []
        for r in records:
            line_vals.append({
                "baseline_id": baseline.id,
                "record_id": r.id,
                "date_start": r[date_start_field] or False,
                "date_stop": r[date_stop_field] or False,
            })
        if line_vals:
            self.env["gantt.studio.baseline.line"].create(line_vals)
        return baseline.id

    @api.model
    def get_active_lines(self, res_model, record_ids):
        """Return lines from the active baseline of res_model intersected
        with record_ids — used by the JS renderer to draw ghost bars."""
        active = self.search([
            ("res_model", "=", res_model),
            ("is_active", "=", True),
        ], limit=1)
        if not active:
            return {"baseline_id": False, "lines": []}
        lines = self.env["gantt.studio.baseline.line"].search_read(
            [
                ("baseline_id", "=", active.id),
                ("record_id", "in", record_ids),
            ],
            ["record_id", "date_start", "date_stop"],
        )
        return {"baseline_id": active.id, "baseline_name": active.name, "lines": lines}

    def action_activate(self):
        """Make this baseline the active one for its res_model (only one active per model)."""
        self.ensure_one()
        self.search([
            ("res_model", "=", self.res_model),
            ("is_active", "=", True),
            ("id", "!=", self.id),
        ]).write({"is_active": False})
        self.is_active = True
        return True

    def action_deactivate(self):
        self.write({"is_active": False})
        return True


class GanttStudioBaselineLine(models.Model):
    _name = "gantt.studio.baseline.line"
    _description = "Gantt Studio Baseline Line"

    baseline_id = fields.Many2one(
        "gantt.studio.baseline", required=True, ondelete="cascade", index=True
    )
    record_id = fields.Integer(string="Record ID", required=True, index=True)
    date_start = fields.Datetime()
    date_stop = fields.Datetime()
