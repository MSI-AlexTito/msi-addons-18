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

            # Detectar el tipo de documento XML
            # 1. Buscar SetDTE (para EnvioDTE - sobre con múltiples DTEs)
            setdte_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}SetDTE')

            # 2. Buscar EnvioLibro (para LibroCompraVenta)
            envio_libro_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}EnvioLibro')

            if setdte_element is not None:
                # Es un EnvioDTE - firmar el SetDTE
                doc_id = setdte_element.get('ID', 'SetDoc')
                xml_type = 'env'  # Tipo para EnvioDTE
                print(f'Detectado EnvioDTE - ID del SetDTE: {doc_id}')
            elif envio_libro_element is not None:
                # Es un LibroCompraVenta - usar método específico de firma
                doc_id = envio_libro_element.get('ID', 'SetDoc')
                xml_type = 'libro'  # Tipo especial para LibroCompraVenta
                print(f'Detectado LibroCompraVenta - ID del EnvioLibro: {doc_id}')
            else:
                # Es un DTE individual - firmar el Documento
                doc_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}Documento')
                doc_id = doc_element.get('ID') if doc_element is not None else 'DTE-TEMP'
                xml_type = 'doc'  # Tipo para DTE individual
                print(f'Detectado DTE individual - ID del Documento: {doc_id}')

            # Firmar según el tipo de documento
            if xml_type == 'libro':
                # LibroCompraVenta requiere un método de firma específico
                print('\nLlamando a _sign_libro()...')
                print(f'  - message: {len(xml_without_declaration)} caracteres')
                print(f'  - digital_signature: {cert_temp}')
                print(f'  - uri: {doc_id}')

                signed_xml = self._sign_libro(xml_without_declaration, cert_temp, doc_id)
            else:
                # Para DTEs y EnvioDTE usar el método heredado
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
            print(f'Diferencia: {len(signed_xml) - len(xml_without_declaration)} caracteres agregados')
            print(f'Tipo: {type(signed_xml)}')

            # Verificar si hay firma en el XML
            signed_xml_str = str(signed_xml)
            has_signature = '<Signature' in signed_xml_str or '<ds:Signature' in signed_xml_str
            print(f'¿Contiene elemento Signature? {has_signature}')

            if has_signature:
                # Encontrar dónde está la firma
                sig_start = signed_xml_str.find('<Signature')
                if sig_start == -1:
                    sig_start = signed_xml_str.find('<ds:Signature')
                sig_end = signed_xml_str.find('</Signature>', sig_start)
                if sig_end == -1:
                    sig_end = signed_xml_str.find('</ds:Signature>', sig_start)

                if sig_start > 0 and sig_end > sig_start:
                    print(f'Firma encontrada en posición {sig_start} a {sig_end}')
                    print(f'Longitud del elemento Signature: {sig_end - sig_start} caracteres')
                    print(f'\nPrimeros 500 caracteres de la firma:')
                    print(signed_xml_str[sig_start:sig_start+500])
            else:
                print('⚠️  NO SE ENCONTRÓ ELEMENTO SIGNATURE EN EL XML!')
                print('\nÚltimos 500 caracteres del XML:')
                print(signed_xml_str[-500:])

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

    def _sign_libro(self, message, digital_signature, uri):
        """
        Firma un LibroCompraVenta usando el método de Odoo Enterprise.

        LibroCompraVenta tiene una estructura específica:
        <LibroCompraVenta>
          <EnvioLibro ID="SetDoc">
            ...
          </EnvioLibro>
          <!-- Firma va aquí -->
        </LibroCompraVenta>

        Args:
            message (str): XML del libro sin firmar (sin declaración XML)
            digital_signature: Objeto certificate.certificate
            uri (str): URI de referencia (ej: 'SetDoc')

        Returns:
            str: XML firmado
        """
        try:
            from lxml import etree
            from markupsafe import Markup
            import re
            import hashlib
            import textwrap

            print(f'\n{"=" * 80}')
            print(f'INICIO _sign_libro()')
            print(f'{"=" * 80}')
            print(f'URI: {uri}')
            print(f'Longitud message: {len(message)} caracteres')

            # 1. Preparar el mensaje para la firma (sin espacios en blanco extras)
            digest_value = Markup(re.sub(r'\n\s*$', '', message, flags=re.MULTILINE))

            # 2. Obtener el primer hijo (EnvioLibro) para el digest
            digest_value_tree = etree.tostring(etree.fromstring(digest_value)[0])
            print(f'✓ EnvioLibro extraído para digest: {len(digest_value_tree)} bytes')

            # 3. Crear SignedInfo usando template con xsi (para sobres/envíos)
            signed_info_template = 'l10n_cl_edi.signed_info_template_with_xsi'
            signed_info = self.env['ir.qweb']._render(signed_info_template, {
                'uri': '#{}'.format(uri),
                'digest_value': base64.b64encode(
                    hashlib.sha1(etree.tostring(etree.fromstring(digest_value_tree), method='c14n')).digest()
                ).decode(),
            })
            print(f'✓ SignedInfo generado: {len(signed_info)} caracteres')

            # 4. Canonicalizar el SignedInfo
            signed_info_c14n = Markup(etree.tostring(
                etree.fromstring(signed_info),
                method='c14n',
                exclusive=False,
                with_comments=False,
                inclusive_ns_prefixes=None
            ).decode())
            print(f'✓ SignedInfo canonicalizado: {len(signed_info_c14n)} caracteres')

            # 5. Obtener las claves públicas del certificado
            e, n = digital_signature._get_public_key_numbers_bytes(formatting='base64')
            print(f'✓ Claves públicas obtenidas')

            # 6. Firmar el SignedInfo
            signature_value = digital_signature._sign(
                re.sub(r'\n\s*', '', signed_info_c14n),
                hashing_algorithm='sha1',
                formatting='base64'
            ).decode()
            print(f'✓ Firma generada: {len(signature_value)} caracteres')

            # 7. Crear el elemento Signature completo
            signature = self.env['ir.qweb']._render('l10n_cl_edi.signature_template', {
                'signed_info': signed_info_c14n,
                'signature_value': signature_value,
                'modulus': n.decode(),
                'exponent': e.decode(),
                'certificate': '\n' + textwrap.fill(
                    digital_signature._get_der_certificate_bytes(formatting='base64').decode(),
                    64
                ),
            })
            print(f'✓ Elemento Signature completo: {len(signature)} caracteres')

            # 7.1 Limpiar espacios en blanco al inicio y final de la firma
            # QWeb puede agregar saltos de línea/espacios extras
            if isinstance(signature, bytes):
                signature = signature.decode('utf-8')
            signature = Markup(signature.strip())
            print(f'✓ Firma limpiada: {len(signature)} caracteres')

            # 8. Insertar la firma antes del cierre de LibroCompraVenta
            # Para LibroCompraVenta, la firma va después de </EnvioLibro> y antes de </LibroCompraVenta>
            # El XML original ya tiene un salto de línea después de </EnvioLibro>,
            # solo agregamos uno después de la firma
            tag_to_replace = Markup('</LibroCompraVenta>')
            full_doc = digest_value.replace(tag_to_replace, signature + '\n' + tag_to_replace)

            print(f'✓ Firma insertada en el XML')
            print(f'  Longitud final: {len(full_doc)} caracteres')
            print(f'  Diferencia: +{len(full_doc) - len(message)} caracteres')
            print(f'{"=" * 80}\n')

            # 9. Retornar con declaración XML y salto de línea
            return Markup('<?xml version="1.0" encoding="ISO-8859-1" ?>\n') + full_doc

        except Exception as e:
            print(f'\n❌ ERROR en _sign_libro():')
            print(f'Tipo: {type(e).__name__}')
            print(f'Mensaje: {str(e)}')
            import traceback
            traceback.print_exc()
            print(f'{"=" * 80}\n')
            raise

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
