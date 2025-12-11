# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
import pytz
import base64

import logging
_logger = logging.getLogger(__name__)

class DteGeneratorService(models.AbstractModel):
    """
    Servicio para Generación de DTEs (Documentos Tributarios Electrónicos).
    Encapsula toda la lógica de creación de XML de DTEs.
    """
    _name = 'l10n_cl_edi.dte.generator.service'
    _description = 'Servicio de Generación de DTEs'

    @api.model
    def generate_dte_for_case(self, case):
        """
        Genera un DTE completo a partir de un caso de prueba.

        Args:
            case: l10n_cl_edi.certification.case

        Returns:
            l10n_cl_edi.certification.generated.document
        """
        # Obtener folio para este tipo de documento
        folio_service = self.env['l10n_cl_edi.folio.service']
        folio = folio_service.get_next_folio(case.project_id, case.document_type_id)

        # Preparar datos para el DTE
        dte_data = self._prepare_dte_data(case, folio)

        # Generar TED (Timbre Electrónico) ANTES del XML para incluirlo
        ted_xml = self._generate_ted(dte_data, case)

        # Agregar TED a los datos del DTE como Markup para que no se escape
        from markupsafe import Markup
        dte_data['TED'] = Markup(ted_xml)

        # Generar XML del DTE (ahora incluye el TED)
        dte_xml = self._generate_dte_xml(dte_data, case)

        # Generar código de barras PDF417
        barcode_image = self._generate_barcode(ted_xml)

        # Crear registro de documento generado
        # IMPORTANTE: Codificar como ISO-8859-1 para coincidir con la declaración XML
        document = self.env['l10n_cl_edi.certification.generated.document'].create({
            'project_id': case.project_id.id,
            'case_id': case.id,
            'document_type_id': case.document_type_id.id,
            'folio': folio,
            'issue_date': fields.Date.context_today(self),
            'emission_date': fields.Datetime.now(),
            'receiver_rut': case.project_id.client_info_id.rut or '60803000-K',  # SII default
            'receiver_name': case.project_id.client_info_id.social_reason or 'SII',
            'xml_dte_file': base64.b64encode(dte_xml.encode('ISO-8859-1')),
            'ted_xml': ted_xml,
            'barcode_image': barcode_image,
            'subtotal_taxable': case.subtotal_taxable,
            'subtotal_exempt': case.subtotal_exempt,
            'tax_amount': case.tax_amount,
            'total_amount': case.total_amount,
            'state': 'generated',
        })

        return document

    def _prepare_dte_data(self, case, folio):
        """Prepara los datos para generar el DTE"""

        print('=' * 80)
        print(f'PREPARANDO DTE: {case.name} (Folio: {folio})')
        print(f'Tipo Documento: {case.document_type_code}')
        print(f'Número de líneas: {len(case.line_ids)}')

        client_info = case.project_id.client_info_id
        if not client_info:
            raise UserError(_('El proyecto no tiene información del cliente configurada.'))

        # Calcular montos
        subtotal_taxable = case.subtotal_taxable
        subtotal_exempt = case.subtotal_exempt
        tax_amount = case.tax_amount
        total = case.total_amount

        # Obtener código ACTECO principal de las actividades económicas
        acteco_code = None
        if client_info.company_activity_ids:
            # Usar la primera actividad económica registrada
            acteco_code = client_info.company_activity_ids[0].code

        if not acteco_code:
            # Fallback por defecto: 620200 = "Servicios de consultoría informática y de gestión"
            acteco_code = '620200'

        # Preparar datos del emisor
        emisor = {
            'RUTEmisor': client_info.rut,
            'RznSoc': client_info.social_reason,
            'GiroEmis': client_info.activity_description[:80],  # Máx 80 caracteres
            'Acteco': acteco_code,  # Código de actividad económica (6 dígitos)
            'DirOrigen': client_info.address,
            'CmnaOrigen': client_info.city,
        }

        # Agregar email del emisor si existe
        if client_info.email:
            emisor['CorreoEmisor'] = client_info.email

        # Preparar datos del receptor (usualmente SII para certificación)
        receptor = {
            'RUTRecep': '60803000-K',  # RUT del SII
            'RznSocRecep': 'Servicio de Impuestos Internos',
            'GiroRecep': 'Administración Publica',
            'DirRecep': 'Teatinos 120',
            'CmnaRecep': 'Santiago',
            'CorreoRecep': 'oficina.partes@sii.cl',  # Email del SII por defecto
        }

        # Preparar datos del documento
        fecha_emision = fields.Date.context_today(self).strftime('%Y-%m-%d')
        id_doc = {
            'TipoDTE': int(case.document_type_code),
            'Folio': folio,
            'FchEmis': fecha_emision,
            'FchVenc': fecha_emision,  # Por defecto igual a fecha de emisión
        }

        # IMPORTANTE: Para certificación, TODOS los documentos deben tener una referencia al caso
        # Según SII: Primera línea de referencia debe ser TpoDocRef="SET" y RazonRef="CASO xxxxx-x"
        referencias = []

        # Línea 1: OBLIGATORIA para certificación - Identificador del caso
        # Es una auto-referencia: el documento referencia a sí mismo con TpoDocRef="SET"
        referencias.append({
            'NroLinRef': 1,
            'TpoDocRef': 'SET',  # Texto exacto según instrucciones SII
            'FolioRef': folio,  # Folio del PROPIO documento (auto-referencia)
            'FchRef': fecha_emision,  # Fecha del propio documento
            'RazonRef': case.name,  # "CASO 4609305-1", "CASO 4609305-2", etc.
        })

        # Línea 2+: Referencias adicionales (para NC/ND)
        if case.reference_case_id and case.reference_case_id.generated_document_id:
            ref_doc = case.reference_case_id.generated_document_id

            # Determinar CodRef automáticamente según la razón de referencia
            # CodRef 1 = Anula Documento de Referencia
            # CodRef 2 = Corrige texto del Documento de Referencia
            # CodRef 3 = Corrige montos del Documento de Referencia
            cod_ref = 3  # Por defecto: corrige montos
            razon_upper = (case.reference_reason or '').upper()

            if 'ANULA' in razon_upper:
                cod_ref = 1  # Anula documento
            elif 'CORRIGE' in razon_upper and total == 0:
                cod_ref = 2  # Corrige texto (NC/ND administrativa sin monto)

            referencias.append({
                'NroLinRef': 2,  # Segunda línea (la primera es del SET)
                'TpoDocRef': ref_doc.document_type_code,
                'FolioRef': ref_doc.folio,
                'FchRef': ref_doc.issue_date.strftime('%Y-%m-%d'),
                'CodRef': cod_ref,
                'RazonRef': case.reference_reason or 'Referencia a documento original',
            })

        # Preparar detalle (líneas)
        detalle = []
        if case.line_ids:
            # Caso normal: tiene líneas
            for idx, line in enumerate(case.line_ids, start=1):
                item = {
                    'NroLinDet': idx,
                    'NmbItem': line.description,
                    'DscItem': line.description,  # Mismo valor que NmbItem
                    'QtyItem': round(float(line.qty), 6),  # 6 decimales
                    'PrcItem': round(float(line.price_unit), 6),  # 6 decimales
                }

                # IMPORTANTE: Si hay descuento, debemos enviar DescuentoMonto (no DescuentoPct)
                # porque line.subtotal YA tiene el descuento aplicado
                if line.discount > 0:
                    base = line.qty * line.price_unit
                    descuento_monto = base * (line.discount / 100.0)
                    item['DescuentoMonto'] = int(round(descuento_monto))
                    # Nota: El SII validará que MontoItem = (PrcItem × QtyItem) - DescuentoMonto

                if line.exempt:
                    item['IndExe'] = 1

                # MontoItem debe ser el total de la línea (con descuento aplicado si existe)
                item['MontoItem'] = int(round(line.subtotal))

                detalle.append(item)
        else:
            # Sin líneas: crear una línea descriptiva
            # El SII requiere al menos una línea de detalle
            import logging
            _logger = logging.getLogger(__name__)
            print('⚠️ Caso sin líneas - Creando detalle por defecto')
            print(f'Total del caso: {total}')
            print(f'Reference reason: {case.reference_reason}')

            item_name = case.reference_reason or 'Item de prueba'

            # Para NC/ND administrativas (total=0), NO incluir QtyItem/PrcItem
            # Basado en Odoo Enterprise: cuando price=0 y total=0, estos campos se omiten
            if total == 0 and case.reference_case_id:
                # NC/ND administrativa (monto $0)
                # Solo NmbItem, DscItem y MontoItem (sin QtyItem ni PrcItem)
                detalle.append({
                    'NroLinDet': 1,
                    'NmbItem': item_name,
                    'DscItem': item_name,
                    'MontoItem': 0,
                })
            else:
                # Caso de prueba normal sin líneas
                detalle.append({
                    'NroLinDet': 1,
                    'NmbItem': item_name,
                    'DscItem': item_name,
                    'QtyItem': 1,
                    'PrcItem': int(total) if total else 1000,
                    'MontoItem': int(total) if total else 1000,
                })

        # Validación: siempre debe haber al menos un detalle
        if not detalle:
            import logging
            _logger = logging.getLogger(__name__)
            print('❌ ERROR CRÍTICO: No se generó ningún detalle')
            detalle.append({
                'NroLinDet': 1,
                'NmbItem': 'Item de emergencia',
                'DscItem': 'Item de emergencia',  # Mismo valor que NmbItem
                'QtyItem': 1,
                'PrcItem': 1000,
                'MontoItem': 1000,
            })

        # Preparar descuentos/recargos globales
        desc_rcg_global = []
        if case.global_discount > 0:
            desc_rcg_global.append({
                'NroLinDR': 1,
                'TpoMov': 'D',  # D=Descuento, R=Recargo
                'TpoValor': '%',  # %=Porcentaje, $=Monto
                'ValorDR': case.global_discount,
            })

        # Preparar totales
        # IMPORTANTE: TasaIVA debe incluirse para documentos afectos a IVA (tipos 33, 34, 56, 61, etc.)
        # incluso cuando el monto de IVA es 0 (como en NC/ND administrativas)
        totales = {
            'MntNeto': int(subtotal_taxable) if subtotal_taxable else 0,
            'MntExe': int(subtotal_exempt) if subtotal_exempt else 0,
            'TasaIVA': 19,  # Siempre incluir TasaIVA para documentos tributables
            'IVA': int(tax_amount) if tax_amount else 0,
            'MntTotal': int(total),
        }

        print(f'✓ Detalles generados: {len(detalle)}')
        for idx, det in enumerate(detalle, 1):
            qty = det.get('QtyItem', 'N/A')
            precio = det.get('PrcItem', 'N/A')
            print(f'  Línea {idx}: {det["NmbItem"]} - Qty: {qty} - Precio: {precio} - Total: {det["MontoItem"]}')
        print('=' * 80)

        # Timestamp de firma (obligatorio según XSD) - SIN timezone
        santiago_tz = pytz.timezone('America/Santiago')
        now_santiago = datetime.now(santiago_tz)
        tmst_firma = now_santiago.strftime('%Y-%m-%dT%H:%M:%S')  # SIN timezone

        return {
            'Encabezado': {
                'IdDoc': id_doc,
                'Emisor': emisor,
                'Receptor': receptor,
                'Totales': totales,
            },
            'Detalle': detalle,
            'DscRcgGlobal': desc_rcg_global if desc_rcg_global else False,
            'Referencia': referencias if referencias else False,
            'TmstFirma': tmst_firma,
        }

    def _generate_dte_xml(self, dte_data, case):
        """
        Genera el XML del DTE usando template QWeb.
        """
        from markupsafe import Markup

        print('\n' + '=' * 80)
        print('GENERANDO XML CON TEMPLATE QWEB')
        print(f"Template: l10n_cl_edi_certification.dte_certification_template")
        print(f"Detalles a renderizar: {len(dte_data.get('Detalle', []))}")

        # Renderizar el template
        template = 'l10n_cl_edi_certification.dte_certification_template'
        xml_content = self.env['ir.qweb']._render(template, {
            'dte_data': dte_data,
            'case': case,
            '__keep_empty_lines': True,  # Preservar indentación y saltos de línea (como Odoo Enterprise)
        })

        # Convertir a string (QWeb puede retornar bytes)
        xml_str = xml_content.decode('ISO-8859-1') if isinstance(xml_content, bytes) else xml_content

        # Convertir a string si es Markup
        if isinstance(xml_str, Markup):
            xml_str = str(xml_str)

        # Nota: No es necesario agregar la declaración XML aquí porque el método _sign_full_xml
        # de Enterprise ya lo hace automáticamente cuando se firma el documento

        # Verificar si el XML contiene elementos Detalle
        if '<Detalle>' in xml_str:
            print(f"✓ XML contiene elementos <Detalle>")
            detalle_count = xml_str.count('<Detalle>')
            print(f"  Cantidad de elementos <Detalle>: {detalle_count}")
        else:
            print("❌ ERROR: XML NO contiene elementos <Detalle>")
            print("Primeros 1000 caracteres del XML:")
            print(xml_str[:1000])
        print('=' * 80 + '\n')

        return xml_str

    def _generate_ted(self, dte_data, case):
        """
        Genera el TED (Timbre Electrónico del Documento).
        El TED se firma con la clave privada del CAF.
        Extrae datos reales del CAF: RNG, FA, RSAPK.
        """
        # Importaciones necesarias
        from xml.sax.saxutils import escape
        from lxml import etree
        from markupsafe import Markup
        import base64

        # Obtener el CAF assignment para este tipo de documento
        assignment = self.env['l10n_cl_edi.certification.folio.assignment'].search([
            ('project_id', '=', case.project_id.id),
            ('document_type_id', '=', case.document_type_id.id),
        ], limit=1)

        if not assignment:
            raise UserError(_('No hay asignación de folios para este tipo de documento.'))

        # Obtener el contenido XML del CAF
        try:
            caf_content = assignment.get_caf_content()
            # Parsear el CAF con encoding ISO-8859-1 (formato del SII)
            # Igual que Odoo Enterprise en l10n_cl.dte.caf._decode_caf()
            parser = etree.XMLParser(encoding='ISO-8859-1', remove_blank_text=True)
            caf_xml = etree.fromstring(caf_content.encode('ISO-8859-1'), parser)
        except Exception as e:
            raise UserError(_('Error al leer el CAF: %s') % str(e))

        # Extraer datos del CAF siguiendo el método de Odoo Enterprise
        try:
            # Estructura: //AUTORIZACION/CAF/DA
            da_node = caf_xml.xpath('//AUTORIZACION/CAF/DA')
            if not da_node:
                raise UserError(_('No se encontró el nodo DA en el archivo CAF.'))

            da = da_node[0]

            # Extraer RNG (Rango de folios)
            rng_d = da.xpath('RNG/D')[0].text  # Desde
            rng_h = da.xpath('RNG/H')[0].text  # Hasta

            # Extraer FA (Fecha de Autorización)
            fa = da.xpath('FA')[0].text

            # Extraer RSAPK (RSA Public Key)
            rsapk_m = da.xpath('RSAPK/M')[0].text  # Módulo
            rsapk_e = da.xpath('RSAPK/E')[0].text  # Exponente

            # Extraer FRMA (Firma del CAF)
            frma_node = caf_xml.xpath('//AUTORIZACION/CAF/FRMA')
            frma = frma_node[0].text if frma_node else ''

            print(f'\n✓ Datos extraídos del CAF:')
            print(f'  RNG: {rng_d} - {rng_h}')
            print(f'  FA: {fa}')
            print(f'  RSAPK/M: {rsapk_m[:50]}...')
            print(f'  RSAPK/E: {rsapk_e}')

        except Exception as e:
            raise UserError(_('Error al extraer datos del CAF: %s') % str(e))

        # Obtener el nombre del primer item
        item1_name = dte_data['Detalle'][0]['NmbItem'] if dte_data['Detalle'] else ''

        # Paso 1: Preparar datos para el DD (Document Data)
        dd_data = {
            'RutEmisor': dte_data['Encabezado']['Emisor']['RUTEmisor'],
            'TipoDTE': dte_data['Encabezado']['IdDoc']['TipoDTE'],
            'Folio': dte_data['Encabezado']['IdDoc']['Folio'],
            'FchEmis': dte_data['Encabezado']['IdDoc']['FchEmis'],
            'RutRecep': dte_data['Encabezado']['Receptor']['RUTRecep'],
            'RznSocRecep': dte_data['Encabezado']['Receptor']['RznSocRecep'],
            'MntTotal': dte_data['Encabezado']['Totales']['MntTotal'],
            'IT1': item1_name,
            'TSTED': dte_data['TmstFirma'],
            'CAF': {
                'RutEmisor': dte_data['Encabezado']['Emisor']['RUTEmisor'],
                'RznSoc': dte_data['Encabezado']['Emisor']['RznSoc'],
                'TipoDTE': dte_data['Encabezado']['IdDoc']['TipoDTE'],
                'RNG_D': rng_d,
                'RNG_H': rng_h,
                'FA': fa,
                'RSAPK_M': rsapk_m,
                'RSAPK_E': rsapk_e,
                'FRMA': frma,
            }
        }

        # Generar DD usando template QWeb (con indentación)
        from markupsafe import Markup
        dd_xml = self.env['ir.qweb']._render('l10n_cl_edi_certification.dd_certification_template', {
            'dd_data': dd_data,
            '__keep_empty_lines': True,
        })

        # Convertir a string
        dd_xml_str = dd_xml.decode('ISO-8859-1') if isinstance(dd_xml, bytes) else dd_xml
        if isinstance(dd_xml_str, Markup):
            dd_xml_str = str(dd_xml_str)

        # Paso 2: Extraer RSASK (clave privada RSA) del CAF
        try:
            rsask_node = caf_xml.xpath('//RSASK')
            if not rsask_node:
                # Intentar con ruta completa
                rsask_node = caf_xml.xpath('//AUTORIZACION/CAF/RSASK')

            if not rsask_node:
                raise UserError(_('No se encontró RSASK (clave privada) en el CAF.'))

            rsask_pem = rsask_node[0].text
            if not rsask_pem:
                raise UserError(_('El nodo RSASK está vacío en el CAF.'))

            rsask_pem = rsask_pem.strip()  # Limpiar espacios y saltos de línea
            print(f'✓ RSASK extraído del CAF')
        except Exception as e:
            raise UserError(_('Error al extraer RSASK del CAF: %s') % str(e))

        # Paso 3: Firmar el DD con RSASK usando SHA1withRSA (como lo hace Odoo Enterprise)
        import re
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        try:
            # Limpiar el DD: remover saltos de línea y espacios (igual que Odoo Enterprise)
            dd_clean = re.sub(r'\n\s*', '', dd_xml_str)

            # Cargar la clave privada RSA desde PEM
            private_key = serialization.load_pem_private_key(
                rsask_pem.encode('utf-8'),
                password=None,  # CAF no tiene password en RSASK
                backend=default_backend()
            )

            # Firmar el DD con SHA1 (algoritmo requerido por SII)
            signature = private_key.sign(
                dd_clean.encode('ISO-8859-1'),
                padding.PKCS1v15(),  # SHA1withRSA usa PKCS1v15 padding
                hashes.SHA1()  # SII requiere SHA1
            )

            # Codificar firma en base64
            frmt = base64.b64encode(signature).decode('utf-8')
            print(f'✓ TED firmado con RSASK del CAF')

        except Exception as e:
            raise UserError(_('Error al firmar el DD con RSASK: %s') % str(e))

        # Paso 4: Construir el TED completo usando template QWeb (con indentación)
        # Preparar datos para el TED
        ted_data = {
            'DD': Markup(dd_xml_str),  # Pasar DD como Markup para que no se escape
            'FRMT': frmt,
        }

        # Generar TED usando template QWeb
        ted_xml = self.env['ir.qweb']._render('l10n_cl_edi_certification.ted_certification_template', {
            'ted_data': ted_data,
            '__keep_empty_lines': True,
        })

        # Convertir a string
        ted_xml_str = ted_xml.decode('ISO-8859-1') if isinstance(ted_xml, bytes) else ted_xml
        if isinstance(ted_xml_str, Markup):
            ted_xml_str = str(ted_xml_str)

        return ted_xml_str

    def _generate_barcode(self, ted_xml):
        """
        Genera el código de barras PDF417 del TED.
        Retorna la imagen en base64.
        """
        # Aquí deberías usar una librería para generar PDF417
        # Por ejemplo: pdf417gen o similar

        # Por ahora retornamos None
        # En producción, deberías generar la imagen real del código de barras
        return False

    @api.model
    def calculate_amounts(self, case):
        """
        Calcula los montos de un caso de prueba.
        Este método es público y puede ser llamado desde otros lugares.

        Returns:
            dict con {subtotal_taxable, subtotal_exempt, tax_amount, discount_amount, total_amount}
        """
        subtotal_taxable = sum(line.subtotal for line in case.line_ids if not line.exempt)
        subtotal_exempt = sum(line.subtotal for line in case.line_ids if line.exempt)

        # Aplicar descuento global solo al subtotal afecto
        discount_amount = 0
        if case.global_discount and subtotal_taxable:
            discount_amount = subtotal_taxable * (case.global_discount / 100.0)
            subtotal_taxable -= discount_amount

        # Calcular IVA (19%)
        tax_amount = subtotal_taxable * 0.19

        # Total
        total_amount = subtotal_taxable + tax_amount + subtotal_exempt

        return {
            'subtotal_taxable': subtotal_taxable,
            'subtotal_exempt': subtotal_exempt,
            'discount_amount': discount_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
        }
