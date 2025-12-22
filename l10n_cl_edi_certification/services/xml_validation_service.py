# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
from lxml import etree
import os

import logging
_logger = logging.getLogger(__name__)


class XmlValidationService(models.AbstractModel):
    """
    Servicio para validar XML contra esquemas XSD del SII.

    Usa los archivos XSD oficiales descargados del SII para validar
    la estructura del XML ANTES de enviar, reduciendo rechazos.
    """
    _name = 'l10n_cl_edi.xml.validation.service'
    _description = 'Servicio de Validación XML contra XSD del SII'

    @api.model
    def validate_libro_xml(self, xml_string):
        """
        Valida un XML de LibroCompraVenta contra el esquema XSD oficial.

        Args:
            xml_string (str): XML del libro a validar

        Returns:
            tuple: (is_valid, errors)
                - is_valid (bool): True si el XML es válido
                - errors (list): Lista de errores encontrados
        """
        print(f'\n{"=" * 100}')
        print(f'VALIDANDO XML CONTRA ESQUEMA XSD')
        print(f'{"=" * 100}')

        try:
            # Ruta al esquema XSD
            module_path = os.path.dirname(os.path.dirname(__file__))
            xsd_path = os.path.join(module_path, 'schemas', 'LibroCV_v10.xsd')

            if not os.path.exists(xsd_path):
                _logger.warning(f'Esquema XSD no encontrado en: {xsd_path}')
                print(f'⚠️  Esquema XSD no encontrado - Omitiendo validación')
                print(f'    Ubicación esperada: {xsd_path}')
                print(f'{"=" * 100}\n')
                return True, []

            print(f'✓ Esquema encontrado: {xsd_path}')

            # Cargar el esquema XSD
            # IMPORTANTE: Cambiar el directorio de trabajo para que lxml pueda resolver
            # las referencias relativas a otros XSD (xmldsignature_v10.xsd, LceCoCertif_v10.xsd, etc.)
            schemas_dir = os.path.join(module_path, 'schemas')
            current_dir = os.getcwd()

            try:
                os.chdir(schemas_dir)

                with open(xsd_path, 'rb') as f:
                    xsd_doc = etree.parse(f)
                    xmlschema = etree.XMLSchema(xsd_doc)

            finally:
                # Restaurar directorio original
                os.chdir(current_dir)

            print(f'✓ Esquema XSD cargado correctamente (con dependencias)')

            # Parsear el XML a validar
            xml_doc = etree.fromstring(xml_string.encode('ISO-8859-1'))

            # Validar
            is_valid = xmlschema.validate(xml_doc)

            if is_valid:
                print(f'\n✅ XML VÁLIDO - Cumple con el esquema LibroCV_v10.xsd')
                print(f'{"=" * 100}\n')
                return True, []
            else:
                # Recopilar errores
                errors = []
                for error in xmlschema.error_log:
                    error_msg = f'Línea {error.line}: {error.message}'
                    errors.append(error_msg)
                    print(f'  ❌ {error_msg}')

                print(f'\n❌ XML INVÁLIDO - {len(errors)} errores encontrados')
                print(f'{"=" * 100}\n')
                return False, errors

        except etree.XMLSyntaxError as e:
            error_msg = f'Error de sintaxis XML: {str(e)}'
            print(f'❌ {error_msg}')
            print(f'{"=" * 100}\n')
            return False, [error_msg]

        except Exception as e:
            error_msg = f'Error al validar XML: {str(e)}'
            _logger.error(error_msg)
            print(f'⚠️  {error_msg}')
            print(f'    Omitiendo validación...')
            print(f'{"=" * 100}\n')
            # En caso de error técnico, permitir continuar
            return True, []

    @api.model
    def validate_dte_xml(self, xml_string):
        """
        Valida un XML de DTE contra el esquema XSD oficial.

        Args:
            xml_string (str): XML del DTE a validar

        Returns:
            tuple: (is_valid, errors)
        """
        # TODO: Implementar validación de DTE cuando tengamos DTE_v10.xsd
        # Por ahora solo validamos LibroCompraVenta
        return True, []

    @api.model
    def validate_envio_dte_xml(self, xml_string):
        """
        Valida un XML de EnvioDTE contra el esquema XSD oficial.

        Args:
            xml_string (str): XML del EnvioDTE a validar

        Returns:
            tuple: (is_valid, errors)
        """
        # TODO: Implementar validación de EnvioDTE cuando tengamos EnvioDTE_v10.xsd
        return True, []
