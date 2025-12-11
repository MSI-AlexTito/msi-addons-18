# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)

class CertificationBookLine(models.Model):
    """
    Línea de detalle en un Libro de Compra/Venta.
    Puede referenciar un DTE generado (ventas) o contener datos manuales (compras).
    """
    _name = 'l10n_cl_edi.certification.book.line'
    _description = 'Línea de Libro de Compra/Venta'
    _order = 'book_id, sequence, id'

    # Relaciones
    book_id = fields.Many2one(
        'l10n_cl_edi.certification.book',
        string='Libro',
        required=True,
        ondelete='cascade',
        index=True
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    # OPCIÓN A: Referencia a DTE generado (para LIBRO DE VENTAS)
    generated_document_id = fields.Many2one(
        'l10n_cl_edi.certification.generated.document',
        string='Documento Generado',
        help='Referencia al DTE emitido (para libro de ventas)'
    )

    # OPCIÓN B: Datos manuales (para LIBRO DE COMPRAS)
    # Tipo de documento
    document_type_code = fields.Char(
        string='Tipo Doc',
        help='Código de tipo de documento (30=Factura, 33=Factura Elect., 46=FC Electr., 60/61=NC)'
    )
    document_type_name = fields.Char(
        string='Tipo Documento',
        compute='_compute_document_type_name',
        store=True
    )

    folio = fields.Integer(
        string='Folio'
    )

    issue_date = fields.Date(
        string='Fecha Emisión'
    )

    # Proveedor/Cliente (según tipo de libro)
    partner_rut = fields.Char(
        string='RUT',
        help='RUT del proveedor (compras) o cliente (ventas)'
    )
    partner_name = fields.Char(
        string='Razón Social'
    )

    # Observaciones y notas
    observations = fields.Text(
        string='Observaciones',
        help='Ej: "FACTURA DEL GIRO CON DERECHO A CREDITO", "COMPRA CON RETENCION TOTAL DEL IVA"'
    )

    # Montos básicos
    mnt_exento = fields.Float(
        string='Monto Exento',
        digits=(16, 0),
        help='Monto exento de IVA'
    )
    mnt_neto = fields.Float(
        string='Monto Neto',
        digits=(16, 0),
        help='Monto neto afecto a IVA'
    )
    mnt_iva = fields.Float(
        string='IVA',
        digits=(16, 0),
        help='Monto del IVA (19%)'
    )
    mnt_total = fields.Float(
        string='Monto Total',
        digits=(16, 0),
        help='Monto total del documento'
    )

    # Campos especiales para LIBRO DE COMPRAS
    iva_uso_comun = fields.Float(
        string='IVA Uso Común',
        digits=(16, 0),
        help='IVA de facturas con uso común (factor de proporcionalidad)'
    )
    iva_no_recuperable = fields.Float(
        string='IVA No Recuperable',
        digits=(16, 0),
        help='IVA no recuperable (Código 4: entrega gratuita)'
    )
    cod_iva_no_rec = fields.Char(
        string='Código IVA No Rec',
        help='Código de IVA no recuperable (ej: 4)'
    )
    iva_ret_total = fields.Float(
        string='IVA Retenido Total',
        digits=(16, 0),
        help='IVA retenido totalmente (Factura de Compra Electrónica)'
    )
    iva_ret_parcial = fields.Float(
        string='IVA Retenido Parcial',
        digits=(16, 0),
        help='IVA retenido parcialmente'
    )
    factor_proporcionalidad = fields.Float(
        string='Factor Proporcionalidad',
        digits=(2, 2),
        help='Factor de proporcionalidad para IVA uso común (ej: 0.60)'
    )
    credito_iva_uso_comun = fields.Float(
        string='Crédito IVA Uso Común',
        digits=(16, 0),
        compute='_compute_credito_iva_uso_comun',
        store=True,
        help='IVA Uso Común × Factor de Proporcionalidad'
    )

    # Tipo de IVA (para uso común)
    tipo_imp = fields.Selection([
        ('1', 'IVA Uso Común'),
        ('2', 'IVA Sin Derecho a Crédito'),
    ], string='Tipo Impuesto')

    # Referencias (para NC/ND en libro de compras)
    ref_doc_type = fields.Char(
        string='Tipo Doc Ref',
        help='Tipo de documento referenciado (para NC/ND)'
    )
    ref_folio = fields.Integer(
        string='Folio Ref',
        help='Folio del documento referenciado (para NC/ND)'
    )

    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)


    # Campos calculados desde generated_document_id (para libro de ventas)
    @api.depends('document_type_code')
    def _compute_document_type_name(self):
        """Traduce el código de documento a nombre legible"""
        doc_types = {
            '30': 'Factura',
            '33': 'Factura Electrónica',
            '34': 'Factura Exenta Electrónica',
            '39': 'Boleta Electrónica',
            '41': 'Boleta Exenta Electrónica',
            '46': 'Factura de Compra Electrónica',
            '52': 'Guía de Despacho Electrónica',
            '56': 'Nota de Débito Electrónica',
            '60': 'Nota de Crédito',
            '61': 'Nota de Crédito Electrónica',
        }
        for line in self:
            line.document_type_name = doc_types.get(line.document_type_code, line.document_type_code or '')

    @api.depends('iva_uso_comun', 'factor_proporcionalidad')
    def _compute_credito_iva_uso_comun(self):
        """Calcula el crédito de IVA uso común"""
        for line in self:
            if line.iva_uso_comun and line.factor_proporcionalidad:
                line.credito_iva_uso_comun = int(round(line.iva_uso_comun * line.factor_proporcionalidad))
            else:
                line.credito_iva_uso_comun = 0

    @api.onchange('generated_document_id')
    def _onchange_generated_document_id(self):
        """Rellena automáticamente campos desde el documento generado"""
        if self.generated_document_id:
            doc = self.generated_document_id
            self.document_type_code = doc.document_type_code
            self.folio = doc.folio
            self.issue_date = doc.issue_date
            self.partner_rut = doc.receiver_rut
            self.partner_name = doc.receiver_name
            self.mnt_exento = doc.subtotal_exempt
            self.mnt_neto = doc.subtotal_taxable
            self.mnt_iva = doc.tax_amount
            self.mnt_total = doc.total_amount

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, si tiene generated_document_id, auto-rellenar campos"""
        for vals in vals_list:
            if vals.get('generated_document_id') and not vals.get('document_type_code'):
                doc = self.env['l10n_cl_edi.certification.generated.document'].browse(vals['generated_document_id'])
                vals.update({
                    'document_type_code': doc.document_type_code,
                    'folio': doc.folio,
                    'issue_date': doc.issue_date,
                    'partner_rut': doc.receiver_rut,
                    'partner_name': doc.receiver_name,
                    'mnt_exento': doc.subtotal_exempt,
                    'mnt_neto': doc.subtotal_taxable,
                    'mnt_iva': doc.tax_amount,
                    'mnt_total': doc.total_amount,
                })
        return super().create(vals_list)
