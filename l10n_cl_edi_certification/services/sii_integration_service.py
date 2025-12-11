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
        try:
            if isinstance(xml_data, bytes):
                xml_str = xml_data.decode('utf-8', errors='ignore')
            else:
                xml_str = str(xml_data)

            # Intentar formatear el XML
            try:
                parsed = etree.fromstring(xml_str.encode('utf-8') if isinstance(xml_str, str) else xml_str)
                pretty_xml = etree.tostring(parsed, pretty_print=True, encoding='unicode')
                print(f'\n{"="*80}\n{label}\n{"="*80}\n{pretty_xml}\n{"="*80}')
            except:
                # Si no se puede parsear, mostrar como texto (truncado si es muy largo)
                if len(xml_str) > 50000:
                    print(f'\n{"="*80}\n{label}\n{"="*80}\n{xml_str[:25000]}\n... (XML truncado - {len(xml_str)} caracteres totales) ...\n{xml_str[-25000:]}\n{"="*80}')
                else:
                    print(f'\n{"="*80}\n{label}\n{"="*80}\n{xml_str}\n{"="*80}')
        except Exception as e:
            print(f'No se pudo loggear XML para {label}: {e}')

    def message_post(self, **kwargs):
        """
        Método dummy para evitar errores cuando l10n_cl.edi.util intenta postear mensajes.
        Como este es un AbstractModel, solo logueamos el mensaje.
        """
        body = kwargs.get('body', '')
        print(f'SII Integration: {body}')
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
            print(f'\n{"=" * 80}')
            print(f'AUTENTICACIÓN SII - USANDO DATOS DEL CLIENTE')
            print(f'Cliente RUT: {client_info.rut}')
            print(f'Ambiente: {client_info.environment} -> Mode: {mode}')

            # Crear certificado temporal con los datos del CLIENTE
            certificate = self._get_certificate(client_info, project.company_id)

            # Obtener token usando método heredado _get_token(mode, digital_signature)
            token = self._get_token(mode, certificate)

            print(f'✓ Autenticación exitosa - Token obtenido')
            print(f'{"=" * 80}\n')
            return token

        except Exception as e:
            print(f'\n❌ Error en autenticación SII: {str(e)}')
            import traceback
            traceback.print_exc()
            print(f'{"=" * 80}\n')
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

        print(f'  Creando certificate.certificate temporal...')
        print(f'  - Tamaño certificado: {len(cert_data)} bytes')
        print(f'  - Tiene password: {bool(password)}')
        print(f'  - Company ID: {company_id.id} ({company_id.name})')

        cert_temp = CertificateModel.new({
            'content': base64.b64encode(cert_data),  # Certificado .pfx/.p12
            'pkcs12_password': password,
            'company_id': company_id.id,
        })

        print(f'  ✓ Certificado temporal creado')
        print(f'    - subject_common_name: {cert_temp.subject_common_name}')
        print(f'    - subject_serial_number: {cert_temp.subject_serial_number}')
        print(f'    - is_valid: {cert_temp.is_valid}')
        print(f'    - date_end: {cert_temp.date_end}')

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
            print(f'\n{"#" * 100}')
            print(f'ENVIANDO SOBRE DE CERTIFICACIÓN AL SII')
            print(f'{"#" * 100}')
            print(f'Sobre: {envelope.name}')
            print(f'Proyecto: {project.name}')
            print(f'Cliente: {client_info.partner_id.name}')
            print(f'RUT Cliente: {client_info.rut}')
            print(f'Ambiente: {mode}')
            print(f'Cantidad de documentos: {envelope.documents_count}')

            # Listar documentos incluidos
            print(f'\nDocumentos en el sobre:')
            for doc in envelope.generated_document_ids:
                print(f'  - {doc.complete_name} (Folio: {doc.folio}, Tipo: {doc.document_type_code})')

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

            print(f'\n{"=" * 80}')
            print(f'PARÁMETROS DE ENVÍO AL SII')
            print(f'{"=" * 80}')
            print(f'RUT formateado: {formatted_rut}')
            print(f'rutSender: {params["rutSender"]}')
            print(f'dvSender: {params["dvSender"]}')
            print(f'rutCompany: {params["rutCompany"]}')
            print(f'dvCompany: {params["dvCompany"]}')
            print(f'Archivo: {file_name}')
            print(f'Tamaño XML: {len(xml_content)} caracteres')
            print(f'Website: {company_website}')
            print(f'Endpoint: /cgi_dte/UPL/DTEUpload')
            print(f'{"=" * 80}')

            # Enviar usando método heredado: _send_xml_to_sii(mode, company_website, params, digital_signature, post)
            print(f'\n>>> Iniciando envío al SII...')
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

            # Extraer información adicional de la respuesta
            try:
                response_str = response.decode('utf-8', errors='ignore') if isinstance(response, bytes) else str(response)
                parsed = etree.fromstring(response_str.encode('utf-8') if isinstance(response_str, str) else response_str)

                status = parsed.findtext('.//STATUS')
                timestamp = parsed.findtext('.//TIMESTAMP')
                file_name_resp = parsed.findtext('.//FILE')

                print(f'\n{"=" * 80}')
                print(f'INFORMACIÓN DE RESPUESTA SII')
                print(f'{"=" * 80}')
                print(f'Track ID: {track_id}')
                print(f'Status: {status}')
                print(f'Timestamp: {timestamp}')
                print(f'Archivo: {file_name_resp}')

                # Mapeo de códigos de STATUS
                status_map = {
                    '0': 'Envío recibido correctamente',
                    '1': 'Error en tamaño del archivo',
                    '2': 'Error en archivo (no reconocido)',
                    '3': 'Error en archivo (no contiene XML)',
                    '5': 'Token no válido',
                    '6': 'Error en firma digital',
                    '7': 'RUT emisor no está autorizado',
                }
                if status in status_map:
                    print(f'Descripción: {status_map[status]}')
                print(f'{"=" * 80}')
            except Exception as e:
                print(f'No se pudo extraer información detallada de la respuesta: {e}')

            print(f'\n✅ SOBRE ENVIADO EXITOSAMENTE')
            print(f'Track ID: {track_id}')
            print(f'{"#" * 100}\n')

            return track_id, response

        except Exception as e:
            print(f'\n{"!" * 80}')
            print(f'ERROR AL ENVIAR SOBRE AL SII')
            print(f'{"!" * 80}')
            print(f'Sobre: {envelope.name}')
            print(f'Error: {str(e)}')
            import traceback
            print(traceback.format_exc())
            print(f'{"!" * 80}\n')
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
            print(f'Error extrayendo Track ID: {str(e)}')
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
            print(f'\n{"#" * 100}')
            print(f'CONSULTANDO ESTADO DE SOBRE EN SII')
            print(f'{"#" * 100}')
            print(f'Track ID: {track_id}')
            print(f'Proyecto: {project.name}')
            print(f'Cliente: {client_info.partner_id.name}')
            print(f'RUT Cliente: {client_info.rut}')
            print(f'Ambiente: {mode}')

            # Crear certificado temporal del cliente
            certificate = self._get_certificate(client_info, project.company_id)

            # Normalizar RUT del cliente
            formatted_rut = self._l10n_cl_format_vat(client_info.rut)

            print(f'\n{"=" * 80}')
            print(f'PARÁMETROS DE CONSULTA')
            print(f'{"=" * 80}')
            print(f'RUT formateado: {formatted_rut}')
            print(f'Track ID: {track_id}')
            print(f'{"=" * 80}')

            # Consultar estado usando método heredado: _get_send_status(mode, track_id, company_vat, digital_signature)
            print(f'\n>>> Consultando estado en el SII...')
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

            # Extraer información detallada de la respuesta
            try:
                response_str = response.decode('utf-8', errors='ignore') if isinstance(response, bytes) else str(response)
                parsed = etree.fromstring(response_str.encode('utf-8') if isinstance(response_str, str) else response_str)

                estado = parsed.findtext('.//ESTADO')
                glosa = parsed.findtext('.//GLOSA')
                err_code = parsed.findtext('.//ERR_CODE')

                # Información del cuerpo de la respuesta
                tipo_docto = parsed.findtext('.//TIPO_DOCTO')
                informados = parsed.findtext('.//INFORMADOS')
                aceptados = parsed.findtext('.//ACEPTADOS')
                rechazados = parsed.findtext('.//RECHAZADOS')
                reparos = parsed.findtext('.//REPAROS')

                print(f'\n{"=" * 80}')
                print(f'INFORMACIÓN DETALLADA DE ESTADO')
                print(f'{"=" * 80}')
                print(f'Estado SII: {estado}')
                print(f'Glosa: {glosa}')
                print(f'Código de error: {err_code}')
                print(f'Estado mapeado: {status}')

                if tipo_docto:
                    print(f'\nResumen de documentos:')
                    print(f'  Tipo de documento: {tipo_docto}')
                    print(f'  Informados: {informados}')
                    print(f'  Aceptados: {aceptados}')
                    print(f'  Rechazados: {rechazados}')
                    print(f'  Reparos: {reparos}')

                print(f'{"=" * 80}')

                # Mapeo de estados
                status_description = {
                    'received': 'Recibido - En proceso',
                    'validating': 'Validando documentos',
                    'accepted': 'Aceptado por el SII',
                    'rejected': 'Rechazado por el SII',
                    'with_repairs': 'Aceptado con reparos',
                }

                if status in status_description:
                    print(f'\n📊 {status_description[status]}')

            except Exception as e:
                print(f'No se pudo extraer información detallada de la respuesta: {e}')

            print(f'\n✅ ESTADO CONSULTADO EXITOSAMENTE')
            print(f'Estado: {status}')
            print(f'{"#" * 100}\n')

            return status, response

        except Exception as e:
            print(f'\n{"!" * 80}')
            print(f'ERROR AL CONSULTAR ESTADO EN SII')
            print(f'{"!" * 80}')
            print(f'Track ID: {track_id}')
            print(f'Error: {str(e)}')
            import traceback
            print(traceback.format_exc())
            print(f'{"!" * 80}\n')
            raise UserError(_('Error al consultar estado: %s') % str(e))

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

                # Mapear otros códigos del SII a nuestros estados
                status_map = {
                    'REC': 'received',  # Recibido (aún no procesado)
                    'PRD': 'validating',  # Procesando
                    'SOK': 'accepted',  # Aceptado
                    'DOK': 'accepted',  # Aceptado (DTE OK)
                    'ACK': 'accepted',  # Aceptado
                    'RCH': 'rejected',  # Rechazado
                    'RCT': 'rejected',  # Rechazado Total
                    'RPR': 'with_repairs',  # Rechazado con Reparos
                    'RLV': 'with_repairs',  # Rechazado Leve
                }

                return status_map.get(estado_code, 'validating')

            return 'validating'

        except Exception as e:
            print(f'Error parseando respuesta de estado: {str(e)}')
            return 'validating'
