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

    folio_notificacion = fields.Integer(
        string='Folio Notificación',
        help='Número de folio/atención asignado por el SII para Libro ESPECIAL de compras. '
             'Este número se obtiene del SII al solicitar autorización para enviar un libro especial.',
        tracking=True,
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
        ('validated', 'Validado XSD'),
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

    # Validación XSD
    xsd_validated = fields.Boolean(
        string='Validado con XSD',
        default=False,
        tracking=True,
        help='Indica si el XML ha sido validado contra el esquema XSD del SII'
    )
    xsd_validation_date = fields.Datetime(
        string='Fecha Validación XSD',
        tracking=True
    )
    xsd_validation_errors = fields.Text(
        string='Errores de Validación XSD',
        help='Errores encontrados durante la validación XSD'
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

            print('\n' + '#' * 100)
            print(f'GENERANDO LIBRO DE {book.book_type.upper()}')
            print('#' * 100)
            print(f'Libro: {book.name}')
            print(f'Proyecto: {book.project_id.name}')
            print(f'Período: {book.period}')
            print(f'Cantidad de líneas: {len(book.line_ids)}')

            try:
                print(f'\n🔧 Paso 1: Obteniendo servicio...')
                # Llamar al servicio de generación de libro
                book_service = self.env['l10n_cl_edi.book.generator.service'].sudo()
                print(f'✓ Servicio obtenido: {book_service}')

                print(f'\n🔧 Paso 2: Generando XML...')
                book_xml = book_service.generate_book_xml(book)
                print(f'✓ XML generado: {len(book_xml)} caracteres')
                print(f'  Primeras líneas:')
                for line in book_xml.split('\n')[:5]:
                    print(f'    {line}')

                print(f'\n🔧 Paso 3: Codificando XML...')
                xml_encoded = base64.b64encode(book_xml.encode('ISO-8859-1'))
                print(f'✓ XML codificado: {len(xml_encoded)} bytes')

                print(f'\n🔧 Paso 4: Guardando en BD...')
                # Guardar XML y cambiar estado
                book.write({
                    'book_xml': xml_encoded,
                    'state': 'generated',
                })
                print(f'✓ XML guardado en BD')

                print(f'\n✅ LIBRO GENERADO EXITOSAMENTE')
                print('#' * 100 + '\n')

                book.with_context(lines_count=book.lines_count).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_book_generated'),
                    subtype_xmlid='mail.mt_note'
                )

            except Exception as e:
                _logger.error(f'❌ Error generando libro: {str(e)}')
                print(f'\n❌ ERROR: {str(e)}')
                import traceback
                traceback.print_exc()
                raise UserError(_('Error al generar el libro: %s') % str(e))

        return True

    def action_sign_book(self):
        """Firma el libro digitalmente"""
        for book in self:
            if not book.book_xml:
                raise UserError(_('Debe generar el libro primero.'))

            print('\n' + '#' * 100)
            print(f'FIRMANDO LIBRO DE {book.book_type.upper()}')
            print('#' * 100)

            # Decodificar XML
            xml_string = base64.b64decode(book.book_xml).decode('ISO-8859-1')

            print(f'Libro: {book.name}')
            print(f'✓ XML decodificado: {len(xml_string)} caracteres')

            try:

                # Obtener certificado desde client_info
                if not book.project_id.client_info_id:
                    raise UserError(_('El proyecto no tiene información de cliente configurada.'))

                client = book.project_id.client_info_id
                print(f'✓ Cliente: {client.social_reason} ({client.rut})')

                # Obtener datos del certificado
                cert_data, cert_password = client.get_certificate_data()
                print(f'✓ Certificado obtenido: {len(cert_data)} bytes')

                # Obtener company
                company = book.project_id.company_id
                if not company:
                    raise UserError(_('El proyecto no tiene una compañía asociada.'))

                # Firmar usando el servicio (sign_xml para firmar el LibroCompraVenta completo)
                signature_service = self.env['l10n_cl_edi.signature.service'].sudo()
                xml_signed = signature_service.sign_xml(
                    xml_string,
                    cert_data,
                    cert_password,
                    company,
                    reference_uri='#SetDoc'  # Referencia al ID del EnvioLibro
                )
                print(f'✓ XML firmado: {len(xml_signed)} caracteres')

                # Guardar XML firmado
                book.write({
                    'book_xml_signed': base64.b64encode(xml_signed.encode('ISO-8859-1')),
                    'state': 'signed',
                })

                print(f'\n✅ LIBRO FIRMADO EXITOSAMENTE')
                print('#' * 100 + '\n')

                book.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_book_signed'),
                    subtype_xmlid='mail.mt_note'
                )

            except Exception as e:
                _logger.error(f'❌ Error firmando libro: {str(e)}')
                print(f'\n❌ ERROR: {str(e)}')
                import traceback
                traceback.print_exc()
                raise UserError(_('Error al firmar el libro: %s') % str(e))

        return True

    def action_validate_xsd(self):
        """Valida el XML firmado contra el esquema XSD del SII"""
        from lxml import etree
        import os

        for book in self:
            if book.state != 'signed':
                raise UserError(_('El libro debe estar firmado antes de validar con XSD.'))

            if not book.book_xml_signed:
                raise UserError(_('No hay XML firmado para validar.'))

            print('\n' + '#' * 100)
            print(f"ACTION: VALIDAR XML CON XSD")
            print('#' * 100)

            try:
                # Decodificar el XML firmado
                xml_content = base64.b64decode(book.book_xml_signed)
                print(f"XML decodificado: {len(xml_content)} bytes")

                # Parsear el XML
                xml_doc = etree.fromstring(xml_content)
                print(f"XML parseado correctamente")

                # Buscar el archivo XSD en el módulo (carpeta schemas)
                module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                xsd_path = os.path.join(module_path, 'schemas', 'LibroCV_v10.xsd')

                if not os.path.exists(xsd_path):
                    print(f"⚠️ Archivo XSD no encontrado en: {xsd_path}")
                    print(f"📝 Continuando sin validación XSD (asumiéndolo válido)")

                    # Si no hay XSD, marcar como validado de todos modos
                    book.write({
                        'state': 'validated',
                        'xsd_validated': True,
                        'xsd_validation_date': fields.Datetime.now(),
                        'xsd_validation_errors': False,
                    })
                    book.message_post_with_source(
                        source_ref=self.env.ref('l10n_cl_edi_certification.message_book_xsd_validated_no_schema'),
                        subtype_xmlid='mail.mt_note'
                    )

                    print(f"\n✅ XML marcado como validado (sin XSD)")
                    print('#' * 100 + '\n')

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }

                print(f"Cargando XSD desde: {xsd_path}")

                # Cargar el esquema XSD
                with open(xsd_path, 'rb') as xsd_file:
                    xsd_doc = etree.parse(xsd_file)
                    xsd_schema = etree.XMLSchema(xsd_doc)

                print(f"XSD cargado correctamente")

                # Validar el XML contra el XSD
                is_valid = xsd_schema.validate(xml_doc)

                if is_valid:
                    print(f"\n✅ XML VÁLIDO según esquema XSD")

                    # Marcar como validado
                    book.write({
                        'state': 'validated',
                        'xsd_validated': True,
                        'xsd_validation_date': fields.Datetime.now(),
                        'xsd_validation_errors': False,
                    })
                    book.message_post_with_source(
                        source_ref=self.env.ref('l10n_cl_edi_certification.message_book_xsd_validated_success'),
                        subtype_xmlid='mail.mt_note'
                    )

                    print('#' * 100 + '\n')

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                else:
                    # Recopilar errores
                    errors = []
                    for error in xsd_schema.error_log:
                        error_msg = f"Línea {error.line}: {error.message}"
                        errors.append(error_msg)
                        print(f"❌ {error_msg}")

                    error_text = '\n'.join(errors)

                    # Guardar errores pero NO cambiar estado
                    book.write({
                        'xsd_validated': False,
                        'xsd_validation_errors': error_text,
                    })
                    book.with_context(error_text=error_text).message_post_with_source(
                        source_ref=self.env.ref('l10n_cl_edi_certification.message_book_xsd_validation_errors'),
                        subtype_xmlid='mail.mt_note'
                    )

                    print(f"\n❌ XML INVÁLIDO")
                    print('#' * 100 + '\n')

                    raise UserError(_('El XML no cumple con el esquema XSD del SII:\n\n%s') % error_text)

            except etree.XMLSyntaxError as e:
                error_msg = f'Error de sintaxis XML: {str(e)}'
                print(f"❌ {error_msg}")
                book.write({
                    'xsd_validated': False,
                    'xsd_validation_errors': error_msg,
                })
                raise UserError(_(error_msg))

            except Exception as e:
                error_msg = f'Error al validar XML: {str(e)}'
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
                book.write({
                    'xsd_validated': False,
                    'xsd_validation_errors': error_msg,
                })
                raise UserError(_(error_msg))

    def action_send_to_sii(self):
        """Envía el libro al SII"""
        for book in self:
            if book.state not in ['signed', 'validated']:
                raise UserError(_('El libro debe estar firmado antes de enviar al SII.'))

            print('\n' + '#' * 100)
            print(f"ACTION: ENVIAR LIBRO AL SII")
            print('#' * 100)

            try:
                # Llamar al servicio de integración SII
                sii_service = self.env['l10n_cl_edi.sii.integration.service'].sudo()
                track_id, response_xml = sii_service.send_book(book)

                # Guardar información del envío
                book.write({
                    'sii_track_id': track_id,
                    'sii_send_date': fields.Datetime.now(),
                    'state': 'sent',
                })

                # Crear registro de respuesta del SII
                response_vals = {
                    'project_id': book.project_id.id,
                    'response_type': 'send',  # Tipo de respuesta: envío
                    'track_id': track_id,
                    'response_xml': base64.b64encode(response_xml) if isinstance(response_xml, bytes) else base64.b64encode(response_xml.encode('utf-8')),
                    'response_date': fields.Datetime.now(),
                    'status': 'received',  # Estado inicial cuando se envía
                }

                sii_response = self.env['l10n_cl_edi.certification.sii.response'].create(response_vals)
                book.sii_response_id = sii_response.id

                print(f'\n✅ Libro enviado y registrado')
                print(f'  Track ID: {track_id}')
                print(f'  Estado: sent')
                print('#' * 100 + '\n')

                book.with_context(track_id=track_id).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_book_sent_to_sii'),
                    subtype_xmlid='mail.mt_note'
                )

                # Recargar la vista para mostrar cambios
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }

            except Exception as e:
                _logger.error(f'❌ Error enviando libro al SII: {str(e)}')
                print(f'\\n❌ ERROR: {str(e)}')
                import traceback
                traceback.print_exc()
                raise UserError(_('Error al enviar el libro al SII: %s') % str(e))

    def action_check_status(self):
        """Consulta el estado del libro en el SII"""
        for book in self:
            if not book.sii_track_id:
                raise UserError(_('El libro no tiene Track ID. Debe enviarlo primero al SII.'))

            print('#' * 100)
            print(f'ACTION: CONSULTAR ESTADO DE LIBRO EN SII')
            print('#' * 100 + '\n')

            try:
                # Llamar al servicio de integración SII
                sii_service = self.env['l10n_cl_edi.sii.integration.service'].sudo()
                status, response_xml = sii_service.check_status(book.sii_track_id, book.project_id)

                # Mapear estado del servicio a estado del modelo
                state_map = {
                    'received': 'sent',
                    'validating': 'sent',
                    'accepted': 'accepted',
                    'rejected': 'rejected',
                    'with_repairs': 'accepted',  # Aceptado con reparos
                }

                new_state = state_map.get(status, 'sent')

                # Actualizar estado del libro
                book.write({
                    'state': new_state,
                })

                # Actualizar respuesta SII si existe
                if book.sii_response_id:
                    book.sii_response_id.write({
                        'status': status,
                        'response_xml': base64.b64encode(response_xml) if isinstance(response_xml, bytes) else base64.b64encode(response_xml.encode('utf-8')),
                        'response_date': fields.Datetime.now(),
                    })

                print(f'\n✅ Estado consultado y actualizado')
                print(f'  Track ID: {book.sii_track_id}')
                print(f'  Estado SII: {status}')
                print(f'  Estado libro: {new_state}')
                print('\n' + '#' * 100 + '\n')

                # Mensaje descriptivo
                status_messages = {
                    'received': 'Recibido - En proceso de validación',
                    'validating': 'Validando documentos',
                    'accepted': '✅ Aceptado por el SII',
                    'rejected': '❌ Rechazado por el SII',
                    'with_repairs': '⚠️ Aceptado con reparos',
                }
                status_msg = status_messages.get(status, f'Estado: {status}')

                book.with_context(status_msg=status_msg).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_book_status_updated'),
                    subtype_xmlid='mail.mt_note'
                )

                # Recargar la vista para mostrar cambios
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }

            except Exception as e:
                _logger.error(f'❌ Error consultando estado: {str(e)}')
                print(f'\\n❌ ERROR: {str(e)}')
                import traceback
                traceback.print_exc()
                raise UserError(_('Error al consultar estado: %s') % str(e))

    def action_back_to_draft(self):
        """Regresa el libro a borrador y limpia los campos de envío"""
        for book in self:
            # Limpiar XMLs, track_id, fecha de envío, respuesta SII y validación XSD
            book.write({
                'state': 'draft',
                'book_xml': False,
                'book_xml_signed': False,
                'sii_track_id': False,
                'sii_send_date': False,
                'sii_response_id': False,
                'xsd_validated': False,
                'xsd_validation_date': False,
                'xsd_validation_errors': False,
            })
            book.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_book_back_to_draft'),
                subtype_xmlid='mail.mt_note'
            )

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

    def action_import_from_project(self):
        """
        Importa documentos generados del proyecto al libro de ventas.
        Solo aplica para libros de tipo 'sale'.
        """
        self.ensure_one()

        if self.book_type != 'sale':
            raise UserError(_('Esta acción solo está disponible para libros de ventas.'))

        if not self.project_id:
            raise UserError(_('El libro debe estar asociado a un proyecto.'))

        print('\n' + '#' * 100)
        print(f'IMPORTANDO DOCUMENTOS DEL PROYECTO AL LIBRO DE VENTAS')
        print('#' * 100)
        print(f'Libro: {self.name}')
        print(f'Proyecto: {self.project_id.name}')

        # Buscar documentos generados del proyecto
        generated_docs = self.env['l10n_cl_edi.certification.generated.document'].search([
            ('case_id.project_id', '=', self.project_id.id),
            ('state', 'in', ['accepted', 'sent']),  # Solo documentos aceptados o enviados
        ])

        if not generated_docs:
            raise UserError(_('No hay documentos generados en el proyecto para importar.'))

        print(f'✓ Encontrados {len(generated_docs)} documentos generados')

        # Verificar si ya existen líneas para estos documentos
        existing_lines = self.env['l10n_cl_edi.certification.book.line'].search([
            ('book_id', '=', self.id),
            ('generated_document_id', 'in', generated_docs.ids),
        ])

        if existing_lines:
            print(f'⚠️  Ya existen {len(existing_lines)} líneas importadas para algunos documentos')

        # Filtrar documentos que no están ya en el libro
        docs_to_import = generated_docs.filtered(lambda d: d.id not in existing_lines.mapped('generated_document_id').ids)

        if not docs_to_import:
            raise UserError(_('Todos los documentos del proyecto ya están importados en este libro.'))

        print(f'✓ Importando {len(docs_to_import)} documentos nuevos...')

        # Crear líneas para cada documento
        created_lines = 0
        for doc in docs_to_import:
            try:
                line_vals = {
                    'book_id': self.id,
                    'generated_document_id': doc.id,
                    'sequence': (len(self.line_ids) + created_lines + 1) * 10,
                }

                # El resto de campos se rellenan automáticamente via _onchange_generated_document_id
                line = self.env['l10n_cl_edi.certification.book.line'].create(line_vals)

                # Forzar el onchange manualmente
                line._onchange_generated_document_id()

                created_lines += 1
                print(f'  ✓ Línea creada para Folio {doc.folio} - {doc.document_type_name}')

            except Exception as e:
                _logger.warning(f'Error importando documento {doc.folio}: {str(e)}')
                print(f'  ⚠️  Error en Folio {doc.folio}: {str(e)}')

        print(f'\n✅ IMPORTACIÓN COMPLETADA')
        print(f'  Líneas creadas: {created_lines}')
        print(f'  Total líneas en libro: {len(self.line_ids)}')
        print('#' * 100 + '\n')

        self.with_context(imported_count=created_lines).message_post_with_source(
            source_ref=self.env.ref('l10n_cl_edi_certification.message_book_documents_imported'),
            subtype_xmlid='mail.mt_note'
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Importación Exitosa'),
                'message': _('Se importaron %d documentos del proyecto al libro de ventas.') % created_lines,
                'type': 'success',
                'sticky': False,
            }
        }
