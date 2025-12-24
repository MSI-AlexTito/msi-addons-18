# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

class CertificationSimulation(models.Model):
    """
    Set de Simulación para certificación SII.
    Genera 20-100 documentos con datos realistas para etapa de simulación.
    """
    _name = 'l10n_cl_edi.certification.simulation'
    _description = 'Set de Simulación para Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

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
        default='Simulación'
    )

    # Configuración
    total_documents = fields.Integer(
        string='Total Documentos',
        default=20,
        required=True,
        help='Debe ser entre 20 y 100 documentos'
    )

    invoices_count = fields.Integer(
        string='Facturas Electrónicas (33)',
        default=12,
        required=True
    )
    folio_start_invoice = fields.Integer(
        string='Folio Inicio Facturas',
        help='Folio desde donde comenzar a generar facturas. Dejar en 0 para usar el siguiente disponible automáticamente.',
        default=0
    )

    credit_notes_count = fields.Integer(
        string='Notas de Crédito (61)',
        default=5,
        required=True
    )
    folio_start_credit_note = fields.Integer(
        string='Folio Inicio NC',
        help='Folio desde donde comenzar a generar notas de crédito. Dejar en 0 para usar el siguiente disponible automáticamente.',
        default=0
    )

    debit_notes_count = fields.Integer(
        string='Notas de Débito (56)',
        default=3,
        required=True
    )
    folio_start_debit_note = fields.Integer(
        string='Folio Inicio ND',
        help='Folio desde donde comenzar a generar notas de débito. Dejar en 0 para usar el siguiente disponible automáticamente.',
        default=0
    )

    date_from = fields.Date(
        string='Fecha Desde',
        default=fields.Date.today,
        required=True
    )

    date_to = fields.Date(
        string='Fecha Hasta',
        default=fields.Date.today,
        required=True
    )

    # Receptor (Partner)
    receiver_id = fields.Many2one(
        'res.partner',
        string='Receptor',
        required=True,
        default=lambda self: self._get_default_receiver(),
        help='Seleccione el partner que será el receptor de los documentos de simulación'
    )

    receiver_rut = fields.Char(
        string='RUT Receptor',
        related='receiver_id.vat',
        store=True,
        readonly=True
    )

    receiver_name = fields.Char(
        string='Razón Social Receptor',
        related='receiver_id.name',
        store=True,
        readonly=True
    )

    receiver_giro = fields.Char(
        string='Giro Receptor',
        compute='_compute_receiver_data',
        store=True
    )

    receiver_address = fields.Char(
        string='Dirección Receptor',
        compute='_compute_receiver_data',
        store=True
    )

    receiver_comuna = fields.Char(
        string='Comuna Receptor',
        compute='_compute_receiver_data',
        store=True
    )

    # Documentos generados
    document_ids = fields.One2many(
        'l10n_cl_edi.certification.generated.document',
        'simulation_id',
        string='Documentos Generados'
    )

    documents_count = fields.Integer(
        string='Cantidad Generada',
        compute='_compute_documents_count',
        store=True
    )

    # Sobre (EnvioDTE)
    envelope_id = fields.Many2one(
        'l10n_cl_edi.certification.envelope',
        string='Sobre Generado',
        readonly=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Documentos Generados'),
        ('envelope_created', 'Sobre Creado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # SII
    sii_track_id = fields.Char(
        string='Track ID SII',
        readonly=True,
        copy=False
    )

    sii_send_date = fields.Datetime(
        string='Fecha Envío SII',
        readonly=True,
        copy=False
    )

    notes = fields.Text(
        string='Notas'
    )

    def _get_default_receiver(self):
        """Obtiene o crea el partner SII por defecto para simulación"""
        # Buscar partner del SII
        sii_partner = self.env['res.partner'].search([
            ('vat', '=', '60803000-K')
        ], limit=1)

        if not sii_partner:
            # Crear partner del SII si no existe
            sii_partner = self.env['res.partner'].create({
                'name': 'Servicio de Impuestos Internos',
                'vat': '60803000-K',
                'street': 'Teatinos 120',
                'city': 'Santiago',
                'l10n_cl_activity_description': 'Administración Pública',
                'email': 'oficina.partes@sii.cl',
                'is_company': True,
            })

        return sii_partner.id

    @api.depends('document_ids')
    def _compute_documents_count(self):
        for rec in self:
            rec.documents_count = len(rec.document_ids)

    @api.depends('receiver_id', 'receiver_id.street', 'receiver_id.city', 'receiver_id.l10n_cl_activity_description')
    def _compute_receiver_data(self):
        """Obtiene los datos del receptor desde el partner"""
        for rec in self:
            if rec.receiver_id:
                # Giro: intentar obtener de l10n_cl_activity_description o usar valor por defecto
                if hasattr(rec.receiver_id, 'l10n_cl_activity_description'):
                    rec.receiver_giro = rec.receiver_id.l10n_cl_activity_description or 'Actividades comerciales'
                else:
                    rec.receiver_giro = 'Actividades comerciales'

                # Dirección: usar street o dirección completa
                if rec.receiver_id.street:
                    rec.receiver_address = rec.receiver_id.street
                else:
                    rec.receiver_address = 'Dirección no especificada'

                # Comuna: usar city
                if rec.receiver_id.city:
                    rec.receiver_comuna = rec.receiver_id.city
                else:
                    rec.receiver_comuna = 'Santiago'
            else:
                rec.receiver_giro = False
                rec.receiver_address = False
                rec.receiver_comuna = False

    @api.constrains('total_documents')
    def _check_total_documents(self):
        for rec in self:
            if rec.total_documents < 20 or rec.total_documents > 100:
                raise UserError(_('El total de documentos debe estar entre 20 y 100.'))

    @api.constrains('invoices_count', 'credit_notes_count', 'debit_notes_count', 'total_documents')
    def _check_distribution(self):
        for rec in self:
            total = rec.invoices_count + rec.credit_notes_count + rec.debit_notes_count
            if total != rec.total_documents:
                raise UserError(_('La suma de facturas, notas de crédito y notas de débito debe ser igual al total de documentos.'))

    @api.constrains('folio_start_invoice', 'folio_start_credit_note', 'folio_start_debit_note', 'project_id')
    def _check_folio_ranges(self):
        """Valida que los folios de inicio estén dentro del rango de CAF"""
        for rec in self:
            if not rec.project_id:
                continue

            # Validar que si se especifica folio manual, sea >= 1
            if rec.folio_start_invoice < 0 or rec.folio_start_credit_note < 0 or rec.folio_start_debit_note < 0:
                raise UserError(_('Los folios de inicio no pueden ser negativos. Use 0 para asignación automática.'))

            # Validar folio inicio de facturas
            if rec.folio_start_invoice > 0:
                doc_type_33 = self.env['l10n_latam.document.type'].search([('code', '=', '33')], limit=1)
                if doc_type_33:
                    folio_final = rec.folio_start_invoice + rec.invoices_count - 1

                    # Buscar TODOS los CAF del tipo de documento
                    assignments = self.env['l10n_cl_edi.certification.folio.assignment'].search([
                        ('project_id', '=', rec.project_id.id),
                        ('document_type_id', '=', doc_type_33.id)
                    ])

                    if assignments:
                        # Verificar que el rango esté dentro de AL MENOS UNO de los CAF
                        valid = False
                        for assignment in assignments:
                            if rec.folio_start_invoice >= assignment.folio_start and folio_final <= assignment.folio_end:
                                valid = True
                                break

                        if not valid:
                            caf_info = '\n'.join([f'  • CAF {i+1}: Folios {a.folio_start} al {a.folio_end} ({a.folio_end - a.folio_start + 1} folios disponibles)'
                                                 for i, a in enumerate(assignments)])

                            # Calcular sugerencias
                            suggestions = []
                            for assignment in assignments:
                                available_in_caf = assignment.folio_end - assignment.folio_start + 1
                                if rec.invoices_count <= available_in_caf:
                                    # Calcular último folio de inicio posible
                                    max_start = assignment.folio_end - rec.invoices_count + 1
                                    suggestions.append(
                                        f'  • Usar folios {assignment.folio_start} al {assignment.folio_end}: '
                                        f'cambie el folio de inicio entre {assignment.folio_start} y {max_start}'
                                    )

                            if not suggestions:
                                suggestions.append(f'  • Reducir la cantidad de facturas a un máximo que quepa en los CAF disponibles')
                                suggestions.append(f'  • Cargar un nuevo CAF que cubra los folios necesarios')

                            raise UserError(
                                _('ERROR: Rango de folios INVÁLIDO para Facturas (tipo 33)\n\n'
                                  '❌ Rango solicitado: Folios %d al %d (%d facturas)\n'
                                  '   Folio inicio: %d\n'
                                  '   Cantidad: %d facturas\n'
                                  '   Folio final: %d\n\n'
                                  '📋 CAF autorizados para Facturas:\n%s\n\n'
                                  '💡 Soluciones posibles:\n%s\n\n'
                                  '⚠️  El rango de folios solicitado excede los CAF autorizados.\n'
                                  '   Debe ajustar el folio de inicio o la cantidad de documentos.') %
                                (rec.folio_start_invoice, folio_final, rec.invoices_count,
                                 rec.folio_start_invoice, rec.invoices_count, folio_final,
                                 caf_info, '\n'.join(suggestions))
                            )

            # Validar folio inicio de NC
            if rec.folio_start_credit_note > 0:
                doc_type_61 = self.env['l10n_latam.document.type'].search([('code', '=', '61')], limit=1)
                if doc_type_61:
                    folio_final = rec.folio_start_credit_note + rec.credit_notes_count - 1

                    # Buscar TODOS los CAF del tipo de documento
                    assignments = self.env['l10n_cl_edi.certification.folio.assignment'].search([
                        ('project_id', '=', rec.project_id.id),
                        ('document_type_id', '=', doc_type_61.id)
                    ])

                    if assignments:
                        # Verificar que el rango esté dentro de AL MENOS UNO de los CAF
                        valid = False
                        for assignment in assignments:
                            if rec.folio_start_credit_note >= assignment.folio_start and folio_final <= assignment.folio_end:
                                valid = True
                                break

                        if not valid:
                            caf_info = '\n'.join([f'  • CAF {i+1}: Folios {a.folio_start} al {a.folio_end} ({a.folio_end - a.folio_start + 1} folios disponibles)'
                                                 for i, a in enumerate(assignments)])

                            # Calcular sugerencias
                            suggestions = []
                            for assignment in assignments:
                                available_in_caf = assignment.folio_end - assignment.folio_start + 1
                                if rec.credit_notes_count <= available_in_caf:
                                    # Calcular último folio de inicio posible
                                    max_start = assignment.folio_end - rec.credit_notes_count + 1
                                    suggestions.append(
                                        f'  • Usar folios {assignment.folio_start} al {assignment.folio_end}: '
                                        f'cambie el folio de inicio entre {assignment.folio_start} y {max_start}'
                                    )

                            if not suggestions:
                                suggestions.append(f'  • Reducir la cantidad de NC a un máximo que quepa en los CAF disponibles')
                                suggestions.append(f'  • Cargar un nuevo CAF que cubra los folios necesarios')

                            raise UserError(
                                _('ERROR: Rango de folios INVÁLIDO para Notas de Crédito (tipo 61)\n\n'
                                  '❌ Rango solicitado: Folios %d al %d (%d NC)\n'
                                  '   Folio inicio: %d\n'
                                  '   Cantidad: %d NC\n'
                                  '   Folio final: %d\n\n'
                                  '📋 CAF autorizados para Notas de Crédito:\n%s\n\n'
                                  '💡 Soluciones posibles:\n%s\n\n'
                                  '⚠️  El rango de folios solicitado excede los CAF autorizados.\n'
                                  '   Debe ajustar el folio de inicio o la cantidad de documentos.') %
                                (rec.folio_start_credit_note, folio_final, rec.credit_notes_count,
                                 rec.folio_start_credit_note, rec.credit_notes_count, folio_final,
                                 caf_info, '\n'.join(suggestions))
                            )

            # Validar folio inicio de ND
            if rec.folio_start_debit_note > 0:
                doc_type_56 = self.env['l10n_latam.document.type'].search([('code', '=', '56')], limit=1)
                if doc_type_56:
                    folio_final = rec.folio_start_debit_note + rec.debit_notes_count - 1

                    # Buscar TODOS los CAF del tipo de documento
                    assignments = self.env['l10n_cl_edi.certification.folio.assignment'].search([
                        ('project_id', '=', rec.project_id.id),
                        ('document_type_id', '=', doc_type_56.id)
                    ])

                    if assignments:
                        # Verificar que el rango esté dentro de AL MENOS UNO de los CAF
                        valid = False
                        for assignment in assignments:
                            if rec.folio_start_debit_note >= assignment.folio_start and folio_final <= assignment.folio_end:
                                valid = True
                                break

                        if not valid:
                            caf_info = '\n'.join([f'  • CAF {i+1}: Folios {a.folio_start} al {a.folio_end} ({a.folio_end - a.folio_start + 1} folios disponibles)'
                                                 for i, a in enumerate(assignments)])

                            # Calcular sugerencias
                            suggestions = []
                            for assignment in assignments:
                                available_in_caf = assignment.folio_end - assignment.folio_start + 1
                                if rec.debit_notes_count <= available_in_caf:
                                    # Calcular último folio de inicio posible
                                    max_start = assignment.folio_end - rec.debit_notes_count + 1
                                    suggestions.append(
                                        f'  • Usar folios {assignment.folio_start} al {assignment.folio_end}: '
                                        f'cambie el folio de inicio entre {assignment.folio_start} y {max_start}'
                                    )

                            if not suggestions:
                                suggestions.append(f'  • Reducir la cantidad de ND a un máximo que quepa en los CAF disponibles')
                                suggestions.append(f'  • Cargar un nuevo CAF que cubra los folios necesarios')

                            raise UserError(
                                _('ERROR: Rango de folios INVÁLIDO para Notas de Débito (tipo 56)\n\n'
                                  '❌ Rango solicitado: Folios %d al %d (%d ND)\n'
                                  '   Folio inicio: %d\n'
                                  '   Cantidad: %d ND\n'
                                  '   Folio final: %d\n\n'
                                  '📋 CAF autorizados para Notas de Débito:\n%s\n\n'
                                  '💡 Soluciones posibles:\n%s\n\n'
                                  '⚠️  El rango de folios solicitado excede los CAF autorizados.\n'
                                  '   Debe ajustar el folio de inicio o la cantidad de documentos.') %
                                (rec.folio_start_debit_note, folio_final, rec.debit_notes_count,
                                 rec.folio_start_debit_note, rec.debit_notes_count, folio_final,
                                 caf_info, '\n'.join(suggestions))
                            )

    def action_generate_documents(self):
        """Genera los documentos de simulación"""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_('Solo se pueden generar documentos en estado borrador.'))

        # Llamar al servicio generador
        generator = self.env['l10n_cl_edi.simulation.generator.service']
        generator.generate_simulation_documents(self)

        self.state = 'generated'
        self.message_post(body=_('Documentos de simulación generados: %d facturas, %d NC, %d ND') %
                         (self.invoices_count, self.credit_notes_count, self.debit_notes_count))

    def action_create_envelope(self):
        """Crea el sobre (EnvioDTE) con todos los documentos"""
        self.ensure_one()

        if self.state != 'generated':
            raise UserError(_('Debe generar los documentos primero.'))

        # Verificar que todos los documentos estén firmados
        unsigned_docs = self.document_ids.filtered(lambda d: not d.xml_dte_signed)
        if unsigned_docs:
            raise UserError(_('Todos los documentos deben estar firmados antes de crear el sobre.'))

        # Crear sobre
        Envelope = self.env['l10n_cl_edi.certification.envelope']
        envelope = Envelope.create({
            'project_id': self.project_id.id,
            'name': f'Simulación - {self.name}',
            'generated_document_ids': [(6, 0, self.document_ids.ids)],
        })

        # Vincular documentos al sobre (actualizar envelope_id en los documentos)
        self.document_ids.write({'envelope_id': envelope.id})

        self.envelope_id = envelope
        self.message_post(body=_('Sobre creado con %d documentos') % self.documents_count)

        # Generar XML del sobre
        envelope_service = self.env['l10n_cl_edi.envelope.service']
        envelope_xml = envelope_service.create_envelope(envelope)

        # Guardar el XML generado en el sobre
        envelope.write({
            'envelope_xml': base64.b64encode(envelope_xml.encode('ISO-8859-1')),
            'state': 'created',
        })

        # Firmar sobre
        envelope.action_sign_envelope()

        # Validar XSD
        validation_service = self.env['l10n_cl_edi.xml.validation.service']

        # Obtener el XML firmado del sobre
        if envelope.envelope_xml_signed:
            envelope_xml_str = base64.b64decode(envelope.envelope_xml_signed).decode('ISO-8859-1')
        else:
            raise UserError(_('El sobre debe estar firmado antes de validar.'))

        is_valid, messages = validation_service.validate_envio_dte_xml(envelope_xml_str)

        if is_valid:
            self.state = 'envelope_created'
        else:
            raise UserError(_('Error en validación XSD del sobre:\n%s') % '\n'.join(messages))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.envelope',
            'res_id': envelope.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_envelope(self):
        """Ver el sobre generado"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.envelope',
            'res_id': self.envelope_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_back_to_draft(self):
        """Regresar a borrador"""
        self.ensure_one()

        # Eliminar documentos y sobre si existen
        if self.envelope_id:
            self.envelope_id.unlink()

        self.document_ids.unlink()

        self.state = 'draft'
        self.message_post(body=_('Simulación regresada a borrador. Documentos eliminados.'))

    def action_send_to_sii(self):
        """Envía el sobre al SII"""
        self.ensure_one()

        if self.state != 'envelope_created':
            raise UserError(_('Debe crear el sobre primero.'))

        if not self.envelope_id:
            raise UserError(_('No hay sobre para enviar.'))

        # Enviar el sobre al SII usando el servicio de integración
        sii_service = self.env['l10n_cl_edi.sii.integration.service']
        result = sii_service.send_envelope(self.envelope_id)

        if result and result.get('track_id'):
            self.write({
                'sii_track_id': result['track_id'],
                'sii_send_date': fields.Datetime.now(),
                'state': 'sent',
            })

            self.message_post(body=_('Sobre enviado al SII. Track ID: %s') % result['track_id'])

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Enviado al SII'),
                    'message': _('El sobre fue enviado exitosamente. Track ID: %s') % result['track_id'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_('Error al enviar al SII: %s') % result.get('error', 'Error desconocido'))

    def action_check_sii_status(self):
        """Consulta el estado en el SII"""
        self.ensure_one()

        if not self.sii_track_id:
            raise UserError(_('No hay Track ID. Debe enviar al SII primero.'))

        # Consultar estado en el SII
        sii_service = self.env['l10n_cl_edi.sii.integration.service']
        result = sii_service.check_status(
            self.sii_track_id,
            self.project_id
        )

        if result:
            estado = result.get('estado', 'DESCONOCIDO')
            glosa = result.get('glosa', '')

            # Actualizar estado según respuesta
            if 'ACEPTADO' in estado.upper() or 'LOK' in estado.upper() or 'SOK' in estado.upper():
                self.state = 'accepted'
                tipo_notif = 'success'
            elif 'RECHAZADO' in estado.upper() or 'RCH' in estado.upper():
                self.state = 'rejected'
                tipo_notif = 'danger'
            else:
                tipo_notif = 'info'

            mensaje = f'Estado SII: {estado}\n{glosa}'
            self.message_post(body=mensaje)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Estado SII'),
                    'message': mensaje,
                    'type': tipo_notif,
                    'sticky': True,
                }
            }
        else:
            raise UserError(_('No se pudo consultar el estado en el SII.'))
