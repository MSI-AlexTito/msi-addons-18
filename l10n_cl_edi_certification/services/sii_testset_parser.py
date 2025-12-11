# -*- coding: utf-8 -*-
import re
from odoo import _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class SIITestSetParser:
    """
    Parser para archivos de Set de Pruebas del SII.
    Extrae casos de prueba desde archivos .txt del SII.
    """

    DOCUMENT_TYPE_MAPPING = {
        'FACTURA ELECTRONICA': '33',
        'FACTURA NO AFECTA O EXENTA ELECTRONICA': '34',
        'NOTA DE CREDITO ELECTRONICA': '61',
        'NOTA DE DEBITO ELECTRONICA': '56',
        'GUIA DE DESPACHO ELECTRONICA': '52',
        'FACTURA DE COMPRA ELECTRONICA': '46',
    }

    @classmethod
    def parse_file(cls, file_content):
        """
        Parsea el contenido del archivo del SII.

        Args:
            file_content (str): Contenido del archivo .txt

        Returns:
            dict: {
                'attention_number': str,
                'cases': [dict, ...],
                'errors': [str, ...]
            }
        """
        import logging
        _logger = logging.getLogger(__name__)

        try:
            print('=' * 80)
            print('INICIANDO PARSEO DE ARCHIVO SII')
            print(f'Tipo de contenido recibido: {type(file_content)}')
            print(f'Longitud del contenido: {len(file_content) if file_content else 0}')

            # Decodificar si viene en bytes
            if isinstance(file_content, bytes):
                print('Contenido es bytes, intentando decodificar...')
                # Probar diferentes encodings
                for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                    try:
                        file_content = file_content.decode(encoding)
                        print(f'✓ Decodificado exitosamente con: {encoding}')
                        break
                    except UnicodeDecodeError:
                        print(f'✗ Falló decodificación con: {encoding}')
                        continue
                else:
                    raise UserError(_('No se pudo decodificar el archivo. Verifique el encoding.'))
            else:
                print('Contenido ya es string')

            # Mostrar primeros caracteres para debug
            print(f'Primeros 200 caracteres del archivo:\n{file_content[:200]}')

            # Extraer número de atención
            print('Buscando número de atención...')
            attention_match = re.search(r'NUMERO DE ATENCION:\s*(\d+)', file_content)
            if not attention_match:
                print('❌ NO SE ENCONTRÓ número de atención')
                print(f'Buscando en contenido: {file_content[:500]}')
                raise UserError(_('No se encontró el número de atención en el archivo.'))

            attention_number = attention_match.group(1)
            print(f'✓ Número de atención encontrado: {attention_number}')

            # Dividir por casos
            print('Dividiendo archivo por casos...')
            case_pattern = r'CASO\s+(\d+-\d+)\s*\n={10,}'
            cases_raw = re.split(case_pattern, file_content)

            print(f'Patrón de búsqueda: {case_pattern}')
            print(f'Partes encontradas después de split: {len(cases_raw)}')

            # Debug: Mostrar las primeras partes
            for idx, part in enumerate(cases_raw[:5]):
                print(f'Parte {idx}: {part[:100] if part else "VACÍO"}...')

            # Procesar casos
            cases = []
            errors = []

            # cases_raw viene como: [texto_antes, caso1_code, caso1_content, caso2_code, caso2_content, ...]
            print(f'Procesando {(len(cases_raw) - 1) // 2} casos...')

            for i in range(1, len(cases_raw), 2):
                if i + 1 < len(cases_raw):
                    case_code = cases_raw[i].strip()
                    case_content = cases_raw[i + 1]

                    print(f'Procesando caso: {case_code}')
                    print(f'Contenido del caso (primeros 200 chars): {case_content[:200]}')

                    try:
                        case_data = cls._parse_case(case_code, case_content, attention_number)
                        if case_data:
                            print(f'✓ Caso {case_code} procesado exitosamente')
                            print(f'  - Tipo documento: {case_data["document_type_code"]}')
                            print(f'  - Items: {len(case_data.get("items", []))}')
                            cases.append(case_data)
                        else:
                            print(f'✗ Caso {case_code} retornó None (sin datos)')
                    except Exception as e:
                        error_msg = f"Error en caso {case_code}: {str(e)}"
                        print(error_msg)
                        _logger.exception('Detalle del error:')
                        errors.append(error_msg)

            # Detectar libros
            books = cls._detect_books(file_content)

            print('=' * 80)
            print(f'RESUMEN DEL PARSEO:')
            print(f'  - Número de atención: {attention_number}')
            print(f'  - Casos procesados exitosamente: {len(cases)}')
            print(f'  - Errores: {len(errors)}')
            if books['sales_book']:
                print(f'  - Libro de Ventas: {books["sales_book"]["name"]}')
            if books['purchase_book']:
                print(f'  - Libro de Compras: {books["purchase_book"]["name"]} ({len(books["purchase_book"].get("lines", []))} líneas)')
            if errors:
                for error in errors:
                    print(f'    {error}')
            print('=' * 80)

            return {
                'attention_number': attention_number,
                'cases': cases,
                'errors': errors,
                'books': books,
            }

        except Exception as e:
            _logger.exception('ERROR FATAL AL PARSEAR ARCHIVO:')
            raise UserError(_('Error al parsear el archivo: %s') % str(e))

    @classmethod
    def _parse_case(cls, case_code, content, attention_number):
        """
        Parsea un caso individual.

        Returns:
            dict con estructura del caso
        """
        lines = content.strip().split('\n')

        # Extraer tipo de documento
        doc_type_line = None
        for line in lines:
            if line.strip().startswith('DOCUMENTO'):
                doc_type_line = line
                break

        if not doc_type_line:
            return None

        doc_type_text = doc_type_line.split('\t', 1)[1].strip() if '\t' in doc_type_line else ''
        doc_type_code = cls.DOCUMENT_TYPE_MAPPING.get(doc_type_text)

        if not doc_type_code:
            raise UserError(_('Tipo de documento no reconocido: %s') % doc_type_text)

        # Extraer items
        items = cls._parse_items(content)

        # Extraer descuento global
        global_discount = cls._parse_global_discount(content)

        # Extraer referencia (para NC/ND)
        reference = cls._parse_reference(content)

        return {
            'code': case_code,
            'name': f'Caso {case_code}',
            'document_type_code': doc_type_code,
            'items': items,
            'global_discount': global_discount,
            'reference': reference,
            'attention_number': attention_number,
        }

    @classmethod
    def _parse_items(cls, content):
        """
        Extrae los items del caso.

        Returns:
            list de dict con {name, qty, price_unit, discount, exempt}
        """
        items = []
        lines = content.split('\n')

        # Buscar la línea de encabezado de items
        header_idx = -1
        for idx, line in enumerate(lines):
            if 'ITEM' in line and ('CANTIDAD' in line or 'PRECIO' in line):
                header_idx = idx
                break

        if header_idx == -1:
            return []

        # Procesar líneas de items
        for idx in range(header_idx + 1, len(lines)):
            line = lines[idx].strip()

            # Detener si encontramos una línea vacía o separador
            if not line or line.startswith('DESCUENTO GLOBAL') or line.startswith('REFERENCIA') or line.startswith('-'):
                break

            # Parsear item
            item = cls._parse_item_line(line)
            if item:
                items.append(item)

        return items

    @classmethod
    def _parse_item_line(cls, line):
        """
        Parsea una línea de item.
        Formato: NOMBRE    CANTIDAD    PRECIO    [DESCUENTO]
        """
        # Dividir por múltiples espacios o tabs
        parts = re.split(r'\s{2,}|\t+', line.strip())
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) < 2:
            return None

        name = parts[0]

        # Detectar si es exento
        exempt = 'EXENTO' in name.upper()

        # Extraer cantidad (puede no estar si es nota de crédito con precio)
        qty = 1
        price_unit = 0
        discount = 0

        if len(parts) >= 2:
            # Limpiar y convertir cantidad
            qty_str = parts[1].replace('.', '').replace(',', '.')
            try:
                qty = float(qty_str)
            except:
                qty = 1

        if len(parts) >= 3:
            # Limpiar y convertir precio
            price_str = parts[2].replace('.', '').replace(',', '.')
            try:
                price_unit = float(price_str)
            except:
                price_unit = 0

        if len(parts) >= 4:
            # Descuento
            discount_str = parts[3].replace('%', '').strip()
            try:
                discount = float(discount_str)
            except:
                discount = 0

        # NOTA: Si price_unit = 0, significa que este ítem es parte de una NC/ND
        # y el precio se copiará de la factura referenciada en el wizard de importación

        return {
            'name': name,
            'qty': qty,
            'price_unit': price_unit,
            'discount': discount,
            'exempt': exempt,
        }

    @classmethod
    def _parse_global_discount(cls, content):
        """
        Extrae descuento global del caso.
        """
        match = re.search(r'DESCUENTO GLOBAL.*?(\d+)%', content, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return 0.0

    @classmethod
    def _parse_reference(cls, content):
        """
        Extrae información de referencia (para NC/ND).

        Returns:
            dict con {reference_case_code, reason} o None
        """
        lines = content.split('\n')

        reference_case = None
        reason = None

        for line in lines:
            if line.strip().startswith('REFERENCIA'):
                # Extraer código del caso referenciado
                # Ejemplo: "FACTURA ELECTRONICA CORRESPONDIENTE A CASO 4606904-1"
                match = re.search(r'CASO\s+(\d+-\d+)', line)
                if match:
                    reference_case = match.group(1)

            if line.strip().startswith('RAZON REFERENCIA'):
                reason = line.split('\t', 1)[1].strip() if '\t' in line else ''

        if reference_case:
            return {
                'reference_case_code': reference_case,
                'reason': reason or 'Referencia',
            }

        return None

    @classmethod
    def _detect_books(cls, file_content):
        """
        Detecta secciones de libros en el archivo.

        Returns:
            dict: {
                'sales_book': {attention_number, period} o None,
                'purchase_book': {attention_number, period, lines} o None
            }
        """
        print('\n' + '=' * 80)
        print('DETECTANDO SECCIONES DE LIBROS')
        print('=' * 80)

        books = {
            'sales_book': None,
            'purchase_book': None
        }

        # Buscar SET LIBRO DE VENTAS
        sales_match = re.search(r'SET LIBRO DE VENTAS.*?NUMERO DE ATENCION:\s*(\d+)', file_content, re.IGNORECASE | re.DOTALL)
        if sales_match:
            attention_number = sales_match.group(1)
            print(f'✓ SET LIBRO DE VENTAS encontrado - Atención: {attention_number}')
            books['sales_book'] = {
                'attention_number': attention_number,
                'name': f'Libro de Ventas {attention_number}',
            }
        else:
            print('✗ SET LIBRO DE VENTAS no encontrado')

        # Buscar SET LIBRO DE COMPRAS
        purchase_match = re.search(r'SET LIBRO DE COMPRAS.*?NUMERO DE ATENCION:\s*(\d+)', file_content, re.IGNORECASE | re.DOTALL)
        if purchase_match:
            attention_number = purchase_match.group(1)
            print(f'✓ SET LIBRO DE COMPRAS encontrado - Atención: {attention_number}')

            # Extraer las líneas de detalle del libro de compras
            purchase_section = cls._extract_purchase_book_section(file_content)
            if purchase_section:
                lines = cls._parse_purchase_book_lines(purchase_section)
                books['purchase_book'] = {
                    'attention_number': attention_number,
                    'name': f'Libro de Compras {attention_number}',
                    'lines': lines,
                }
                print(f'  Líneas procesadas: {len(lines)}')
            else:
                print('  ⚠️ No se pudo extraer el detalle del libro de compras')
        else:
            print('✗ SET LIBRO DE COMPRAS no encontrado')

        print('=' * 80 + '\n')
        return books

    @classmethod
    def _extract_purchase_book_section(cls, file_content):
        """
        Extrae la sección del libro de compras desde el archivo.
        """
        # Buscar desde "SET LIBRO DE COMPRAS" hasta la siguiente sección o final
        match = re.search(
            r'SET LIBRO DE COMPRAS.*?={10,}.*?={10,}(.*?)(?:OBSERVACIONES GENERALES|$)',
            file_content,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return match.group(1)
        return None

    @classmethod
    def _parse_purchase_book_lines(cls, section_content):
        """
        Parsea las líneas del libro de compras.

        Formato esperado:
        TIPO DOCUMENTO                FOLIO
        OBSERVACIONES
        MONTO EXENTO    MONTO AFECTO

        Returns:
            list de dict con los detalles de cada documento
        """
        print('\n  >> Parseando líneas del libro de compras...')
        lines = []

        # Dividir por líneas y procesar
        raw_lines = section_content.split('\n')

        i = 0
        line_number = 0
        while i < len(raw_lines):
            line = raw_lines[i].strip()

            # Detectar línea de tipo de documento (comienza con letras mayúsculas)
            if not line or line.startswith('=') or line.startswith('-'):
                i += 1
                continue

            # Si la línea contiene un tipo de documento conocido
            if any(doc_type in line.upper() for doc_type in ['FACTURA', 'NOTA DE CREDITO', 'NOTA DE DEBITO']):
                line_number += 1
                print(f'\n    Línea {line_number}: {line[:60]}...')

                try:
                    # Parsear tipo documento y folio de la primera línea
                    doc_info = cls._parse_purchase_doc_line(line)

                    # Leer observaciones (siguiente línea)
                    observations = ''
                    if i + 1 < len(raw_lines):
                        next_line = raw_lines[i + 1].strip()
                        if next_line and not any(char.isdigit() for char in next_line[:10]):
                            observations = next_line
                            i += 1

                    # Leer montos (siguiente línea)
                    mnt_exento = 0
                    mnt_neto = 0
                    if i + 1 < len(raw_lines):
                        amounts_line = raw_lines[i + 1].strip()
                        mnt_exento, mnt_neto = cls._parse_purchase_amounts(amounts_line)
                        i += 1

                    # Agregar línea procesada
                    line_data = {
                        'sequence': line_number * 10,
                        'document_type_code': doc_info['type_code'],
                        'document_type_name': doc_info['type_name'],
                        'folio': doc_info['folio'],
                        'observations': observations,
                        'mnt_exento': int(mnt_exento) if mnt_exento else 0,
                        'mnt_neto': int(mnt_neto) if mnt_neto else 0,
                    }

                    lines.append(line_data)
                    print(f'      ✓ Tipo: {line_data["document_type_name"]} ({line_data["document_type_code"]})')
                    print(f'      ✓ Folio: {line_data["folio"]}')
                    print(f'      ✓ Exento: {line_data["mnt_exento"]}, Neto: {line_data["mnt_neto"]}')
                    print(f'      ✓ Obs: {observations[:50]}...' if observations else '')

                except Exception as e:
                    print(f'      ✗ Error parseando línea: {str(e)}')
                    _logger.exception(f'Error en línea {line_number}:')

            i += 1

        print(f'\n  >> Total líneas procesadas: {len(lines)}')
        return lines

    @classmethod
    def _parse_purchase_doc_line(cls, line):
        """
        Parsea la línea de tipo de documento y folio.
        Ejemplo: "FACTURA                    234"
        """
        parts = re.split(r'\s{2,}', line.strip())

        doc_type_text = parts[0].strip()
        folio = int(parts[1].strip()) if len(parts) > 1 else 0

        # Mapear tipo de documento a código
        doc_type_mapping = {
            'FACTURA': '30',
            'FACTURA ELECTRONICA': '33',
            'FACTURA DE COMPRA ELECTRONICA': '46',
            'NOTA DE CREDITO': '60',
            'NOTA DE CREDITO ELECTRONICA': '61',
            'NOTA DE DEBITO': '55',
            'NOTA DE DEBITO ELECTRONICA': '56',
        }

        doc_type_code = doc_type_mapping.get(doc_type_text, '30')

        return {
            'type_name': doc_type_text,
            'type_code': doc_type_code,
            'folio': folio,
        }

    @classmethod
    def _parse_purchase_amounts(cls, line):
        """
        Parsea los montos de la línea.
        Ejemplo: "           5024" o "   7933           4009"
        """
        # Limpiar y dividir por espacios
        parts = [p.strip() for p in re.split(r'\s+', line.strip()) if p.strip()]

        mnt_exento = 0
        mnt_neto = 0

        if len(parts) == 1:
            # Solo un monto (puede ser exento o neto, asumimos neto)
            mnt_neto = float(parts[0])
        elif len(parts) >= 2:
            # Dos montos: exento y neto
            mnt_exento = float(parts[0])
            mnt_neto = float(parts[1])

        return mnt_exento, mnt_neto
