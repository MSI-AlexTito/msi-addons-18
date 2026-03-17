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
    simulation_id = fields.Many2one(
        'l10n_cl_edi.certification.simulation',
        string='Simulación',
        help='Simulación que generó este documento'
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
    receiver_giro = fields.Char(
        string='Giro Receptor'
    )
    receiver_address = fields.Char(
        string='Dirección Receptor'
    )
    receiver_comuna = fields.Char(
        string='Comuna Receptor'
    )

    # Montos (alternativa a los campos Monetary para compatibilidad SII)
    mnt_neto = fields.Integer(
        string='Monto Neto',
        help='Monto neto (afecto a IVA)'
    )
    mnt_exento = fields.Integer(
        string='Monto Exento',
        help='Monto exento de IVA'
    )
    iva_percent = fields.Integer(
        string='% IVA',
        default=19
    )
    mnt_iva = fields.Integer(
        string='Monto IVA',
        help='Monto del IVA'
    )
    mnt_total = fields.Integer(
        string='Monto Total',
        help='Monto total del documento'
    )

    # Detalle de líneas (JSON)
    detalle_json = fields.Text(
        string='Detalle JSON',
        help='Detalle de líneas del documento en formato JSON'
    )

    # Referencias (para NC y ND)
    reference_doc_type = fields.Char(
        string='Tipo Doc Referencia',
        help='Tipo de documento referenciado (ej: 33 para Factura)'
    )
    reference_folio = fields.Integer(
        string='Folio Referencia',
        help='Folio del documento referenciado'
    )
    reference_date = fields.Date(
        string='Fecha Referencia',
        help='Fecha del documento referenciado'
    )
    reference_code = fields.Char(
        string='Código Referencia',
        help='Código de referencia (1=Anula, 2=Corrige texto, 3=Corrige monto)'
    )
    reference_reason = fields.Char(
        string='Razón Referencia',
        help='Razón de la referencia'
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

    # PDF Impreso
    pdf_file = fields.Binary(
        string='PDF Tributario',
        attachment=True,
        help='PDF impreso del documento con timbre TED (Copia Tributaria)'
    )
    pdf_filename = fields.Char(
        string='Nombre PDF',
        compute='_compute_filenames',
        store=True
    )
    pdf_cedible_file = fields.Binary(
        string='PDF Cedible',
        attachment=True,
        help='PDF Copia Cedible (solo Factura Electrónica tipo 33)'
    )
    pdf_cedible_filename = fields.Char(
        string='Nombre PDF Cedible',
        compute='_compute_filenames',
        store=True
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
                doc.pdf_filename = f"{base_name}_tributaria.pdf"
                doc.pdf_cedible_filename = f"{base_name}_cedible.pdf"
            else:
                doc.xml_dte_filename = "DTE.xml"
                doc.xml_dte_signed_filename = "DTE_signed.xml"
                doc.pdf_filename = "DTE_tributaria.pdf"
                doc.pdf_cedible_filename = "DTE_cedible.pdf"

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
                doc.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_document_validated'),
                    subtype_xmlid='mail.mt_note'
                )
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
            doc.with_context(cert_subject=cert_subject).message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_document_signed'),
                subtype_xmlid='mail.mt_note'
            )

        return True

    def _populate_fields_from_xml(self):
        """
        Extrae montos y detalle del XML firmado y los guarda en los campos del documento.
        Necesario para documentos creados antes de que se almacenaran estos campos.
        """
        import re
        import json
        from lxml import etree

        for doc in self:
            xml_source = doc.xml_dte_signed or doc.xml_dte_file
            if not xml_source:
                continue

            try:
                xml_bytes = base64.b64decode(xml_source)
                xml_content = xml_bytes.decode('ISO-8859-1')

                # Quitar namespace para facilitar xpath
                xml_clean = re.sub(r' xmlns[^"]*"[^"]*"', '', xml_content)
                root = etree.fromstring(xml_clean.encode('ISO-8859-1'))

                vals = {}

                # Extraer Totales
                totales = root.find('.//Totales')
                if totales is not None:
                    def _int(tag):
                        n = totales.find(tag)
                        return int(n.text) if n is not None and n.text else 0

                    vals['mnt_neto'] = _int('MntNeto')
                    vals['mnt_exento'] = _int('MntExe')
                    vals['mnt_iva'] = _int('IVA')
                    vals['mnt_total'] = _int('MntTotal')

                # Extraer Detalle
                items = []
                for det in root.findall('.//Detalle'):
                    def _txt(tag):
                        n = det.find(tag)
                        return n.text.strip() if n is not None and n.text else ''

                    def _num(tag):
                        n = det.find(tag)
                        try:
                            return float(n.text) if n is not None and n.text else 0
                        except Exception:
                            return 0

                    items.append({
                        'nombre': _txt('NmbItem'),
                        'cantidad': _num('QtyItem') or 1,
                        'precio': _num('PrcItem'),
                        'total': _num('MontoItem'),
                    })

                if items:
                    vals['detalle_json'] = json.dumps(items, ensure_ascii=False)

                if vals:
                    doc.write(vals)

            except Exception as e:
                _logger.warning('No se pudo extraer datos del XML para doc %s: %s', doc.id, e)

    def action_generate_ted(self):
        """
        Genera el TED (Timbre Electrónico) extrayéndolo del XML firmado.

        El TED debe ser el que está embebido en el XML firmado — no se genera
        uno nuevo, ya que cualquier TED nuevo tendría un TSTED distinto y su
        firma FRMT no coincidiría con la del XML, lo que el SII rechaza.
        También repobla montos y detalle desde el XML si están vacíos.
        """
        import re

        for doc in self:
            if not doc.xml_dte_signed:
                raise UserError(_('Debe firmar el documento antes de generar el TED.'))

            # Repoblar detalle desde el XML si falta (documentos legacy)
            if not doc.detalle_json:
                doc._populate_fields_from_xml()

            # Extraer el TED directamente del XML firmado (fuente autoritativa).
            # El barcode debe contener exactamente el mismo TED que está en el XML.
            xml_content = base64.b64decode(doc.xml_dte_signed).decode('ISO-8859-1')

            ted_match = re.search(
                r'(<TED[^>]*>.*?</TED>)\s*<TmstFirma>(.*?)</TmstFirma>',
                xml_content,
                re.DOTALL,
            )
            if not ted_match:
                raise UserError(_(
                    'No se encontró el bloque <TED> en el XML firmado del documento %s.\n'
                    'El XML firmado no tiene un timbre electrónico embebido.'
                ) % doc.complete_name)

            ted_xml = ted_match.group(1) + '<TmstFirma>' + ted_match.group(2) + '</TmstFirma>'

            # Generar código de barras PDF417 del TED extraído
            pdf_service = self.env['l10n_cl_edi.pdf.generator.service']
            barcode_data = pdf_service.generate_ted_barcode(ted_xml)

            doc.write({
                'ted_xml': ted_xml,
                'barcode_image': base64.b64encode(barcode_data),
            })

            doc.message_post(body=_('TED generado exitosamente.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TED Generado'),
                'message': _('El Timbre Electrónico fue generado correctamente.'),
                'type': 'success',
            }
        }

    def _format_rut(self, rut):
        """Formatea un RUT chileno con puntos: 77626554-3 → 77.626.554-3"""
        if not rut:
            return ''
        rut = rut.replace('.', '').strip()
        if '-' not in rut:
            return rut
        digits, dv = rut.rsplit('-', 1)
        formatted = ''
        for i, c in enumerate(reversed(digits)):
            if i > 0 and i % 3 == 0:
                formatted = '.' + formatted
            formatted = c + formatted
        return formatted + '-' + dv.upper()

    def _get_detalle_items(self):
        """Retorna la lista de items del detalle para el template QWeb."""
        import json
        if not self.detalle_json:
            return []
        try:
            items = json.loads(self.detalle_json) if isinstance(self.detalle_json, str) else self.detalle_json
            return items if isinstance(items, list) else []
        except Exception:
            return []

    def action_generate_pdf(self):
        """
        Genera el PDF impreso del documento.
        Si faltan datos (detalle, montos, TED), los genera automáticamente
        a partir del XML firmado antes de crear el PDF.
        """
        self.ensure_one()

        if not self.xml_dte_signed:
            raise UserError(_('Debe firmar el documento antes de generar el PDF.'))

        # Paso 1: Poblar montos y detalle desde el XML si faltan
        if not self.detalle_json:
            self._populate_fields_from_xml()

        # Paso 2: Generar/regenerar TED desde el XML firmado
        self.action_generate_ted()

        # Paso 3: Generar PDF Tributario usando el reporte QWeb
        pdf_content, _mime = self.env['ir.actions.report'].with_context(
            dte_copy_type='tributaria'
        )._render_qweb_pdf(
            'l10n_cl_edi_certification.certification_dte_document',
            [self.id]
        )

        vals = {'pdf_file': base64.b64encode(pdf_content)}

        # Paso 4: Para Factura Electrónica tipo 33, generar también Copia Cedible
        if self.document_type_code == '33':
            cedible_content, _mime = self.env['ir.actions.report'].with_context(
                dte_copy_type='cedible'
            )._render_qweb_pdf(
                'l10n_cl_edi_certification.certification_dte_document',
                [self.id]
            )
            vals['pdf_cedible_file'] = base64.b64encode(cedible_content)

        self.write(vals)

        msg = _('PDF impreso generado exitosamente.')
        if self.document_type_code == '33':
            msg = _('PDF Tributario y Copia Cedible generados exitosamente.')
        self.message_post(body=msg)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('PDF Generado'),
                'message': _('El PDF impreso fue generado correctamente.'),
                'type': 'success',
            }
        }

    def action_download_pdf(self):
        """Descarga el PDF impreso"""
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(_('No hay PDF generado para descargar.'))

        # Buscar el attachment del PDF
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'pdf_file'),
        ], limit=1)

        if not attachment:
            raise UserError(_('No se encontró el archivo PDF.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_download_pdf_cedible(self):
        """Descarga la Copia Cedible (solo Factura tipo 33)"""
        self.ensure_one()
        if not self.pdf_cedible_file:
            raise UserError(_('No hay Copia Cedible generada. Solo disponible para Factura Electrónica (tipo 33).'))

        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'pdf_cedible_file'),
        ], limit=1)

        if not attachment:
            raise UserError(_('No se encontró el archivo PDF Cedible.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_download_xml(self):
        """Descarga el XML firmado"""
        self.ensure_one()
        if not self.xml_dte_signed:
            raise UserError(_('No hay XML firmado para descargar.'))

        # Buscar el attachment del XML firmado
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'xml_dte_signed'),
        ], limit=1)

        if not attachment:
            raise UserError(_('No se encontró el archivo XML firmado.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
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
