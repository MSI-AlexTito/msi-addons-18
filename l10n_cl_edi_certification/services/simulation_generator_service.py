# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError
from datetime import timedelta
import random

class SimulationGeneratorService(models.AbstractModel):
    """
    Servicio para generar documentos de simulación con datos realistas.
    """
    _name = 'l10n_cl_edi.simulation.generator.service'
    _description = 'Generador de Documentos de Simulación'

    # Razones de referencia para NC (Notas de Crédito)
    NC_REASONS = [
        'Devolución de mercadería',
        'Descuento por volumen',
        'Descuento comercial',
        'Ajuste de precio',
        'Bonificación especial',
        'Corrección de monto facturado',
        'Descuento por pronto pago',
        'Producto en mal estado',
        'Error en facturación',
        'Devolución parcial de productos',
    ]

    # Razones de referencia para ND (Notas de Débito)
    ND_REASONS = [
        'Cargo por flete',
        'Intereses por mora',
        'Cargo adicional por servicio',
        'Ajuste de precio',
        'Corrección de monto',
        'Cargo por embalaje especial',
        'Reajuste según contrato',
        'Cargo por gestión administrativa',
        'Diferencia de cambio',
        'Cargo adicional acordado',
    ]

    # Productos/Servicios predefinidos
    PRODUCTS = [
        {'name': 'Servicio de Consultoría Empresarial', 'price_range': (500000, 2000000)},
        {'name': 'Desarrollo de Software a Medida', 'price_range': (1000000, 5000000)},
        {'name': 'Soporte Técnico Mensual', 'price_range': (200000, 800000)},
        {'name': 'Licencia Software Empresarial', 'price_range': (300000, 1500000)},
        {'name': 'Capacitación y Entrenamiento', 'price_range': (150000, 600000)},
        {'name': 'Mantenimiento de Sistemas', 'price_range': (250000, 1000000)},
        {'name': 'Auditoría de Seguridad Informática', 'price_range': (800000, 3000000)},
        {'name': 'Hosting y Servicios Cloud', 'price_range': (100000, 500000)},
        {'name': 'Diseño y Desarrollo Web', 'price_range': (400000, 2000000)},
        {'name': 'Integración de Sistemas', 'price_range': (600000, 2500000)},
    ]

    def generate_simulation_documents(self, simulation):
        """
        Genera los documentos de simulación según la configuración.

        Args:
            simulation: Registro de l10n_cl_edi.certification.simulation
        """

        # Obtener cliente
        client = simulation.project_id.client_info_id
        if not client:
            raise UserError(_('El proyecto debe tener un cliente configurado.'))

        # Generar facturas
        facturas = self._generate_invoices(simulation, client)

        # Generar notas de crédito que referencien facturas
        nc = self._generate_credit_notes(simulation, client, facturas)

        # Generar notas de débito que referencien facturas
        nd = self._generate_debit_notes(simulation, client, facturas)

        # Generar XMLs y firmar todos los documentos
        all_documents = facturas + nc + nd

        for idx, doc in enumerate(all_documents, start=1):
            # Generar XML
            self._generate_xml_for_document(doc, simulation)

            # Firmar documento
            doc.action_sign()


    def _generate_invoices(self, simulation, client):
        
        """Genera facturas electrónicas (tipo 33)"""
        DocumentType = self.env['l10n_latam.document.type']
        GeneratedDoc = self.env['l10n_cl_edi.certification.generated.document']

        # Tipo 33: Factura Electrónica
        doc_type = DocumentType.search([('code', '=', '33')], limit=1)
        if not doc_type:
            raise UserError(_('No se encontró el tipo de documento 33 (Factura Electrónica).'))

        facturas = []
        date_range = (simulation.date_to - simulation.date_from).days or 1

        # Obtener el folio de inicio (manual o automático)
        if simulation.folio_start_invoice > 0:
            folio_start = simulation.folio_start_invoice
        else:
            folio_start = self._get_next_folio(simulation.project_id, doc_type)

        # VALIDAR que existan CAF para todos los folios que se van a generar
        folio_end = folio_start + simulation.invoices_count - 1
        self._validate_caf_range(simulation.project_id, doc_type, folio_start, folio_end)

        for i in range(simulation.invoices_count):
            folio = folio_start + i
            # Fecha aleatoria dentro del rango
            days_offset = random.randint(0, date_range)
            issue_date = simulation.date_from + timedelta(days=days_offset)

            # Generar líneas de detalle (2-5 líneas por factura)
            lines_count = random.randint(2, 5)
            detalle, totales = self._generate_invoice_lines(lines_count)

            # Crear el documento
            factura = GeneratedDoc.create({
                'project_id': simulation.project_id.id,
                'simulation_id': simulation.id,
                'document_type_id': doc_type.id,
                'folio': folio,
                'issue_date': issue_date,
                'receiver_rut': simulation.receiver_rut,
                'receiver_name': simulation.receiver_name[:100],
                'receiver_giro': simulation.receiver_giro or 'Actividades empresariales',
                'receiver_address': simulation.receiver_address or 'Dirección no especificada',
                'receiver_comuna': simulation.receiver_comuna or 'Santiago',
                'mnt_neto': totales['neto'],
                'mnt_exento': 0,
                'iva_percent': 19,
                'mnt_iva': totales['iva'],
                'mnt_total': totales['total'],
                'detalle_json': str(detalle),  # Guardamos el detalle como JSON string
                'state': 'draft',
            })

            facturas.append(factura)
        return facturas

    def _generate_credit_notes(self, simulation, client, facturas):
        """Genera notas de crédito (tipo 61) que referencian facturas"""
        DocumentType = self.env['l10n_latam.document.type']
        GeneratedDoc = self.env['l10n_cl_edi.certification.generated.document']

        # Tipo 61: Nota de Crédito Electrónica
        doc_type = DocumentType.search([('code', '=', '61')], limit=1)
        if not doc_type:
            raise UserError(_('No se encontró el tipo de documento 61 (Nota de Crédito Electrónica).'))

        notas_credito = []

        # Obtener el folio de inicio (manual o automático)
        if simulation.folio_start_credit_note > 0:
            folio_start = simulation.folio_start_credit_note
        else:
            folio_start = self._get_next_folio(simulation.project_id, doc_type)

        # VALIDAR que existan CAF para todos los folios que se van a generar
        folio_end = folio_start + simulation.credit_notes_count - 1
        self._validate_caf_range(simulation.project_id, doc_type, folio_start, folio_end)

        # Seleccionar facturas aleatorias para referenciar
        facturas_ref = random.sample(list(facturas), min(simulation.credit_notes_count, len(facturas)))

        for i, factura_ref in enumerate(facturas_ref):
            folio = folio_start + i

            # Fecha posterior a la factura referenciada
            issue_date = factura_ref.issue_date + timedelta(days=random.randint(5, 15))
            if issue_date > simulation.date_to:
                issue_date = simulation.date_to

            # Monto de NC: entre 20% y 80% del monto de la factura
            porcentaje = random.uniform(0.2, 0.8)
            mnt_neto = int(factura_ref.mnt_neto * porcentaje)
            mnt_iva = int(mnt_neto * 0.19)
            mnt_total = mnt_neto + mnt_iva

            # Razón aleatoria para la NC
            razon = random.choice(self.NC_REASONS)

            # Generar una línea de detalle para la NC
            detalle = [{
                'NroLinDet': 1,
                'NmbItem': razon.upper(),
                'QtyItem': 1,
                'UnmdItem': 'UN',
                'PrcItem': mnt_neto,
                'MontoItem': mnt_neto,
            }]

            # Determinar código de referencia según el monto
            # 1 = Anula documento (montos deben coincidir 100%)
            # 3 = Corrige montos (montos diferentes, parcial)
            # Comparar si la NC es por el 100% de la factura
            if mnt_total == factura_ref.mnt_total:
                cod_ref = 1  # Anula completamente (100%)
            else:
                cod_ref = 3  # Corrige montos (parcial)

            # Crear el documento
            nc = GeneratedDoc.create({
                'project_id': simulation.project_id.id,
                'simulation_id': simulation.id,
                'document_type_id': doc_type.id,
                'folio': folio,
                'issue_date': issue_date,
                'receiver_rut': simulation.receiver_rut,
                'receiver_name': simulation.receiver_name[:100],
                'receiver_giro': simulation.receiver_giro or 'Actividades empresariales',
                'receiver_address': simulation.receiver_address or 'Dirección no especificada',
                'receiver_comuna': simulation.receiver_comuna or 'Santiago',
                'mnt_neto': mnt_neto,
                'mnt_exento': 0,
                'iva_percent': 19,
                'mnt_iva': mnt_iva,
                'mnt_total': mnt_total,
                'detalle_json': str(detalle),
                'reference_doc_type': '33',
                'reference_folio': factura_ref.folio,
                'reference_date': factura_ref.issue_date,
                'reference_code': str(cod_ref),
                'reference_reason': razon.upper(),
                'state': 'draft',
            })

            notas_credito.append(nc)

        return notas_credito

    def _generate_debit_notes(self, simulation, client, facturas):
        """Genera notas de débito (tipo 56) que referencian facturas"""
        DocumentType = self.env['l10n_latam.document.type']
        GeneratedDoc = self.env['l10n_cl_edi.certification.generated.document']

        # Tipo 56: Nota de Débito Electrónica
        doc_type = DocumentType.search([('code', '=', '56')], limit=1)
        if not doc_type:
            raise UserError(_('No se encontró el tipo de documento 56 (Nota de Débito Electrónica).'))

        notas_debito = []

        # Obtener el folio de inicio (manual o automático)
        if simulation.folio_start_debit_note > 0:
            folio_start = simulation.folio_start_debit_note
        else:
            folio_start = self._get_next_folio(simulation.project_id, doc_type)

        # VALIDAR que existan CAF para todos los folios que se van a generar
        folio_end = folio_start + simulation.debit_notes_count - 1
        self._validate_caf_range(simulation.project_id, doc_type, folio_start, folio_end)

        # Seleccionar facturas aleatorias para referenciar (diferentes a las de NC)
        facturas_disponibles = [f for f in facturas if f not in facturas[:simulation.credit_notes_count]]
        facturas_ref = random.sample(list(facturas_disponibles), min(simulation.debit_notes_count, len(facturas_disponibles)))

        for i, factura_ref in enumerate(facturas_ref):
            folio = folio_start + i

            # Fecha posterior a la factura referenciada
            issue_date = factura_ref.issue_date + timedelta(days=random.randint(5, 15))
            if issue_date > simulation.date_to:
                issue_date = simulation.date_to

            # Monto de ND: entre 10% y 30% del monto de la factura (menor que NC)
            porcentaje = random.uniform(0.1, 0.3)
            mnt_neto = int(factura_ref.mnt_neto * porcentaje)
            mnt_iva = int(mnt_neto * 0.19)
            mnt_total = mnt_neto + mnt_iva

            # Razón aleatoria para la ND
            razon = random.choice(self.ND_REASONS)

            # Generar una línea de detalle para la ND
            detalle = [{
                'NroLinDet': 1,
                'NmbItem': razon.upper(),
                'QtyItem': 1,
                'UnmdItem': 'UN',
                'PrcItem': mnt_neto,
                'MontoItem': mnt_neto,
            }]

            # Crear el documento
            nd = GeneratedDoc.create({
                'project_id': simulation.project_id.id,
                'simulation_id': simulation.id,
                'document_type_id': doc_type.id,
                'folio': folio,
                'issue_date': issue_date,
                'receiver_rut': simulation.receiver_rut,
                'receiver_name': simulation.receiver_name[:100],
                'receiver_giro': simulation.receiver_giro or 'Actividades empresariales',
                'receiver_address': simulation.receiver_address or 'Dirección no especificada',
                'receiver_comuna': simulation.receiver_comuna or 'Santiago',
                'mnt_neto': mnt_neto,
                'mnt_exento': 0,
                'iva_percent': 19,
                'mnt_iva': mnt_iva,
                'mnt_total': mnt_total,
                'detalle_json': str(detalle),
                'reference_doc_type': '33',
                'reference_folio': factura_ref.folio,
                'reference_date': factura_ref.issue_date,
                'reference_code': '3',  # 3 = Corrige monto
                'reference_reason': razon.upper(),
                'state': 'draft',
            })

            notas_debito.append(nd)

        return notas_debito

    def _generate_invoice_lines(self, lines_count):
        """Genera líneas de detalle para una factura"""
        detalle = []
        neto_total = 0

        # Seleccionar productos aleatorios
        productos = random.sample(self.PRODUCTS, min(lines_count, len(self.PRODUCTS)))

        for i, producto in enumerate(productos):
            # Precio aleatorio dentro del rango del producto
            precio = random.randint(producto['price_range'][0], producto['price_range'][1])
            cantidad = random.randint(1, 5)
            monto_linea = precio * cantidad

            detalle.append({
                'NroLinDet': i + 1,
                'NmbItem': producto['name'],
                'QtyItem': cantidad,
                'UnmdItem': 'UN',
                'PrcItem': precio,
                'MontoItem': monto_linea,
            })

            neto_total += monto_linea

        # Calcular totales
        iva = int(neto_total * 0.19)
        total = neto_total + iva

        return detalle, {
            'neto': neto_total,
            'iva': iva,
            'total': total
        }

    def _get_next_folio(self, project, doc_type):
        """Obtiene el siguiente folio disponible para un tipo de documento"""
        # Buscar asignación de folios
        FolioAssignment = self.env['l10n_cl_edi.certification.folio.assignment']
        assignment = FolioAssignment.search([
            ('project_id', '=', project.id),
            ('document_type_id', '=', doc_type.id)
        ], limit=1)

        if not assignment:
            raise UserError(_('No hay asignación de folios para el tipo de documento %s.') % doc_type.name)

        # Buscar el último folio usado
        GeneratedDoc = self.env['l10n_cl_edi.certification.generated.document']
        last_doc = GeneratedDoc.search([
            ('project_id', '=', project.id),
            ('document_type_id', '=', doc_type.id)
        ], order='folio desc', limit=1)

        if last_doc:
            next_folio = last_doc.folio + 1
        else:
            next_folio = assignment.folio_from

        # Verificar que no exceda el rango
        if next_folio > assignment.folio_to:
            raise UserError(_('Se agotaron los folios para el tipo de documento %s. Rango: %d - %d') %
                          (doc_type.name, assignment.folio_from, assignment.folio_to))

        return next_folio

    def _generate_xml_for_document(self, document, simulation):
        """
        Genera el XML DTE para un documento de simulación.

        Args:
            document: l10n_cl_edi.certification.generated.document
            simulation: l10n_cl_edi.certification.simulation
        """
        import base64
        import json
        from datetime import datetime
        import pytz
        from markupsafe import Markup

        client_info = simulation.project_id.client_info_id
        if not client_info:
            raise UserError(_('El proyecto no tiene información del cliente configurada.'))

        # Obtener código ACTECO principal
        acteco_code = None
        if client_info.company_activity_ids:
            acteco_code = client_info.company_activity_ids[0].code
        if not acteco_code:
            acteco_code = '620200'  # Fallback: Servicios de consultoría

        # Preparar datos del emisor
        emisor = {
            'RUTEmisor': client_info.rut,
            'RznSoc': client_info.social_reason,
            'GiroEmis': client_info.activity_description[:80] if client_info.activity_description else 'GIRO NO ESPECIFICADO',
            'Acteco': acteco_code,
            'DirOrigen': client_info.address or 'DIRECCIÓN NO ESPECIFICADA',
            'CmnaOrigen': client_info.city or 'Santiago',
        }

        if client_info.email:
            emisor['CorreoEmisor'] = client_info.email

        # Preparar datos del receptor (desde simulación)
        receptor = {
            'RUTRecep': document.receiver_rut,
            'RznSocRecep': document.receiver_name[:100],
            'GiroRecep': document.receiver_giro or 'Actividades empresariales',
            'DirRecep': document.receiver_address or 'Dirección no especificada',
            'CmnaRecep': document.receiver_comuna or 'Santiago',
        }

        # Preparar ID del documento
        fecha_emision = document.issue_date.strftime('%Y-%m-%d')
        id_doc = {
            'TipoDTE': int(document.document_type_id.code),
            'Folio': document.folio,
            'FchEmis': fecha_emision,
            'FchVenc': fecha_emision,
        }

        # Totales
        totales = {
            'MntNeto': document.mnt_neto,
            'TasaIVA': document.iva_percent or 19,
            'IVA': document.mnt_iva,
            'MntTotal': document.mnt_total,
        }

        if document.mnt_exento:
            totales['MntExe'] = document.mnt_exento

        # Parsear detalle desde JSON
        detalle = []
        if document.detalle_json:
            try:
                detalle = eval(document.detalle_json)  # Convertir string a lista
            except:
                detalle = json.loads(document.detalle_json)

        # Referencias (para NC y ND)
        referencias = []
        if document.reference_folio:
            referencias.append({
                'NroLinRef': 1,
                'TpoDocRef': document.reference_doc_type,
                'FolioRef': document.reference_folio,
                'FchRef': document.reference_date.strftime('%Y-%m-%d'),
                'CodRef': int(document.reference_code) if document.reference_code else 1,
                'RazonRef': (document.reference_reason or 'REFERENCIA')[:90].upper(),
            })

        # Preparar datos completos del DTE
        from datetime import datetime
        dte_data = {
            'Encabezado': {
                'Emisor': emisor,
                'Receptor': receptor,
                'IdDoc': id_doc,
                'Totales': totales,
            },
            'Detalle': detalle,
            'Referencias': referencias,
            'TmstFirma': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        }

        # Generar TED (Timbre Electrónico)
        dte_generator = self.env['l10n_cl_edi.dte.generator.service']
        ted_xml = dte_generator._generate_ted(dte_data, document)

        # Agregar TED a los datos
        dte_data['TED'] = Markup(ted_xml)

        # Generar XML del DTE
        dte_xml = dte_generator._generate_dte_xml(dte_data, document)

        # Generar código de barras PDF417
        barcode_image = dte_generator._generate_barcode(ted_xml)

        # Actualizar documento con XML y TED
        document.write({
            'xml_dte_file': base64.b64encode(dte_xml.encode('ISO-8859-1')),
            'ted_xml': ted_xml,
            'barcode_image': barcode_image,
            'state': 'generated',
        })

        return True

    def _validate_caf_range(self, project, document_type, folio_start, folio_end):
        """
        Valida que existan CAF que cubran completamente el rango de folios.

        Args:
            project: Proyecto de certificación
            document_type: Tipo de documento
            folio_start: Folio inicial del rango
            folio_end: Folio final del rango

        Raises:
            UserError: Si no hay CAF válidos para el rango completo
        """
        FolioAssignment = self.env['l10n_cl_edi.certification.folio.assignment']

        # Buscar todas las asignaciones para este tipo de documento
        assignments = FolioAssignment.search([
            ('project_id', '=', project.id),
            ('document_type_id', '=', document_type.id),
        ], order='folio_start')

        if not assignments:
            raise UserError(_(
                'No hay asignaciones de CAF para el tipo de documento %s.\n\n'
                'Debe cargar al menos un CAF en la pestaña "Folios Asignados" del proyecto.'
            ) % document_type.name)

        # Verificar cada folio del rango
        folios_sin_caf = []
        for folio in range(folio_start, folio_end + 1):
            # Buscar asignación que cubra este folio
            assignment = assignments.filtered(
                lambda a: a.folio_start <= folio <= a.folio_end
            )

            if not assignment:
                folios_sin_caf.append(folio)
                continue

            # Verificar que la asignación tenga CAF cargado
            if not assignment[0].caf_file:
                folios_sin_caf.append(folio)

        if folios_sin_caf:
            # Mostrar asignaciones disponibles
            caf_info = '\n'.join([
                f'  - Folios {a.folio_start}-{a.folio_end}: {"✓ CAF cargado" if a.caf_file else "✗ Sin CAF"}'
                for a in assignments
            ])

            raise UserError(_(
                'No hay CAF válido para cubrir todos los folios solicitados.\n\n'
                'Tipo de documento: %s\n'
                'Rango solicitado: %s - %s\n'
                'Folios sin CAF: %s\n\n'
                'Asignaciones disponibles en el proyecto:\n%s\n\n'
                'SOLUCIÓN:\n'
                '1. Sube CAF que cubran el rango %s-%s en "Folios Asignados"\n'
                '2. O ajusta el folio de inicio para usar folios con CAF disponible'
            ) % (
                document_type.name,
                folio_start,
                folio_end,
                ', '.join(map(str, folios_sin_caf[:10])) + ('...' if len(folios_sin_caf) > 10 else ''),
                caf_info,
                folio_start,
                folio_end
            ))
