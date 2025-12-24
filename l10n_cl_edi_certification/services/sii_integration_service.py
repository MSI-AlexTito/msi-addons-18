# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import base64
import logging
from lxml import etree

_logger = logging.getLogger(__name__)


class SiiIntegrationService(models.AbstractModel):
    """
    Servicio para Integración con el SII.
    REUTILIZA la lógica de l10n_cl.edi.util de Odoo Enterprise.
    """
    _name = 'l10n_cl_edi.sii.integration.service'
    _description = 'Servicio de Integración con SII'
    _inherit = 'l10n_cl.edi.util'  # Heredar utilidades de Enterprise

    def _log_xml_pretty(self, xml_data, label):
        """Helper para loggear XML de forma legible"""
        pass

    def message_post(self, **kwargs):
        """
        Método dummy para evitar errores cuando l10n_cl.edi.util intenta postear mensajes.
        Como este es un AbstractModel, solo logueamos el mensaje.
        """
        return True

    @api.model
    def authenticate(self, project):
        """
        Autentica con el SII usando la lógica de Enterprise.
        USA SOLO DATOS DEL CLIENTE, no de la company (somos certificadores, no el emisor).

        Args:
            project: l10n_cl_edi.certification.project

        Returns:
            str: Token de autenticación
        """
        client_info = project.client_info_id
        if not client_info:
            raise UserError(_('No hay información del cliente configurada.'))

        # Mapear environment a mode/provider de Enterprise
        if client_info.environment == 'certification':
            mode = 'SIITEST'  # maullin.sii.cl
        else:
            mode = 'SII'  # palena.sii.cl

        try:
            # Crear certificado temporal con los datos del CLIENTE
            certificate = self._get_certificate(client_info, project.company_id)

            # Obtener token usando método heredado _get_token(mode, digital_signature)
            token = self._get_token(mode, certificate)

            return token

        except Exception as e:
            print(f'\n❌ Error en autenticación SII: {str(e)}')
            import traceback
            traceback.print_exc()
            raise UserError(_('Error al autenticar con SII: %s') % str(e))

    def _get_certificate(self, client_info, company_id):
        """
        Crea un objeto certificate.certificate temporal con los datos del CLIENTE.
        Este objeto es lo que los métodos de l10n_cl.edi.util esperan.
        """
        # Obtener certificado y contraseña del cliente
        cert_data, password = client_info.get_certificate_data()

        # Crear objeto certificate.certificate temporal
        # Usamos .new() para crear un objeto en memoria (no se guarda en BD)
        CertificateModel = self.env['certificate.certificate']

        cert_temp = CertificateModel.new({
            'content': base64.b64encode(cert_data),  # Certificado .pfx/.p12
            'pkcs12_password': password,
            'company_id': company_id.id,
        })

        # Forzar el cálculo del subject_serial_number si no está presente
        if not cert_temp.subject_serial_number and cert_temp.pem_certificate:
            cert_temp._compute_subject_serial_number()

        # Si el certificado no tiene subject_serial_number en el Subject del X.509,
        # usar el RUT del cliente (ya que el certificado le pertenece)
        if not cert_temp.subject_serial_number:
            # Asignar manualmente el RUT del cliente al certificado temporal
            cert_temp.subject_serial_number = self._l10n_cl_format_vat(client_info.rut)

        if not cert_temp.is_valid:
            raise UserError(_('El certificado del cliente no es válido o ha expirado.'))

        return cert_temp

    @api.model
    def send_envelope(self, envelope):
        """
        Envía un sobre al SII usando DATOS DEL CLIENTE.

        Args:
            envelope: l10n_cl_edi.certification.envelope

        Returns:
            tuple: (track_id, response_xml)
        """
        project = envelope.project_id
        client_info = project.client_info_id

        if not envelope.envelope_xml_signed:
            raise UserError(_('El sobre debe estar firmado antes de enviar.'))

        # Mapear environment a mode
        mode = 'SIITEST' if client_info.environment == 'certification' else 'SII'

        try:
            # Crear certificado temporal del cliente
            certificate = self._get_certificate(client_info, project.company_id)

            # Preparar XML (ISO-8859-1 encoding requerido por SII)
            xml_content = base64.b64decode(envelope.envelope_xml_signed).decode('ISO-8859-1')

            # LOG: Mostrar el XML completo del sobre firmado
            self._log_xml_pretty(xml_content, f'XML ENVIODTE FIRMADO COMPLETO - {envelope.name}')

            # ============================================================================
            # 🛑 MODO DEBUG: VERIFICAR XML ANTES DE ENVIAR
            # ============================================================================
            # COMENTADO - XML verificado, listo para enviar al SII
            # raise UserError(_(
            #     '🛑 MODO DEBUG ACTIVADO\n\n'
            #     'El sobre NO se envió al SII.\n'
            #     'Revisa los logs para verificar que el XML esté correcto.\n\n'
            #     'Información del sobre:\n'
            #     '- Nombre: %s\n'
            #     '- Documentos: %d\n'
            #     '- Tamaño XML: %d caracteres\n\n'
            #     'Para enviar al SII, comenta el "raise UserError" en:\n'
            #     'services/sii_integration_service.py línea ~177'
            # ) % (envelope.name, envelope.documents_count, len(xml_content)))
            # ============================================================================

            # Normalizar RUT del cliente (remover puntos, mantener guión y DV)
            formatted_rut = self._l10n_cl_format_vat(client_info.rut)  # Ej: "76393041-K"

            # Preparar parámetros para el upload
            file_name = f'EnvioDTE_{envelope.name}.xml'
            params = {
                'rutSender': formatted_rut[:-2],  # Número sin DV ni guión: "76393041"
                'dvSender': formatted_rut[-1],  # Solo el DV: "K"
                'rutCompany': formatted_rut[:-2],  # Mismo RUT (es el emisor)
                'dvCompany': formatted_rut[-1],
                'archivo': (file_name, xml_content.encode('ISO-8859-1', 'replace'), 'text/xml'),
            }

            # Sitio web del cliente (usar sitio genérico)
            company_website = 'http://www.odoo.com'

            # Enviar usando método heredado: _send_xml_to_sii(mode, company_website, params, digital_signature, post)
            response = self._send_xml_to_sii(
                mode,
                company_website,
                params,
                certificate,
                '/cgi_dte/UPL/DTEUpload'  # Endpoint para envío de DTEs
            )

            if not response:
                raise UserError(_('No se obtuvo respuesta del SII'))

            # LOG: Mostrar respuesta del SII
            self._log_xml_pretty(response, 'RESPUESTA SII - ENVÍO DE SOBRE')

            # Extraer Track ID de la respuesta
            track_id = self._extract_track_id(response)

            return track_id, response

        except Exception as e:
            print(f'\n❌ ERROR AL ENVIAR SOBRE AL SII: {str(e)}')
            import traceback
            print(traceback.format_exc())
            raise UserError(_('Error al enviar al SII: %s') % str(e))

    def _extract_track_id(self, response_xml):
        """Extrae el Track ID de la respuesta del SII"""
        try:
            from lxml import etree
            xml_doc = etree.fromstring(response_xml.encode('utf-8') if isinstance(response_xml, str) else response_xml)

            # Buscar TRACKID en diferentes ubicaciones posibles
            track_nodes = xml_doc.xpath('//TRACKID')
            if track_nodes:
                return track_nodes[0].text

            # Si no se encuentra, buscar en otras ubicaciones
            track_nodes = xml_doc.xpath('//SII:TRACKID', namespaces={'SII': 'http://www.sii.cl/XMLSchema'})
            if track_nodes:
                return track_nodes[0].text

            raise UserError(_('No se pudo obtener Track ID de la respuesta del SII'))

        except Exception as e:
            print(f'❌ Error extrayendo Track ID: {str(e)}')
            # Retornar un ID temporal si falla
            import uuid
            return str(uuid.uuid4())[:10]

    @api.model
    def check_status(self, track_id, project):
        """
        Consulta el estado de un envío en el SII usando DATOS DEL CLIENTE.

        Args:
            track_id (str): ID de seguimiento
            project: l10n_cl_edi.certification.project

        Returns:
            tuple: (status, response_xml)
        """
        client_info = project.client_info_id

        # Mapear environment a mode
        mode = 'SIITEST' if client_info.environment == 'certification' else 'SII'

        try:
            # Crear certificado temporal del cliente
            certificate = self._get_certificate(client_info, project.company_id)

            # Normalizar RUT del cliente
            formatted_rut = self._l10n_cl_format_vat(client_info.rut)

            # Consultar estado usando método heredado: _get_send_status(mode, track_id, company_vat, digital_signature)
            response = self._get_send_status(
                mode,
                track_id,
                formatted_rut,  # RUT del cliente (company_vat) formato "76393041-K"
                certificate
            )

            if not response:
                raise UserError(_('No se obtuvo respuesta del SII al consultar estado'))

            # LOG: Mostrar respuesta del SII
            self._log_xml_pretty(response, f'RESPUESTA SII - CONSULTA DE ESTADO (Track: {track_id})')

            # Parsear respuesta para obtener estado
            status = self._parse_status_response(response)

            return status, response

        except Exception as e:
            print(f'\n❌ ERROR AL CONSULTAR ESTADO EN SII - Track ID: {track_id} - Error: {str(e)}')
            import traceback
            print(traceback.format_exc())
            raise UserError(_('Error al consultar estado: %s') % str(e))

    @api.model
    def send_book(self, book):
        """
        Envía un LibroCompraVenta al SII usando DATOS DEL CLIENTE.

        Args:
            book: l10n_cl_edi.certification.book

        Returns:
            tuple: (track_id, response_xml)
        """
        project = book.project_id
        client_info = project.client_info_id

        if not book.book_xml_signed:
            raise UserError(_('El libro debe estar firmado antes de enviar.'))

        # Mapear environment a mode
        mode = 'SIITEST' if client_info.environment == 'certification' else 'SII'

        try:
            # Crear certificado temporal del cliente
            certificate = self._get_certificate(client_info, project.company_id)

            # Preparar XML (ISO-8859-1 encoding requerido por SII)
            xml_content = base64.b64decode(book.book_xml_signed).decode('ISO-8859-1')

            # LOG: Mostrar el XML completo del libro firmado
            self._log_xml_pretty(xml_content, f'XML LIBRO {book.book_type.upper()} FIRMADO COMPLETO - {book.name}')

            # IMPORTANTE: Para libros, los parámetros deben coincidir con el XML:
            # - rutSender/dvSender = RutEnvia del XML (RUT del cliente/certificado)
            # - rutCompany/dvCompany = RutEmisorLibro del XML (RUT de la empresa)
            company = project.company_id
            if not company or not company.partner_id.vat:
                raise UserError(_('La compañía debe tener un RUT configurado.'))

            # Normalizar RUTs (remover puntos, mantener guión y DV)
            company_rut = self._l10n_cl_format_vat(company.partner_id.vat)  # RutEmisorLibro: "77697659-8"
            client_rut = self._l10n_cl_format_vat(client_info.rut)  # RutEnvia: "8530047-4"

            # Preparar parámetros para el upload
            book_type_str = 'Ventas' if book.book_type == 'sale' else 'Compras'
            file_name = f'Libro{book_type_str}_{book.period.replace("-", "")}.xml'

            params = {
                # rutSender: Quien envía (RutEnvia en XML = cliente/certificado)
                'rutSender': client_rut[:-2],  # "8530047"
                'dvSender': client_rut[-1],     # "4"

                # rutCompany: Empresa emisora del libro (RutEmisorLibro en XML)
                'rutCompany': company_rut[:-2],  # "77697659"
                'dvCompany': company_rut[-1],    # "8"

                'archivo': (file_name, xml_content.encode('ISO-8859-1', 'replace'), 'text/xml'),
            }

            # Sitio web del cliente (usar sitio genérico)
            company_website = 'http://www.odoo.com'

            # Enviar usando método heredado: _send_xml_to_sii(mode, company_website, params, digital_signature, post)
            response = self._send_xml_to_sii(
                mode,
                company_website,
                params,
                certificate,
                '/cgi_dte/UPL/DTEUpload'  # Mismo endpoint que DTEs
            )

            if not response:
                raise UserError(_('No se obtuvo respuesta del SII'))

            # LOG: Mostrar respuesta del SII
            self._log_xml_pretty(response, 'RESPUESTA SII - ENVÍO DE LIBRO')

            # Extraer Track ID de la respuesta
            track_id = self._extract_track_id(response)

            return track_id, response

        except Exception as e:
            print(f'\n❌ ERROR AL ENVIAR LIBRO AL SII - Libro: {book.name} - Error: {str(e)}')
            import traceback
            print(traceback.format_exc())
            raise UserError(_('Error al enviar libro al SII: %s') % str(e))

    def _parse_status_response(self, response_xml):
        """Parsea la respuesta de estado del SII"""
        try:
            from lxml import etree
            xml_doc = etree.fromstring(response_xml.encode('utf-8') if isinstance(response_xml, str) else response_xml)

            # Buscar estado
            estado_nodes = xml_doc.xpath('//ESTADO')
            if not estado_nodes:
                estado_nodes = xml_doc.xpath('//SII:ESTADO', namespaces={'SII': 'http://www.sii.cl/XMLSchema'})

            if estado_nodes:
                estado_code = estado_nodes[0].text.strip()

                # EPR (Envío Procesado) requiere análisis de los contadores de documentos
                if estado_code == 'EPR':
                    informados = xml_doc.findtext('.//INFORMADOS')
                    aceptados = xml_doc.findtext('.//ACEPTADOS')
                    rechazados = xml_doc.findtext('.//RECHAZADOS')
                    reparos = xml_doc.findtext('.//REPAROS')

                    if informados and aceptados and rechazados:
                        informados = int(informados)
                        aceptados = int(aceptados)
                        rechazados = int(rechazados)
                        reparos = int(reparos) if reparos else 0

                        # Todos aceptados
                        if informados == aceptados and rechazados == 0 and reparos == 0:
                            return 'accepted'
                        # Todos rechazados
                        elif informados == rechazados and aceptados == 0:
                            return 'rejected'
                        # Hay reparos o mezcla de aceptados/rechazados
                        elif reparos > 0 or (aceptados > 0 and rechazados > 0):
                            return 'with_repairs'
                        # Sin procesar aún (todos en 0)
                        elif aceptados == 0 and rechazados == 0:
                            return 'validating'

                # Para libros, primero verificar si hay un estado del libro tributario
                # Buscar el elemento que contiene información del libro tributario
                libro_estado_nodes = xml_doc.xpath('//text()[contains(., "Libro Cerrado")]')
                if libro_estado_nodes:
                    # Si el libro está cerrado, significa que fue aceptado
                    return 'accepted'

                # Buscar estado del libro tributario en el XML
                # Puede estar como "LTC", "LRH", etc.
                libro_tributario_text = xml_doc.xpath('string(//text()[contains(., "Estado del Libro Tributario")])')
                if libro_tributario_text and 'LTC' in libro_tributario_text:
                    # LTC = Libro Cerrado - Información Cuadrada
                    return 'accepted'

                # Mapear otros códigos del SII a nuestros estados
                status_map = {
                    # Estados de DTEs
                    'REC': 'received',  # Recibido (aún no procesado)
                    'PRD': 'validating',  # Procesando
                    'SOK': 'accepted',  # Aceptado
                    'DOK': 'accepted',  # Aceptado (DTE OK)
                    'ACK': 'accepted',  # Aceptado
                    'RCH': 'rejected',  # Rechazado
                    'RCT': 'rejected',  # Rechazado Total
                    'RPR': 'with_repairs',  # Rechazado con Reparos
                    'RLV': 'with_repairs',  # Rechazado Leve

                    # Estados específicos de Libros - Envío
                    'LOK': 'accepted',  # Libro Aceptado - Cuadrado
                    'LRH': 'rejected',  # Libro Rechazado
                    'LRC': 'rejected',  # Libro Rechazado - Carátula inválida
                    'LER': 'with_repairs',  # Libro con Errores/Reparos
                    'LNC': 'validating',  # Libro No Corresponde (problema con tipo de envío, pero el libro puede estar aceptado)

                    # Estados del Libro Tributario (dentro de la respuesta)
                    'LTC': 'accepted',  # Libro Cerrado - Información Cuadrada (ACEPTADO)
                    'LTO': 'validating',  # Libro Abierto (en proceso)
                }

                return status_map.get(estado_code, 'validating')

            return 'validating'

        except Exception as e:
            print(f'❌ Error parseando respuesta de estado: {str(e)}')
            return 'validating'
