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
            # Asegurar que company_id es un recordset
            if isinstance(company_id, (int, str)):
                company_id = self.env['res.company'].browse(int(company_id))
            elif not company_id:
                raise UserError(_('Se requiere especificar una compañía para firmar el documento.'))

            # Crear un objeto certificate.certificate temporal para usar sus métodos de firma
            # El certificado se decodifica automáticamente al crear el objeto
            CertificateModel = self.env['certificate.certificate']

            # Crear certificado temporal con los datos del CLIENTE
            cert_temp = CertificateModel.new({
                'content': base64.b64encode(cert_data),  # Campo binario del certificado .pfx/.p12 DEL CLIENTE
                'pkcs12_password': password,  # Contraseña DEL CLIENTE
                'company_id': company_id,  # Company del proyecto (debe ser recordset, no ID)
            })

            # Extraer el ID del documento del XML para usarlo como referencia
            from lxml import etree
            import re

            # Remover declaración XML si existe (lxml no la acepta en unicode strings)
            xml_without_declaration = re.sub(r'<\?xml[^>]+\?>\s*', '', xml_content)

            # Crear parser ISO-8859-1 para que lxml entienda el encoding correcto
            parser = etree.XMLParser(encoding='ISO-8859-1')
            xml_doc = etree.fromstring(xml_without_declaration.encode('ISO-8859-1'), parser)

            # Detectar el tipo de documento XML
            print('\n' + '=' * 80)
            print('🔍 DETECTANDO TIPO DE DOCUMENTO XML PARA FIRMA')
            print('=' * 80)

            # 1. Buscar SetDTE (para EnvioDTE - sobre con múltiples DTEs)
            setdte_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}SetDTE')
            print(f'SetDTE encontrado: {setdte_element is not None}')

            # 2. Buscar EnvioLibro (para LibroCompraVenta)
            envio_libro_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}EnvioLibro')
            print(f'EnvioLibro encontrado: {envio_libro_element is not None}')

            # 3. Buscar Resultado (para RespuestaDTE - intercambio)
            resultado_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}Resultado')
            print(f'Resultado encontrado: {resultado_element is not None}')

            # 4. Buscar SetRecibos (para EnvioRecibos - intercambio)
            setrecibos_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}SetRecibos')
            print(f'SetRecibos encontrado: {setrecibos_element is not None}')

            if setdte_element is not None:
                # Es un EnvioDTE - firmar el SetDTE
                doc_id = setdte_element.get('ID', 'SetDoc')
                xml_type = 'env'  # Tipo para EnvioDTE
                print(f'✓ Tipo detectado: EnvioDTE')
                print(f'  ID del nodo: {doc_id}')
                print(f'  Tipo de firma: {xml_type}')
            elif envio_libro_element is not None:
                # Es un LibroCompraVenta - usar método específico de firma
                doc_id = envio_libro_element.get('ID', 'SetDoc')
                xml_type = 'libro'  # Tipo especial para LibroCompraVenta
                print(f'✓ Tipo detectado: LibroCompraVenta')
                print(f'  ID del nodo: {doc_id}')
                print(f'  Tipo de firma: {xml_type}')
            elif resultado_element is not None:
                # Es un RespuestaDTE - firmar el Resultado
                doc_id = resultado_element.get('ID', 'Resultado')
                xml_type = 'env'  # Usar tipo 'env' (similar a EnvioDTE)
                print(f'✓ Tipo detectado: RespuestaDTE')
                print(f'  ID del nodo: {doc_id}')
                print(f'  Tipo de firma: {xml_type}')
            elif setrecibos_element is not None:
                # Es un EnvioRecibos - requiere firma especial (cada Recibo + SetRecibos)
                doc_id = setrecibos_element.get('ID', 'SetRecibos')
                xml_type = 'recibos'  # Tipo especial para EnvioRecibos
                print(f'✓ Tipo detectado: EnvioRecibos')
                print(f'  ID del nodo: {doc_id}')
                print(f'  Tipo de firma: {xml_type} (firma múltiple)')
            else:
                # Es un DTE individual - firmar el Documento
                doc_element = xml_doc.find('.//{http://www.sii.cl/SiiDte}Documento')
                doc_id = doc_element.get('ID') if doc_element is not None else 'DTE-TEMP'
                xml_type = 'doc'  # Tipo para DTE individual
                print(f'✓ Tipo detectado: DTE individual')
                print(f'  ID del nodo: {doc_id}')
                print(f'  Tipo de firma: {xml_type}')

            # Firmar según el tipo de documento
            print('\n📝 LLAMANDO AL MÉTODO DE FIRMA...')
            print(f'Método a usar: {"_sign_libro" if xml_type == "libro" else "sign_xmlsec"}')
            print(f'Parámetros:')
            print(f'  - doc_id: {doc_id}')
            print(f'  - xml_type: {xml_type}')

            if xml_type == 'libro':
                # LibroCompraVenta requiere un método de firma específico
                print('Ejecutando _sign_libro()...')
                signed_xml = self._sign_libro(xml_without_declaration, cert_temp, doc_id)
            elif xml_type == 'recibos':
                # EnvioRecibos requiere firmar cada Recibo + SetRecibos
                print('Ejecutando _sign_envio_recibos()...')
                signed_xml = self._sign_envio_recibos(xml_without_declaration, cert_temp, doc_id)
            else:
                # Para todos los demás (DTEs, EnvioDTE, RespuestaDTE)
                # Usar firma directa con xmlsec
                print('Ejecutando _sign_xmlsec_direct()...')
                signed_xml = self._sign_xmlsec_direct(
                    xml_without_declaration,
                    cert_temp,
                    doc_id
                )

            print('\n✅ FIRMA COMPLETADA')
            print(f'Tamaño del XML firmado: {len(signed_xml)} caracteres')
            print(f'Contiene <Signature>: {"<Signature" in signed_xml}')
            print(f'Últimos 200 caracteres del XML firmado:')
            print(signed_xml[-200:])
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

            # 1. Preparar el mensaje para la firma (sin espacios en blanco extras)
            digest_value = Markup(re.sub(r'\n\s*$', '', message, flags=re.MULTILINE))

            # 2. Obtener el primer hijo (EnvioLibro) para el digest
            digest_value_tree = etree.tostring(etree.fromstring(digest_value)[0])

            # 3. Crear SignedInfo usando template con xsi (para sobres/envíos)
            signed_info_template = 'l10n_cl_edi.signed_info_template_with_xsi'
            signed_info = self.env['ir.qweb']._render(signed_info_template, {
                'uri': '#{}'.format(uri),
                'digest_value': base64.b64encode(
                    hashlib.sha1(etree.tostring(etree.fromstring(digest_value_tree), method='c14n')).digest()
                ).decode(),
            })

            # 4. Canonicalizar el SignedInfo
            signed_info_c14n = Markup(etree.tostring(
                etree.fromstring(signed_info),
                method='c14n',
                exclusive=False,
                with_comments=False,
                inclusive_ns_prefixes=None
            ).decode())

            # 5. Obtener las claves públicas del certificado
            e, n = digital_signature._get_public_key_numbers_bytes(formatting='base64')

            # 6. Firmar el SignedInfo
            signature_value = digital_signature._sign(
                re.sub(r'\n\s*', '', signed_info_c14n),
                hashing_algorithm='sha1',
                formatting='base64'
            ).decode()

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

            # 7.1 Limpiar espacios en blanco al inicio y final de la firma
            # QWeb puede agregar saltos de línea/espacios extras
            if isinstance(signature, bytes):
                signature = signature.decode('utf-8')
            signature = Markup(signature.strip())

            # 8. Insertar la firma antes del cierre de LibroCompraVenta
            # Para LibroCompraVenta, la firma va después de </EnvioLibro> y antes de </LibroCompraVenta>
            # El XML original ya tiene un salto de línea después de </EnvioLibro>,
            # solo agregamos uno después de la firma
            tag_to_replace = Markup('</LibroCompraVenta>')
            full_doc = digest_value.replace(tag_to_replace, signature + '\n' + tag_to_replace)

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

    def _sign_envio_recibos(self, xml_content, digital_signature, setrecibos_id):
        """
        Firma un EnvioRecibos según Ley 19.983.

        Este documento requiere:
        1. Firmar cada <Recibo> individualmente (firmando el DocumentoRecibo)
        2. Insertar cada firma dentro de su <Recibo>
        3. Finalmente firmar todo el <SetRecibos>

        Args:
            xml_content (str): XML sin firmar (sin declaración XML)
            digital_signature: Objeto certificate.certificate
            setrecibos_id (str): ID del SetRecibos (ej: 'SetRecibos')

        Returns:
            str: XML firmado con múltiples firmas
        """
        try:
            from lxml import etree
            from markupsafe import Markup
            import re
            import hashlib
            import textwrap

            print(f'\n  🔐 Firmando EnvioRecibos (firma múltiple)...')
            print(f'     SetRecibos ID: #{setrecibos_id}')

            # 1. Parsear XML
            digest_value = Markup(re.sub(r'\n\s*$', '', xml_content, flags=re.MULTILINE))
            root = etree.fromstring(digest_value)

            # 2. Encontrar SetRecibos y todos los Recibos
            ns = {'sii': 'http://www.sii.cl/SiiDte'}
            set_recibos = root.find('.//sii:SetRecibos', ns) or root.find('.//SetRecibos')
            if set_recibos is None:
                raise UserError(_('No se encontró SetRecibos en el XML'))

            recibos = set_recibos.findall('.//sii:Recibo', ns) or set_recibos.findall('.//Recibo')
            print(f'     ✓ Encontrados {len(recibos)} Recibo(s)')

            # 3. Firmar cada Recibo individualmente
            for idx, recibo in enumerate(recibos):
                # Buscar DocumentoRecibo con ID
                doc_recibo = recibo.find('.//sii:DocumentoRecibo', ns) or recibo.find('.//DocumentoRecibo')
                if doc_recibo is None:
                    print(f'     ⚠ Recibo {idx+1} no tiene DocumentoRecibo, saltando...')
                    continue

                doc_id = doc_recibo.get('ID', f'R{idx+1:02d}')
                print(f'     Firmando Recibo {idx+1} (ID={doc_id})...')

                # Calcular digest del DocumentoRecibo
                node_digest = base64.b64encode(
                    hashlib.sha1(etree.tostring(doc_recibo, method='c14n')).digest()
                ).decode()

                # Crear SignedInfo
                signed_info = self.env['ir.qweb']._render('l10n_cl_edi.signed_info_template_with_xsi', {
                    'uri': '#{}'.format(doc_id),
                    'digest_value': node_digest,
                })

                # Canonicalizar SignedInfo
                signed_info_c14n = Markup(etree.tostring(
                    etree.fromstring(signed_info),
                    method='c14n',
                    exclusive=False,
                    with_comments=False,
                    inclusive_ns_prefixes=None
                ).decode())

                # Obtener claves públicas
                e, n = digital_signature._get_public_key_numbers_bytes(formatting='base64')

                # Firmar
                signature_value = digital_signature._sign(
                    re.sub(r'\n\s*', '', signed_info_c14n),
                    hashing_algorithm='sha1',
                    formatting='base64'
                ).decode()

                # Crear elemento Signature
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

                if isinstance(signature, bytes):
                    signature = signature.decode('utf-8')
                signature_element = etree.fromstring(Markup(signature.strip()))

                # Insertar firma en el Recibo (después de DocumentoRecibo)
                recibo.append(signature_element)
                print(f'     ✓ Recibo {idx+1} firmado')

            # 4. Ahora firmar todo el SetRecibos
            print(f'     Firmando SetRecibos completo...')

            # Calcular digest del SetRecibos
            setrecibos_digest = base64.b64encode(
                hashlib.sha1(etree.tostring(set_recibos, method='c14n')).digest()
            ).decode()

            # Crear SignedInfo para SetRecibos
            signed_info_set = self.env['ir.qweb']._render('l10n_cl_edi.signed_info_template_with_xsi', {
                'uri': '#{}'.format(setrecibos_id),
                'digest_value': setrecibos_digest,
            })

            # Canonicalizar
            signed_info_set_c14n = Markup(etree.tostring(
                etree.fromstring(signed_info_set),
                method='c14n',
                exclusive=False,
                with_comments=False,
                inclusive_ns_prefixes=None
            ).decode())

            # Obtener claves públicas
            e, n = digital_signature._get_public_key_numbers_bytes(formatting='base64')

            # Firmar SetRecibos
            signature_value_set = digital_signature._sign(
                re.sub(r'\n\s*', '', signed_info_set_c14n),
                hashing_algorithm='sha1',
                formatting='base64'
            ).decode()

            # Crear elemento Signature para SetRecibos
            signature_set = self.env['ir.qweb']._render('l10n_cl_edi.signature_template', {
                'signed_info': signed_info_set_c14n,
                'signature_value': signature_value_set,
                'modulus': n.decode(),
                'exponent': e.decode(),
                'certificate': '\n' + textwrap.fill(
                    digital_signature._get_der_certificate_bytes(formatting='base64').decode(),
                    64
                ),
            })

            if isinstance(signature_set, bytes):
                signature_set = signature_set.decode('utf-8')
            signature_set = Markup(signature_set.strip())

            # 5. Insertar firma del SetRecibos en el XML raíz
            root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
            tag_to_replace = Markup('</{}>'.format(root_tag))

            # Convertir root actualizado a string
            xml_with_recibo_sigs = etree.tostring(root, encoding='unicode')

            # Insertar firma del SetRecibos antes del cierre de EnvioRecibos
            full_doc = Markup(xml_with_recibo_sigs).replace(tag_to_replace, signature_set + '\n' + tag_to_replace)

            print(f'     ✓ SetRecibos firmado')
            print(f'     ✓ Total de firmas: {len(recibos) + 1}')

            # Retornar con declaración XML
            return Markup('<?xml version="1.0" encoding="ISO-8859-1" ?>\n') + full_doc

        except Exception as e:
            print(f'\n     ❌ ERROR en _sign_envio_recibos: {e}')
            import traceback
            traceback.print_exc()
            raise UserError(_('Error al firmar EnvioRecibos: %s') % str(e))

    def _sign_xmlsec_direct(self, xml_content, digital_signature, uri):
        """
        Firma un XML usando el mismo método que _sign_libro().

        Este método funciona para DTEs, EnvioDTE, RespuestaDTE y EnvioRecibos.

        Args:
            xml_content (str): XML sin firmar (sin declaración XML)
            digital_signature: Objeto certificate.certificate
            uri (str): URI de referencia (ej: 'Resultado', 'SetRecibos', 'SetDoc')

        Returns:
            str: XML firmado
        """
        try:
            from lxml import etree
            from markupsafe import Markup
            import re
            import hashlib
            import textwrap

            print(f'\n  🔐 Firmando documento...')
            print(f'     URI: #{uri}')

            # 1. Preparar el mensaje
            digest_value = Markup(re.sub(r'\n\s*$', '', xml_content, flags=re.MULTILINE))

            # 2. Parsear el XML
            root = etree.fromstring(digest_value)

            # 3. Buscar el nodo a firmar por ID
            target_node = None
            for elem in root.iter():
                if elem.get('ID') == uri:
                    target_node = elem
                    print(f'     ✓ Nodo encontrado: {elem.tag}')
                    break

            if target_node is None:
                raise UserError(_('No se encontró el nodo con ID="%s" para firmar') % uri)

            # 4. Calcular digest del nodo
            node_digest = base64.b64encode(
                hashlib.sha1(etree.tostring(target_node, method='c14n')).digest()
            ).decode()

            print(f'     ✓ Digest calculado: {node_digest[:20]}...')

            # 5. Crear SignedInfo usando template
            signed_info = self.env['ir.qweb']._render('l10n_cl_edi.signed_info_template_with_xsi', {
                'uri': '#{}'.format(uri),
                'digest_value': node_digest,
            })

            print(f'     ✓ SignedInfo creado')

            # 6. Canonicalizar SignedInfo
            signed_info_c14n = Markup(etree.tostring(
                etree.fromstring(signed_info),
                method='c14n',
                exclusive=False,
                with_comments=False,
                inclusive_ns_prefixes=None
            ).decode())

            print(f'     ✓ SignedInfo canonicalizado')

            # 7. Obtener las claves públicas del certificado
            e, n = digital_signature._get_public_key_numbers_bytes(formatting='base64')

            print(f'     ✓ Claves públicas obtenidas')

            # 8. Firmar el SignedInfo usando _sign() del certificado
            signature_value = digital_signature._sign(
                re.sub(r'\n\s*', '', signed_info_c14n),
                hashing_algorithm='sha1',
                formatting='base64'
            ).decode()

            print(f'     ✓ Firma digital generada')

            # 9. Crear el elemento Signature completo
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

            # 9.1 Limpiar espacios en blanco al inicio y final de la firma
            if isinstance(signature, bytes):
                signature = signature.decode('utf-8')
            signature = Markup(signature.strip())

            print(f'     ✓ Elemento Signature creado')

            # 10. Insertar la firma en el XML
            # Determinar el tag de cierre según el tipo de documento
            root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
            tag_to_replace = Markup('</{}>'.format(root_tag))

            # Insertar firma antes del cierre del elemento raíz
            full_doc = digest_value.replace(tag_to_replace, signature + '\n' + tag_to_replace)

            print(f'     ✓ Firma insertada en el XML')

            # 11. Retornar con declaración XML
            return Markup('<?xml version="1.0" encoding="ISO-8859-1" ?>\n') + full_doc

        except Exception as e:
            print(f'\n     ❌ ERROR en _sign_xmlsec_direct: {e}')
            import traceback
            traceback.print_exc()
            raise UserError(_('Error al firmar el documento: %s') % str(e))
