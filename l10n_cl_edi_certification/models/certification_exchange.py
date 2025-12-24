# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from lxml import etree

class CertificationExchange(models.Model):
    """
    Proceso de Intercambio para Certificación SII.
    El SII envía un DTE y debemos generar 3 respuestas:
    1. EnvioRecibos (Respuesta de Intercambio)
    2. RecepcionEnvio (Recibo de Mercaderías - Ley 19.983)
    3. ResultadoDTE (Resultado Comercial)
    """
    _name = 'l10n_cl_edi.certification.exchange'
    _description = 'Proceso de Intercambio para Certificación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Nombre',
        required=True,
        default='Nuevo Intercambio',
        tracking=True
    )

    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    # XML Descargado del SII (contiene el DTE de prueba)
    sii_downloaded_xml = fields.Binary(
        string='XML Descargado del SII',
        attachment=True,
        help='XML que descargaste del portal SII con el DTE de prueba para intercambio'
    )
    sii_downloaded_filename = fields.Char(
        string='Nombre Archivo SII',
        default='DTE_SII_Intercambio.xml'
    )

    # Información extraída del DTE principal (para el cliente)
    dte_type = fields.Char(string='Tipo DTE', readonly=True)
    dte_folio = fields.Integer(string='Folio DTE', readonly=True)
    dte_date = fields.Date(string='Fecha Emisión DTE', readonly=True)
    dte_rut_emisor = fields.Char(string='RUT Emisor', readonly=True)
    dte_rut_receptor = fields.Char(string='RUT Receptor', readonly=True)
    dte_monto_total = fields.Integer(string='Monto Total', readonly=True)

    # Información de TODOS los DTEs del sobre (JSON)
    all_dtes_info = fields.Text(
        string='Información de Todos los DTEs',
        readonly=True,
        help='JSON con información de todos los DTEs incluidos en el EnvioDTE del SII'
    )

    # XMLs Generados (3 respuestas)
    # 1. Respuesta de Intercambio (EnvioRecibos)
    envio_recibos_xml = fields.Binary(
        string='1. Respuesta de Intercambio',
        attachment=True,
        help='EnvioRecibos - Acuse de recibo técnico'
    )
    envio_recibos_filename = fields.Char(
        string='Nombre Archivo',
        compute='_compute_filenames',
        store=True
    )

    # 2. Recibo de Mercaderías (RecepcionEnvio - Ley 19.983)
    recepcion_envio_xml = fields.Binary(
        string='2. Recibo de Mercaderías',
        attachment=True,
        help='RecepcionEnvio - Validación Ley 19.983'
    )
    recepcion_envio_filename = fields.Char(
        string='Nombre Archivo',
        compute='_compute_filenames',
        store=True
    )

    # 3. Resultado Comercial (ResultadoDTE)
    resultado_dte_xml = fields.Binary(
        string='3. Resultado Comercial',
        attachment=True,
        help='ResultadoDTE - Aceptación o rechazo del DTE'
    )
    resultado_dte_filename = fields.Char(
        string='Nombre Archivo',
        compute='_compute_filenames',
        store=True
    )

    # Estado del proceso
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('dte_received', 'DTE Recibido'),
        ('responses_generated', 'Respuestas Generadas'),
        ('uploaded_to_sii', 'Subido al SII'),
        ('completed', 'Completado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Notas
    notes = fields.Text(string='Notas')

    @api.depends('name', 'dte_folio')
    def _compute_filenames(self):
        for rec in self:
            base_name = f'Intercambio_{rec.dte_folio}' if rec.dte_folio else 'Intercambio'
            rec.envio_recibos_filename = f'{base_name}_EnvioRecibos.xml'
            rec.recepcion_envio_filename = f'{base_name}_RecepcionEnvio.xml'
            rec.resultado_dte_filename = f'{base_name}_ResultadoDTE.xml'

    def action_process_received_dte(self):
        """
        Procesa el XML descargado del SII y extrae información del DTE.
        El SII proporciona un XML que puede contener el DTE directamente o dentro de un EnvioDTE.
        """
        self.ensure_one()

        if not self.sii_downloaded_xml:
            raise UserError(_('Debe subir el XML descargado del portal SII.'))

        try:
            # Decodificar XML
            xml_data = base64.b64decode(self.sii_downloaded_xml).decode('ISO-8859-1')

            print('\n' + '=' * 100)
            print('PROCESANDO XML DESCARGADO DEL SII')
            print('=' * 100)
            print(f'Tamaño del archivo: {len(xml_data)} bytes')
            print(f'Primeros 200 caracteres:\n{xml_data[:200]}')
            print('=' * 100 + '\n')
            parser = etree.XMLParser(remove_blank_text=True, encoding='ISO-8859-1')
            root = etree.fromstring(xml_data.encode('ISO-8859-1'), parser)

            # Namespace del SII
            ns = {'sii': 'http://www.sii.cl/SiiDte'}

            # Intentar múltiples formas de encontrar el DTE
            # 1. Intentar con namespace
            dte_node = root.xpath('//sii:DTE/sii:Documento', namespaces=ns)

            # 2. Intentar sin namespace
            if not dte_node:
                dte_node = root.xpath('//DTE/Documento')

            # 3. Intentar si el root mismo es DTE
            if not dte_node and root.tag.endswith('DTE'):
                doc_node = root.xpath('.//Documento') or root.xpath('.//sii:Documento', namespaces=ns)
                if doc_node:
                    dte_node = doc_node

            # 4. Intentar si está dentro de SetDTE
            if not dte_node:
                dte_node = root.xpath('//SetDTE/DTE/Documento') or root.xpath('//sii:SetDTE/sii:DTE/sii:Documento', namespaces=ns)

            if not dte_node:
                raise UserError(_(
                    'No se encontró el nodo DTE/Documento en el XML.\n\n'
                    'El XML debe contener un DTE válido del SII.\n'
                    'Revise que el archivo descargado sea el correcto.'
                ))

            print(f'✓ Se encontraron {len(dte_node)} DTE(s) en el XML')

            # Función helper para extraer valores con y sin namespace
            def extract_value(node, xpath_expr):
                """Extrae valor probando con y sin namespace"""
                # Sin namespace
                result = node.xpath(f'.//{xpath_expr}/text()')
                if result:
                    return result[0]
                # Con namespace
                result = node.xpath(f'.//sii:{xpath_expr}/text()', namespaces=ns)
                if result:
                    return result[0]
                return None

            # PROCESAR TODOS los DTEs del sobre (no solo el del cliente)
            client_rut = self.project_id.client_info_id.rut
            doc = None  # DTE principal (para el cliente)
            all_dtes = []  # Información de todos los DTEs

            print(f'\n📋 PROCESANDO TODOS LOS DTEs DEL SOBRE:')
            print(f'   Total de DTEs en el sobre: {len(dte_node)}')
            print(f'   RUT del cliente: {client_rut}')
            print('-' * 100)

            for dte in dte_node:
                # Extraer info de cada DTE
                tipo_dte = extract_value(dte, 'TipoDTE')
                folio = extract_value(dte, 'Folio')
                fch_emis = extract_value(dte, 'FchEmis')
                rut_emisor = extract_value(dte, 'RUTEmisor')
                rut_receptor = extract_value(dte, 'RUTRecep')
                mnt_total = extract_value(dte, 'MntTotal')

                # Guardar info de este DTE
                dte_info = {
                    'TipoDTE': tipo_dte or '',
                    'Folio': folio or '',
                    'FchEmis': fch_emis or '',
                    'RutEmisor': rut_emisor or '',
                    'RutReceptor': rut_receptor or '',
                    'MntTotal': mnt_total or '0',
                }
                all_dtes.append(dte_info)

                print(f'   DTE {len(all_dtes)}: Folio {folio} | Tipo {tipo_dte} | Receptor {rut_receptor}')

                # Identificar el DTE para el cliente
                if rut_receptor == client_rut:
                    print(f'      ✓ Este DTE es para el cliente')
                    doc = dte
                    # Usar esta info como DTE principal
                    tipo_dte_principal = tipo_dte
                    folio_principal = folio
                    fch_emis_principal = fch_emis
                    rut_emisor_principal = rut_emisor
                    rut_receptor_principal = rut_receptor
                    mnt_total_principal = mnt_total

            print('-' * 100)

            if doc is None:
                raise UserError(_(
                    'No se encontró ningún DTE para el RUT %s en el XML.\n\n'
                    'El XML contiene %d DTE(s) pero ninguno tiene como receptor el RUT del cliente.\n'
                    'Verifique que descargó el archivo correcto del SII.'
                ) % (client_rut, len(dte_node)))

            print(f'✓ Se procesaron {len(all_dtes)} DTEs del sobre')
            print(f'✓ DTE principal para el cliente: Folio {folio_principal}')
            print('=' * 100 + '\n')

            # Extraer Digest del EnvioDTE (necesario para las respuestas)
            # El Digest está en la firma del SetDTE
            digest_value = None
            try:
                # Buscar el DigestValue en la firma del SetDTE
                ns_ds = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
                digest_nodes = root.xpath('//ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue/text()', namespaces=ns_ds)
                if digest_nodes:
                    digest_value = digest_nodes[0]
                    print(f'  ✓ Digest extraído del SetDTE: {digest_value[:20]}...')
                else:
                    print('  ⚠ No se encontró Digest en el XML')
            except Exception as e:
                print(f'  ⚠ Error extrayendo Digest: {e}')

            # Actualizar campos
            import json
            self.write({
                'dte_type': tipo_dte_principal or '',
                'dte_folio': int(folio_principal) if folio_principal else 0,
                'dte_date': fch_emis_principal if fch_emis_principal else False,
                'dte_rut_emisor': rut_emisor_principal or '',
                'dte_rut_receptor': rut_receptor_principal or '',
                'dte_monto_total': int(mnt_total_principal) if mnt_total_principal else 0,
                'all_dtes_info': json.dumps(all_dtes, indent=2),  # Guardar todos los DTEs
                'notes': f'Digest del EnvioDTE: {digest_value}\nTotal DTEs en sobre: {len(all_dtes)}' if digest_value else f'Total DTEs en sobre: {len(all_dtes)}',
                'state': 'dte_received',
            })

            self.message_post(body=_(
                'DTE procesado correctamente:\n'
                '- Tipo: %s\n'
                '- Folio: %s\n'
                '- Emisor: %s\n'
                '- Receptor: %s\n'
                '- Monto: $%s'
            ) % (self.dte_type, self.dte_folio, self.dte_rut_emisor, self.dte_rut_receptor, self.dte_monto_total))

            # Recargar el formulario para mostrar los cambios
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'l10n_cl_edi.certification.exchange',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_message': _('✓ DTE procesado correctamente. Ahora puede generar las respuestas.')
                }
            }

        except Exception as e:
            raise UserError(_('Error al procesar el DTE recibido:\n%s') % str(e))

    def action_generate_responses(self):
        """Genera los 3 XMLs de respuesta"""
        self.ensure_one()

        if self.state != 'dte_received':
            raise UserError(_('Debe procesar el DTE recibido primero.'))

        # Llamar al servicio generador
        exchange_service = self.env['l10n_cl_edi.exchange.generator.service']
        exchange_service.generate_exchange_responses(self)

        self.state = 'responses_generated'
        self.message_post(body=_('Se generaron las 3 respuestas de intercambio correctamente.'))

        # Recargar el formulario para mostrar los archivos generados
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.exchange',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_message': _('✓ Respuestas generadas exitosamente. Puede descargar los 3 archivos XML.')
            }
        }

    def action_download_envio_recibos(self):
        """Descarga el XML de EnvioRecibos"""
        self.ensure_one()
        if not self.envio_recibos_xml:
            raise UserError(_('No hay archivo EnvioRecibos generado.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/l10n_cl_edi.certification.exchange/{self.id}/envio_recibos_xml/{self.envio_recibos_filename}?download=true',
            'target': 'self',
        }

    def action_download_recepcion_envio(self):
        """Descarga el XML de RecepcionEnvio"""
        self.ensure_one()
        if not self.recepcion_envio_xml:
            raise UserError(_('No hay archivo RecepcionEnvio generado.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/l10n_cl_edi.certification.exchange/{self.id}/recepcion_envio_xml/{self.recepcion_envio_filename}?download=true',
            'target': 'self',
        }

    def action_download_resultado_dte(self):
        """Descarga el XML de ResultadoDTE"""
        self.ensure_one()
        if not self.resultado_dte_xml:
            raise UserError(_('No hay archivo ResultadoDTE generado.'))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/l10n_cl_edi.certification.exchange/{self.id}/resultado_dte_xml/{self.resultado_dte_filename}?download=true',
            'target': 'self',
        }

    def action_mark_uploaded(self):
        """Marcar como subido al SII"""
        self.ensure_one()
        self.state = 'uploaded_to_sii'
        self.message_post(body=_('Marcado como subido al portal del SII.'))

    def action_mark_completed(self):
        """Marcar como completado"""
        self.ensure_one()
        self.state = 'completed'
        self.message_post(body=_('Proceso de intercambio completado exitosamente.'))

    def action_back_to_draft(self):
        """Regresar a borrador"""
        self.ensure_one()
        self.write({
            'envio_recibos_xml': False,
            'recepcion_envio_xml': False,
            'resultado_dte_xml': False,
            'state': 'draft',
        })
        self.message_post(body=_('Regresado a borrador.'))
