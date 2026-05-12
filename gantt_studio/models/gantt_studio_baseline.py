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
    # Sprint 3.7 — multi-baseline diff visual.
    # color index al estilo Odoo (0-11). Auto-asignado al activarse para
    # que múltiples baselines visibles tengan colores distintos.
    color = fields.Integer(
        string="Color",
        default=0,
        help="Color index used to differentiate ghost bars in multi-baseline mode.",
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
        with record_ids — used by the JS renderer to draw ghost bars.

        Legacy: devuelve UN solo baseline activo (el primero por
        create_date desc). Para multi-baseline usar `get_visible_baselines`.
        """
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

    # Sprint 3.7 — Multi-baseline ────────────────────────────────────

    @api.model
    def get_visible_baselines(self, res_model, record_ids):
        """Devuelve TODAS las baselines activas para `res_model` con sus
        líneas, para que el renderer dibuje N capas de ghost bars.

        Returns:
            [
                {
                    "baseline_id": int,
                    "baseline_name": str,
                    "color": int,
                    "lines": [{record_id, date_start, date_stop}, ...],
                },
                ...
            ]
        """
        if not record_ids:
            return []
        baselines = self.search([
            ("res_model", "=", res_model),
            ("is_active", "=", True),
        ])
        out = []
        for b in baselines:
            lines = self.env["gantt.studio.baseline.line"].search_read(
                [
                    ("baseline_id", "=", b.id),
                    ("record_id", "in", record_ids),
                ],
                ["record_id", "date_start", "date_stop"],
            )
            out.append({
                "baseline_id": b.id,
                "baseline_name": b.name,
                "color": b.color or 0,
                "lines": lines,
            })
        return out

    @api.model
    def list_baselines(self, res_model):
        """Lista resumen de baselines (visible o no) para el selector UI."""
        items = self.search_read(
            [("res_model", "=", res_model)],
            ["id", "name", "is_active", "color", "line_count", "create_date"],
        )
        return items

    def action_toggle_visible(self):
        """Toggle is_active sin desactivar a los demás (multi-baseline).
        Si se activa, asigna automáticamente un `color` si era 0 para
        que las capas se distingan visualmente.
        """
        self.ensure_one()
        if self.is_active:
            self.is_active = False
        else:
            # Asignar color distinto a los ya activos.
            used = set(self.search([
                ("res_model", "=", self.res_model),
                ("is_active", "=", True),
                ("id", "!=", self.id),
            ]).mapped("color"))
            for c in range(1, 12):  # color indexes 1-11 (0 = default/gris)
                if c not in used:
                    self.color = c
                    break
            self.is_active = True
        return True

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
