# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
_logger = logging.getLogger(__name__)

class CertificationGeneratedDocument(models.Model):
    """
    Documento DTE Generado para Certificación.
    Almacena el XML del DTE, firma, timbre y toda la información del documento.
    """
    _name = 'l10n_cl_edi.certification.generated.document'
    _description = 'Documento DTE Generado para Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'l10n_cl.edi.util']
    _order = 'project_id, create_date desc'
    _rec_name = 'complete_name'

    # Relaciones
    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        index=True
    )
    case_id = fields.Many2one(
        'l10n_cl_edi.certification.case',
        string='Caso de Prueba',
        help='Caso de prueba que generó este documento'
    )
    envelope_id = fields.Many2one(
        'l10n_cl_edi.certification.envelope',
        string='Sobre de Envío',
        help='Sobre en el que se incluyó este documento'
    )

    # Tipo y Folio
    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de Documento',
        required=True
    )
    document_type_code = fields.Char(
        related='document_type_id.code',
        string='Código',
        store=True
    )
    folio = fields.Integer(
        string='Folio',
        required=True,
        help='Número de folio asignado'
    )

    # Fechas
    issue_date = fields.Date(
        string='Fecha Emisión',
        default=fields.Date.context_today,
        required=True
    )
    emission_date = fields.Datetime(
        string='Fecha/Hora Emisión',
        default=fields.Datetime.now,
        required=True
    )

    # Receptor (desde client_info del proyecto)
    receiver_rut = fields.Char(
        string='RUT Receptor',
        help='RUT del receptor (usualmente SII para certificación: 60803000-K)'
    )
    receiver_name = fields.Char(
        string='Razón Social Receptor'
    )

    # Archivos XML
    xml_dte_file = fields.Binary(
        string='XML DTE',
        attachment=True,
        help='XML del DTE sin firmar'
    )
    xml_dte_filename = fields.Char(
        string='Nombre Archivo DTE',
        compute='_compute_filenames',
        store=True
    )
    xml_dte_signed = fields.Binary(
        string='XML DTE Firmado',
        attachment=True,
        help='XML del DTE firmado digitalmente'
    )
    xml_dte_signed_filename = fields.Char(
        string='Nombre Archivo Firmado',
        compute='_compute_filenames',
        store=True
    )

    # Timbre Electrónico (TED)
    ted_xml = fields.Text(
        string='TED XML',
        help='Timbre Electrónico del Documento en formato XML'
    )
    barcode_image = fields.Binary(
        string='Código de Barras',
        attachment=True,
        help='Imagen del código de barras PDF417'
    )

    # Montos
    subtotal_taxable = fields.Monetary(
        string='Subtotal Afecto',
        currency_field='currency_id'
    )
    subtotal_exempt = fields.Monetary(
        string='Subtotal Exento',
        currency_field='currency_id'
    )
    tax_amount = fields.Monetary(
        string='IVA',
        currency_field='currency_id'
    )
    total_amount = fields.Monetary(
        string='Total',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.ref('base.CLP').id
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('validated', 'Validado'),
        ('signed', 'Firmado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Validación
    validation_messages = fields.Text(
        string='Mensajes de Validación',
        help='Mensajes de validación (errores o advertencias)'
    )
    validation_date = fields.Datetime(
        string='Fecha Validación'
    )

    # SII
    sii_track_id = fields.Char(
        string='Track ID SII',
        help='ID de seguimiento en el SII'
    )
    sii_status = fields.Char(
        string='Estado SII',
        help='Estado reportado por el SII'
    )
    sii_response_date = fields.Datetime(
        string='Fecha Respuesta SII'
    )

    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )

    @api.depends('document_type_id.name', 'folio')
    def _compute_complete_name(self):
        for doc in self:
            if doc.document_type_id and doc.folio:
                doc.complete_name = f"{doc.document_type_id.name} #{doc.folio}"
            else:
                doc.complete_name = _('Nuevo Documento')

    @api.depends('document_type_code', 'folio')
    def _compute_filenames(self):
        for doc in self:
            if doc.document_type_code and doc.folio:
                base_name = f"DTE_{doc.document_type_code}_{doc.folio}"
                doc.xml_dte_filename = f"{base_name}.xml"
                doc.xml_dte_signed_filename = f"{base_name}_signed.xml"
            else:
                doc.xml_dte_filename = "DTE.xml"
                doc.xml_dte_signed_filename = "DTE_signed.xml"

    # Métodos de Acción
    def action_validate(self):
        """Valida el documento contra esquemas XSD y reglas de negocio"""
        for doc in self:
            if not doc.xml_dte_signed:
                raise UserError(_('Debe firmar el documento antes de validar.'))

            validator = self.env['l10n_cl_edi.validation.service']
            is_valid, messages = validator.validate_document(doc)

            doc.write({
                'validation_messages': '\n'.join(messages) if messages else _('Validación exitosa'),
                'validation_date': fields.Datetime.now(),
            })

            if is_valid:
                doc.state = 'validated'
                doc.message_post(body=_('Documento validado correctamente'))
            else:
                raise UserError(_('El documento tiene errores de validación:\n%s') % doc.validation_messages)

        return True

    def action_sign(self):
        """Firma el documento digitalmente usando el certificado del cliente"""
        for doc in self:
            if not doc.xml_dte_file:
                raise UserError(_('No hay XML para firmar.'))

            # Obtener certificado digital del cliente (del proyecto)
            client_info = doc.project_id.client_info_id
            if not client_info:
                raise UserError(_('El proyecto no tiene información del cliente configurada.'))

            # Obtener datos del certificado (archivo + contraseña)
            try:
                cert_data, cert_password = client_info.get_certificate_data()
            except Exception as e:
                raise UserError(_('Error al obtener certificado del cliente:\n%s') % str(e))

            # Decodificar el XML (ISO-8859-1 encoding requerido por SII)
            import html
            xml_content = base64.b64decode(doc.xml_dte_file).decode('ISO-8859-1')

            # Des-escapar entidades HTML si están presentes
            if '&lt;' in xml_content or '&#34;' in xml_content:
                xml_content = html.unescape(xml_content)

            print('\n' + '=' * 80)
            print('FIRMANDO DOCUMENTO')
            print(f'Documento ID: {doc.id}, Folio: {doc.folio}')
            print(f'Longitud XML original: {len(xml_content)} caracteres')

            # Verificar si el XML original contiene Detalle
            if '<Detalle>' in xml_content:
                detalle_count = xml_content.count('<Detalle>')
                print(f'✓ XML ORIGINAL contiene {detalle_count} elementos <Detalle>')
            else:
                print('❌ XML ORIGINAL NO contiene elementos <Detalle>')

            # Preparar ID del documento para la firma
            doc_id = f"DTE-{doc.document_type_code}-{doc.folio}"

            # Firmar el XML usando el servicio de firma
            signature_service = self.env['l10n_cl_edi.signature.service']
            signed_xml = signature_service.sign_xml(
                xml_content,
                cert_data,
                cert_password,
                doc.project_id.company_id,  # Company ID (cuarto parámetro)
                doc_id  # Reference URI (quinto parámetro opcional)
            )

            print(f'Longitud XML firmado: {len(signed_xml)} caracteres')

            # Verificar si el XML firmado contiene Detalle
            if '<Detalle>' in signed_xml:
                detalle_count = signed_xml.count('<Detalle>')
                print(f'✓ XML FIRMADO contiene {detalle_count} elementos <Detalle>')
            else:
                print('❌ XML FIRMADO NO contiene elementos <Detalle>')
                print('\nPrimeros 1500 caracteres del XML firmado:')
                print(signed_xml[:1500])

            print('=' * 80 + '\n')

            # Guardar XML firmado (ISO-8859-1 encoding requerido por SII)
            doc.write({
                'xml_dte_signed': base64.b64encode(signed_xml.encode('ISO-8859-1', 'replace')),
                'state': 'signed',
            })

            cert_subject = client_info.social_reason or 'Cliente'
            doc.message_post(body=_('Documento firmado digitalmente - Certificado de: %s') % cert_subject)

        return True

    def action_download_xml(self):
        """Descarga el XML firmado"""
        self.ensure_one()
        if not self.xml_dte_signed:
            raise UserError(_('No hay XML firmado para descargar.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.id}?field=xml_dte_signed&download=true&filename={self.xml_dte_signed_filename}',
            'target': 'self',
        }

    def action_view_case(self):
        """Ver el caso de prueba asociado"""
        self.ensure_one()
        if not self.case_id:
            raise UserError(_('Este documento no tiene caso asociado.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Caso de Prueba'),
            'res_model': 'l10n_cl_edi.certification.case',
            'res_id': self.case_id.id,
            'view_mode': 'form',
        }

    def action_view_envelope(self):
        """Ver el sobre de envío"""
        self.ensure_one()
        if not self.envelope_id:
            raise UserError(_('Este documento no ha sido agregado a un sobre.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sobre de Envío'),
            'res_model': 'l10n_cl_edi.certification.envelope',
            'res_id': self.envelope_id.id,
            'view_mode': 'form',
        }
