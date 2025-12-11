# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import base64

import logging
_logger = logging.getLogger(__name__)

class ValidationService(models.AbstractModel):
    """
    Servicio para Validación de DTEs.
    Valida contra esquemas XSD y reglas de negocio del SII.
    """
    _name = 'l10n_cl_edi.validation.service'
    _description = 'Servicio de Validación de DTEs'

    @api.model
    def validate_document(self, document):
        """
        Valida un documento generado.

        Args:
            document: l10n_cl_edi.certification.generated.document

        Returns:
            tuple: (bool, list) - (es_válido, mensajes)
        """
        messages = []

        # Validar que exista XML firmado
        if not document.xml_dte_signed:
            messages.append(_('El documento no está firmado'))
            return False, messages

        # Obtener XML como bytes (para validación XSD) y como string (para otras validaciones)
        xml_bytes = base64.b64decode(document.xml_dte_signed)
        xml_content = xml_bytes.decode('ISO-8859-1')

        print('\n' + '=' * 80)
        print('VALIDANDO DOCUMENTO')
        print(f'Documento ID: {document.id}, Folio: {document.folio}')
        print(f'Longitud XML a validar: {len(xml_content)} caracteres')

        # Verificar si el XML contiene Detalle
        if '<Detalle>' in xml_content:
            detalle_count = xml_content.count('<Detalle>')
            print(f'✓ XML A VALIDAR contiene {detalle_count} elementos <Detalle>')
        else:
            print('❌ XML A VALIDAR NO contiene elementos <Detalle>')
            print('\nPrimeros 2000 caracteres del XML a validar:')
            print(xml_content[:2000])

        print('=' * 80 + '\n')

        # 1. Validar esquema XSD (pasar bytes porque tiene declaración de encoding)
        is_valid_schema, schema_messages = self._validate_schema(xml_bytes, 'DTE')
        messages.extend(schema_messages)

        # 2. Validar firma digital
        signature_service = self.env['l10n_cl_edi.signature.service']
        is_valid_signature, signature_message = signature_service.validate_signature(xml_content)
        if not is_valid_signature:
            messages.append(signature_message)

        # 3. Validar reglas de negocio
        business_valid, business_messages = self._validate_business_rules(document)
        messages.extend(business_messages)

        # Documento válido si pasa todas las validaciones
        is_valid = is_valid_schema and is_valid_signature and business_valid

        return is_valid, messages

    @api.model
    def validate_envelope(self, envelope):
        """
        Valida un sobre de envío.

        Args:
            envelope: l10n_cl_edi.certification.envelope

        Returns:
            tuple: (bool, list) - (es_válido, mensajes)
        """
        messages = []

        if not envelope.envelope_xml_signed:
            messages.append(_('El sobre no está firmado'))
            return False, messages

        # Obtener XML como bytes (para validación XSD)
        xml_bytes = base64.b64decode(envelope.envelope_xml_signed)

        # Validar esquema XSD de EnvioDTE (pasar bytes porque tiene declaración de encoding)
        is_valid, schema_messages = self._validate_schema(xml_bytes, 'EnvioDTE')
        messages.extend(schema_messages)

        # Validar que tenga documentos
        if not envelope.generated_document_ids:
            messages.append(_('El sobre no tiene documentos'))
            is_valid = False

        return is_valid, messages

    def _validate_schema(self, xml_bytes, schema_type):
        """
        Valida XML contra esquema XSD usando el sistema de Odoo.

        Busca esquemas en múltiples ubicaciones:
        1. ir.attachment con prefijo 'l10n_cl_edi' (Odoo Enterprise)
        2. ir.attachment con prefijo 'l10n_cl_edi_certification' (este módulo)
        3. Archivos del módulo l10n_cl_edi

        Args:
            xml_bytes (bytes): Contenido XML en bytes (con declaración de encoding)
            schema_type (str): Tipo de esquema ('DTE', 'EnvioDTE', etc.)

        Returns:
            tuple: (bool, list) - (es_válido, mensajes)
        """
        try:
            from odoo.tools.xml_utils import validate_xml_from_attachment
            from lxml import etree
            import logging

            _logger = logging.getLogger(__name__)
            messages = []

            # Nombre del archivo XSD
            xsd_filename = f'{schema_type}_v10.xsd'

            # Intentar múltiples ubicaciones (orden de prioridad)
            search_locations = [
                (None, 'Sin prefijo (archivos del sistema)'),
                ('l10n_cl_edi', 'Odoo Enterprise l10n_cl_edi'),
                ('l10n_cl_edi_certification', 'Este módulo'),
            ]

            print("="*80)
            print(f"INICIANDO BÚSQUEDA DE XSD: {xsd_filename}")
            print("="*80)

            # Buscar en ir.attachment directamente
            for prefix, description in search_locations:
                full_name = f'{prefix}.{xsd_filename}' if prefix else xsd_filename
                print(f"Buscando XSD en ir.attachment: {full_name} ({description})")

                attachment = self.env['ir.attachment'].search([
                    ('name', '=', full_name)
                ], limit=1)

                if attachment:
                    print(f"✓ ENCONTRADO: {full_name}")
                    print(f"  - ID: {attachment.id}")
                    print(f"  - Tamaño: {len(attachment.raw) if attachment.raw else 0} bytes")
                    print(f"  - Tipo MIME: {attachment.mimetype}")
                else:
                    print(f"✗ NO ENCONTRADO: {full_name}")

            # Buscar todos los XSD en la base de datos
            print("\nBuscando TODOS los archivos XSD en ir.attachment...")
            all_xsd = self.env['ir.attachment'].search([
                ('name', 'like', '%.xsd')
            ])
            print(f"Total de archivos .xsd encontrados: {len(all_xsd)}")
            for xsd in all_xsd:
                print(f"  - {xsd.name} (ID: {xsd.id})")

            # Intentar validar con cada ubicación
            for prefix, description in search_locations:
                try:
                    prefix_str = prefix if prefix else 'None (sin prefijo)'
                    print(f"\nIntentando validar con prefijo: {prefix_str}")

                    # Debug: Ver qué XML se está enviando al validador
                    xml_str_debug = xml_bytes.decode('ISO-8859-1')
                    print(f"DEBUG - Longitud XML bytes: {len(xml_bytes)}")
                    print(f"DEBUG - XML COMPLETO a validar:")
                    print(xml_str_debug)
                    print(f"\nDEBUG - ¿Contiene '<Detalle>'?: {'✓ SÍ' if '<Detalle>' in xml_str_debug else '❌ NO'}")

                    validate_xml_from_attachment(
                        self.env,
                        xml_bytes,
                        xsd_filename,
                        prefix=prefix
                    )
                    # Si llegamos aquí, la validación pasó
                    full_name = f'{prefix}.{xsd_filename}' if prefix else xsd_filename
                    print(f"✓ VALIDACIÓN EXITOSA usando: {full_name}")
                    messages.append(f"✅ Validación XSD exitosa usando: {description}")
                    return True, messages

                except FileNotFoundError:
                    print(f"✗ FileNotFoundError con prefijo: {prefix_str}")
                    continue
                except etree.DocumentInvalid as e:
                    # El XSD existe pero el XML no es válido
                    full_name = f'{prefix}.{xsd_filename}' if prefix else xsd_filename
                    print(f"✗ XML INVÁLIDO según {full_name}")
                    for error in e.error_log:
                        error_msg = f"Línea {error.line}: {error.message}"
                        print(f"  - {error_msg}")
                        messages.append(error_msg)
                    return False, messages

            # Si llegamos aquí, no se encontró ningún XSD
            print("="*80)
            print("NO SE ENCONTRÓ NINGÚN ESQUEMA XSD EN NINGUNA UBICACIÓN")
            print("="*80)

            messages.append(_(
                'Advertencia: Validación XSD omitida (esquema no encontrado).\n'
                'Ubicaciones buscadas:\n'
                '  1. {xsd} (sin prefijo - archivos del sistema)\n'
                '  2. l10n_cl_edi.{xsd} (Odoo Enterprise)\n'
                '  3. l10n_cl_edi_certification.{xsd} (este módulo)\n\n'
                'Para habilitar validación:\n'
                '  • Use el wizard: Certificación SII → Configuración → Cargar Esquemas XSD\n'
                '  • O instale el módulo l10n_cl_edi de Odoo Enterprise'
            ).format(xsd=xsd_filename))
            return True, messages  # No fallar si no hay esquema

        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception("Error inesperado en validación de esquema:")
            return False, [_('Error en validación de esquema: %s') % str(e)]

    def _validate_business_rules(self, document):
        """
        Valida reglas de negocio del SII.

        Args:
            document: l10n_cl_edi.certification.generated.document

        Returns:
            tuple: (bool, list) - (es_válido, mensajes)
        """
        messages = []
        is_valid = True

        # Validar RUT
        if not document.receiver_rut:
            messages.append(_('Falta RUT del receptor'))
            is_valid = False

        # Validar folio
        if not document.folio or document.folio <= 0:
            messages.append(_('Folio inválido'))
            is_valid = False

        # Validar montos
        # NOTA: Las Notas de Crédito (61) y Notas de Débito (56) pueden tener monto 0
        # cuando son por correcciones administrativas (giro, dirección, etc.)
        doc_type_code = document.document_type_code
        if document.total_amount <= 0 and doc_type_code not in ['61', '56']:
            messages.append(_('El monto total debe ser mayor a 0'))
            is_valid = False

        # Validar IVA (debe ser 19% del neto)
        if document.subtotal_taxable > 0:
            expected_tax = round(document.subtotal_taxable * 0.19)
            actual_tax = round(document.tax_amount)
            if abs(expected_tax - actual_tax) > 1:  # Tolerancia de 1 peso
                messages.append(_('El IVA no corresponde al 19%% del neto'))
                is_valid = False

        # Validar fechas
        from datetime import datetime, timedelta
        issue_date = document.issue_date
        today = datetime.now().date()

        if issue_date > today:
            messages.append(_('La fecha de emisión no puede ser futura'))
            is_valid = False

        if (today - issue_date).days > 60:
            messages.append(_('La fecha de emisión no puede tener más de 60 días de antigüedad'))
            is_valid = False

        return is_valid, messages
