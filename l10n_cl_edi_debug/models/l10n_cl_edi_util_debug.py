# -*- coding: utf-8 -*-
from odoo import models
import logging
import time
import base64
from lxml import etree

_logger = logging.getLogger(__name__)


class L10nClEdiUtilDebug(models.AbstractModel):
    _inherit = 'l10n_cl.edi.util'

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
                _logger.info(f'\n{"="*80}\n{label}\n{"="*80}\n{pretty_xml}\n{"="*80}')
            except:
                # Si no se puede parsear, mostrar como texto
                _logger.info(f'\n{"="*80}\n{label}\n{"="*80}\n{xml_str}\n{"="*80}')
        except Exception as e:
            _logger.info(f'No se pudo loggear XML para {label}: {e}')

    def _get_seed(self, mode):
        """Log solo si falla después de todos los reintentos"""
        start_time = time.time()
        try:
            result = super()._get_seed(mode)
            elapsed = time.time() - start_time

            # Solo log si tardó mucho (indica reintentos) o falló
            if elapsed > 5 or not result:
                _logger.info(f'SII getSeed: {elapsed:.1f}s, success={bool(result)}, mode={mode}')

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.info(f'SII getSeed FAILED after {elapsed:.1f}s: {type(e).__name__}: {str(e)[:100]}')
            raise

    def _get_token(self, mode, digital_signature):
        """Log token y certificado usado"""
        had_token = bool(digital_signature.last_token)
        start_time = time.time()

        try:
            result = super()._get_token(mode, digital_signature)
            elapsed = time.time() - start_time

            # Log información del token
            _logger.info(f'\n{"="*80}\nTOKEN OBTENIDO\n{"="*80}')
            _logger.info(f'Modo: {mode}')
            _logger.info(f'Tiempo: {elapsed:.1f}s')
            _logger.info(f'Tenía token en cache: {had_token}')
            _logger.info(f'Certificado S/N: {digital_signature.subject_serial_number}')
            _logger.info(f'Token obtenido: {result[:50]}...' if result and len(result) > 50 else f'Token: {result}')
            _logger.info(f'{"="*80}')

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.info(f'SII getToken FAILED after {elapsed:.1f}s (had_cache={had_token}): {str(e)[:100]}')
            raise

    def _send_xml_to_sii(self, mode, company_website, params, digital_signature, post='/cgi_dte/UPL/DTEUpload'):
        """Log completo del envío al SII"""
        start_time = time.time()

        # LOG 1: Información del envío
        _logger.info(f'\n{"="*80}\nENVÍO DTE AL SII - INICIO\n{"="*80}')
        _logger.info(f'Modo: {mode}')
        _logger.info(f'URL: {post}')
        _logger.info(f'Website: {company_website}')
        _logger.info(f'RUT Emisor: {params.get("rutSender")}-{params.get("dvSender")}')
        _logger.info(f'RUT Empresa: {params.get("rutCompany")}-{params.get("dvCompany")}')

        # LOG 2: Archivo XML que se está enviando
        if 'archivo' in params and isinstance(params['archivo'], tuple):
            file_name, file_content, mime_type = params['archivo']
            _logger.info(f'\nArchivo a enviar:')
            _logger.info(f'  Nombre: {file_name}')
            _logger.info(f'  Tipo MIME: {mime_type}')
            _logger.info(f'  Tamaño: {len(file_content)} bytes')

            # Mostrar el XML completo del DTE
            self._log_xml_pretty(file_content, f'XML DTE COMPLETO - {file_name}')

        try:
            result = super()._send_xml_to_sii(mode, company_website, params, digital_signature, post)
            elapsed = time.time() - start_time

            # LOG 3: Respuesta del SII
            _logger.info(f'\n{"="*80}\nRESPUESTA DEL SII\n{"="*80}')
            _logger.info(f'Tiempo de respuesta: {elapsed:.1f}s')

            if result:
                # Parsear y mostrar la respuesta completa
                self._log_xml_pretty(result, 'XML RESPUESTA SII COMPLETA')

                # Extraer información clave de la respuesta
                try:
                    result_str = result.decode('utf-8', errors='ignore') if isinstance(result, bytes) else str(result)
                    parsed = etree.fromstring(result_str.encode('utf-8') if isinstance(result_str, str) else result_str)

                    trackid = parsed.findtext('.//TRACKID')
                    status = parsed.findtext('.//STATUS')

                    _logger.info(f'\nInformación clave de la respuesta:')
                    _logger.info(f'  TRACKID: {trackid}')
                    _logger.info(f'  STATUS: {status}')

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
                        _logger.info(f'  Descripción: {status_map[status]}')
                except Exception as e:
                    _logger.info(f'No se pudo parsear respuesta XML: {e}')
            else:
                _logger.info('Respuesta vacía del SII')

            _logger.info(f'{"="*80}\n')

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.info(f'\n{"="*80}\nERROR EN ENVÍO AL SII\n{"="*80}')
            _logger.info(f'Tiempo transcurrido: {elapsed:.1f}s')
            _logger.info(f'Tipo de error: {type(e).__name__}')
            _logger.info(f'Mensaje: {str(e)}')
            _logger.info(f'{"="*80}\n')
            raise

    def _send_xml_to_sii_rest(self, mode, company_vat, file_name, xml_message, digital_signature):
        """Log completo del envío REST (para boletas)"""
        start_time = time.time()

        _logger.info(f'\n{"="*80}\nENVÍO DTE AL SII REST - INICIO\n{"="*80}')
        _logger.info(f'Modo: {mode}')
        _logger.info(f'RUT Empresa: {company_vat}')
        _logger.info(f'Archivo: {file_name}')

        # Mostrar el XML de la boleta
        self._log_xml_pretty(xml_message, f'XML BOLETA COMPLETO - {file_name}')

        try:
            result = super()._send_xml_to_sii_rest(mode, company_vat, file_name, xml_message, digital_signature)
            elapsed = time.time() - start_time

            _logger.info(f'\n{"="*80}\nRESPUESTA DEL SII REST\n{"="*80}')
            _logger.info(f'Tiempo de respuesta: {elapsed:.1f}s')

            if result:
                _logger.info(f'Respuesta JSON: {result}')
            else:
                _logger.info('Respuesta vacía del SII')

            _logger.info(f'{"="*80}\n')

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.info(f'\nERROR EN ENVÍO REST: {elapsed:.1f}s - {type(e).__name__}: {str(e)}')
            raise

    def _get_send_status(self, mode, track_id, company_vat, digital_signature):
        """Log completo de verificación de estado"""
        _logger.info(f'\n{"="*80}\nVERIFICACIÓN DE ESTADO DTE - INICIO\n{"="*80}')
        _logger.info(f'Modo: {mode}')
        _logger.info(f'Track ID: {track_id}')
        _logger.info(f'RUT Empresa: {company_vat}')

        try:
            result = super()._get_send_status(mode, track_id, company_vat, digital_signature)

            _logger.info(f'\n{"="*80}\nRESPUESTA VERIFICACIÓN DE ESTADO\n{"="*80}')

            if result:
                # Mostrar respuesta completa
                self._log_xml_pretty(result, 'XML RESPUESTA VERIFICACIÓN COMPLETA')

                # Extraer información clave
                try:
                    result_str = result.decode('utf-8', errors='ignore') if isinstance(result, bytes) else str(result)
                    parsed = etree.fromstring(result_str.encode('utf-8') if isinstance(result_str, str) else result_str)

                    estado = parsed.findtext('.//ESTADO')
                    err_code = parsed.findtext('.//ERR_CODE')
                    glosa = parsed.findtext('.//GLOSA')

                    _logger.info(f'\nInformación de estado:')
                    _logger.info(f'  ESTADO: {estado}')
                    _logger.info(f'  ERR_CODE: {err_code}')
                    _logger.info(f'  GLOSA: {glosa}')
                except Exception as e:
                    _logger.info(f'No se pudo parsear respuesta: {e}')
            else:
                _logger.info('Respuesta vacía')

            _logger.info(f'{"="*80}\n')

            return result
        except Exception as e:
            _logger.info(f'\nERROR EN VERIFICACIÓN: {type(e).__name__}: {str(e)}')
            raise

    def _get_send_status_rest(self, mode, track_id, company_vat, digital_signature):
        """Log completo de verificación REST"""
        _logger.info(f'\n{"="*80}\nVERIFICACIÓN REST - Track: {track_id}\n{"="*80}')

        try:
            result = super()._get_send_status_rest(mode, track_id, company_vat, digital_signature)

            if result:
                _logger.info(f'Respuesta JSON: {result}')

            _logger.info(f'{"="*80}\n')
            return result
        except Exception as e:
            _logger.info(f'ERROR EN VERIFICACIÓN REST: {str(e)}')
            raise

    def _report_connection_err(self, msg):
        """Log errores de conexión críticos"""
        _logger.info(f'\n{"="*80}\nERROR DE CONEXIÓN SII\n{"="*80}')
        _logger.info(f'{msg}')
        _logger.info(f'{"="*80}\n')
        return super()._report_connection_err(msg)
