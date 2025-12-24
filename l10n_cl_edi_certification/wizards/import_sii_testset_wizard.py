# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from ..services.sii_testset_parser import SIITestSetParser

import logging
_logger = logging.getLogger(__name__)

class ImportSIITestSetWizard(models.TransientModel):
    """
    Wizard para importar Set de Pruebas desde archivo del SII.
    """
    _name = 'l10n_cl_edi.import.sii.testset.wizard'
    _description = 'Importar Set de Pruebas SII'

    project_id = fields.Many2one(
        'l10n_cl_edi.certification.project',
        string='Proyecto',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
        readonly=True
    )

    file = fields.Binary(
        string='Archivo del SII',
        required=True,
        help='Archivo .txt descargado del sitio del SII con el set de pruebas'
    )
    filename = fields.Char(
        string='Nombre del Archivo'
    )

    attention_number = fields.Char(
        string='Número de Atención',
        readonly=True,
        help='Número de atención detectado en el archivo'
    )

    cases_count = fields.Integer(
        string='Casos Detectados',
        readonly=True
    )

    preview_text = fields.Text(
        string='Vista Previa',
        readonly=True
    )

    state = fields.Selection([
        ('upload', 'Subir Archivo'),
        ('done', 'Completado'),
    ], default='upload', string='Estado')

    error_messages = fields.Text(
        string='Errores',
        readonly=True
    )

    @api.onchange('file')
    def _onchange_file(self):
        """Parsea el archivo cuando se carga."""
        import logging
        _logger = logging.getLogger(__name__)

        if self.file:
            try:

                # Decodificar archivo
                file_content = base64.b64decode(self.file)

                # Parsear
                result = SIITestSetParser.parse_file(file_content)

                # Actualizar campos
                self.attention_number = result['attention_number']
                self.cases_count = len(result['cases'])

                # Generar preview
                preview_lines = [
                    f"NÚMERO DE ATENCIÓN: {result['attention_number']}",
                    f"CASOS DETECTADOS: {len(result['cases'])}",
                    "",
                    "CASOS:",
                ]

                for case in result['cases']:
                    preview_lines.append(f"  - {case['code']}: {case['name']} ({case['document_type_code']})")
                    if case['items']:
                        preview_lines.append(f"    Items: {len(case['items'])}")
                    if case['global_discount']:
                        preview_lines.append(f"    Descuento Global: {case['global_discount']}%")
                    if case['reference']:
                        preview_lines.append(f"    Referencia: {case['reference']['reference_case_code']}")

                # Mostrar libros detectados
                books = result.get('books', {})
                if books.get('sales_book') or books.get('purchase_book'):
                    preview_lines.append("")
                    preview_lines.append("LIBROS DETECTADOS:")

                    if books.get('sales_book'):
                        sales = books['sales_book']
                        preview_lines.append(f"  - {sales['name']} (Atención: {sales['attention_number']})")

                    if books.get('purchase_book'):
                        purchase = books['purchase_book']
                        lines_count = len(purchase.get('lines', []))
                        preview_lines.append(f"  - {purchase['name']} (Atención: {purchase['attention_number']})")
                        preview_lines.append(f"    Líneas: {lines_count}")

                if result['errors']:
                    preview_lines.append("")
                    preview_lines.append("ERRORES:")
                    for error in result['errors']:
                        preview_lines.append(f"  - {error}")
                    self.error_messages = '\n'.join(result['errors'])
                else:
                    self.error_messages = False

                self.preview_text = '\n'.join(preview_lines)

            except Exception as e:
                _logger.exception('ERROR EN WIZARD AL PROCESAR ARCHIVO:')
                error_detail = f"ERROR: {str(e)}\n\nRevise los logs del servidor para más detalles."
                self.preview_text = error_detail
                self.error_messages = str(e)
                self.cases_count = 0
                self.attention_number = False

    def action_import(self):
        """Importa los casos al proyecto."""
        self.ensure_one()

        if not self.file:
            raise UserError(_('Debe cargar un archivo.'))

        # Verificar que no haya casos ya importados
        if self.project_id.certification_case_ids:
            raise UserError(_(
                'El proyecto ya tiene casos de prueba.\n'
                'Si desea reimportar, elimine los casos existentes primero.'
            ))

        # Parsear archivo
        file_content = base64.b64decode(self.file)
        result = SIITestSetParser.parse_file(file_content)

        if not result['cases']:
            raise UserError(_('No se detectaron casos en el archivo.'))

        # Crear casos
        CertificationCase = self.env['l10n_cl_edi.certification.case']
        CaseLine = self.env['l10n_cl_edi.certification.case.line']

        cases_created = []
        case_map = {}  # Para resolver referencias

        # Primera pasada: crear todos los casos
        for idx, case_data in enumerate(result['cases'], start=1):
            # Obtener tipo de documento
            doc_type = self.env['l10n_latam.document.type'].search([
                ('code', '=', case_data['document_type_code']),
                ('country_id.code', '=', 'CL'),
            ], limit=1)

            if not doc_type:
                raise UserError(_(
                    'No se encontró el tipo de documento con código %s.\n'
                    'Verifique que el módulo de localización chilena esté instalado.'
                ) % case_data['document_type_code'])

            # Crear caso
            case_vals = {
                'project_id': self.project_id.id,
                'sequence': idx * 10,
                'code': case_data['code'],
                'name': case_data['name'],
                'document_type_id': doc_type.id,
                'global_discount': case_data.get('global_discount', 0),
                'description': f"Importado desde set de pruebas SII (Atención: {result['attention_number']})",
            }

            # Manejar referencia (se resolverá después)
            if case_data.get('reference'):
                case_vals['reference_reason'] = case_data['reference']['reason']

            case = CertificationCase.create(case_vals)
            case_map[case_data['code']] = case

            # Crear líneas
            for line_idx, item_data in enumerate(case_data.get('items', []), start=1):
                CaseLine.create({
                    'case_id': case.id,
                    'sequence': line_idx * 10,
                    'description': item_data['name'],
                    'qty': item_data['qty'],
                    'price_unit': item_data['price_unit'],
                    'discount': item_data.get('discount', 0),
                    'exempt': item_data.get('exempt', False),
                })

            cases_created.append(case.name)

        # Segunda pasada: resolver referencias
        for case_data in result['cases']:
            if case_data.get('reference'):
                ref_code = case_data['reference']['reference_case_code']
                current_case = case_map.get(case_data['code'])
                ref_case = case_map.get(ref_code)

                if current_case and ref_case:
                    current_case.write({
                        'reference_case_id': ref_case.id,
                    })

        # Tercera pasada: copiar precios de factura referenciada a NC/ND
        for case_data in result['cases']:
            current_case = case_map.get(case_data['code'])

            # Solo para NC (61) y ND (56)
            if not current_case or case_data['document_type_code'] not in ['61', '56']:
                continue

            # Solo si tiene referencia
            if not case_data.get('reference'):
                continue

            ref_code = case_data['reference']['reference_case_code']
            ref_case = case_map.get(ref_code)

            if not ref_case:
                continue

            # CASO 1: NC/ND sin ítems que es ANULACIÓN → Copiar TODOS los ítems de la factura
            if not current_case.line_ids and current_case.reference_reason and 'ANULA' in current_case.reference_reason.upper():
                if ref_case.line_ids:
                    # Copiar todos los ítems de la factura original
                    for idx, ref_line in enumerate(ref_case.line_ids, start=1):
                        new_line = CaseLine.create({
                            'case_id': current_case.id,
                            'sequence': idx * 10,
                            'description': ref_line.description,
                            'qty': ref_line.qty,
                            'price_unit': ref_line.price_unit,
                            'discount': ref_line.discount,
                            'exempt': ref_line.exempt,
                        })

                # Recalcular montos del caso
                current_case._compute_amounts()

            # CASO 2: NC/ND con ítems parciales → Copiar solo precios
            elif current_case.line_ids:

                for current_line in current_case.line_ids:
                    # Buscar línea correspondiente en factura original (por nombre del ítem)
                    ref_line = ref_case.line_ids.filtered(
                        lambda l: l.description.strip().upper() == current_line.description.strip().upper()
                    )

                    if ref_line:
                        ref_line = ref_line[0]  # Tomar la primera coincidencia

                        current_line.write({
                            'price_unit': ref_line.price_unit,
                            'discount': ref_line.discount,
                        })


        # =====================================================================
        # PASO 4: Crear libros si fueron detectados
        # =====================================================================
        books_created = []
        books = result.get('books', {})

        if books.get('sales_book'):

            sales_book_data = books['sales_book']
            sales_book = self.env['l10n_cl_edi.certification.book'].create({
                'project_id': self.project_id.id,
                'name': sales_book_data['name'],
                'book_type': 'sale',
                'attention_number': sales_book_data['attention_number'],
                'period': fields.Date.context_today(self).strftime('%Y-%m'),
                'notes': 'Importado desde set de pruebas SII. El libro se generará automáticamente desde los documentos del SET BASICO.',
            })

            books_created.append({
                'name': sales_book.name,
                'type': 'sale',
                'lines_count': 0  # Las líneas se agregan después al generar DTEs
            })

        if books.get('purchase_book'):

            purchase_book_data = books['purchase_book']
            purchase_book = self.env['l10n_cl_edi.certification.book'].create({
                'project_id': self.project_id.id,
                'name': purchase_book_data['name'],
                'book_type': 'purchase',
                'attention_number': purchase_book_data['attention_number'],
                'period': fields.Date.context_today(self).strftime('%Y-%m'),
                'notes': 'Importado desde set de pruebas SII.',
            })

            # Crear líneas del libro de compras
            BookLine = self.env['l10n_cl_edi.certification.book.line']
            for line_data in purchase_book_data.get('lines', []):
                # Calcular IVA y total con redondeo matemático (como el SII)
                from decimal import Decimal, ROUND_HALF_UP

                mnt_neto = line_data['mnt_neto']
                mnt_exento = line_data['mnt_exento']

                # Calcular IVA con redondeo matemático
                if mnt_neto > 0:
                    iva_decimal = Decimal(str(mnt_neto)) * Decimal('0.19')
                    mnt_iva = int(iva_decimal.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                else:
                    mnt_iva = 0

                # Para Tipo 46 (Factura de Compra con IVA Retenido), el total NO incluye el IVA
                # Porque el IVA es retenido por el comprador y no se paga al proveedor
                if line_data['document_type_code'] == '46':
                    mnt_total = mnt_neto + mnt_exento  # SIN IVA
                else:
                    mnt_total = mnt_neto + mnt_exento + mnt_iva

                # Preparar valores base de la línea
                line_vals = {
                    'book_id': purchase_book.id,
                    'sequence': line_data['sequence'],
                    'document_type_code': line_data['document_type_code'],
                    'folio': line_data['folio'],
                    'issue_date': fields.Date.context_today(self),  # Fecha actual
                    'partner_rut': '17096073-4',  # RUT genérico de proveedor
                    'partner_name': 'Razón Social Proveedor',
                    'observations': line_data['observations'],
                    'mnt_exento': mnt_exento,
                    'mnt_neto': mnt_neto,
                    'mnt_iva': mnt_iva,
                    'mnt_total': mnt_total,
                }

                # CONFIGURACIÓN AUTOMÁTICA DE CAMPOS ESPECÍFICOS DE COMPRAS
                tipo_doc = line_data['document_type_code']
                folio = line_data['folio']

                # Tipo 46: Factura de Compra Electrónica → IVA Retenido Total
                if tipo_doc == '46' and mnt_iva > 0:
                    line_vals['iva_ret_total'] = mnt_iva

                # Tipo 33 Folio 67: Entrega Gratuita → IVA No Recuperable código 4
                elif tipo_doc == '33' and folio == 67 and mnt_iva > 0:
                    line_vals['iva_no_recuperable'] = mnt_iva
                    line_vals['cod_iva_no_rec'] = '4'  # Código 4: Entregas gratuitas

                # Tipo 30: Factura → Solo IVA Uso Común si la observación lo indica
                elif tipo_doc == '30' and mnt_iva > 0 and 'IVA USO COMUN' in line_data.get('observations', '').upper():
                    line_vals['iva_uso_comun'] = mnt_iva
                    line_vals['factor_proporcionalidad'] = 0.60
                    # Calcular crédito IVA uso común
                    credito = int(Decimal(str(mnt_iva)) * Decimal('0.60'))
                    line_vals['credito_iva_uso_comun'] = credito

                # Crear la línea con todos los valores (base + específicos)
                BookLine.create(line_vals)

            books_created.append({
                'name': purchase_book.name,
                'type': 'purchase',
                'lines_count': len(purchase_book_data.get('lines', []))
            })

        # Preparar contexto para el template
        template_ctx = {
            'attention_number': result['attention_number'],
            'cases_count': len(cases_created),
            'cases_names': cases_created,
            'books_count': len(books_created),
            'books_names': books_created,
        }

        # Publicar mensaje con template
        self.project_id.with_context(**template_ctx).message_post_with_source(
            source_ref=self.env.ref('l10n_cl_edi_certification.message_project_sii_testset_imported'),
            subtype_xmlid='mail.mt_note'
        )

        self.state = 'done'

        # Mensaje de notificación actualizado
        notification_message = f'{len(cases_created)} casos importados correctamente'
        if books_created:
            notification_message += f' + {len(books_created)} libro(s)'
        notification_message += f' desde set SII {result["attention_number"]}'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('¡Importación Exitosa!'),
                'message': notification_message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

