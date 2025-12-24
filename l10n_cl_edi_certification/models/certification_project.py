# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging
_logger = logging.getLogger(__name__)

class CertificationProject(models.Model):
    """
    Proyecto de Certificación para una Empresa Cliente.
    Gestiona todo el proceso de certificación ante el SII.
    """
    _name = 'l10n_cl_edi.certification.project'
    _description = 'Proyecto de Certificación SII'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'complete_name'

    # Información Básica

    sequence = fields.Char(
        string='Secuencia',
        readonly=True,
        copy=False
    )
    code = fields.Char(
        string='Código',
        readonly=True,
        copy=False
    )
    name = fields.Char(
        string='Nombre del Proyecto',
        required=True,
        tracking=True,
        help='Nombre identificativo del proyecto de certificación'
    )

    # NOTA: Los campos relacionados con folios están en el modelo certification_folio_assignment
    # No duplicar aquí - acceder mediante folio_assignment_ids

    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía Consultora',
        required=True,
        default=lambda self: self.env.company,
        help='Compañía que realiza la certificación'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Empresa Cliente',
        required=True,
        tracking=True,
        help='Empresa que será certificada'
    )

    # Fechas
    start_date = fields.Date(
        string='Fecha Inicio',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    due_date = fields.Date(
        string='Fecha Vencimiento',
        tracking=True,
        help='Fecha límite para completar la certificación'
    )
    completion_date = fields.Date(
        string='Fecha Completado',
        readonly=True,
        tracking=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('in_progress', 'En Progreso'),
        ('validating', 'En Validación'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Descripción
    description = fields.Text(
        string='Descripción',
        help='Descripción del proyecto y objetivos'
    )

    # Relaciones One2many
    client_info_id = fields.Many2one(
        'l10n_cl_edi.certification.client',
        string='Información del Cliente',
        help='Snapshot de datos del cliente al momento de la certificación'
    )

    certification_case_ids = fields.One2many(
        'l10n_cl_edi.certification.case',
        'project_id',
        string='Casos de Prueba'
    )

    book_ids = fields.One2many(
        'l10n_cl_edi.certification.book',
        'project_id',
        string='Libros de Compra/Venta',
        help='Libros electrónicos de compra y venta para certificación'
    )

    books_count = fields.Integer(
        string='Cantidad de Libros',
        compute='_compute_books_count',
        store=True
    )

    folio_assignment_ids = fields.One2many(
        'l10n_cl_edi.certification.folio.assignment',
        'project_id',
        string='Asignación de Folios'
    )

    generated_document_ids = fields.One2many(
        'l10n_cl_edi.certification.generated.document',
        'project_id',
        string='Documentos Generados'
    )

    envelope_ids = fields.One2many(
        'l10n_cl_edi.certification.envelope',
        'project_id',
        string='Sobres de Envío'
    )

    sii_response_ids = fields.One2many(
        'l10n_cl_edi.certification.sii.response',
        'project_id',
        string='Respuestas del SII'
    )

    # Campos Computados - Estadísticas
    cases_total_count = fields.Integer(
        string='Total Casos',
        compute='_compute_cases_stats',
        store=True
    )
    cases_draft_count = fields.Integer(
        string='Casos en Borrador',
        compute='_compute_cases_stats',
        store=True
    )
    cases_ready_count = fields.Integer(
        string='Casos Listos',
        compute='_compute_cases_stats',
        store=True
    )
    cases_generated_count = fields.Integer(
        string='Casos Generados',
        compute='_compute_cases_stats',
        store=True
    )
    cases_validated_count = fields.Integer(
        string='Casos Validados',
        compute='_compute_cases_stats',
        store=True
    )
    cases_sent_count = fields.Integer(
        string='Casos Enviados',
        compute='_compute_cases_stats',
        store=True
    )
    cases_accepted_count = fields.Integer(
        string='Casos Aceptados',
        compute='_compute_cases_stats',
        store=True
    )
    cases_rejected_count = fields.Integer(
        string='Casos Rechazados',
        compute='_compute_cases_stats',
        store=True
    )

    documents_total_count = fields.Integer(
        string='Total Documentos',
        compute='_compute_documents_count',
        store=True
    )

    envelopes_count = fields.Integer(
        string='Total Sobres',
        compute='_compute_envelopes_count',
        store=True
    )

    progress_percentage = fields.Float(
        string='Progreso %',
        compute='_compute_progress_percentage',
        store=True
    )

    # Campos de Control
    user_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True
    )

    color = fields.Integer(string='Color', default=0)

    # Computed fields
    @api.depends('name', 'partner_id.name')
    def _compute_complete_name(self):
        for record in self:
            if record.partner_id:
                record.complete_name = f"{record.name} - {record.partner_id.name}"
            else:
                record.complete_name = record.name

    @api.depends('certification_case_ids.state')
    def _compute_cases_stats(self):
        for project in self:
            cases = project.certification_case_ids
            project.cases_total_count = len(cases)
            project.cases_draft_count = len(cases.filtered(lambda c: c.state == 'draft'))
            project.cases_ready_count = len(cases.filtered(lambda c: c.state == 'ready'))
            project.cases_generated_count = len(cases.filtered(lambda c: c.state == 'generated'))
            project.cases_validated_count = len(cases.filtered(lambda c: c.state == 'validated'))
            project.cases_sent_count = len(cases.filtered(lambda c: c.state == 'sent'))
            project.cases_accepted_count = len(cases.filtered(lambda c: c.state == 'accepted'))
            project.cases_rejected_count = len(cases.filtered(lambda c: c.state == 'rejected'))

    @api.depends('generated_document_ids')
    def _compute_documents_count(self):
        for project in self:
            project.documents_total_count = len(project.generated_document_ids)

    @api.depends('envelope_ids')
    def _compute_envelopes_count(self):
        for project in self:
            project.envelopes_count = len(project.envelope_ids)

    @api.depends('book_ids')
    def _compute_books_count(self):
        for project in self:
            project.books_count = len(project.book_ids)

    @api.depends('cases_total_count', 'cases_accepted_count')
    def _compute_progress_percentage(self):
        for project in self:
            if project.cases_total_count > 0:
                project.progress_percentage = (project.cases_accepted_count / project.cases_total_count) * 100
            else:
                project.progress_percentage = 0.0

    # Constraints
    @api.constrains('start_date', 'due_date')
    def _check_dates(self):
        for record in self:
            if record.due_date and record.start_date > record.due_date:
                raise ValidationError(_('La fecha de vencimiento debe ser posterior a la fecha de inicio.'))

    # Métodos de Acción - Transiciones de Estado
    def action_start(self):
        """Inicia el proyecto de certificación"""
        for record in self:
            if not record.client_info_id:
                raise UserError(_('Debe configurar la información del cliente antes de iniciar.'))
            if not record.certification_case_ids:
                raise UserError(_('Debe agregar al menos un caso de prueba.'))
            if not record.folio_assignment_ids:
                raise UserError(_('Debe asignar folios para los tipos de documentos.'))

            record.state = 'in_progress'
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_started')
            )

    def action_validate(self):
        """Marca el proyecto como en validación"""
        for record in self:
            # Contar documentos generados (no importa el estado del caso)
            docs_generated = self.env['l10n_cl_edi.certification.generated.document'].search_count([
                ('project_id', '=', record.id)
            ])

            # La validación debería ser: al menos 1 documento generado (en cualquier estado)
            if docs_generated == 0:
                raise UserError(_('Debe generar al menos un documento antes de validar.'))

            record.state = 'validating'
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_validating')
            )

    def action_complete(self):
        """Completa el proyecto de certificación"""
        for record in self:
            if record.cases_rejected_count > 0:
                raise UserError(_('No puede completar el proyecto con casos rechazados. Debe corregirlos primero.'))

            if record.cases_accepted_count < record.cases_total_count:
                raise UserError(_('Debe tener todos los casos aceptados para completar el proyecto.'))

            record.write({
                'state': 'completed',
                'completion_date': fields.Date.context_today(record),
            })
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_completed')
            )

    def action_back_to_progress(self):
        """Regresa el proyecto a estado en progreso"""
        for record in self:
            record.state = 'in_progress'
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_back_to_progress')
            )

    def action_cancel(self):
        """Cancela el proyecto"""
        for record in self:
            record.state = 'cancelled'
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_cancelled')
            )

    def action_back_to_draft(self):
        """Regresa el proyecto a borrador"""
        for record in self:
            if record.state != 'cancelled':
                raise UserError(_('Solo puede regresar a borrador un proyecto cancelado.'))
            record.state = 'draft'
            record.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_project_back_to_draft')
            )

    def action_import_basic_testset(self):
        """
        Importa automáticamente los casos del SET BÁSICO del SII
        (Número de atención: 3660207 - 8 casos estándar)
        """
        self.ensure_one()

        # Verificar que no haya casos ya importados
        if self.certification_case_ids:
            raise UserError(_(
                'El proyecto ya tiene casos de prueba.\n'
                'Si desea reimportar, elimine los casos existentes primero.'
            ))

        # Buscar templates del SET BÁSICO
        templates = self.env['l10n_cl_edi.test.case.template'].search([
            ('category', '=', 'standard'),
            ('code', 'like', '3660207-%')
        ], order='code')

        if not templates:
            raise UserError(_(
                'No se encontraron plantillas del SET BÁSICO.\n'
                'Verifique que los datos de prueba estén cargados correctamente.'
            ))

        # Crear casos desde las plantillas
        cases_created = []
        CertificationCase = self.env['l10n_cl_edi.certification.case']

        for template in templates:
            case = CertificationCase.create_from_template(template, self)
            cases_created.append(case.name)

        # Mensaje de éxito con template
        self.with_context(
            cases_count=len(cases_created),
            cases_names=cases_created
        ).message_post_with_source(
            source_ref=self.env.ref('l10n_cl_edi_certification.message_project_testset_imported')
        )

        # Mostrar notificación y recargar
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('¡Importación exitosa!'),
                'message': _('%d casos del SET BÁSICO importados correctamente') % len(cases_created),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            }
        }

    # Métodos de Vista
    def action_view_cases(self):
        """Abre la vista de casos de prueba del proyecto"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Casos de Prueba'),
            'res_model': 'l10n_cl_edi.certification.case',
            'domain': [('project_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_project_id': self.id},
        }

    def action_view_documents(self):
        """Abre la vista de documentos generados"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documentos Generados'),
            'res_model': 'l10n_cl_edi.certification.generated.document',
            'domain': [('project_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_project_id': self.id},
        }

    def action_view_envelopes(self):
        """Abre la vista de sobres de envío"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sobres de Envío'),
            'res_model': 'l10n_cl_edi.certification.envelope',
            'domain': [('project_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_project_id': self.id},
        }

    def action_view_sii_responses(self):
        """Abre la vista de respuestas del SII"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Respuestas del SII'),
            'res_model': 'l10n_cl_edi.certification.sii.response',
            'domain': [('project_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_project_id': self.id},
        }

    def action_view_books(self):
        """Abre la vista de libros de compra/venta"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Libros de Compra/Venta'),
            'res_model': 'l10n_cl_edi.certification.book',
            'domain': [('project_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_project_id': self.id},
        }

    def action_open_wizard_generate(self):
        """Abre el wizard para generar documentos"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Documentos'),
            'res_model': 'l10n_cl_edi.certification.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_project_id': self.id},
        }

    # Métodos para Generación Masiva de PDFs (Última Etapa de Certificación)
    def action_bulk_generate_ted(self):
        """
        Genera TED para todos los documentos firmados que no lo tienen.
        Útil para la última etapa de certificación donde se requieren PDFs impresos.
        """
        self.ensure_one()

        # Buscar documentos firmados sin código de barras
        documents = self.env['l10n_cl_edi.certification.generated.document'].search([
            ('project_id', '=', self.id),
            ('xml_dte_signed', '!=', False),
            ('barcode_image', '=', False),
        ])

        if not documents:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin documentos'),
                    'message': _('No hay documentos firmados pendientes de generar TED y código de barras.'),
                    'type': 'warning',
                }
            }

        # Generar TED para cada documento
        success_count = 0
        error_count = 0
        errors = []

        for doc in documents:
            try:
                doc.action_generate_ted()
                success_count += 1
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                errors.append(f'{doc.complete_name}: {error_msg}')

        # Mensaje de resultado
        message = _(
            'TED generado exitosamente para %d documentos.%s'
        ) % (success_count, '\n\nErrores:\n' + '\n'.join(errors) if errors else '')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TED Generados'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True if error_count > 0 else False,
            }
        }

    def action_bulk_generate_pdf(self):
        """
        Genera PDFs impresos para todos los documentos con TED que no tienen PDF.
        Útil para la última etapa de certificación donde se requieren PDFs impresos.
        """
        self.ensure_one()

        # Buscar documentos con TED sin PDF
        documents = self.env['l10n_cl_edi.certification.generated.document'].search([
            ('project_id', '=', self.id),
            ('ted_xml', '!=', False),
            ('pdf_file', '=', False),
        ])

        if not documents:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin documentos'),
                    'message': _('No hay documentos con TED pendientes de generar PDF.'),
                    'type': 'warning',
                }
            }

        # Generar PDF para cada documento
        success_count = 0
        error_count = 0
        errors = []

        for doc in documents:
            try:
                doc.action_generate_pdf()
                success_count += 1
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                errors.append(f'{doc.complete_name}: {error_msg}')

        # Mensaje de resultado
        message = _(
            'PDF generado exitosamente para %d documentos.%s'
        ) % (success_count, '\n\nErrores:\n' + '\n'.join(errors) if errors else '')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('PDFs Generados'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True if error_count > 0 else False,
            }
        }
