# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class CertificationCase(models.Model):
    """
    Caso de Prueba Asignado a un Proyecto de Certificación.
    Basado en un template pero con datos específicos del proyecto.
    """
    _name = 'l10n_cl_edi.certification.case'
    _description = 'Caso de Prueba de Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'project_id, sequence, id'
    _rec_name = 'complete_name'

    # Relaciones
    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        index=True
    )
    template_id = fields.Many2one(
        'l10n_cl_edi.test.case.template',
        string='Plantilla',
        help='Plantilla base de la que se creó este caso'
    )

    # Identificación
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    name = fields.Char(
        string='Nombre',
        required=True
    )
    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )
    code = fields.Char(
        string='Código',
        help='Código del caso (ej: 033-001)'
    )

    # Tipo de Documento
    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de Documento',
        required=True,
        domain=[('country_id.code', '=', 'CL'), ('internal_type', '=', 'invoice')]
    )
    document_type_code = fields.Char(
        related='document_type_id.code',
        string='Código Documento',
        store=True
    )

    # Folio Asignado
    folio_assigned = fields.Integer(
        string='Folio Asignado',
        readonly=True,
        help='Folio que se asignó a este caso al generar el documento'
    )

    # Referencias (para NC/ND)
    reference = fields.Char(
        string='Referencia'
    )
    reference_reason = fields.Char(
        string='Razón de Referencia'
    )
    reference_case_id = fields.Many2one(
        'l10n_cl_edi.certification.case',
        string='Caso de Referencia',
        help='Caso original al que hace referencia (para NC/ND)'
    )

    # Descuento Global
    global_discount = fields.Float(
        string='Descuento Global %',
        digits=(5, 2)
    )

    # Líneas
    line_ids = fields.One2many(
        'l10n_cl_edi.certification.case.line',
        'case_id',
        string='Líneas de Detalle'
    )

    # Documento Generado
    generated_document_id = fields.Many2one(
        'l10n_cl_edi.certification.generated.document',
        string='Documento Generado',
        readonly=True,
        help='Documento DTE generado para este caso'
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('ready', 'Listo'),
        ('generated', 'Generado'),
        ('validated', 'Validado'),
        ('sent', 'Enviado'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Descripción
    description = fields.Text(
        string='Descripción'
    )

    # Montos Computados
    subtotal_taxable = fields.Monetary(
        string='Subtotal Afecto',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    subtotal_exempt = fields.Monetary(
        string='Subtotal Exento',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    discount_amount = fields.Monetary(
        string='Descuento Global',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    tax_amount = fields.Monetary(
        string='IVA',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    total_amount = fields.Monetary(
        string='Total',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.ref('base.CLP').id
    )

    # Computed fields
    @api.depends('code', 'name')
    def _compute_complete_name(self):
        for record in self:
            if record.code:
                record.complete_name = f"[{record.code}] {record.name}"
            else:
                record.complete_name = record.name

    @api.depends('line_ids.subtotal', 'line_ids.exempt', 'global_discount')
    def _compute_amounts(self):
        """Calcula los montos del caso"""
        for case in self:
            # Calcular subtotales
            subtotal_taxable = sum(line.subtotal for line in case.line_ids if not line.exempt)
            subtotal_exempt = sum(line.subtotal for line in case.line_ids if line.exempt)

            # Aplicar descuento global solo al subtotal afecto
            discount_amount = 0
            if case.global_discount and subtotal_taxable:
                discount_amount = subtotal_taxable * (case.global_discount / 100.0)
                subtotal_taxable -= discount_amount

            # Calcular IVA (19% sobre subtotal afecto)
            tax_amount = subtotal_taxable * 0.19

            # Total
            total_amount = subtotal_taxable + tax_amount + subtotal_exempt

            case.subtotal_taxable = subtotal_taxable
            case.subtotal_exempt = subtotal_exempt
            case.discount_amount = discount_amount
            case.tax_amount = tax_amount
            case.total_amount = total_amount

    # Métodos
    @api.model
    def create_from_template(self, template, project):
        """Crea un caso a partir de un template"""
        # Obtener moneda CLP
        currency_clp = self.env.ref('base.CLP', raise_if_not_found=False)
        if not currency_clp:
            # Fallback: buscar CLP en el sistema
            currency_clp = self.env['res.currency'].search([('name', '=', 'CLP')], limit=1)

        # Crear el caso
        case_vals = {
            'project_id': project.id,
            'template_id': template.id,
            'name': template.name,
            'code': template.code,
            'document_type_id': template.document_type_id.id,
            'reference': template.reference,
            'reference_reason': template.reference_reason,
            'global_discount': template.global_discount,
            'description': template.description,
            'currency_id': currency_clp.id if currency_clp else False,
        }
        case = self.create(case_vals)

        # Crear las líneas
        CaseLine = self.env['l10n_cl_edi.certification.case.line']
        for template_line in template.line_ids:
            CaseLine.create({
                'case_id': case.id,
                'sequence': template_line.sequence,
                'description': template_line.description,
                'qty': template_line.qty,
                'price_unit': template_line.price_unit,
                'discount': template_line.discount,
                'exempt': template_line.exempt,
            })

        # Forzar recalculo de montos
        case._compute_amounts()

        return case

    def action_prepare(self):
        """Prepara el caso para generación"""
        for case in self:
            # Validar que tenga líneas, excepto para NC/ND que solo corrigen encabezado
            is_credit_note = case.document_type_code == '56'
            is_debit_note = case.document_type_code == '61'
            has_reference = bool(case.reference_reason)

            # Permitir casos sin líneas solo para NC/ND con referencia (corrección de encabezado)
            allows_no_lines = (is_credit_note or is_debit_note) and has_reference

            if not case.line_ids and not allows_no_lines:
                raise UserError(_(
                    'El caso debe tener al menos una línea.\n\n'
                    'Nota: Las Notas de Crédito/Débito pueden no tener líneas '
                    'solo cuando corrigen datos del encabezado de otro documento.'
                ))

            case.state = 'ready'
            case.message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_case_prepared')
            )

    def action_generate(self):
        """Genera el documento DTE para este caso"""
        import logging
        _logger = logging.getLogger(__name__)

        for case in self:
            if case.state not in ['ready', 'generated']:
                raise UserError(_('El caso debe estar en estado Listo o Generado.'))

            # Si ya existe un documento generado, eliminarlo (regeneración)
            if case.generated_document_id:
                print(f'🔄 Regenerando documento para caso {case.name} - Eliminando documento anterior ID {case.generated_document_id.id}')
                old_document = case.generated_document_id
                case.write({'generated_document_id': False})
                old_document.unlink()

            # Llamar al servicio de generación
            generator = self.env['l10n_cl_edi.dte.generator.service']
            document = generator.generate_dte_for_case(case)

            print(f'✓ Documento generado: ID {document.id}, Folio: {document.folio}')

            case.write({
                'generated_document_id': document.id,
                'folio_assigned': document.folio,
                'state': 'generated',
            })
            case.with_context(folio=document.folio).message_post_with_source(
                source_ref=self.env.ref('l10n_cl_edi_certification.message_case_generated')
            )

        return True

    def action_validate(self):
        """Valida el documento generado"""
        for case in self:
            if not case.generated_document_id:
                raise UserError(_('Debe generar el documento primero.'))

            # Llamar al servicio de validación
            validator = self.env['l10n_cl_edi.validation.service']
            is_valid, messages = validator.validate_document(case.generated_document_id)

            if is_valid:
                case.state = 'validated'
                case.message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_case_validated')
                )
            else:
                case.with_context(validation_messages=messages).message_post_with_source(
                    source_ref=self.env.ref('l10n_cl_edi_certification.message_case_validation_errors')
                )
                raise UserError(_('El documento tiene errores de validación. Revise el chatter.'))

        return True

    def action_back_to_draft(self):
        """Regresa el caso a borrador"""
        for case in self:
            case.state = 'draft'

    def action_view_generated_document(self):
        """Abre el documento generado"""
        self.ensure_one()
        if not self.generated_document_id:
            raise UserError(_('No hay documento generado para este caso.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Documento Generado'),
            'res_model': 'l10n_cl_edi.certification.generated.document',
            'res_id': self.generated_document_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_normalize_item_names(self):
        """
        Normaliza todos los nombres de items a ASCII (sin acentos)
        para evitar problemas de encoding en XMLs.
        """
        import unicodedata

        def normalize_to_ascii(text):
            """Normaliza texto a ASCII eliminando acentos"""
            if not text:
                return text
            normalized = unicodedata.normalize('NFD', text)
            return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

        updated_count = 0
        for case in self:
            for line in case.line_ids:
                if line.description:
                    normalized_desc = normalize_to_ascii(line.description)
                    if normalized_desc != line.description:
                        print(f"Normalizando: '{line.description}' → '{normalized_desc}'")
                        line.description = normalized_desc
                        updated_count += 1

        if updated_count > 0:
            self.env.cr.commit()  # Guardar cambios
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Nombres normalizados'),
                    'message': _('%d líneas actualizadas exitosamente') % updated_count,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin cambios'),
                    'message': _('No se encontraron nombres para normalizar'),
                    'type': 'info',
                    'sticky': False,
                }
            }
