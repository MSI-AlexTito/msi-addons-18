# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64


class CertificationClient(models.Model):
    """
    Información del Cliente para Certificación.
    Almacena un snapshot de los datos del cliente al momento de la certificación
    para mantener histórico inmutable.
    """
    _name = 'l10n_cl_edi.certification.client'
    _description = 'Información del Cliente para Certificación'
    _rec_name = 'partner_id'

    # Relación con Proyecto
    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade'
    )

    # Relación con Partner (referencia, no copia)
    partner_id = fields.Many2one(
        'res.partner',
        string='Empresa Cliente',
        required=True,
        help='Empresa que será certificada'
    )

    # Snapshot de Datos Tributarios (inmutables una vez creados)
    rut = fields.Char(
        string='RUT',
        required=True,
        help='RUT de la empresa cliente'
    )
    social_reason = fields.Char(
        string='Razón Social',
        required=True
    )
    activity_description = fields.Char(
        string='Giro / Actividad',
        required=True,
        help='Descripción de la actividad económica'
    )

    # Dirección
    address = fields.Char(
        string='Dirección',
        required=True
    )
    city = fields.Char(
        string='Ciudad/Comuna',
        required=True
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Región'
    )
    country_id = fields.Many2one(
        'res.country',
        string='País',
        default=lambda self: self.env.ref('base.cl').id
    )

    # Contacto
    email = fields.Char(
        string='Email',
        help='Email para notificaciones'
    )
    phone = fields.Char(
        string='Teléfono'
    )

    # Certificado Digital del Cliente
    certificate_file = fields.Binary(
        string='Archivo Certificado (.pfx/.p12)',
        required=True,
        help='Archivo .pfx o .p12 con el certificado digital del cliente que será certificado'
    )
    certificate_filename = fields.Char(
        string='Nombre del Archivo'
    )
    certificate_password = fields.Char(
        string='Contraseña del Certificado',
        required=True,
        help='Contraseña del certificado digital (se guarda en texto plano en la BD, use con precaución)'
    )
    subject_serial_number = fields.Char(
        string='RUT Emisor del Certificado',
        required=True,
        help='RUT de la persona o entidad que firma el certificado digital.\n'
             'Este RUT se usará como "RutEnvia" en el XML del sobre (EnvioDTE).\n'
             'Formato: 12345678-9'
    )

    # Información Tributaria SII (Requerida para Certificación)
    sii_regional_office = fields.Selection(
        selection='_get_sii_regional_offices',
        string='Oficina Regional SII',
        help='Oficina regional del SII donde está registrada la empresa'
    )
    company_activity_ids = fields.Many2many(
        'l10n_cl.company.activities',
        string='Actividades Económicas',
        help='Códigos de actividad económica registrados en el SII'
    )
    dte_resolution_number = fields.Char(
        string='N° Resolución Exenta SII',
        default='0',
        help='Para CERTIFICACIÓN: usar "0" (cero).\n'
             'Para PRODUCCIÓN: número de resolución entregado por el SII.'
    )
    dte_resolution_date = fields.Date(
        string='Fecha Resolución SII',
        help='Para CERTIFICACIÓN: fecha específica entregada por el SII al iniciar proceso de certificación.\n'
             'Para PRODUCCIÓN: fecha de la resolución exenta del SII.\n\n'
             'IMPORTANTE: Esta fecha la proporciona el SII, NO es la fecha actual.'
    )
    sii_certification_notes = fields.Text(
        string='Notas de Certificación SII',
        help='Información proporcionada por el SII para el proceso de certificación:\n'
             '- Fecha de resolución asignada\n'
             '- Instrucciones específicas\n'
             '- Contacto del SII\n'
             '- Cualquier observación del proceso'
    )

    # Ambiente SII
    environment = fields.Selection([
        ('certification', 'Certificación (maullin.sii.cl)'),
        ('production', 'Producción (palena.sii.cl)'),
    ], string='Ambiente', default='certification', required=True)

    # Metadatos
    snapshot_date = fields.Datetime(
        string='Fecha de Snapshot',
        default=fields.Datetime.now,
        readonly=True,
        help='Fecha en que se capturaron los datos del cliente'
    )

    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre la configuración del cliente'
    )

    # Constraints
    _sql_constraints = [
        ('project_unique', 'unique(project_id)', 'Ya existe información de cliente para este proyecto.'),
    ]

    @api.model
    def _get_sii_regional_offices(self):
        """Obtiene lista de oficinas regionales del SII desde l10n_cl_edi"""
        # Importar la lista desde el módulo de Odoo Enterprise
        try:
            from odoo.addons.l10n_cl_edi.models.res_company import L10N_CL_SII_REGIONAL_OFFICES_ITEMS
            return L10N_CL_SII_REGIONAL_OFFICES_ITEMS
        except ImportError:
            # Si no está disponible, usar lista básica
            return [
                ('ur_SaC', 'Santiago Centro'),
                ('ur_SaN', 'Santiago Norte'),
                ('ur_SaO', 'Santiago Oriente'),
                ('ur_SaP', 'Santiago Poniente'),
                ('ur_SaS', 'Santiago Sur'),
                ('ur_Val', 'Valparaíso'),
                ('ur_Con', 'Concepción'),
            ]

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, captura datos del partner si no se proporcionan"""
        for vals in vals_list:
            if 'partner_id' in vals and vals['partner_id']:
                partner = self.env['res.partner'].browse(vals['partner_id'])

                # Capturar datos del partner si no se proporcionan
                if 'rut' not in vals or not vals.get('rut'):
                    vals['rut'] = partner.vat or ''
                if 'social_reason' not in vals or not vals.get('social_reason'):
                    vals['social_reason'] = partner.name or ''
                if 'activity_description' not in vals or not vals.get('activity_description'):
                    vals['activity_description'] = partner.l10n_cl_activity_description or ''
                if 'address' not in vals or not vals.get('address'):
                    vals['address'] = partner.street or ''
                if 'city' not in vals or not vals.get('city'):
                    vals['city'] = partner.city or ''
                if 'state_id' not in vals or not vals.get('state_id'):
                    vals['state_id'] = partner.state_id.id if partner.state_id else False
                if 'email' not in vals or not vals.get('email'):
                    vals['email'] = partner.email or ''
                if 'phone' not in vals or not vals.get('phone'):
                    vals['phone'] = partner.phone or ''

                # Capturar datos SII desde la company si el partner es una compañía
                if partner.is_company and partner.company_id:
                    company = partner.company_id
                elif partner.parent_id and partner.parent_id.company_id:
                    company = partner.parent_id.company_id
                else:
                    company = self.env.company

                # Capturar información tributaria SII
                if 'sii_regional_office' not in vals:
                    vals['sii_regional_office'] = company.l10n_cl_sii_regional_office if hasattr(company, 'l10n_cl_sii_regional_office') else False
                if 'company_activity_ids' not in vals:
                    vals['company_activity_ids'] = [(6, 0, company.l10n_cl_company_activity_ids.ids)] if hasattr(company, 'l10n_cl_company_activity_ids') else False
                if 'dte_resolution_number' not in vals:
                    vals['dte_resolution_number'] = company.l10n_cl_dte_resolution_number if hasattr(company, 'l10n_cl_dte_resolution_number') else '0'
                if 'dte_resolution_date' not in vals:
                    vals['dte_resolution_date'] = company.l10n_cl_dte_resolution_date if hasattr(company, 'l10n_cl_dte_resolution_date') else False

        return super().create(vals_list)


    def action_test_certificate(self):
        """Prueba que el certificado y contraseña sean válidos"""
        self.ensure_one()

        if not self.certificate_file:
            raise ValidationError(_('Debe cargar un archivo de certificado (.pfx o .p12).'))

        if not self.certificate_password:
            raise ValidationError(_('Debe ingresar la contraseña del certificado.'))

        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography.hazmat.backends import default_backend

            # Decodificar y cargar el certificado
            cert_data = base64.b64decode(self.certificate_file)
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                cert_data,
                self.certificate_password.encode(),
                backend=default_backend()
            )

            # Extraer información del certificado
            subject = certificate.subject
            issuer = certificate.issuer
            not_before = certificate.not_valid_before
            not_after = certificate.not_valid_after

            # Si llegamos aquí, el certificado es válido
            message = _(
                'El certificado es válido.\n\n'
                'Sujeto: %s\n'
                'Emisor: %s\n'
                'Válido desde: %s\n'
                'Válido hasta: %s'
            ) % (
                subject.rfc4514_string(),
                issuer.rfc4514_string(),
                not_before.strftime('%Y-%m-%d'),
                not_after.strftime('%Y-%m-%d')
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✓ Certificado Válido'),
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }

        except Exception as e:
            raise ValidationError(_('Error al validar el certificado: %s\n\nVerifique que el archivo y la contraseña sean correctos.') % str(e))

    def get_certificate_data(self):
        """
        Obtiene los datos del certificado para firmar documentos.
        Retorna tupla: (cert_data_bytes, password_string)
        """
        self.ensure_one()

        if not self.certificate_file:
            raise ValidationError(_(
                'No hay certificado configurado.\n\n'
                'Suba el archivo .pfx/.p12 del cliente en la pestaña "Certificado Digital".'
            ))

        if not self.certificate_password:
            raise ValidationError(_(
                'No hay contraseña del certificado configurada.\n\n'
                'Ingrese la contraseña en la pestaña "Certificado Digital".'
            ))

        cert_data = base64.b64decode(self.certificate_file)
        return (cert_data, self.certificate_password)

    @api.constrains('rut')
    def _check_rut_format(self):
        """Valida el formato básico del RUT"""
        for record in self:
            if record.rut:
                # Remover puntos y guiones
                rut_clean = record.rut.replace('.', '').replace('-', '')
                if not rut_clean:
                    raise ValidationError(_('El RUT no puede estar vacío.'))

                # Verificar que tenga al menos 2 caracteres (número + dígito verificador)
                if len(rut_clean) < 2:
                    raise ValidationError(_('El RUT debe tener al menos 2 caracteres.'))
