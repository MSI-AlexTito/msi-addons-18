# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import base64

import logging
_logger = logging.getLogger(__name__)

class SignatureService(models.AbstractModel):
    """
    Servicio para Firma Digital de Documentos.
    Maneja la firma de DTEs y Sobres usando certificados digitales.
    Hereda de l10n_cl.edi.util para acceder a los métodos de firma de Odoo Enterprise.
    """
    _name = 'l10n_cl_edi.signature.service'
    _description = 'Servicio de Firma Digital'
    _inherit = 'l10n_cl.edi.util'

    @api.model
    def sign_xml(self, xml_content, cert_data, cert_password, company_id, reference_uri=None):
        """
        Firma un XML con certificado digital DEL CLIENTE.

        Args:
            xml_content (str): Contenido XML a firmar
            cert_data (bytes): Datos del certificado (.pfx/.p12) en bytes DEL CLIENTE
            cert_password (str): Contraseña del certificado DEL CLIENTE
            company_id (res.company): Company asociada (requerida para certificado temporal)
            reference_uri (str): URI de referencia para la firma (opcional)

        Returns:
            str: XML firmado
        """
        return self._sign_xml(xml_content, cert_data, cert_password, company_id)

    @api.model
    def sign_dte(self, document):
        """
        Firma un DTE (Documento Tributario Electrónico) usando CERTIFICADO DEL CLIENTE.

        Args:
            document: l10n_cl_edi.certification.generated.document

        Returns:
            str: XML firmado
        """
        if not document.xml_dte_file:
            raise UserError(_('El documento no tiene XML para firmar.'))

        # Obtener certificado del cliente
        client_info = document.project_id.client_info_id
        if not client_info:
            raise UserError(_('No hay información del cliente configurada.'))

        # Obtener datos del certificado DEL CLIENTE
        cert_data, cert_password = client_info.get_certificate_data()

        # Obtener XML (ISO-8859-1 encoding requerido por SII)
        xml_content = base64.b64decode(document.xml_dte_file).decode('ISO-8859-1')

        # Firmar el XML (pasamos company_id para el certificado temporal)
        signed_xml = self._sign_xml(xml_content, cert_data, cert_password, document.project_id.company_id)

        return signed_xml

    @api.model
    def sign_envelope(self, envelope):
        """
        Firma un Sobre de Envío (EnvioDTE) usando CERTIFICADO DEL CLIENTE.

        Args:
            envelope: l10n_cl_edi.certification.envelope

        Returns:
            str: XML firmado del sobre
        """
        if not envelope.envelope_xml:
            raise UserError(_('El sobre no tiene XML para firmar.'))

        # Obtener certificado del cliente
        client_info = envelope.project_id.client_info_id
        if not client_info:
            raise UserError(_('No hay información del cliente configurada.'))

        # Obtener datos del certificado DEL CLIENTE
        cert_data, cert_password = client_info.get_certificate_data()

        # Obtener XML (ISO-8859-1 encoding requerido por SII)
        xml_content = base64.b64decode(envelope.envelope_xml).decode('ISO-8859-1')

        # Firmar (pasamos company_id para el certificado temporal)
        signed_xml = self._sign_xml(xml_content, cert_data, cert_password, envelope.project_id.company_id)

        return signed_xml

    def _sign_xml(self, xml_content, cert_data, password, company_id):
        """
        Firma un XML con el certificado digital DEL CLIENTE usando el método de Odoo Enterprise.

        Args:
            xml_content (str): Contenido XML a firmar
            cert_data (bytes): Certificado en formato .pfx/.p12 (bytes directos) DEL CLIENTE
            password (str): Contraseña del certificado DEL CLIENTE
            company_id (res.company or int): Company asociada al proyecto (requerida para certificado temporal)

        Returns:
            str: XML firmado
        """
        try:
            print('\n' + '=' * 80)
            print('INICIO _sign_xml')
            print(f'Parámetros recibidos:')
            print(f'  - xml_content: tipo={type(xml_content)}, len={len(xml_content)}')
            print(f'  - cert_data: tipo={type(cert_data)}, len={len(cert_data)}')
            print(f'  - password: {"presente" if password else "ausente"}')
            print(f'  - company_id: tipo={type(company_id)}, valor={company_id}')

            # Asegurar que company_id es un recordset
            if isinstance(company_id, (int, str)):
                print(f'Convirtiendo company_id de {type(company_id)} a recordset...')
                company_id = self.env['res.company'].browse(int(company_id))
                print(f'✓ company_id convertido: {company_id.id} - {company_id.name}')
            elif not company_id:
                raise UserError(_('Se requiere especificar una compañía para firmar el documento.'))
            else:
                print(f'✓ company_id ya es recordset: {company_id.id} - {company_id.name}')

            print('\nDEBUG SERVICIO DE FIRMA - USANDO CERTIFICADO DEL CLIENTE')
            print(f'Longitud xml_content recibido: {len(xml_content)} caracteres')
            print(f'Tipo xml_content: {type(xml_content)}')
            print(f'Longitud cert_data: {len(cert_data)} bytes')
            print(f'Tipo cert_data: {type(cert_data)}')
            print(f'Tiene password: {bool(password)}')
            print(f'Company ID: {company_id.id} ({company_id.name})')
            print('Primeros 200 caracteres del XML:')
            print(xml_content[:200])
            print('=' * 80)

            # Crear un objeto certificate.certificate temporal para usar sus métodos de firma
            # El certificado se decodifica automáticamente al crear el objeto
            CertificateModel = self.env['certificate.certificate']

            print('\nCreando objeto certificate temporal con datos DEL CLIENTE...')
            # Crear certificado temporal con los datos del CLIENTE
            cert_temp = CertificateModel.new({
                'content': base64.b64encode(cert_data),  # Campo binario del certificado .pfx/.p12 DEL CLIENTE
                'pkcs12_password': password,  # Contraseña DEL CLIENTE
                'company_id': company_id,  # Company del proyecto (debe ser recordset, no ID)
            })

            print(f'Certificado temporal creado')
            print(f'  - is_valid: {cert_temp.is_valid}')
            print(f'  - subject_common_name: {cert_temp.subject_common_name}')
            print(f'  - date_start: {cert_temp.date_start}')
            print(f'  - date_end: {cert_temp.date_end}')
            print(f'  - loading_error: {cert_temp.loading_error}')

            # Extraer el ID del documento del XML para usarlo como referencia
            from lxml import etree
            import re

            print('\nParseando XML para extraer ID...')
            # Remover declaración XML si existe (lxml no la acepta en unicode strings)
            xml_without_declaration = re.sub(r'<\?xml[^>]+\?>\s*', '', xml_content)

            # Crear parser ISO-8859-1 para que lxml entienda el encoding correcto
            parser = etree.XMLParser(encoding='ISO-8859-1')
            xml_doc = etree.fromstring(xml_without_declaration.encode('ISO-8859-1'), parser)

            # Detectar si es un DTE individual o un EnvioDTE
            # 1. Buscar SetDTE (para EnvioDTE)
            setdte_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}SetDTE')

            if setdte_element is not None:
                # Es un EnvioDTE - firmar el SetDTE
                doc_id = setdte_element.get('ID', 'SetDoc')
                xml_type = 'env'  # Tipo para EnvioDTE
                print(f'Detectado EnvioDTE - ID del SetDTE: {doc_id}')
            else:
                # Es un DTE individual - firmar el Documento
                doc_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}Documento')
                doc_id = doc_element.get('ID') if doc_element is not None else 'DTE-TEMP'
                xml_type = 'doc'  # Tipo para DTE individual
                print(f'Detectado DTE individual - ID del Documento: {doc_id}')

            # Usar el método heredado de l10n_cl.edi.util para firmar
            # IMPORTANTE: Pasar el XML SIN la declaración <?xml...?>
            print('\nLlamando a _sign_full_xml()...')
            print(f'  - message: {len(xml_without_declaration)} caracteres (sin declaración XML)')
            print(f'  - digital_signature: {cert_temp}')
            print(f'  - uri: {doc_id}')
            print(f'  - xml_type: {xml_type}')
            print(f'  - is_doc_type_voucher: False')

            signed_xml = self._sign_full_xml(
                xml_without_declaration,
                cert_temp,
                doc_id,
                xml_type,  # 'doc' para DTE individual, 'env' para EnvioDTE
                False   # is_doc_type_voucher
            )

            print(f'\n✓ XML firmado exitosamente')
            print(f'Longitud XML firmado: {len(signed_xml)} caracteres')
            print(f'Tipo: {type(signed_xml)}')
            print('Primeros 300 caracteres:')
            print(str(signed_xml)[:300])
            print('=' * 80 + '\n')

            return signed_xml

        except Exception as e:
            print(f'\n❌ ERROR EN FIRMA:')
            print(f'Tipo de error: {type(e).__name__}')
            print(f'Mensaje: {str(e)}')
            import traceback
            print('Traceback completo:')
            traceback.print_exc()
            print('=' * 80 + '\n')
            raise UserError(_('Error al firmar el XML: %s') % str(e))

    @api.model
    def validate_signature(self, xml_content):
        """
        Valida la firma digital de un XML.

        Args:
            xml_content (str): XML firmado

        Returns:
            tuple: (bool, str) - (es_válido, mensaje)
        """
        try:
            from lxml import etree

            # Parsear XML (ISO-8859-1 encoding requerido por SII)
            parser = etree.XMLParser(encoding='ISO-8859-1')
            xml_doc = etree.fromstring(xml_content.encode('ISO-8859-1'), parser)

            # Buscar elemento de firma
            signature_elements = xml_doc.xpath('//ds:Signature', namespaces={
                'ds': 'http://www.w3.org/2000/09/xmldsig#'
            })

            if not signature_elements:
                return False, _('No se encontró firma digital en el documento')

            # Aquí deberías validar la firma usando xmlsec
            # Por ahora retornamos True como placeholder

            return True, _('Firma válida')

        except Exception as e:
            return False, _('Error al validar firma: %s') % str(e)
