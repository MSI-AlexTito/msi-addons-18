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
                print('=' * 80)
                print('WIZARD: Iniciando procesamiento de archivo')
                print(f'Nombre del archivo: {self.filename}')

                # Decodificar archivo
                print('Decodificando archivo desde base64...')
                file_content = base64.b64decode(self.file)
                print(f'Archivo decodificado - Tamaño: {len(file_content)} bytes')

                # Parsear
                print('Llamando al parser SII...')
                result = SIITestSetParser.parse_file(file_content)
                print(f'Parser completado - Resultado: {result.get("attention_number")}, {len(result.get("cases", []))} casos')

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

                print('Vista previa generada:')
                print(self.preview_text)
                print('=' * 80)

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
        print('\n' + '=' * 80)
        print('COPIANDO PRECIOS Y/O ÍTEMS DE FACTURAS REFERENCIADAS A NC/ND')
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
                print(f'⚠️ Caso {current_case.code}: No se encontró caso referenciado {ref_code}')
                continue

            print(f'\nProcesando {current_case.code} (NC/ND) → Referencia: {ref_case.code}')
            print(f'  Tipo: {current_case.document_type_id.name}')
            print(f'  Razón: {current_case.reference_reason or "Sin razón"}')

            # CASO 1: NC/ND sin ítems que es ANULACIÓN → Copiar TODOS los ítems de la factura
            if not current_case.line_ids and current_case.reference_reason and 'ANULA' in current_case.reference_reason.upper():
                print(f'  ⚠️ Es una ANULACIÓN sin ítems → Copiando TODOS los ítems de la factura referenciada')

                if not ref_case.line_ids:
                    print(f'    ❌ ERROR: Factura referenciada {ref_case.code} tampoco tiene ítems')
                else:
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
                        print(f'    ✓ Copiado ítem {idx}: {ref_line.description} - Qty: {ref_line.qty} - Precio: {ref_line.price_unit}')

                # Recalcular montos del caso
                current_case._compute_amounts()
                print(f'    ✓ Montos recalculados - Total: {current_case.total_amount}')

            # CASO 2: NC/ND con ítems parciales → Copiar solo precios
            elif current_case.line_ids:
                print(f'  ℹ️ Tiene {len(current_case.line_ids)} ítems → Copiando precios de ítems coincidentes')

                for current_line in current_case.line_ids:
                    # Buscar línea correspondiente en factura original (por nombre del ítem)
                    ref_line = ref_case.line_ids.filtered(
                        lambda l: l.description.strip().upper() == current_line.description.strip().upper()
                    )

                    if ref_line:
                        ref_line = ref_line[0]  # Tomar la primera coincidencia

                        # Copiar precio y descuento de la factura original
                        print(f'    ✓ {current_line.description}:')
                        print(f'      Antes: precio={current_line.price_unit}, desc={current_line.discount}%')
                        print(f'      Después: precio={ref_line.price_unit}, desc={ref_line.discount}%')

                        current_line.write({
                            'price_unit': ref_line.price_unit,
                            'discount': ref_line.discount,
                        })
                    else:
                        print(f'    ⚠️ {current_line.description}: No se encontró en factura original')

            # CASO 3: NC/ND sin ítems administrativa (CORRIGE GIRO, etc.) → Dejar como está
            else:
                print(f'  ℹ️ NC/ND administrativa sin ítems (monto $0) - OK')

        print('=' * 80 + '\n')

        # =====================================================================
        # PASO 4: Crear libros si fueron detectados
        # =====================================================================
        books_created = []
        books = result.get('books', {})

        if books.get('sales_book'):
            print('\n' + '=' * 80)
            print('CREANDO LIBRO DE VENTAS')
            print('=' * 80)

            sales_book_data = books['sales_book']
            sales_book = self.env['l10n_cl_edi.certification.book'].create({
                'project_id': self.project_id.id,
                'name': sales_book_data['name'],
                'book_type': 'sale',
                'attention_number': sales_book_data['attention_number'],
                'period': fields.Date.context_today(self).strftime('%Y-%m'),
                'notes': 'Importado desde set de pruebas SII. El libro se generará automáticamente desde los documentos del SET BASICO.',
            })

            print(f'✓ Libro de Ventas creado: {sales_book.name}')
            print(f'  ID: {sales_book.id}')
            print(f'  Las líneas se agregarán automáticamente al generar DTEs del SET BASICO')
            print('=' * 80 + '\n')

            books_created.append(sales_book.name)

        if books.get('purchase_book'):
            print('\n' + '=' * 80)
            print('CREANDO LIBRO DE COMPRAS')
            print('=' * 80)

            purchase_book_data = books['purchase_book']
            purchase_book = self.env['l10n_cl_edi.certification.book'].create({
                'project_id': self.project_id.id,
                'name': purchase_book_data['name'],
                'book_type': 'purchase',
                'attention_number': purchase_book_data['attention_number'],
                'period': fields.Date.context_today(self).strftime('%Y-%m'),
                'notes': 'Importado desde set de pruebas SII.',
            })

            print(f'✓ Libro de Compras creado: {purchase_book.name}')
            print(f'  ID: {purchase_book.id}')
            print(f'  Creando {len(purchase_book_data.get("lines", []))} líneas...')

            # Crear líneas del libro de compras
            BookLine = self.env['l10n_cl_edi.certification.book.line']
            for line_data in purchase_book_data.get('lines', []):
                # Calcular IVA y total
                mnt_neto = line_data['mnt_neto']
                mnt_exento = line_data['mnt_exento']
                mnt_iva = int(round(mnt_neto * 0.19)) if mnt_neto else 0
                mnt_total = mnt_neto + mnt_exento + mnt_iva

                BookLine.create({
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
                })

                print(f'    ✓ Línea {line_data["sequence"]}: {line_data["document_type_name"]} - Folio {line_data["folio"]}')

            print(f'✓ {len(purchase_book_data.get("lines", []))} líneas creadas')
            print('=' * 80 + '\n')

            books_created.append(purchase_book.name)

        # Mensaje de éxito
        message_body_parts = [
            '<p><strong>Set de Pruebas SII Importado</strong></p>',
            '<ul>',
            f'<li>Número de Atención: {result["attention_number"]}</li>',
            f'<li>Casos Importados: {len(cases_created)}</li>',
        ]

        if books_created:
            message_body_parts.append(f'<li>Libros Creados: {len(books_created)}</li>')

        message_body_parts.append('</ul>')
        message_body_parts.append('<p>Casos creados:</p>')
        message_body_parts.append('<ul>')
        for name in cases_created:
            message_body_parts.append(f'<li>{name}</li>')
        message_body_parts.append('</ul>')

        if books_created:
            message_body_parts.append('<p>Libros creados:</p>')
            message_body_parts.append('<ul>')
            for name in books_created:
                message_body_parts.append(f'<li>{name}</li>')
            message_body_parts.append('</ul>')

        self.project_id.message_post(
            body=''.join(message_body_parts)
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

