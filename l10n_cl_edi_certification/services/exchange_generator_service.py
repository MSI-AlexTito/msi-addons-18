# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
from datetime import datetime
import base64
from lxml import etree

class ExchangeGeneratorService(models.AbstractModel):
    """
    Servicio para generar los 3 XMLs de respuesta de intercambio:
    1. EnvioRecibos (Respuesta de Intercambio)
    2. RecepcionEnvio (Recibo de Mercaderías - Ley 19.983)
    3. ResultadoDTE (Resultado Comercial)
    """
    _name = 'l10n_cl_edi.exchange.generator.service'
    _description = 'Servicio Generador de Respuestas de Intercambio'

    @api.model
    def generate_exchange_responses(self, exchange):
        """
        Genera los 3 XMLs de respuesta para el proceso de intercambio.

        Args:
            exchange: l10n_cl_edi.certification.exchange
        """
        print('\n' + '=' * 100)
        print(f'GENERANDO RESPUESTAS DE INTERCAMBIO')
        print('=' * 100)
        print(f'DTE Recibido: Tipo {exchange.dte_type}, Folio {exchange.dte_folio}')
        print(f'Emisor: {exchange.dte_rut_emisor}')
        print(f'Receptor: {exchange.dte_rut_receptor}')
        print(f'Monto: ${exchange.dte_monto_total:,}')
        print('=' * 100 + '\n')

        # Extraer Digest del XML descargado del SII
        digest_value = self._extract_digest_from_sii_xml(exchange)
        if not digest_value:
            raise UserError(_('No se pudo extraer el Digest del XML del SII. Verifique el archivo.'))

        print(f'✓ Digest extraído: {digest_value[:30]}...')

        # 1. Generar RespuestaDTE con RecepcionEnvio (Respuesta de Intercambio)
        print('[1/3] Generando RespuestaDTE con RecepcionEnvio...')
        envio_recibos_xml = self._generate_envio_recibos(exchange, digest_value)
        print(f'  XML generado (primeros 300 chars):\n{envio_recibos_xml[:300]}...')

        # Firmar RespuestaDTE (detecta automáticamente el nodo Resultado)
        print('  Firmando RespuestaDTE con RecepcionEnvio...')
        envio_recibos_signed = self._sign_exchange_xml(envio_recibos_xml, exchange.project_id)

        print(f'\n  📄 ARCHIVO 1 - RespuestaDTE con RecepcionEnvio:')
        print(f'     Tamaño: {len(envio_recibos_signed)} caracteres')
        print(f'     Tiene <Signature>: {"<Signature" in envio_recibos_signed}')
        print(f'     Últimos 150 caracteres:\n{envio_recibos_signed[-150:]}')

        exchange.write({
            'envio_recibos_xml': base64.b64encode(envio_recibos_signed.encode('ISO-8859-1')),
        })
        print('  ✓ RespuestaDTE con RecepcionEnvio guardado en BD\n')

        # 2. Generar EnvioRecibos (Recibo de Mercaderías - Ley 19.983)
        print('[2/3] Generando EnvioRecibos (Recibo de Mercaderías - Ley 19.983)...')
        recepcion_envio_xml = self._generate_recepcion_envio(exchange, digest_value)
        print(f'  XML generado (primeros 300 chars):\n{recepcion_envio_xml[:300]}...')

        # Firmar EnvioRecibos (detecta automáticamente el nodo SetRecibos)
        print('  Firmando EnvioRecibos...')
        recepcion_envio_signed = self._sign_exchange_xml(recepcion_envio_xml, exchange.project_id)

        print(f'\n  📄 ARCHIVO 2 - EnvioRecibos:')
        print(f'     Tamaño: {len(recepcion_envio_signed)} caracteres')
        print(f'     Tiene <Signature>: {"<Signature" in recepcion_envio_signed}')
        print(f'     Últimos 150 caracteres:\n{recepcion_envio_signed[-150:]}')

        exchange.write({
            'recepcion_envio_xml': base64.b64encode(recepcion_envio_signed.encode('ISO-8859-1')),
        })
        print('  ✓ EnvioRecibos guardado en BD\n')

        # 3. Generar RespuestaDTE con ResultadoDTE (Resultado Comercial)
        print('[3/3] Generando RespuestaDTE con ResultadoDTE (Resultado Comercial)...')
        resultado_dte_xml = self._generate_resultado_dte(exchange, digest_value)
        print(f'  XML generado (primeros 300 chars):\n{resultado_dte_xml[:300]}...')

        # Firmar RespuestaDTE (detecta automáticamente el nodo Resultado)
        print('  Firmando RespuestaDTE con ResultadoDTE...')
        resultado_dte_signed = self._sign_exchange_xml(resultado_dte_xml, exchange.project_id)

        print(f'\n  📄 ARCHIVO 3 - RespuestaDTE con ResultadoDTE:')
        print(f'     Tamaño: {len(resultado_dte_signed)} caracteres')
        print(f'     Tiene <Signature>: {"<Signature" in resultado_dte_signed}')
        print(f'     Últimos 150 caracteres:\n{resultado_dte_signed[-150:]}')

        exchange.write({
            'resultado_dte_xml': base64.b64encode(resultado_dte_signed.encode('ISO-8859-1')),
        })
        print('  ✓ ResultadoDTE guardado en BD\n')

        print('=' * 100)
        print('✓ LAS 3 RESPUESTAS DE INTERCAMBIO FUERON GENERADAS EXITOSAMENTE')
        print('=' * 100 + '\n')

    def _extract_digest_from_sii_xml(self, exchange):
        """
        Extrae el Digest del XML descargado del SII.
        El Digest está en la firma del SetDTE.
        """
        if not exchange.sii_downloaded_xml:
            return None

        try:
            xml_data = base64.b64decode(exchange.sii_downloaded_xml).decode('ISO-8859-1')
            parser = etree.XMLParser(remove_blank_text=True, encoding='ISO-8859-1')
            root = etree.fromstring(xml_data.encode('ISO-8859-1'), parser)

            # Buscar el DigestValue en la firma del SetDTE
            ns_ds = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}

            # Buscar la firma que referencia SetDoc
            digest_nodes = root.xpath('//ds:Signature/ds:SignedInfo/ds:Reference[@URI="#SetDoc"]/ds:DigestValue/text()', namespaces=ns_ds)

            if not digest_nodes:
                # Intentar sin verificar URI
                digest_nodes = root.xpath('//ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue/text()', namespaces=ns_ds)

            if digest_nodes:
                return digest_nodes[-1]  # Último digest (normalmente es del SetDTE)

            return None
        except Exception as e:
            print(f'Error extrayendo digest: {e}')
            return None

    def _generate_envio_recibos(self, exchange, digest):
        """
        Genera XML de RespuestaDTE con RecepcionEnvio (Respuesta de Intercambio - Acuse de Recibo Técnico)

        Este documento confirma la recepción técnica del DTE.
        RecepcionEnvio contiene elementos RecepcionDTE para TODOS los DTEs del sobre.
        """
        import json
        client_info = exchange.project_id.client_info_id
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # Cargar información de TODOS los DTEs del sobre
        all_dtes = []
        if exchange.all_dtes_info:
            try:
                all_dtes = json.loads(exchange.all_dtes_info)
            except:
                # Fallback: usar solo el DTE principal
                all_dtes = [{
                    'TipoDTE': exchange.dte_type,
                    'Folio': str(exchange.dte_folio),
                    'FchEmis': exchange.dte_date.strftime('%Y-%m-%d') if exchange.dte_date else datetime.now().strftime('%Y-%m-%d'),
                    'RutEmisor': exchange.dte_rut_emisor,
                    'RutReceptor': exchange.dte_rut_receptor,
                    'MntTotal': str(exchange.dte_monto_total),
                }]

        print(f'   Generando RecepcionDTE para {len(all_dtes)} DTE(s)')

        # Datos del recibo
        recibo_data = {
            'NmbEnvio': f'Respuesta_{exchange.dte_folio}',
            'FchRecep': timestamp,  # dateTime completo
            'CodEnvio': str(exchange.id),  # Código interno
            'EnvioDTEID': 'SetDoc',  # ID del SetDTE en el XML del SII
            'Digest': digest,  # Digest real extraído del XML del SII
            'RutEmisor': exchange.dte_rut_emisor,
            'RutReceptor': client_info.rut,
            'RecepEnvio': '0',  # 0=Recibido OK, 1=Fallo Schema, 2=Error firma
            'RecepEnvioGlosa': 'EnvioDTE Recibido Conforme',
            'NroDTE': str(len(all_dtes)),  # Total de DTEs en el sobre
            'TmstFirmaEnv': timestamp,
            'IdRespuesta': '1',
            'NroDetalles': str(len(all_dtes)),  # Total de detalles = total de DTEs
            'NmbContacto': 'Sistema Certificacion',
            'FonoContacto': '+56900000000',
            'MailContacto': client_info.email or 'certificacion@empresa.cl',
            'all_dtes': all_dtes,  # Pasar todos los DTEs al template
        }

        # Generar XML usando template
        xml_content = self.env['ir.qweb']._render('l10n_cl_edi_certification.envio_recibos_template', {
            'recibo_data': recibo_data,
            '__keep_empty_lines': True,
        })

        xml_str = xml_content.decode('ISO-8859-1') if isinstance(xml_content, bytes) else str(xml_content)
        return xml_str

    def _generate_recepcion_envio(self, exchange, digest):
        """
        Genera XML de EnvioRecibos (Recibo de Mercaderías - Ley 19.983)

        Este documento valida el acuse de recibo de mercancías según Ley 19.983.
        """
        client_info = exchange.project_id.client_info_id
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # Datos de recepción
        recepcion_data = {
            'RutResponde': client_info.rut,
            'RutRecibe': exchange.dte_rut_emisor,
            'NroDetalles': '1',
            'TipoDTE': exchange.dte_type,
            'Folio': exchange.dte_folio,
            'FchEmis': exchange.dte_date.strftime('%Y-%m-%d') if exchange.dte_date else datetime.now().strftime('%Y-%m-%d'),
            'RutEmisor': exchange.dte_rut_emisor,
            'RutReceptor': client_info.rut,
            'MntTotal': exchange.dte_monto_total,
            'Recinto': 'Bodega Principal',
            'RutFirma': client_info.rut,
            'Declaracion': 'Se declara bajo juramento que la mercadería ha sido recibida conforme a Ley 19.983',
            'TmstFirmaRecibo': timestamp,
            'TmstFirmaEnv': timestamp,
        }

        # Generar XML usando template
        xml_content = self.env['ir.qweb']._render('l10n_cl_edi_certification.recepcion_envio_template', {
            'recepcion_data': recepcion_data,
            '__keep_empty_lines': True,
        })

        xml_str = xml_content.decode('ISO-8859-1') if isinstance(xml_content, bytes) else str(xml_content)
        return xml_str

    def _generate_resultado_dte(self, exchange, digest):
        """
        Genera XML de RespuestaDTE con ResultadoDTE (Resultado Comercial - Aceptación/Rechazo)

        Este documento indica la aceptación o rechazo comercial del DTE.
        """
        import json
        client_info = exchange.project_id.client_info_id
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # Cargar información de TODOS los DTEs del sobre
        all_dtes = []
        if exchange.all_dtes_info:
            try:
                all_dtes = json.loads(exchange.all_dtes_info)
            except:
                # Fallback: usar solo el DTE principal
                all_dtes = [{
                    'TipoDTE': exchange.dte_type,
                    'Folio': str(exchange.dte_folio),
                    'FchEmis': exchange.dte_date.strftime('%Y-%m-%d') if exchange.dte_date else datetime.now().strftime('%Y-%m-%d'),
                    'RutEmisor': exchange.dte_rut_emisor,
                    'RutReceptor': exchange.dte_rut_receptor,
                    'MntTotal': str(exchange.dte_monto_total),
                }]

        print(f'   Generando ResultadoDTE para {len(all_dtes)} DTE(s)')

        # Datos del resultado
        # Estados posibles:
        # 0 = Aceptado
        # 1 = Reparos (acepta con reparos)
        # 2 = Rechazado
        resultado_data = {
            'NmbEnvio': f'ResultadoComercial_{exchange.dte_folio}',
            'FchRecep': timestamp,  # dateTime completo
            'CodEnvio': str(exchange.id),
            'EnvioDTEID': 'SetDoc',
            'Digest': digest,
            'RutEmisor': exchange.dte_rut_emisor,
            'RutReceptor': client_info.rut,
            'TipoDTE': exchange.dte_type,
            'Folio': exchange.dte_folio,
            'FchEmis': exchange.dte_date.strftime('%Y-%m-%d') if exchange.dte_date else datetime.now().strftime('%Y-%m-%d'),
            'MntTotal': exchange.dte_monto_total,
            'CodRespuesta': '0',  # 0=Aceptado, 1=Aceptado con reparos, 2=Rechazado
            'DescRespuesta': 'DTE Aceptado - Mercadería Conforme',
            'RecepEnvio': '0',
            'RecepEnvioGlosa': 'EnvioDTE Recibido Conforme',
            'NroDTE': str(len(all_dtes)),  # Total de DTEs en el sobre
            'TmstFirmaEnv': timestamp,
            'IdRespuesta': '1',
            'NroDetalles': str(len(all_dtes)),  # Total de detalles = total de DTEs
            'NmbContacto': 'Sistema Certificacion',
            'FonoContacto': '+56900000000',
            'MailContacto': client_info.email or 'certificacion@empresa.cl',
            'all_dtes': all_dtes,  # Pasar todos los DTEs al template
        }

        # Generar XML usando template
        xml_content = self.env['ir.qweb']._render('l10n_cl_edi_certification.resultado_dte_template', {
            'resultado_data': resultado_data,
            '__keep_empty_lines': True,
        })

        xml_str = xml_content.decode('ISO-8859-1') if isinstance(xml_content, bytes) else str(xml_content)
        return xml_str

    def _sign_exchange_xml(self, xml_str, project):
        """
        Firma digitalmente un XML de intercambio usando el certificado del cliente.
        El servicio de firma detecta automáticamente el tipo de documento (RespuestaDTE o EnvioRecibos).

        Args:
            xml_str: String del XML sin firmar
            project: l10n_cl_edi.certification.project

        Returns:
            str: XML firmado
        """
        signature_service = self.env['l10n_cl_edi.signature.service']

        # Obtener certificado del cliente
        client_info = project.client_info_id
        if not client_info:
            raise UserError(_('No hay información del cliente configurada.'))

        # Obtener datos del certificado DEL CLIENTE
        cert_data, cert_password = client_info.get_certificate_data()

        # Firmar usando el método _sign_xml que detecta automáticamente el tipo
        xml_signed = signature_service._sign_xml(
            xml_str,
            cert_data,
            cert_password,
            project.company_id
        )

        return xml_signed
