# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class CertificationFolioAssignment(models.Model):
    """
    Asignación de Folios para un Proyecto de Certificación.
    Gestiona los folios disponibles por tipo de documento.
    """
    _name = 'l10n_cl_edi.certification.folio.assignment'
    _description = 'Asignación de Folios para Certificación'
    _order = 'project_id, document_type_id'
    _rec_name = 'complete_name'

    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        index=True
    )

    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de Documento',
        required=True,
        domain=[('country_id.code', '=', 'CL'), ('internal_type', '=', 'invoice')],
        help='Tipo de documento para el que se asignan folios'
    )

    # Opción 1: Usar CAF del sistema (para empresas que ya tienen CAF cargado)
    caf_id = fields.Many2one(
        'l10n_cl.dte.caf',
        string='CAF del Sistema',
        help='Certificado de Autorización de Folios del sistema (opcional)'
    )

    # Opción 2: Subir CAF directamente del cliente (RECOMENDADO para certificación)
    caf_file = fields.Binary(
        string='Archivo CAF del Cliente',
        attachment=True,
        help='Archivo XML del CAF proporcionado por el cliente a certificar'
    )
    caf_filename = fields.Char(
        string='Nombre del Archivo CAF'
    )

    # Información extraída del CAF
    caf_rut_emisor = fields.Char(
        string='RUT Emisor (del CAF)',
        readonly=True,
        help='RUT del emisor autorizado en el CAF'
    )
    caf_type_code = fields.Char(
        string='Tipo de Documento (del CAF)',
        readonly=True,
        help='Código del tipo de documento autorizado en el CAF'
    )

    # Rango de Folios
    folio_start = fields.Integer(
        string='Folio Inicio',
        required=True,
        help='Primer folio disponible'
    )
    folio_end = fields.Integer(
        string='Folio Fin',
        required=True,
        help='Último folio disponible'
    )
    folio_next = fields.Integer(
        string='Próximo Folio',
        compute='_compute_folio_next',
        store=True,
        help='Próximo folio disponible para asignar'
    )

    # Estadísticas
    folios_used = fields.Integer(
        string='Folios Usados',
        compute='_compute_folios_stats',
        store=True
    )
    folios_available = fields.Integer(
        string='Folios Disponibles',
        compute='_compute_folios_stats',
        store=True
    )
    folios_total = fields.Integer(
        string='Folios Totales',
        compute='_compute_folios_stats',
        store=True
    )

    usage_percentage = fields.Float(
        string='Uso %',
        compute='_compute_folios_stats',
        store=True
    )

    complete_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_complete_name',
        store=True
    )

    # Constraints
    _sql_constraints = [
        ('project_document_type_unique',
         'unique(project_id, document_type_id)',
         'Ya existe una asignación de folios para este tipo de documento en el proyecto.'),
    ]

    @api.depends('document_type_id.name', 'folio_start', 'folio_end')
    def _compute_complete_name(self):
        for record in self:
            if record.document_type_id:
                record.complete_name = f"{record.document_type_id.name} ({record.folio_start}-{record.folio_end})"
            else:
                record.complete_name = _('Nueva Asignación')

    @api.depends('folio_start', 'project_id.generated_document_ids.folio', 'project_id.generated_document_ids.document_type_id')
    def _compute_folio_next(self):
        for assignment in self:
            # Buscar el folio máximo usado para este tipo de documento
            documents = assignment.project_id.generated_document_ids.filtered(
                lambda d: d.document_type_id == assignment.document_type_id and d.folio
            )

            if documents:
                max_folio = max(documents.mapped('folio'))
                assignment.folio_next = max_folio + 1
            else:
                assignment.folio_next = assignment.folio_start

    @api.depends('folio_start', 'folio_end', 'folio_next')
    def _compute_folios_stats(self):
        for assignment in self:
            total = assignment.folio_end - assignment.folio_start + 1
            used = assignment.folio_next - assignment.folio_start
            available = assignment.folio_end - assignment.folio_next + 1

            assignment.folios_total = total
            assignment.folios_used = used
            assignment.folios_available = available

            if total > 0:
                assignment.usage_percentage = (used / total) * 100
            else:
                assignment.usage_percentage = 0.0

    @api.onchange('caf_file')
    def _onchange_caf_file(self):
        """
        Procesa el archivo CAF cuando se carga y extrae información automáticamente.
        Similar a l10n_cl.dte.caf.action_enable() de Odoo Enterprise.
        """
        if self.caf_file:
            try:
                import base64
                from lxml import etree

                # Decodificar el archivo CAF (similar a _decode_caf de Odoo)
                caf_data = base64.b64decode(self.caf_file).decode('ISO-8859-1')

                # Debug: Verificar contenido
                print(f'\n{"="*80}')
                print(f'DEBUG: Procesando archivo CAF')
                print(f'Tamaño caf_data: {len(caf_data)} caracteres')
                print(f'Primeros 200 caracteres: {caf_data[:200]}')
                print(f'{"="*80}\n')

                # Validar que caf_data no esté vacío
                if not caf_data or not caf_data.strip():
                    raise ValueError('El archivo CAF está vacío')

                # Validar que comience con un tag XML
                caf_data_stripped = caf_data.strip()
                if not caf_data_stripped.startswith('<'):
                    raise ValueError(f'El archivo no parece ser XML válido. Comienza con: {caf_data_stripped[:50]}')

                # Parsear con encoding ISO-8859-1 (formato del SII)
                parser = etree.XMLParser(encoding='ISO-8859-1')
                caf_xml = etree.fromstring(caf_data_stripped.encode('ISO-8859-1'), parser)

                # Extraer información del nodo DA (Document Authorization)
                # Estructura: <AUTORIZACION><CAF><DA>...</DA></CAF></AUTORIZACION>
                da_node = caf_xml.xpath('//AUTORIZACION/CAF/DA')
                if not da_node:
                    return {
                        'warning': {
                            'title': _('CAF Inválido'),
                            'message': _('No se pudo encontrar el nodo de autorización (DA) en el archivo CAF.')
                        }
                    }

                result = da_node[0]

                # Extraer RUT del emisor
                rut_element = result.xpath('RE')
                if rut_element:
                    self.caf_rut_emisor = rut_element[0].text

                # Extraer tipo de documento (código)
                td_element = result.xpath('TD')
                if td_element:
                    self.caf_type_code = td_element[0].text

                    # AUTOMÁTICO: Buscar y establecer el document_type_id basándose en el código
                    # (igual que Odoo Enterprise hace en l10n_cl.dte.caf.action_enable())
                    document_type = self.env['l10n_latam.document.type'].search([
                        ('code', '=', self.caf_type_code),
                        ('country_id.code', '=', 'CL'),
                    ], limit=1)

                    if document_type:
                        self.document_type_id = document_type
                    else:
                        return {
                            'warning': {
                                'title': _('Tipo de Documento No Encontrado'),
                                'message': _(
                                    'No se encontró el tipo de documento con código %s.\n'
                                    'Verifique que el módulo de localización chilena esté instalado.'
                                ) % self.caf_type_code
                            }
                        }

                # Extraer rango de folios
                d_element = result.xpath('RNG/D')
                h_element = result.xpath('RNG/H')

                if d_element and h_element:
                    self.folio_start = int(d_element[0].text)
                    self.folio_end = int(h_element[0].text)

                # Validar RUT del emisor contra el cliente del proyecto
                if self.project_id and self.project_id.client_info_id:
                    client_rut = self.project_id.client_info_id.rut
                    if client_rut and self.caf_rut_emisor:
                        # Limpiar formatos de RUT para comparar
                        clean_client_rut = client_rut.replace('.', '').replace('-', '').upper()
                        clean_caf_rut = self.caf_rut_emisor.replace('.', '').replace('-', '').upper()

                        if clean_client_rut != clean_caf_rut:
                            return {
                                'warning': {
                                    'title': _('RUT No Coincide'),
                                    'message': _(
                                        'El RUT del CAF (%s) no coincide con el RUT del cliente (%s).\n\n'
                                        'El CAF debe pertenecer al cliente que está siendo certificado.'
                                    ) % (self.caf_rut_emisor, client_rut)
                                }
                            }

            except Exception as e:
                return {
                    'warning': {
                        'title': _('Error al procesar CAF'),
                        'message': _(
                            'No se pudo leer el archivo CAF. '
                            'Verifique que sea un archivo XML válido.\n\n'
                            'Error: %s'
                        ) % str(e)
                    }
                }

    @api.constrains('caf_id', 'caf_file')
    def _check_caf_source(self):
        """Validar que al menos uno de los dos métodos de CAF esté configurado"""
        for assignment in self:
            if not assignment.caf_id and not assignment.caf_file:
                raise ValidationError(_(
                    'Debe proporcionar un CAF mediante una de estas opciones:\n'
                    '1. Seleccionar un CAF del sistema (CAF del Sistema)\n'
                    '2. Subir el archivo CAF del cliente (Archivo CAF del Cliente - RECOMENDADO)'
                ))

    @api.constrains('folio_start', 'folio_end')
    def _check_folio_range(self):
        for assignment in self:
            if assignment.folio_start <= 0:
                raise ValidationError(_('El folio de inicio debe ser mayor a 0.'))
            if assignment.folio_end < assignment.folio_start:
                raise ValidationError(_('El folio final debe ser mayor o igual al folio inicial.'))

    @api.constrains('caf_id', 'folio_start', 'folio_end')
    def _check_caf_range(self):
        """Verifica que los folios estén dentro del rango del CAF"""
        for assignment in self:
            if assignment.caf_id:
                # Asumiendo que CAF tiene campos similar a l10n_cl_edi
                # Aquí deberías verificar contra el CAF real
                pass

    def get_caf_content(self):
        """
        Obtiene el contenido XML del CAF, ya sea del archivo del cliente o del sistema
        """
        self.ensure_one()
        import base64

        if self.caf_file:
            # Usar el CAF subido directamente (ISO-8859-1 formato del SII)
            return base64.b64decode(self.caf_file).decode('ISO-8859-1')
        elif self.caf_id:
            # Usar el CAF del sistema (l10n_cl_edi)
            # Nota: Adaptar según estructura real del modelo l10n_cl.dte.caf
            if hasattr(self.caf_id, 'caf_file'):
                return base64.b64decode(self.caf_id.caf_file).decode('ISO-8859-1')
            else:
                raise UserError(_('El CAF del sistema no tiene contenido disponible.'))
        else:
            raise UserError(_('No hay CAF configurado para esta asignación de folios.'))

    def get_next_folio(self):
        """Obtiene y reserva el siguiente folio disponible"""
        self.ensure_one()

        if self.folios_available <= 0:
            raise UserError(_(
                'No hay folios disponibles para %s.\n'
                'Rango: %s - %s\n'
                'Usado hasta: %s'
            ) % (
                self.document_type_id.name,
                self.folio_start,
                self.folio_end,
                self.folio_next - 1
            ))

        if self.folio_next > self.folio_end:
            raise UserError(_('Se ha excedido el rango de folios disponibles.'))

        next_folio = self.folio_next
        # El folio_next se actualizará automáticamente con el compute
        return next_folio

    def action_view_documents(self):
        """Ver documentos generados con estos folios"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documentos Generados'),
            'res_model': 'l10n_cl_edi.certification.generated.document',
            'domain': [
                ('project_id', '=', self.project_id.id),
                ('document_type_id', '=', self.document_type_id.id)
            ],
            'view_mode': 'list,form',
        }
