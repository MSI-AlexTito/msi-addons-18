# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CertificationCaseLine(models.Model):
    """
    Línea de detalle de un caso de prueba.
    """
    _name = 'l10n_cl_edi.certification.case.line'
    _description = 'Línea de Caso de Prueba de Certificación'
    _order = 'case_id, sequence, id'

    case_id = fields.Many2one(
        'l10n_cl_edi.certification.case',
        string='Caso',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10
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
        default=0.0
    )
    exempt = fields.Boolean(
        string='Exento',
        default=False,
        help='Si está marcado, esta línea está exenta de IVA'
    )

    # Campos Computados
    subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )

    currency_id = fields.Many2one(
        related='case_id.currency_id',
        string='Moneda',
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
