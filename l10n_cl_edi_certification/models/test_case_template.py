# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TestCaseTemplate(models.Model):
    """
    Catálogo de Casos de Prueba Estándar para Certificación SII.
    Basado en los 50+ casos de prueba de LibreDTE.
    """
    _name = 'l10n_cl_edi.test.case.template'
    _description = 'Plantilla de Caso de Prueba para Certificación SII'
    _order = 'document_type_id, code'
    _rec_name = 'complete_name'

    # Identificación
    code = fields.Char(
        string='Código',
        required=True,
        help='Código único del caso (ej: 033-001, 034-002)'
    )
    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo del caso de prueba'
    )
    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )

    # Tipo de Documento
    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de Documento',
        required=True,
        domain=[('country_id.code', '=', 'CL'), ('internal_type', '=', 'invoice')],
        help='Tipo de DTE a generar (33, 34, 56, 61, etc.)'
    )
    document_type_code = fields.Char(
        related='document_type_id.code',
        string='Código Documento',
        store=True
    )

    # Descripción y Categoría
    description = fields.Text(
        string='Descripción',
        help='Descripción detallada de lo que prueba este caso'
    )
    category = fields.Selection([
        ('standard', 'Estándar'),
        ('custom', 'Personalizado'),
    ], string='Categoría', default='standard', required=True)

    # Referencias (para notas de crédito/débito)
    reference = fields.Char(
        string='Referencia',
        help='Código de referencia (ej: CASO 01-01)'
    )
    reference_reason = fields.Char(
        string='Razón de Referencia',
        help='Motivo de la referencia para NC/ND'
    )

    # Descuento Global
    global_discount = fields.Float(
        string='Descuento Global %',
        digits=(5, 2),
        help='Porcentaje de descuento global aplicable'
    )

    # Líneas del Caso
    line_ids = fields.One2many(
        'l10n_cl_edi.test.case.template.line',
        'template_id',
        string='Líneas de Detalle'
    )

    # Estado
    active = fields.Boolean(
        string='Activo',
        default=True
    )

    # Metadatos
    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre el caso de prueba'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El código del caso de prueba debe ser único.'),
    ]

    @api.depends('code', 'name')
    def _compute_complete_name(self):
        for record in self:
            record.complete_name = f"[{record.code}] {record.name}"

    @api.constrains('global_discount')
    def _check_global_discount(self):
        for record in self:
            if record.global_discount < 0 or record.global_discount > 100:
                raise ValidationError(_('El descuento global debe estar entre 0 y 100%.'))

    def action_duplicate_to_custom(self):
        """Duplica un caso estándar para personalizarlo"""
        self.ensure_one()
        new_code = f"{self.code}-CUSTOM"
        return self.copy({
            'code': new_code,
            'name': f"{self.name} (Personalizado)",
            'category': 'custom',
        })


class TestCaseTemplateLine(models.Model):
    """
    Línea de detalle de un caso de prueba.
    """
    _name = 'l10n_cl_edi.test.case.template.line'
    _description = 'Línea de Plantilla de Caso de Prueba'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'l10n_cl_edi.test.case.template',
        string='Plantilla',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de la línea en el documento'
    )
    description = fields.Char(
        string='Descripción',
        required=True,
        help='Descripción del producto o servicio'
    )
    qty = fields.Float(
        string='Cantidad',
        digits='Product Unit of Measure',
        default=1.0,
        required=True
    )
    price_unit = fields.Float(
        string='Precio Unitario',
        digits='Product Price',
        required=True
    )
    discount = fields.Float(
        string='Descuento %',
        digits=(5, 2),
        default=0.0,
        help='Porcentaje de descuento para esta línea'
    )
    exempt = fields.Boolean(
        string='Exento',
        default=False,
        help='Si está marcado, esta línea está exenta de IVA'
    )

    # Campos computados
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_amounts',
        digits='Product Price',
        store=True
    )

    @api.depends('qty', 'price_unit', 'discount')
    def _compute_amounts(self):
        for line in self:
            subtotal = line.qty * line.price_unit
            if line.discount:
                subtotal = subtotal * (1 - line.discount / 100.0)
            line.subtotal = subtotal

    @api.constrains('qty', 'price_unit')
    def _check_positive_values(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a 0.'))
            if line.price_unit < 0:
                raise ValidationError(_('El precio unitario no puede ser negativo.'))

    @api.constrains('discount')
    def _check_discount(self):
        for line in self:
            if line.discount < 0 or line.discount > 100:
                raise ValidationError(_('El descuento debe estar entre 0 y 100%.'))
