# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class CertificationSiiResponse(models.Model):
    """
    Respuesta del SII para el proceso de Certificación.
    Almacena todas las respuestas del SII (envíos, consultas de estado, etc.)
    """
    _name = 'l10n_cl_edi.certification.sii.response'
    _description = 'Respuesta del SII para Certificación'
    _order = 'response_date desc, id desc'
    _rec_name = 'complete_name'

    # Relaciones
    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        index=True
    )
    envelope_id = fields.Many2one(
        'l10n_cl_edi.certification.envelope',
        string='Sobre',
        help='Sobre relacionado con esta respuesta'
    )

    # Tipo de Respuesta
    response_type = fields.Selection([
        ('send', 'Envío'),
        ('status', 'Consulta Estado'),
    ], string='Tipo de Respuesta', required=True)

    # Track ID
    track_id = fields.Char(
        string='Track ID',
        required=True,
        help='ID de seguimiento del SII'
    )

    # Fecha y Hora
    response_date = fields.Datetime(
        string='Fecha Respuesta',
        required=True,
        default=fields.Datetime.now
    )

    # Contenido de la Respuesta
    response_xml = fields.Text(
        string='XML Respuesta',
        help='Respuesta completa del SII en formato XML'
    )

    # Estado
    status = fields.Selection([
        ('received', 'Recibido'),
        ('validating', 'En Validación'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
        ('with_repairs', 'Aceptado con Reparos'),
    ], string='Estado', required=True, default='received')

    # Mensajes
    error_messages = fields.Text(
        string='Mensajes de Error',
        help='Mensajes de error reportados por el SII'
    )
    repair_messages = fields.Text(
        string='Mensajes de Reparos',
        help='Reparos o advertencias del SII'
    )
    info_messages = fields.Text(
        string='Mensajes Informativos',
        help='Información adicional del SII'
    )

    # Código de Estado
    status_code = fields.Char(
        string='Código Estado',
        help='Código numérico del estado (ej: EPR, DOK, RCT, etc.)'
    )

    # Nombre Completo
    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )

    # Color para vista (basado en estado)
    color = fields.Integer(
        string='Color',
        compute='_compute_color'
    )

    @api.depends('response_type', 'track_id', 'status')
    def _compute_complete_name(self):
        for record in self:
            type_label = dict(record._fields['response_type'].selection).get(record.response_type, '')
            status_label = dict(record._fields['status'].selection).get(record.status, '')
            record.complete_name = f"{type_label} - {record.track_id} ({status_label})"

    @api.depends('status')
    def _compute_color(self):
        """Asigna color según estado"""
        color_map = {
            'received': 1,  # Azul
            'validating': 3,  # Amarillo
            'accepted': 10,  # Verde
            'rejected': 1,  # Rojo
            'with_repairs': 9,  # Naranja
        }
        for record in self:
            record.color = color_map.get(record.status, 0)

    def action_parse_response(self):
        """Parsea la respuesta XML y extrae información relevante"""
        for response in self:
            if not response.response_xml:
                continue

            try:
                from lxml import etree
                xml_doc = etree.fromstring(response.response_xml.encode('utf-8'))

                # Extraer mensajes según estructura del XML del SII
                # Esto dependerá del formato exacto de respuesta del SII
                # Aquí un ejemplo básico:

                error_nodes = xml_doc.xpath('//ERROR')
                if error_nodes:
                    errors = [node.text for node in error_nodes if node.text]
                    response.error_messages = '\n'.join(errors)

                # Extraer código de estado
                status_node = xml_doc.xpath('//ESTADO')
                if status_node and status_node[0].text:
                    response.status_code = status_node[0].text

                response.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_sii_response_parsed'),
                    subtype_xmlid='mail.mt_note'
                )

            except Exception as e:
                response.with_context(error=str(e)).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_sii_response_parse_error'),
                    subtype_xmlid='mail.mt_note'
                )

        return True

    def action_view_envelope(self):
        """Ver el sobre relacionado"""
        self.ensure_one()
        if not self.envelope_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sobre de Envío'),
            'res_model': 'l10n_cl_edi.certification.envelope',
            'res_id': self.envelope_id.id,
            'view_mode': 'form',
        }
