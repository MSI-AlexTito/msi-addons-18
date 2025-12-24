# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
from datetime import datetime
from lxml import etree
import base64
import io
import logging

_logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm, cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.pdfgen import canvas
except ImportError:
    _logger.warning('ReportLab library not found. PDF generation will not work.')

try:
    import pdf417gen
except ImportError:
    _logger.warning('pdf417gen library not found. TED barcode generation will not work.')


class PDFGeneratorService(models.AbstractModel):
    """
    Servicio para generar PDFs impresos de DTEs con Timbre Electrónico (TED).

    Genera PDFs con formato tributario chileno estándar que incluyen:
    - Información del DTE (emisor, receptor, detalle)
    - Timbre Electrónico (TED) en código de barras PDF417
    - Leyendas legales requeridas por SII
    """
    _name = 'l10n_cl_edi.pdf.generator.service'
    _description = 'Servicio Generador de PDFs para DTEs'

    @api.model
    def generate_ted_xml(self, document):
        """
        Genera el XML del Timbre Electrónico del Documento (TED).

        El TED contiene la información esencial del DTE y debe ser firmado
        con la clave privada del CAF.

        Formato según SII:
        <TED version="1.0">
            <DD>...</DD>
            <FRMT algoritmo="SHA1withRSA">...</FRMT>
        </TED><TmstFirma>...</TmstFirma>

        Args:
            document: l10n_cl_edi.certification.generated.document

        Returns:
            str: XML del TED firmado con TmstFirma
        """
        client_info = document.project_id.client_info_id

        # Obtener el CAF usado para este documento
        folio_assignment = self.env['l10n_cl_edi.certification.folio.assignment'].search([
            ('project_id', '=', document.project_id.id),
            ('document_type_id', '=', document.document_type_id.id),
            ('folio_start', '<=', document.folio),
            ('folio_end', '>=', document.folio),
        ], limit=1)

        if not folio_assignment:
            raise UserError(_(
                'No se encontró el CAF para el folio %s del tipo de documento %s'
            ) % (document.folio, document.document_type_id.name))

        # Verificar que tenga CAF
        if not folio_assignment.caf_file:
            raise UserError(_(
                'La asignación de folios %s-%s no tiene archivo CAF cargado'
            ) % (folio_assignment.folio_start, folio_assignment.folio_end))

        # Decodificar el CAF XML
        caf_xml_str = base64.b64decode(folio_assignment.caf_file).decode('ISO-8859-1')
        caf_root = etree.fromstring(caf_xml_str.encode('ISO-8859-1'))

        # Extraer el nodo DA completo del CAF
        caf_da = caf_root.find('.//DA')
        if caf_da is None:
            raise UserError(_('No se encontró el nodo DA en el CAF'))

        # CRÍTICO: Verificar que el folio esté en el rango del CAF
        caf_rng_d = caf_da.find('.//RNG/D')
        caf_rng_h = caf_da.find('.//RNG/H')
        if caf_rng_d is not None and caf_rng_h is not None:
            caf_start = int(caf_rng_d.text)
            caf_end = int(caf_rng_h.text)
            if int(document.folio) < caf_start or int(document.folio) > caf_end:
                print(f'\n❌ ERROR CRÍTICO - FOLIO FUERA DE RANGO CAF:')
                print(f'   Documento: {document.document_type_id.name} #{document.folio}')
                print(f'   Asignación en Odoo: Folios {folio_assignment.folio_start}-{folio_assignment.folio_end}')
                print(f'   Rango en archivo CAF: [{caf_start}-{caf_end}]')
                print(f'   ⚠️  El archivo CAF adjunto NO cubre el folio {document.folio}')
                print(f'   SOLUCIÓN: Sube el CAF correcto en la asignación de folios {folio_assignment.folio_start}-{folio_assignment.folio_end}\n')

                raise UserError(_(
                    'ERROR: El folio %s está fuera del rango autorizado en el CAF.\n\n'
                    'Asignación en Odoo: %s-%s\n'
                    'Rango en archivo CAF: [%s-%s]\n\n'
                    'El archivo CAF adjunto a la asignación de folios no corresponde.\n'
                    'Por favor, sube el CAF correcto que cubra el rango %s-%s.'
                ) % (
                    document.folio,
                    folio_assignment.folio_start, folio_assignment.folio_end,
                    caf_start, caf_end,
                    folio_assignment.folio_start, folio_assignment.folio_end
                ))

        # Extraer el nodo FRMA del CAF
        caf_frma = caf_root.find('.//FRMA')
        if caf_frma is None:
            raise UserError(_('No se encontró el nodo FRMA en el CAF'))

        # Obtener primer item del detalle para IT1
        primer_item = 'Item de prueba'

        if document.detalle_json:
            import json
            try:
                if isinstance(document.detalle_json, str):
                    detalle_items = json.loads(document.detalle_json)
                elif isinstance(document.detalle_json, bytes):
                    detalle_items = json.loads(document.detalle_json.decode('utf-8'))
                else:
                    detalle_items = document.detalle_json

                if detalle_items and len(detalle_items) > 0:
                    if isinstance(detalle_items[0], dict) and 'nombre' in detalle_items[0]:
                        primer_item = detalle_items[0]['nombre']
                    elif isinstance(detalle_items[0], dict) and 'description' in detalle_items[0]:
                        primer_item = detalle_items[0]['description']
                    else:
                        primer_item = str(detalle_items[0])
            except:
                primer_item = 'Item de prueba'

        # Limitar a 40 caracteres como lo hace el módulo enterprise
        primer_item = primer_item[:40]

        # Timestamps
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # Construir DD del TED (Document Digest)
        # Formato según template enterprise
        dd_xml = f"""<DD>
<RE>{client_info.rut}</RE>
<TD>{document.document_type_code}</TD>
<F>{document.folio}</F>
<FE>{document.issue_date.strftime('%Y-%m-%d')}</FE>
<RR>{document.receiver_rut}</RR>
<RSR>{(document.receiver_name or 'RECEPTOR')[:40]}</RSR>
<MNT>{document.mnt_total}</MNT>
<IT1>{primer_item}</IT1>
<CAF version="1.0">
<DA>
{etree.tostring(caf_da, encoding='unicode', method='html').replace('<DA>', '').replace('</DA>', '').strip()}
</DA>
<FRMA algoritmo="{caf_frma.get('algoritmo')}">{caf_frma.text}</FRMA>
</CAF>
<TSTED>{timestamp}</TSTED>
</DD>"""

        # Firmar el DD con la clave privada del CAF
        frmt = self._sign_ted_with_caf(dd_xml, caf_root)

        # Construir TED completo con TmstFirma
        ted_xml = f"""<TED version="1.0">
{dd_xml}
<FRMT algoritmo="SHA1withRSA">{frmt}</FRMT>
</TED><TmstFirma>{timestamp}</TmstFirma>"""

        return ted_xml

    def _sign_ted_with_caf(self, dd_xml, caf_root):
        """
        Firma el DD del TED con la clave privada del CAF.

        Utiliza el método de Odoo certificate.key._sign_with_key para firmar
        el DD con la clave privada RSA del CAF (RSASK) usando SHA1withRSA.

        Este método replica exactamente el enfoque usado en l10n_cl_edi enterprise.

        Args:
            dd_xml: XML del DD a firmar (string)
            caf_root: Elemento raíz del CAF (etree element)

        Returns:
            str: Firma en Base64
        """
        import re

        # Extraer la clave privada del CAF (RSASK)
        rsask_node = caf_root.find('.//RSASK')
        if rsask_node is None:
            raise UserError(_('No se encontró la clave privada (RSASK) en el CAF'))

        # Limpiar el DD eliminando saltos de línea y espacios
        dd_clean = re.sub(b'\n\\s*', b'', dd_xml.encode('ISO-8859-1', 'replace'))

        # Extraer RSASK y codificarlo en base64 (doble codificación como en enterprise)
        rsask_text = rsask_node.text.strip()
        rsask_encoded = base64.b64encode(rsask_text.encode('utf-8'))

        # Usar el método de Odoo para firmar (igual que l10n_cl_edi enterprise)
        try:
            signature_b64 = self.env['certificate.key']._sign_with_key(
                dd_clean,
                rsask_encoded,
                hashing_algorithm='sha1',
                formatting='base64',
            ).decode()
            return signature_b64
        except Exception as e:
            raise UserError(_(
                'Error al firmar el TED con la clave privada del CAF.\n'
                'Error: %s'
            ) % str(e))

    @api.model
    def generate_ted_barcode(self, ted_xml):
        """
        Genera el código de barras PDF417 del TED.

        El código de barras contiene el TED sin el tag TmstFirma
        (igual que el módulo enterprise).

        Args:
            ted_xml: XML del TED completo con TmstFirma

        Returns:
            bytes: Imagen PNG del código de barras
        """
        import re


        try:
            # Remover el TmstFirma del TED para el código de barras
            # (como lo hace el módulo enterprise)
            ted_for_barcode = re.sub(
                r'<TmstFirma>.*?</TmstFirma>',
                '',
                ted_xml
            )

            # Generar código de barras PDF417
            # Parámetros según módulo enterprise:
            # - security_level=5
            # - columns=13
            barcode = pdf417gen.encode(
                ted_for_barcode,
                columns=13,
                security_level=5
            )

            # Convertir a imagen PIL
            # Parámetros según módulo enterprise:
            # - padding=15
            # - scale=1
            image = pdf417gen.render_image(barcode, padding=15, scale=1)

            # Guardar en buffer
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)


            return buffer.getvalue()

        except Exception as e:
            _logger.error(f'Error al generar código de barras PDF417: {e}')
            raise UserError(_('Error al generar código de barras PDF417:\n%s') % str(e))

    @api.model
    def generate_printed_pdf(self, document):
        """
        Genera el PDF impreso del DTE con formato tributario chileno.

        Incluye:
        - Información del emisor y receptor
        - Detalle de items
        - Totales
        - Timbre Electrónico (TED) en código de barras PDF417
        - Leyendas legales

        Args:
            document: l10n_cl_edi.certification.generated.document

        Returns:
            bytes: PDF generado
        """
        # Verificar que tenga TED
        if not document.ted_xml:
            raise UserError(_(
                'El documento no tiene TED generado. '
                'Debe generar el TED antes de crear el PDF.'
            ))

        # Verificar que tenga código de barras
        if not document.barcode_image:
            raise UserError(_(
                'El documento no tiene código de barras generado. '
                'Debe generar el TED antes de crear el PDF.'
            ))

        # Crear buffer para el PDF
        buffer = io.BytesIO()

        # Crear documento PDF
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )

        # Contenedor de elementos
        story = []
        styles = getSampleStyleSheet()

        # Estilos personalizados
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f4788'),
            alignment=TA_CENTER,
            spaceAfter=12
        )

        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_LEFT
        )

        # 1. ENCABEZADO - TIPO DE DOCUMENTO
        doc_type_name = document.document_type_id.name.upper()
        story.append(Paragraph(f'<b>{doc_type_name}</b>', title_style))
        story.append(Paragraph(f'<b>N° {document.folio}</b>', title_style))
        story.append(Spacer(1, 0.3*cm))

        # 2. INFORMACIÓN DEL EMISOR
        client_info = document.project_id.client_info_id
        emisor_data = [
            ['<b>EMISOR</b>', ''],
            ['RUT:', client_info.rut],
            ['Razón Social:', client_info.social_reason],
            ['Giro:', client_info.activity_description or '-'],
            ['Dirección:', f"{client_info.address or '-'}, {client_info.city or '-'}"],
        ]

        emisor_table = Table(emisor_data, colWidths=[3.5*cm, 12*cm])
        emisor_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(emisor_table)
        story.append(Spacer(1, 0.5*cm))

        # 3. INFORMACIÓN DEL RECEPTOR
        receptor_data = [
            ['<b>RECEPTOR</b>', ''],
            ['RUT:', document.receiver_rut or '-'],
            ['Razón Social:', document.receiver_name or '-'],
            ['Giro:', document.receiver_giro or '-'],
            ['Dirección:', f"{document.receiver_address or '-'}, {document.receiver_comuna or '-'}"],
        ]

        receptor_table = Table(receptor_data, colWidths=[3.5*cm, 12*cm])
        receptor_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(receptor_table)
        story.append(Spacer(1, 0.5*cm))

        # 4. FECHA EMISIÓN
        fecha_data = [
            ['Fecha Emisión:', document.issue_date.strftime('%d-%m-%Y')],
        ]
        fecha_table = Table(fecha_data, colWidths=[3.5*cm, 12*cm])
        fecha_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        story.append(fecha_table)
        story.append(Spacer(1, 0.5*cm))

        # 5. DETALLE DE ITEMS
        detalle_items = []
        if document.detalle_json:
            import json
            try:
                # Intentar parsear el JSON con manejo de errores
                if isinstance(document.detalle_json, str):
                    detalle_items = json.loads(document.detalle_json)
                elif isinstance(document.detalle_json, bytes):
                    detalle_items = json.loads(document.detalle_json.decode('utf-8'))
                else:
                    detalle_items = document.detalle_json
            except (json.JSONDecodeError, Exception) as e:
                # Continuar con lista vacía, se agregará item por defecto
                detalle_items = []

        detalle_header = ['Item', 'Descripción', 'Cantidad', 'Precio Unit.', 'Total']
        detalle_data = [detalle_header]

        for idx, item in enumerate(detalle_items, 1):
            # Manejar diferentes formatos de item
            if isinstance(item, dict):
                nombre = item.get('nombre') or item.get('description') or 'Item'
                cantidad = item.get('cantidad') or item.get('quantity') or 1
                precio = item.get('precio') or item.get('price') or 0
                total = item.get('total') or item.get('amount') or 0
            else:
                nombre = str(item)
                cantidad = 1
                precio = 0
                total = 0

            detalle_data.append([
                str(idx),
                nombre,
                str(cantidad),
                f"${precio:,.0f}",
                f"${total:,.0f}",
            ])

        # Si no hay items, mostrar al menos uno por defecto
        if len(detalle_data) == 1:
            detalle_data.append(['1', 'Item genérico', '1', f"${document.mnt_total:,.0f}", f"${document.mnt_total:,.0f}"])

        detalle_table = Table(detalle_data, colWidths=[1.5*cm, 7*cm, 2*cm, 2.5*cm, 2.5*cm])
        detalle_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(detalle_table)
        story.append(Spacer(1, 0.5*cm))

        # 6. TOTALES
        totales_data = []

        # Monto Neto (si aplica)
        if document.mnt_neto > 0:
            totales_data.append(['Monto Neto:', f"${document.mnt_neto:,.0f}"])

        # Monto Exento (si aplica)
        if document.mnt_exento > 0:
            totales_data.append(['Monto Exento:', f"${document.mnt_exento:,.0f}"])

        # IVA (si aplica)
        if document.mnt_iva > 0:
            totales_data.append([f'IVA ({document.iva_percent}%):', f"${document.mnt_iva:,.0f}"])

        # Total
        totales_data.append(['<b>TOTAL:</b>', f"<b>${document.mnt_total:,.0f}</b>"])

        totales_table = Table(totales_data, colWidths=[10.5*cm, 5*cm])
        totales_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(totales_table)
        story.append(Spacer(1, 1*cm))

        # 7. TIMBRE ELECTRÓNICO (TED)
        story.append(Paragraph('<b>TIMBRE ELECTRÓNICO SII</b>', title_style))
        story.append(Spacer(1, 0.3*cm))

        # Decodificar imagen del código de barras
        barcode_data = base64.b64decode(document.barcode_image)
        barcode_buffer = io.BytesIO(barcode_data)

        # Agregar imagen del código de barras
        barcode_img = Image(barcode_buffer, width=10*cm, height=3*cm)
        barcode_img.hAlign = 'CENTER'
        story.append(barcode_img)
        story.append(Spacer(1, 0.3*cm))

        # 8. LEYENDAS LEGALES
        leyenda_style = ParagraphStyle(
            'Leyenda',
            parent=styles['Normal'],
            fontSize=7,
            alignment=TA_CENTER,
            textColor=colors.grey
        )

        story.append(Paragraph(
            'Timbre Electrónico SII<br/>'
            f'Resolución Exenta SII - Fecha: {document.issue_date.strftime("%d-%m-%Y")}<br/>'
            'Verifique documento en: www.sii.cl',
            leyenda_style
        ))

        # Construir PDF
        doc.build(story)

        # Obtener PDF
        buffer.seek(0)
        pdf_data = buffer.getvalue()
        buffer.close()

        return pdf_data
