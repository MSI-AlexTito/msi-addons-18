# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
from datetime import datetime
import pytz
from collections import defaultdict

import logging
_logger = logging.getLogger(__name__)


class BookGeneratorService(models.AbstractModel):
    """
    Servicio para generar XML de LibroCompraVenta (IECV)
    según especificación del SII Chile.
    """
    _name = 'l10n_cl_edi.book.generator.service'
    _description = 'Servicio de Generación de Libros de Compra/Venta'

    def generate_book_xml(self, book):
        """
        Genera el XML del LibroCompraVenta.

        Args:
            book: Registro de l10n_cl_edi.certification.book

        Returns:
            str: XML del libro sin firmar
        """
        print(f'\n{"=" * 80}')
        print(f'GENERANDO XML DE LIBRO: {book.name}')
        print(f'{"=" * 80}')

        if not book.line_ids:
            raise UserError(_('El libro no tiene líneas para generar.'))

        # Preparar datos del libro
        book_data = self._prepare_book_data(book)

        # Generar XML usando template QWeb
        xml_string = self._generate_book_xml_with_template(book_data, book)

        print(f'✓ XML generado: {len(xml_string)} caracteres')
        print(f'{"=" * 80}\n')

        return xml_string

    def _prepare_book_data(self, book):
        """Prepara los datos del libro para el template"""
        print(f'\nPreparando datos del libro...')

        # Obtener información del cliente (quien envía/firma con certificado)
        client_info = book.project_id.client_info_id
        if not client_info:
            raise UserError(_('El proyecto debe tener información de cliente asociada.'))

        # Validar período tributario (formato YYYY-MM)
        if not book.period or len(book.period) != 7:
            raise UserError(_('El período debe tener formato YYYY-MM (ej: 2025-12)'))

        # Validar datos de resolución DTE del cliente
        if not client_info.dte_resolution_date:
            raise UserError(_('El cliente debe tener una Fecha de Resolución DTE configurada.'))
        if not client_info.dte_resolution_number:
            raise UserError(_('El cliente debe tener un Número de Resolución DTE configurado.'))

        # Preparar Carátula
        caratula = {
            # RutEmisorLibro: RUT de la EMPRESA que se está certificando
            'RutEmisorLibro': client_info.rut,

            # RutEnvia: RUT del CLIENTE (dueño del certificado que firma/envía)
            'RutEnvia': client_info.subject_serial_number,

            # Período tributario
            'PeriodoTributario': book.period,  # YYYY-MM

            # Resolución DTE del cliente (no valores hardcodeados)
            'FchResol': client_info.dte_resolution_date.strftime('%Y-%m-%d'),
            'NroResol': client_info.dte_resolution_number,

            # Configuración del libro
            'TipoOperacion': 'COMPRA' if book.book_type == 'purchase' else 'VENTA',
            'TipoLibro': 'MENSUAL',  # MENSUAL para libros normales (ESPECIAL requiere FolioNotificacion)
            'TipoEnvio': 'TOTAL',  # TOTAL, PARCIAL, FINAL, AJUSTE
        }

        # FolioNotificacion: Solo para libros de COMPRAS ESPECIALES
        if book.book_type == 'purchase' and book.folio_notificacion:
            caratula['FolioNotificacion'] = book.folio_notificacion

        # Preparar ResumenPeriodo (agrupado por tipo de documento)
        resumen = self._prepare_resumen_periodo(book)

        # Preparar Detalles
        detalles = self._prepare_detalles(book)

        print(f'  Carátula: {caratula["TipoOperacion"]} - Período {caratula["PeriodoTributario"]}')
        print(f'  RutEmisorLibro (empresa): {caratula["RutEmisorLibro"]}')
        print(f'  RutEnvia (cliente/certificado): {caratula["RutEnvia"]}')
        print(f'  Resolución DTE: N°{caratula["NroResol"]} del {caratula["FchResol"]}')
        if caratula.get('FolioNotificacion'):
            print(f'  FolioNotificacion (Libro ESPECIAL): {caratula["FolioNotificacion"]}')
        print(f'  Resumen: {len(resumen)} tipos de documento')
        print(f'  Detalles: {len(detalles)} líneas')

        return {
            'Caratula': caratula,
            'ResumenPeriodo': resumen,
            'Detalles': detalles,
            'TipoLibro': book.book_type,  # 'sale' o 'purchase'
        }

    def _prepare_resumen_periodo(self, book):
        """
        Prepara el ResumenPeriodo agrupando por tipo de documento.

        Returns:
            list: Lista de diccionarios con totales por tipo de documento
        """
        print(f'\n{"=" * 100}')
        print(f'PREPARANDO RESUMEN PERIODO - DEBUG')
        print(f'{"=" * 100}')

        # Agrupar líneas por tipo de documento
        doc_groups = defaultdict(lambda: {
            'cantidad': 0,
            'mnt_neto': 0,
            'mnt_exento': 0,
            'mnt_iva': 0,
            'mnt_total': 0,
            'iva_uso_comun': 0,
            'iva_uso_comun_count': 0,  # Cantidad de operaciones con IVA Uso Común
            'iva_no_recuperable': 0,
            'iva_no_rec_count': 0,  # Cantidad de operaciones con IVA No Rec
            'cod_iva_no_rec': None,  # Código del primer IVA No Rec encontrado
            'iva_ret_total': 0,
            'iva_ret_total_count': 0,  # Cantidad de operaciones con IVA Ret Total
            'iva_ret_parcial': 0,
            'iva_ret_parcial_count': 0,  # Cantidad de operaciones con IVA Ret Parcial
        })

        for line in book.line_ids:
            tipo_doc = line.document_type_code
            if not tipo_doc:
                continue

            doc_groups[tipo_doc]['cantidad'] += 1
            doc_groups[tipo_doc]['mnt_neto'] += line.mnt_neto or 0
            doc_groups[tipo_doc]['mnt_exento'] += line.mnt_exento or 0

            # Solo sumar MntIVA si NO hay IVA No Recuperable NI IVA Uso Común
            # Cuando hay IVA No Rec o Uso Común, el IVA va en campos específicos, NO en MntIVA
            if book.book_type == 'purchase' and (line.iva_no_recuperable or line.iva_uso_comun):
                # No sumar al mnt_iva (quedará en 0)
                pass
            else:
                doc_groups[tipo_doc]['mnt_iva'] += line.mnt_iva or 0

            doc_groups[tipo_doc]['mnt_total'] += line.mnt_total or 0

            # Campos específicos de libro de COMPRAS
            if book.book_type == 'purchase':
                # IVA Uso Común
                if line.iva_uso_comun:
                    doc_groups[tipo_doc]['iva_uso_comun'] += line.iva_uso_comun
                    doc_groups[tipo_doc]['iva_uso_comun_count'] += 1

                # IVA No Recuperable
                if line.iva_no_recuperable:
                    doc_groups[tipo_doc]['iva_no_recuperable'] += line.iva_no_recuperable
                    doc_groups[tipo_doc]['iva_no_rec_count'] += 1
                    # Capturar el código del primer documento que lo tenga
                    if line.cod_iva_no_rec and not doc_groups[tipo_doc]['cod_iva_no_rec']:
                        doc_groups[tipo_doc]['cod_iva_no_rec'] = line.cod_iva_no_rec

                # IVA Retenido Total
                if line.iva_ret_total:
                    doc_groups[tipo_doc]['iva_ret_total'] += line.iva_ret_total
                    doc_groups[tipo_doc]['iva_ret_total_count'] += 1

                # IVA Retenido Parcial
                if line.iva_ret_parcial:
                    doc_groups[tipo_doc]['iva_ret_parcial'] += line.iva_ret_parcial
                    doc_groups[tipo_doc]['iva_ret_parcial_count'] += 1

        # Convertir a lista de diccionarios
        resumen = []
        for tipo_doc, totales in sorted(doc_groups.items()):
            print(f'\nTipo Doc {tipo_doc}:')
            print(f'  Cantidad: {totales["cantidad"]}')
            print(f'  MntNeto: {totales["mnt_neto"]}, MntExe: {totales["mnt_exento"]}, MntIVA: {totales["mnt_iva"]}')
            print(f'  Campos específicos COMPRAS:')
            print(f'    iva_uso_comun: {totales["iva_uso_comun"]}')
            print(f'    iva_no_recuperable: {totales["iva_no_recuperable"]}')
            print(f'    iva_ret_total: {totales["iva_ret_total"]}')
            print(f'    iva_ret_parcial: {totales["iva_ret_parcial"]}')

            item = {
                'TpoDoc': tipo_doc,
                'TotDoc': totales['cantidad'],
                'MntNeto': int(totales['mnt_neto']),
                'MntExe': int(totales['mnt_exento']) if totales['mnt_exento'] else 0,
                'MntIVA': int(totales['mnt_iva']) if totales['mnt_iva'] else 0,
                'TotMntTotal': int(totales['mnt_total']),
            }

            # Agregar campos específicos de COMPRAS si aplican
            if book.book_type == 'purchase':
                # IVA Uso Común
                if totales['iva_uso_comun']:
                    item['TotOpIVAUsoComun'] = totales['iva_uso_comun_count']
                    item['IVAUsoComun'] = int(totales['iva_uso_comun'])
                    # Factor de Proporcionalidad (0.6 por defecto según ejemplo SIMPLE API)
                    # TODO: Este valor debería venir de configuración o línea
                    factor_prop = 0.6
                    item['FctProp'] = factor_prop
                    item['TotCredIVAUsoComun'] = int(round(totales['iva_uso_comun'] * factor_prop, 0))
                    print(f'    ✓ AGREGADO al resumen: TotOpIVAUsoComun = {totales["iva_uso_comun_count"]}')
                    print(f'    ✓ AGREGADO al resumen: TotIVAUsoComun = {int(totales["iva_uso_comun"])}')
                    print(f'    ✓ AGREGADO al resumen: FctProp = {factor_prop}')
                    print(f'    ✓ AGREGADO al resumen: TotCredIVAUsoComun = {item["TotCredIVAUsoComun"]}')
                else:
                    print(f'    ✗ NO agregado al resumen: TotIVAUsoComun (total: {totales["iva_uso_comun"]})')

                # IVA No Recuperable
                if totales['iva_no_recuperable']:
                    # En ResumenPeriodo: TotIVANoRec tiene código, cantidad de ops y monto
                    cod = totales['cod_iva_no_rec'] or '1'  # Default a código 1
                    item['IVANoRec'] = {
                        'CodIVANoRec': cod,
                        'TotOpIVANoRec': totales['iva_no_rec_count'],
                        'TotMntIVANoRec': int(totales['iva_no_recuperable']),
                    }
                    print(f'    ✓ AGREGADO al resumen: TotIVANoRec = {int(totales["iva_no_recuperable"])} ({totales["iva_no_rec_count"]} ops, código: {cod})')
                else:
                    print(f'    ✗ NO agregado al resumen: TotIVANoRec (total: {totales["iva_no_recuperable"]})')

                # IVA Retenido Total
                if totales['iva_ret_total']:
                    item['TotOpIVARetTotal'] = totales['iva_ret_total_count']
                    item['IVARetTotal'] = int(totales['iva_ret_total'])
                    print(f'    ✓ AGREGADO al resumen: TotOpIVARetTotal = {totales["iva_ret_total_count"]}')
                    print(f'    ✓ AGREGADO al resumen: TotIVARetTotal = {int(totales["iva_ret_total"])}')
                else:
                    print(f'    ✗ NO agregado al resumen: TotIVARetTotal (total: {totales["iva_ret_total"]})')

                # IVA Retenido Parcial
                if totales['iva_ret_parcial']:
                    item['TotOpIVARetParcial'] = totales['iva_ret_parcial_count']
                    item['IVARetParcial'] = int(totales['iva_ret_parcial'])
                    print(f'    ✓ AGREGADO al resumen: TotOpIVARetParcial = {totales["iva_ret_parcial_count"]}')
                    print(f'    ✓ AGREGADO al resumen: TotIVARetParcial = {int(totales["iva_ret_parcial"])}')
                else:
                    print(f'    ✗ NO agregado al resumen: TotIVARetParcial (total: {totales["iva_ret_parcial"]})')

                # TotOtrosImp: Otros Impuestos (IVA Retenido Total/Parcial)
                otros_impuestos = []
                if totales['iva_ret_total']:
                    otros_impuestos.append({
                        'CodImp': 15,  # Código 15 = IVA Retenido Total
                        'TotMntImp': int(totales['iva_ret_total'])
                    })
                    print(f'    ✓ AGREGADO TotOtrosImp: Código 15 (IVA Ret Total) = {int(totales["iva_ret_total"])}')

                if totales['iva_ret_parcial']:
                    otros_impuestos.append({
                        'CodImp': 16,  # Código 16 = IVA Retenido Parcial
                        'TotMntImp': int(totales['iva_ret_parcial'])
                    })
                    print(f'    ✓ AGREGADO TotOtrosImp: Código 16 (IVA Ret Parcial) = {int(totales["iva_ret_parcial"])}')

                if otros_impuestos:
                    item['OtrosImpuestos'] = otros_impuestos

            resumen.append(item)

        print(f'{"=" * 100}\n')
        return resumen

    def _prepare_detalles(self, book):
        """
        Prepara los Detalles (líneas individuales) del libro.

        Returns:
            list: Lista de diccionarios con datos de cada documento
        """
        detalles = []

        print(f'\n{"=" * 100}')
        print(f'PREPARANDO DETALLES DEL LIBRO - DEBUG')
        print(f'{"=" * 100}')
        print(f'Tipo de libro: {book.book_type}')
        print(f'Total líneas: {len(book.line_ids)}')

        for line in book.line_ids:
            # Calcular MntIVA según reglas del SII
            # Cuando hay IVA No Recuperable o IVA Uso Común, MntIVA debe ser 0
            mnt_iva = 0
            if book.book_type == 'purchase':
                if line.iva_no_recuperable or line.iva_uso_comun:
                    mnt_iva = 0  # IVA No Recuperable o Uso Común: MntIVA = 0
                else:
                    mnt_iva = int(line.mnt_iva) if line.mnt_iva else 0
            else:
                mnt_iva = int(line.mnt_iva) if line.mnt_iva else 0

            # Datos comunes para COMPRAS y VENTAS
            detalle = {
                'TpoDoc': line.document_type_code,
                'NroDoc': line.folio,  # En LibroCompraVenta se llama NroDoc, no Folio
                'FchDoc': line.issue_date.strftime('%Y-%m-%d') if line.issue_date else '',
                'RUTDoc': line.partner_rut,
                'RznSoc': line.partner_name[:50] if line.partner_name else '',  # Máx 50 caracteres
                'MntNeto': int(line.mnt_neto) if line.mnt_neto else 0,
                'MntExe': int(line.mnt_exento) if line.mnt_exento else 0,
                'MntIVA': mnt_iva,
                'MntTotal': int(line.mnt_total),
            }

            # TasaImp: Tasa de IVA cuando el documento tiene IVA
            # El SII requiere este campo en certificación aunque sea opcional en el esquema XSD
            if line.mnt_iva and line.mnt_iva > 0:
                detalle['TasaImp'] = 19  # Tasa IVA en Chile

            print(f'\n--- Línea {line.folio} (Tipo {line.document_type_code}) ---')
            print(f'  MntNeto: {line.mnt_neto}, MntExe: {line.mnt_exento}, MntIVA: {line.mnt_iva}')

            # Campos específicos de LIBRO DE COMPRAS
            if book.book_type == 'purchase':
                print(f'  → Es COMPRA, verificando campos específicos...')
                print(f'     iva_uso_comun: {line.iva_uso_comun}')
                print(f'     iva_no_recuperable: {line.iva_no_recuperable}')
                print(f'     cod_iva_no_rec: {line.cod_iva_no_rec}')
                print(f'     iva_ret_total: {line.iva_ret_total}')
                print(f'     iva_ret_parcial: {line.iva_ret_parcial}')
                print(f'     factor_proporcionalidad: {line.factor_proporcionalidad}')
                print(f'     credito_iva_uso_comun: {line.credito_iva_uso_comun}')
                # IVA Uso Común
                if line.iva_uso_comun:
                    detalle['IVAUsoComun'] = int(line.iva_uso_comun)
                    print(f'     ✓ AGREGADO: IVAUsoComun = {int(line.iva_uso_comun)}')
                else:
                    print(f'     ✗ NO agregado: IVAUsoComun (valor: {line.iva_uso_comun})')

                # IVA No Recuperable
                if line.iva_no_recuperable:
                    detalle['IVANoRec'] = {
                        'CodIVANoRec': line.cod_iva_no_rec or '1',
                        'MntIVANoRec': int(line.iva_no_recuperable),
                    }
                    print(f'     ✓ AGREGADO: IVANoRec = {int(line.iva_no_recuperable)} (código: {line.cod_iva_no_rec or "1"})')
                else:
                    print(f'     ✗ NO agregado: IVANoRec (valor: {line.iva_no_recuperable})')

                # OtrosImp: Otros Impuestos (IVA Retenido Total/Parcial)
                otros_imp_detalle = []
                if line.iva_ret_total:
                    otros_imp_detalle.append({
                        'CodImp': 15,  # Código 15 = IVA Retenido Total
                        'TasaImp': 19,
                        'MntImp': int(line.iva_ret_total)
                    })
                    print(f'     ✓ AGREGADO OtrosImp: Código 15 (IVA Ret Total) = {int(line.iva_ret_total)}')

                if line.iva_ret_parcial:
                    otros_imp_detalle.append({
                        'CodImp': 16,  # Código 16 = IVA Retenido Parcial
                        'TasaImp': 19,
                        'MntImp': int(line.iva_ret_parcial)
                    })
                    print(f'     ✓ AGREGADO OtrosImp: Código 16 (IVA Ret Parcial) = {int(line.iva_ret_parcial)}')

                if otros_imp_detalle:
                    detalle['OtrosImp'] = otros_imp_detalle

                # IVA Retenido Total (para FC Electrónica tipo 46)
                if line.iva_ret_total:
                    detalle['IVARetTotal'] = int(line.iva_ret_total)
                    print(f'     ✓ AGREGADO: IVARetTotal = {int(line.iva_ret_total)}')
                else:
                    print(f'     ✗ NO agregado: IVARetTotal (valor: {line.iva_ret_total})')

                # IVA Retenido Parcial
                if line.iva_ret_parcial:
                    detalle['IVARetParcial'] = int(line.iva_ret_parcial)
                    print(f'     ✓ AGREGADO: IVARetParcial = {int(line.iva_ret_parcial)}')
                else:
                    print(f'     ✗ NO agregado: IVARetParcial (valor: {line.iva_ret_parcial})')

                # CreditoIVAUsoComun NO se incluye (no está en esquema XSD del SII)
                # Observaciones NO se incluyen en LibroCompraVenta (no es válido según esquema SII)

            detalles.append(detalle)

        print(f'\n{"=" * 100}')
        print(f'RESUMEN DETALLES:')
        print(f'  Total detalles generados: {len(detalles)}')
        campos_agregados = sum(1 for d in detalles if any(k in d for k in ['IVAUsoComun', 'IVANoRec', 'IVARetTotal', 'IVARetParcial']))
        print(f'  Detalles con campos específicos de compras: {campos_agregados}')
        print(f'{"=" * 100}\n')

        return detalles

    def _generate_book_xml_with_template(self, book_data, book):
        """Genera el XML usando template QWeb"""
        try:
            # Timestamp de firma (va al final del EnvioLibro, NO en la Carátula)
            santiago_tz = pytz.timezone('America/Santiago')
            now_santiago = datetime.now(santiago_tz)
            tmst_firma = now_santiago.strftime('%Y-%m-%dT%H:%M:%S')

            # Agregar timestamp (TmstFirma va al final del EnvioLibro)
            book_data['TmstFirma'] = tmst_firma

            # Seleccionar template según tipo de operación
            if book.book_type == 'purchase':
                template_id = 'l10n_cl_edi_certification.book_purchase_template'
                print('✓ Usando template de LIBRO DE COMPRAS')
            else:  # sale
                template_id = 'l10n_cl_edi_certification.book_sales_template'
                print('✓ Usando template de LIBRO DE VENTAS')

            xml_string = self.env['ir.qweb']._render(template_id, {
                'book_data': book_data,
            })

            # Limpiar el XML
            if isinstance(xml_string, bytes):
                xml_string = xml_string.decode('utf-8')

            # Eliminar líneas vacías y espacios extras
            lines = [line for line in xml_string.split('\n') if line.strip()]
            xml_string = '\n'.join(lines)

            # IMPORTANTE: QWeb/lxml pueden reordenar los atributos xmlns alfabéticamente.
            # Necesitamos asegurar que xmlns venga ANTES de xmlns:xsi (como en Enterprise).
            # Este reemplazo se hace ANTES de firmar, por lo que no afecta la firma.
            import re
            xml_string = re.sub(
                r'<LibroCompraVenta\s+xmlns:xsi="([^"]+)"\s+xmlns="([^"]+)"',
                r'<LibroCompraVenta xmlns="\2" xmlns:xsi="\1"',
                xml_string
            )

            return xml_string

        except Exception as e:
            _logger.error(f'Error generando XML de libro: {str(e)}')
            import traceback
            traceback.print_exc()
            raise UserError(_('Error al generar XML del libro: %s') % str(e))
