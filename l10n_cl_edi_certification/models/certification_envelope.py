# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

import logging
_logger = logging.getLogger(__name__)

class CertificationEnvelope(models.Model):
    """
    Sobre de Envío (EnvioDTE) para el SII.
    Agrupa múltiples documentos DTE para enviarlos juntos.
    """
    _name = 'l10n_cl_edi.certification.envelope'
    _description = 'Sobre de Envío DTE para Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'project_id, create_date desc'

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
        default='Nuevo Sobre'
    )

    # Documentos Incluidos
    generated_document_ids = fields.Many2many(
        'l10n_cl_edi.certification.generated.document',
        'certification_envelope_document_rel',
        'envelope_id',
        'document_id',
        string='Documentos',
        help='Documentos DTE incluidos en este sobre'
    )

    documents_count = fields.Integer(
        string='Cantidad Documentos',
        compute='_compute_documents_count',
        store=True
    )

    # Archivos XML del Sobre
    envelope_xml = fields.Binary(
        string='XML Sobre',
        attachment=True,
        help='XML del EnvioDTE sin firmar'
    )
    envelope_xml_filename = fields.Char(
        string='Nombre Archivo',
        compute='_compute_filenames',
        store=True
    )
    envelope_xml_signed = fields.Binary(
        string='XML Sobre Firmado',
        attachment=True,
        help='XML del EnvioDTE firmado'
    )
    envelope_xml_signed_filename = fields.Char(
        string='Nombre Archivo Firmado',
        compute='_compute_filenames',
        store=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('created', 'Creado'),
        ('signed', 'Firmado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
        ('with_repairs', 'Con Reparos'),
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

    # Validación
    validation_messages = fields.Text(
        string='Mensajes de Validación'
    )

    @api.depends('generated_document_ids')
    def _compute_documents_count(self):
        for envelope in self:
            envelope.documents_count = len(envelope.generated_document_ids)

    @api.depends('name', 'sii_track_id')
    def _compute_filenames(self):
        for envelope in self:
            base_name = envelope.name.replace(' ', '_')
            if envelope.sii_track_id:
                base_name = f"{base_name}_{envelope.sii_track_id}"

            envelope.envelope_xml_filename = f"EnvioDTE_{base_name}.xml"
            envelope.envelope_xml_signed_filename = f"EnvioDTE_{base_name}_signed.xml"

    # Métodos de Acción
    def action_create_envelope(self):
        """Crea el XML del sobre con los documentos incluidos"""
        for envelope in self:
            if not envelope.generated_document_ids:
                raise UserError(_('Debe agregar al menos un documento al sobre.'))

            print(f'\n{"#" * 100}')
            print(f'CREANDO SOBRE DE ENVÍO')
            print(f'{"#" * 100}')
            print(f'Sobre: {envelope.name}')
            print(f'Proyecto: {envelope.project_id.name}')
            print(f'Cantidad de documentos: {len(envelope.generated_document_ids)}')

            print(f'\nEstado de documentos a incluir:')
            for doc in envelope.generated_document_ids:
                print(f'  - {doc.complete_name}:')
                print(f'      Estado: {doc.state}')
                print(f'      XML Firmado: {"✓" if doc.xml_dte_signed else "✗"}')
                print(f'      Folio: {doc.folio}')

            # Verificar que todos los documentos tengan XML firmado
            unsigned_docs = envelope.generated_document_ids.filtered(lambda d: not d.xml_dte_signed)

            if unsigned_docs:
                print(f'\n❌ Documentos sin firmar: {len(unsigned_docs)}')
                for doc in unsigned_docs:
                    print(f'  - {doc.complete_name} (estado: {doc.state})')
                raise UserError(_(
                    'Todos los documentos deben estar firmados antes de crear el sobre.\n'
                    'Documentos sin firmar: %s'
                ) % ', '.join(unsigned_docs.mapped('complete_name')))

            # Llamar al servicio de sobre
            print(f'\n>>> Generando XML del sobre...')
            envelope_service = self.env['l10n_cl_edi.envelope.service']
            envelope_xml = envelope_service.create_envelope(envelope)

            envelope.write({
                'envelope_xml': base64.b64encode(envelope_xml.encode('ISO-8859-1')),
                'state': 'created',
            })

            print(f'\n✅ SOBRE CREADO EXITOSAMENTE')
            print(f'Nombre: {envelope.name}')
            print(f'Documentos incluidos: {envelope.documents_count}')
            print(f'Tamaño XML: {len(envelope_xml)} caracteres')
            print(f'{"#" * 100}\n')

            envelope.with_context(documents_count=envelope.documents_count).message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_created'),
                subtype_xmlid='mail.mt_note'
            )

        return True

    def action_sign_envelope(self):
        """Firma el sobre digitalmente"""
        for envelope in self:
            if not envelope.envelope_xml:
                raise UserError(_('Debe crear el sobre primero.'))

            print(f'\n{"#" * 100}')
            print(f'FIRMANDO SOBRE DIGITALMENTE')
            print(f'{"#" * 100}')
            print(f'Sobre: {envelope.name}')
            print(f'Proyecto: {envelope.project_id.name}')

            signature_service = self.env['l10n_cl_edi.signature.service']
            signed_xml = signature_service.sign_envelope(envelope)

            envelope.write({
                'envelope_xml_signed': base64.b64encode(signed_xml.encode('ISO-8859-1')),
                'state': 'signed',
            })

            print(f'\n✅ SOBRE FIRMADO EXITOSAMENTE')
            print(f'Tamaño XML firmado: {len(signed_xml)} caracteres')
            print(f'{"#" * 100}\n')

            envelope.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_signed'),
                subtype_xmlid='mail.mt_note'
            )

        return True

    def action_validate_envelope(self):
        """Valida el sobre contra esquemas XSD"""
        for envelope in self:
            if not envelope.envelope_xml_signed:
                raise UserError(_('Debe firmar el sobre primero.'))

            validator = self.env['l10n_cl_edi.validation.service']
            is_valid, messages = validator.validate_envelope(envelope)

            envelope.validation_messages = '\n'.join(messages) if messages else _('Validación exitosa')

            if not is_valid:
                raise UserError(_('El sobre tiene errores de validación:\n%s') % envelope.validation_messages)

            envelope.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_validated'),
                subtype_xmlid='mail.mt_note'
            )

        return True

    def action_send_to_sii(self):
        """Envía el sobre al SII"""
        for envelope in self:
            if envelope.state != 'signed':
                raise UserError(_('El sobre debe estar firmado antes de enviar al SII.'))

            print(f'\n{"#" * 100}')
            print(f'INICIANDO ENVÍO AL SII')
            print(f'{"#" * 100}')
            print(f'Sobre: {envelope.name}')
            print(f'Estado actual: {envelope.state}')
            print(f'Documentos: {envelope.documents_count}')

            # Validar primero
            print(f'\n>>> Validando sobre contra esquemas XSD...')
            envelope.action_validate_envelope()
            print(f'✓ Validación exitosa')

            # Enviar al SII
            print(f'\n>>> Enviando sobre al SII...')
            sii_service = self.env['l10n_cl_edi.sii.integration.service']
            track_id, response = sii_service.send_envelope(envelope)

            # Crear registro de respuesta
            response_vals = {
                'project_id': envelope.project_id.id,
                'envelope_id': envelope.id,
                'response_type': 'send',
                'track_id': track_id,
                'response_date': fields.Datetime.now(),
                'response_xml': response if response else False,
                'status': 'received',
            }
            sii_response = self.env['l10n_cl_edi.certification.sii.response'].create(response_vals)

            envelope.write({
                'sii_track_id': track_id,
                'sii_send_date': fields.Datetime.now(),
                'sii_response_id': sii_response.id,
                'state': 'sent',
            })

            # Actualizar estado de documentos
            envelope.generated_document_ids.write({
                'state': 'sent',
                'sii_track_id': track_id,
            })

            print(f'\n✅ SOBRE ENVIADO AL SII EXITOSAMENTE')
            print(f'Track ID: {track_id}')
            print(f'Estado sobre: sent')
            print(f'Documentos actualizados: {len(envelope.generated_document_ids)}')
            print(f'{"#" * 100}\n')

            envelope.with_context(track_id=track_id).message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_sent'),
                subtype_xmlid='mail.mt_note'
            )

        return True

    def action_check_sii_status(self):
        """Consulta el estado del sobre en el SII"""
        for envelope in self:
            if not envelope.sii_track_id:
                raise UserError(_('El sobre no ha sido enviado al SII.'))

            print(f'\n{"#" * 100}')
            print(f'VERIFICANDO ESTADO DEL SOBRE EN SII')
            print(f'{"#" * 100}')
            print(f'Sobre: {envelope.name}')
            print(f'Track ID: {envelope.sii_track_id}')
            print(f'Estado actual: {envelope.state}')

            sii_service = self.env['l10n_cl_edi.sii.integration.service']
            status, response = sii_service.check_status(envelope.sii_track_id, envelope.project_id)

            # Crear registro de respuesta de estado
            response_vals = {
                'project_id': envelope.project_id.id,
                'envelope_id': envelope.id,
                'response_type': 'status',
                'track_id': envelope.sii_track_id,
                'response_date': fields.Datetime.now(),
                'response_xml': response if response else False,
                'status': status,
            }
            sii_response = self.env['l10n_cl_edi.certification.sii.response'].create(response_vals)

            # Actualizar estado del sobre
            previous_state = envelope.state
            if status == 'accepted':
                envelope.state = 'accepted'
                envelope.generated_document_ids.write({'state': 'accepted'})
                print(f'\n✅ SOBRE ACEPTADO POR EL SII')
                print(f'Estado cambió de {previous_state} a accepted')
                print(f'Documentos aceptados: {len(envelope.generated_document_ids)}')
                envelope.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_accepted'),
                    subtype_xmlid='mail.mt_note'
                )
            elif status == 'rejected':
                envelope.state = 'rejected'
                envelope.generated_document_ids.write({'state': 'rejected'})
                print(f'\n❌ SOBRE RECHAZADO POR EL SII')
                print(f'Estado cambió de {previous_state} a rejected')
                envelope.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_rejected'),
                    subtype_xmlid='mail.mt_note'
                )
            elif status == 'with_repairs':
                envelope.state = 'with_repairs'
                print(f'\n⚠️  SOBRE CON REPAROS')
                print(f'Estado cambió de {previous_state} a with_repairs')
                envelope.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_with_repairs'),
                    subtype_xmlid='mail.mt_note'
                )
            elif status in ['received', 'validating']:
                # Estados intermedios: el sobre fue recibido pero aún no procesado
                # Mantener en 'sent' pero registrar la consulta
                print(f'\n⏳ SOBRE EN PROCESO DE VALIDACIÓN')
                print(f'Estado SII: {status}')
                print(f'Estado del sobre: {envelope.state} (sin cambios - esperando procesamiento)')
                envelope.with_context(status=status).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_status_received'),
                    subtype_xmlid='mail.mt_note'
                )
            else:
                # Estado desconocido
                print(f'\n⚠️  ESTADO DESCONOCIDO')
                print(f'Estado SII reportado: {status}')
                print(f'Estado del sobre: {envelope.state}')
                envelope.with_context(status=status).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_envelope_status_updated'),
                    subtype_xmlid='mail.mt_note'
                )

            print(f'{"#" * 100}\n')

        return True

    def action_view_documents(self):
        """Ver los documentos del sobre"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documentos del Sobre'),
            'res_model': 'l10n_cl_edi.certification.generated.document',
            'domain': [('id', 'in', self.generated_document_ids.ids)],
            'view_mode': 'list,form',
        }

    def action_view_sii_responses(self):
        """Ver respuestas del SII para este sobre"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Respuestas del SII'),
            'res_model': 'l10n_cl_edi.certification.sii.response',
            'domain': [('envelope_id', '=', self.id)],
            'view_mode': 'list,form',
        }

    def action_download_envelope_xml(self):
        """Descarga el XML firmado del sobre"""
        self.ensure_one()
        if not self.envelope_xml_signed:
            raise UserError(_('No hay XML firmado para descargar.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.id}?field=envelope_xml_signed&download=true&filename={self.envelope_xml_signed_filename}',
            'target': 'self',
        }
