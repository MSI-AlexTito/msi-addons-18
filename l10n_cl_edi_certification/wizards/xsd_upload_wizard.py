# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class XsdUploadWizard(models.TransientModel):
    """
    Wizard para subir esquemas XSD del SII como adjuntos.
    Facilita la instalación de esquemas para validación local.
    """
    _name = 'l10n_cl_edi.xsd.upload.wizard'
    _description = 'Asistente de Carga de Esquemas XSD'

    # Archivos XSD
    dte_xsd_file = fields.Binary(
        string='DTE_v10.xsd',
        help='Esquema para Documentos Tributarios Electrónicos'
    )
    dte_xsd_filename = fields.Char(
        string='Nombre DTE',
        default='DTE_v10.xsd'
    )

    envio_dte_xsd_file = fields.Binary(
        string='EnvioDTE_v10.xsd',
        help='Esquema para Sobres de Envío'
    )
    envio_dte_xsd_filename = fields.Char(
        string='Nombre EnvioDTE',
        default='EnvioDTE_v10.xsd'
    )

    respuesta_dte_xsd_file = fields.Binary(
        string='RespuestaDTE_v10.xsd',
        help='Esquema para Respuestas del SII'
    )
    respuesta_dte_xsd_filename = fields.Char(
        string='Nombre RespuestaDTE',
        default='RespuestaDTE_v10.xsd'
    )

    sii_types_xsd_file = fields.Binary(
        string='SiiTypes_v10.xsd',
        help='Esquema de tipos comunes (dependencia)'
    )
    sii_types_xsd_filename = fields.Char(
        string='Nombre SiiTypes',
        default='SiiTypes_v10.xsd'
    )

    # Estado
    existing_schemas = fields.Text(
        string='Esquemas Existentes',
        compute='_compute_existing_schemas',
        readonly=True
    )

    @api.depends('dte_xsd_file')
    def _compute_existing_schemas(self):
        """Muestra qué esquemas ya están instalados"""
        for wizard in self:
            prefix = 'l10n_cl_edi_certification'
            schemas = [
                'DTE_v10.xsd',
                'EnvioDTE_v10.xsd',
                'RespuestaDTE_v10.xsd',
                'SiiTypes_v10.xsd'
            ]

            existing = []
            missing = []

            for schema in schemas:
                full_name = f"{prefix}.{schema}"
                attachment = self.env['ir.attachment'].search([
                    ('name', '=', full_name)
                ], limit=1)

                if attachment:
                    existing.append(f"✓ {schema}")
                else:
                    missing.append(f"✗ {schema}")

            result = "Esquemas instalados:\n" + "\n".join(existing)
            if missing:
                result += "\n\nEsquemas faltantes:\n" + "\n".join(missing)

            wizard.existing_schemas = result

    def action_upload_schemas(self):
        """Sube los esquemas XSD como adjuntos en ir.attachment"""
        self.ensure_one()

        prefix = 'l10n_cl_edi_certification'
        uploaded = []
        updated = []

        schemas_to_upload = [
            (self.dte_xsd_file, 'DTE_v10.xsd'),
            (self.envio_dte_xsd_file, 'EnvioDTE_v10.xsd'),
            (self.respuesta_dte_xsd_file, 'RespuestaDTE_v10.xsd'),
            (self.sii_types_xsd_file, 'SiiTypes_v10.xsd'),
        ]

        for xsd_file, filename in schemas_to_upload:
            if not xsd_file:
                continue  # Saltar si no se subió este archivo

            full_name = f"{prefix}.{filename}"

            # Buscar si ya existe
            existing = self.env['ir.attachment'].search([
                ('name', '=', full_name)
            ], limit=1)

            if existing:
                # Actualizar existente
                existing.write({
                    'raw': xsd_file,
                })
                updated.append(filename)
            else:
                # Crear nuevo
                self.env['ir.attachment'].create({
                    'name': full_name,
                    'raw': xsd_file,
                    'public': True,
                    'description': f'Esquema XSD del SII para validación de documentos electrónicos chilenos',
                })
                uploaded.append(filename)

        # Mensaje de resultado
        messages = []
        if uploaded:
            messages.append(f"Esquemas subidos: {', '.join(uploaded)}")
        if updated:
            messages.append(f"Esquemas actualizados: {', '.join(updated)}")

        if not uploaded and not updated:
            raise UserError(_('No se seleccionó ningún archivo XSD para subir.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Esquemas XSD Instalados'),
                'message': '\n'.join(messages),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_delete_schemas(self):
        """Elimina todos los esquemas XSD del módulo"""
        self.ensure_one()

        prefix = 'l10n_cl_edi_certification'
        attachments = self.env['ir.attachment'].search([
            ('name', 'like', f'{prefix}.%'),
            ('name', 'like', '%.xsd')
        ])

        count = len(attachments)
        if count == 0:
            raise UserError(_('No hay esquemas XSD instalados para eliminar.'))

        attachments.unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Esquemas Eliminados'),
                'message': _('%s esquema(s) XSD fueron eliminados.') % count,
                'type': 'warning',
                'sticky': False,
            }
        }
