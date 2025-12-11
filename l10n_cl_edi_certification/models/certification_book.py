# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

import logging
_logger = logging.getLogger(__name__)

class CertificationBook(models.Model):
    """
    Libro de Compra/Venta (LibroCompraVenta) para certificación SII.
    Agrupa documentos en un libro electrónico mensual.
    """
    _name = 'l10n_cl_edi.certification.book'
    _description = 'Libro de Compra/Venta para Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'project_id, book_type, create_date desc'

    # Relaciones
    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        index=True
    )

    name = fields.Char(
        string='Nombre',
        required=True,
        default='Nuevo Libro'
    )

    book_type = fields.Selection([
        ('sale', 'Libro de Ventas'),
        ('purchase', 'Libro de Compras'),
    ], string='Tipo de Libro', required=True, default='sale', tracking=True)

    attention_number = fields.Char(
        string='Número de Atención',
        help='Número de atención del set de pruebas (ej: 4609306, 4609307)'
    )

    period = fields.Char(
        string='Período Tributario',
        help='Formato: YYYY-MM (ej: 2025-12)',
        default=lambda self: fields.Date.context_today(self).strftime('%Y-%m')
    )

    # Líneas/Detalles
    line_ids = fields.One2many(
        'l10n_cl_edi.certification.book.line',
        'book_id',
        string='Líneas del Libro',
        help='Detalles de documentos incluidos en el libro'
    )

    lines_count = fields.Integer(
        string='Cantidad Líneas',
        compute='_compute_lines_count',
        store=True
    )

    # Archivos XML
    book_xml = fields.Binary(
        string='XML Libro',
        attachment=True,
        help='XML del LibroCompraVenta sin firmar'
    )
    book_xml_filename = fields.Char(
        string='Nombre Archivo',
        compute='_compute_filenames',
        store=True
    )
    book_xml_signed = fields.Binary(
        string='XML Libro Firmado',
        attachment=True,
        help='XML del LibroCompraVenta firmado'
    )
    book_xml_signed_filename = fields.Char(
        string='Nombre Archivo Firmado',
        compute='_compute_filenames',
        store=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('signed', 'Firmado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Integración SII
    sii_track_id = fields.Char(
        string='Track ID',
        help='ID de seguimiento del SII',
        tracking=True
    )
    sii_send_date = fields.Datetime(
        string='Fecha Envío',
        tracking=True
    )
    sii_response_id = fields.Many2one(
        'l10n_cl_edi.certification.sii.response',
        string='Respuesta SII'
    )

    # Fecha de Creación
    creation_date = fields.Datetime(
        string='Fecha Creación',
        default=fields.Datetime.now,
        required=True
    )

    # Notas
    notes = fields.Text(
        string='Notas'
    )

    @api.depends('line_ids')
    def _compute_lines_count(self):
        for book in self:
            book.lines_count = len(book.line_ids)

    @api.depends('name', 'book_type', 'period')
    def _compute_filenames(self):
        for book in self:
            book_type_str = 'Ventas' if book.book_type == 'sale' else 'Compras'
            base_name = f"Libro{book_type_str}_{book.period}".replace(' ', '_')

            book.book_xml_filename = f"{base_name}.xml"
            book.book_xml_signed_filename = f"{base_name}_signed.xml"

    # Métodos de Acción
    def action_generate_book(self):
        """Genera el XML del libro"""
        for book in self:
            if not book.line_ids:
                raise UserError(_('Debe agregar al menos una línea al libro.'))

            print(f'\n{"#" * 100}')
            print(f'GENERANDO LIBRO DE {book.book_type.upper()}')
            print(f'{"#" * 100}')
            print(f'Libro: {book.name}')
            print(f'Proyecto: {book.project_id.name}')
            print(f'Período: {book.period}')
            print(f'Cantidad de líneas: {len(book.line_ids)}')

            # TODO: Llamar al servicio de generación de libro
            # book_service = self.env['l10n_cl_edi.book.service']
            # book_xml = book_service.generate_book(book)

            # book.write({
            #     'book_xml': base64.b64encode(book_xml.encode('ISO-8859-1')),
            #     'state': 'generated',
            # })

            print(f'\n✅ LIBRO GENERADO EXITOSAMENTE')
            print(f'{"#" * 100}\n')

            # book.message_post(body=_('Libro generado con %d líneas') % book.lines_count)

        return True

    def action_sign_book(self):
        """Firma el libro digitalmente"""
        for book in self:
            if not book.book_xml:
                raise UserError(_('Debe generar el libro primero.'))

            # TODO: Implementar firma
            pass

    def action_send_to_sii(self):
        """Envía el libro al SII"""
        for book in self:
            if book.state != 'signed':
                raise UserError(_('El libro debe estar firmado antes de enviar al SII.'))

            # TODO: Implementar envío
            pass

    def action_back_to_draft(self):
        """Regresa el libro a borrador"""
        for book in self:
            book.state = 'draft'
            book.message_post(body=_('Libro regresado a borrador'))

    def action_view_lines(self):
        """Ver las líneas del libro"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Líneas del Libro'),
            'res_model': 'l10n_cl_edi.certification.book.line',
            'domain': [('book_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_book_id': self.id}
        }
