# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import base64
from datetime import datetime
import pytz
import logging
_logger = logging.getLogger(__name__)

class EnvelopeService(models.AbstractModel):
    """
    Servicio para Creación de Sobres de Envío (EnvioDTE).
    Agrupa múltiples DTEs en un sobre para enviar al SII.
    """
    _name = 'l10n_cl_edi.envelope.service'
    _description = 'Servicio de Sobres de Envío'

    @api.model
    def create_envelope(self, envelope):
        """
        Crea el XML del sobre con los documentos incluidos.

        Args:
            envelope: l10n_cl_edi.certification.envelope

        Returns:
            str: XML del sobre
        """
        if not envelope.generated_document_ids:
            raise UserError(_('El sobre debe contener al menos un documento.'))

        # Obtener información del cliente
        client_info = envelope.project_id.client_info_id
        if not client_info:
            raise UserError(_('No hay información del cliente configurada.'))

        # Preparar datos del sobre
        envelope_data = self._prepare_envelope_data(envelope, client_info)

        # Generar XML
        envelope_xml = self._generate_envelope_xml(envelope_data)

        return envelope_xml

    def _prepare_envelope_data(self, envelope, client_info):
        """Prepara los datos para el sobre"""
        # IMPORTANTE: Ordenar documentos para que las facturas vayan PRIMERO
        # y luego las NC/ND que las referencian (evita error REF-3-750 del SII)
        # Orden de prioridad de tipos: 33, 34, 39 (facturas) → 61 (NC) → 56 (ND)
        def document_sort_key(doc):
            # Tipos de documento ordenados de menor a mayor prioridad
            type_order = {
                '33': 1,  # Factura Electrónica
                '34': 2,  # Factura no Afecta o Exenta
                '39': 3,  # Boleta Electrónica
                '61': 4,  # Nota de Crédito (debe ir después de facturas)
                '56': 5,  # Nota de Débito (debe ir después de todo)
            }
            # Ordenar por: 1) tipo de documento, 2) folio
            return (type_order.get(doc.document_type_code, 99), doc.folio)

        documents = envelope.generated_document_ids.sorted(key=document_sort_key)

        # Validar datos requeridos
        if not client_info.subject_serial_number:
            raise UserError(_('Debe configurar el RUT Emisor del Certificado en la información del cliente.'))
        if not client_info.dte_resolution_date:
            raise UserError(_('Debe configurar la Fecha de Resolución SII en la información del cliente.'))

        # Preparar carátula
        # Obtener hora de Santiago de Chile - SIN timezone
        santiago_tz = pytz.timezone('America/Santiago')
        now_santiago = datetime.now(santiago_tz)

        # Formatear timestamp SIN timezone
        # Ejemplo: 2025-12-09T22:15:18
        timestamp_str = now_santiago.strftime('%Y-%m-%dT%H:%M:%S')

        caratula = {
            'RutEmisor': client_info.rut,
            'RutEnvia': client_info.subject_serial_number,  # RUT del emisor del certificado
            'RutReceptor': '60803000-K',  # SII
            'FchResol': client_info.dte_resolution_date.strftime('%Y-%m-%d'),  # Fecha de resolución del SII
            'NroResol': client_info.dte_resolution_number or '0',  # Número de resolución
            'TmstFirmaEnv': timestamp_str,  # SIN timezone (ej: 2025-12-09T22:15:18)
        }

        # Contar documentos por tipo
        document_types = {}
        for doc in documents:
            doc_type = doc.document_type_code
            if doc_type not in document_types:
                document_types[doc_type] = []
            document_types[doc_type].append(doc)

        # Agregar subtotales por tipo
        caratula['SubTotDTE'] = []
        for doc_type, docs in document_types.items():
            caratula['SubTotDTE'].append({
                'TpoDTE': doc_type,
                'NroDTE': len(docs),
            })

        # Preparar lista de DTEs
        dtes = []
        import re

        for doc in documents:
            if not doc.xml_dte_signed:
                raise UserError(_('Todos los documentos deben estar firmados. Documento %s no está firmado.') % doc.complete_name)

            # Decodificar XML firmado
            dte_xml = base64.b64decode(doc.xml_dte_signed).decode('ISO-8859-1')

            # IMPORTANTE: Los DTEs dentro del SetDTE SÍ deben incluir su firma individual
            # según el esquema XSD y los ejemplos de Odoo Enterprise
            # Estructura: <DTE><Documento>...</Documento><Signature>...</Signature></DTE>

            # Remover solo la declaración XML (no la firma)
            dte_xml_sin_declaracion = re.sub(r'<\?xml[^>]+\?>\s*', '', dte_xml)

            dtes.append({
                'folio': doc.folio,
                'xml': dte_xml_sin_declaracion,
            })

        return {
            'Caratula': caratula,
            'DTEs': dtes,
        }

    def _generate_envelope_xml(self, envelope_data):
        """Genera el XML del sobre usando template"""
        from markupsafe import Markup

        # Convertir los XMLs de DTEs a Markup para que QWeb no los escape
        for dte_item in envelope_data['DTEs']:
            dte_item['xml'] = Markup(dte_item['xml'])

        template = 'l10n_cl_edi_certification.envelope_certification_template'

        xml_content = self.env['ir.qweb']._render(template, {
            'envelope_data': envelope_data,
            '__keep_empty_lines': True,  # Preservar indentación y saltos de línea (como Odoo Enterprise)
        })

        # Convertir a string (QWeb puede retornar bytes)
        xml_str = xml_content.decode('ISO-8859-1') if isinstance(xml_content, bytes) else xml_content

        # Convertir a string si es Markup
        if isinstance(xml_str, Markup):
            xml_str = str(xml_str)

        # IMPORTANTE: QWeb/lxml pueden reordenar los atributos xmlns alfabéticamente.
        # Necesitamos asegurar que xmlns venga ANTES de xmlns:xsi (como en Enterprise).
        # Este reemplazo se hace ANTES de firmar, por lo que no afecta la firma.
        import re
        xml_str = re.sub(
            r'<EnvioDTE\s+xmlns:xsi="([^"]+)"\s+xmlns="([^"]+)"',
            r'<EnvioDTE xmlns="\2" xmlns:xsi="\1"',
            xml_str
        )

        # Nota: No es necesario agregar la declaración XML aquí porque el método _sign_full_xml
        # de Enterprise ya lo hace automáticamente

        return xml_str

    @api.model
    def normalize_envelope(self, envelope):
        """
        Normaliza el sobre al formato esperado por el SII.
        Esto puede incluir ajustes de encoding, namespaces, etc.

        Args:
            envelope: l10n_cl_edi.certification.envelope

        Returns:
            str: XML normalizado
        """
        if not envelope.envelope_xml:
            raise UserError(_('No hay XML del sobre para normalizar.'))

        xml_content = base64.b64decode(envelope.envelope_xml).decode('ISO-8859-1')

        # Aquí podrías aplicar normalizaciones específicas
        # Por ejemplo: asegurar encoding ISO-8859-1, ajustar namespaces, etc.

        return xml_content
