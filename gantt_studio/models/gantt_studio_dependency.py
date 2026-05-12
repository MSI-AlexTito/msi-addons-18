from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


DEPENDENCY_TYPES = [
    ("FS", "Finish-to-Start"),
    ("SS", "Start-to-Start"),
    ("FF", "Finish-to-Finish"),
    ("SF", "Start-to-Finish"),
]


class GanttStudioDependency(models.Model):
    """Polymorphic typed dependency between two records of the same model.

    The model is intentionally generic: it stores `res_model + predecessor_id
    + successor_id` so it can express dependencies on project.task,
    sale.order, mrp.production, or any other model that the user wants to
    plan in a Gantt Studio view.
    """

    _name = "gantt.studio.dependency"
    _description = "Gantt Studio Dependency"
    _order = "res_model, predecessor_id, successor_id"

    res_model = fields.Char(
        string="Model",
        required=True,
        index=True,
        help="Technical name of the model these records belong to (e.g. project.task).",
    )
    predecessor_id = fields.Integer(
        string="Predecessor ID",
        required=True,
        index=True,
        help="DB id of the predecessor record within res_model.",
    )
    successor_id = fields.Integer(
        string="Successor ID",
        required=True,
        index=True,
        help="DB id of the successor record within res_model.",
    )
    dep_type = fields.Selection(
        DEPENDENCY_TYPES,
        default="FS",
        required=True,
        string="Type",
    )
    lag_days = fields.Float(
        default=0.0,
        string="Lag (days)",
        help="Lag time in days. Can be negative (lead time).",
    )

    _sql_constraints = [
        (
            "unique_pair",
            "UNIQUE(res_model, predecessor_id, successor_id, dep_type)",
            "A dependency of this type already exists between these two records.",
        ),
    ]

    @api.constrains("predecessor_id", "successor_id")
    def _check_no_self_link(self):
        for d in self:
            if d.predecessor_id == d.successor_id:
                raise ValidationError(
                    _("A record cannot depend on itself.")
                )

    @api.constrains("res_model")
    def _check_model_exists(self):
        for d in self:
            if d.res_model not in self.env:
                raise ValidationError(
                    _("Unknown model: %s", d.res_model)
                )

    # ----------------------------------------------------------------------
    # RPC API — used by the gantt_studio JS Model layer
    # ----------------------------------------------------------------------

    @api.model
    def get_dependencies(self, res_model, record_ids):
        """Return all dependencies touching the given records as plain dicts."""
        if not record_ids:
            return []
        return self.search_read(
            [
                ("res_model", "=", res_model),
                "|",
                ("predecessor_id", "in", record_ids),
                ("successor_id", "in", record_ids),
            ],
            ["id", "predecessor_id", "successor_id", "dep_type", "lag_days"],
        )

    @api.model
    def link(self, res_model, predecessor_id, successor_id, dep_type="FS", lag_days=0.0):
        """Idempotent helper to create a dependency from JS or scripts."""
        existing = self.search(
            [
                ("res_model", "=", res_model),
                ("predecessor_id", "=", predecessor_id),
                ("successor_id", "=", successor_id),
                ("dep_type", "=", dep_type),
            ],
            limit=1,
        )
        if existing:
            existing.lag_days = lag_days
            return existing.id
        return self.create({
            "res_model": res_model,
            "predecessor_id": predecessor_id,
            "successor_id": successor_id,
            "dep_type": dep_type,
            "lag_days": lag_days,
        }).id

    @api.model
    def unlink_pair(self, res_model, predecessor_id, successor_id, dep_type=None):
        domain = [
            ("res_model", "=", res_model),
            ("predecessor_id", "=", predecessor_id),
            ("successor_id", "=", successor_id),
        ]
        if dep_type:
            domain.append(("dep_type", "=", dep_type))
        return self.search(domain).unlink()
