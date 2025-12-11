{
    'name': 'Certificación SII Chile - Facturación Electrónica',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Gestión de Certificación de Empresas ante SII Chile',
    'description': '''
        Módulo para gestionar el proceso de certificación de facturación
        electrónica de empresas externas ante el Servicio de Impuestos
        Internos (SII) de Chile.

        Características:
        ================
        * Gestión de proyectos de certificación
        * Catálogo de 50+ casos de prueba estándar
        * Generación automática de DTEs (Documentos Tributarios Electrónicos)
        * Validación local contra esquemas XSD
        * Integración con ambiente de certificación del SII (maullin.sii.cl)
        * Seguimiento de respuestas del SII
        * Reportes de certificación en PDF
        * Control de folios y CAF (Código de Autorización de Folios)
        * Firma digital de documentos
        * Histórico y auditoría completa

        Tipos de Documentos Soportados:
        ================================
        * Factura Electrónica (33) - 16 casos de prueba
        * Factura Exenta (34) - 5 casos de prueba
        * Boleta Electrónica (39) - 5 casos de prueba
        * Boleta Exenta (41) - 4 casos de prueba
        * Nota de Crédito (56)
        * Nota de Débito (61)
        * Guía de Despacho (52)

        Flujo del Proceso:
        ==================
        1. Crear proyecto de certificación
        2. Registrar empresa cliente con certificado digital
        3. Cargar CAF (folios autorizados)
        4. Seleccionar casos de prueba del catálogo
        5. Generar DTEs automáticamente
        6. Validar localmente (esquema XSD + firma)
        7. Crear sobre de envío (EnvioDTE)
        8. Enviar al SII ambiente certificación
        9. Consultar estado y recibir respuestas
        10. Generar reporte final
    ''',
    'author': 'Alex Tito',
    'website': 'https://www.multiserviciosmsi.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'l10n_latam_invoice_document',
        'l10n_cl',
        'l10n_cl_edi',
        'account_edi',
    ],
    'external_dependencies': {
        'python': [
            'lxml',
            'xmlsec',
            'cryptography',
            'pytz',
            'PyYAML',
        ],
    },
    'data': [

        # Security
        'security/certification_security.xml',
        'security/ir.model.access.csv',

        # Data - Sequences
        'data/ir_sequence.xml',

        # Data - Test Case Templates (SET BÁSICO SII)
        'data/test_case_templates_set_basico.xml',

        # Data - Mail Message Templates
        'data/mail_message_templates.xml',

        # Data - DTE XML Templates
        'data/dte_templates.xml',

        # Wizards without menu dependencies (Load BEFORE views that reference them)
        'wizards/import_sii_testset_wizard_views.xml',

        # Views (IMPORTANT: Load views with actions BEFORE menus)
        'views/certification_project_views.xml',
        'views/certification_case_views.xml',
        'views/certification_generated_document_views.xml',
        'views/certification_client_views.xml',
        'views/certification_envelope_views.xml',
        'views/certification_book_views.xml',
        # TODO: Create these view files
        # 'views/certification_folio_assignment_views.xml',
        # 'views/certification_sii_response_views.xml',
        # 'views/test_case_template_views.xml',

        # Menus (Load AFTER views so actions are available)
        'views/menus.xml',

        # Wizards with menu dependencies (Load AFTER menus)
        'wizards/xsd_upload_wizard_views.xml',

        # TODO: Create wizard files
        # 'wizards/certification_project_wizard_views.xml',
        # 'wizards/certification_generate_wizard_views.xml',

        # TODO: Create report file
        # Reports
        # 'report/certification_project_report.xml',
    ],
    'demo': [
        # TODO: Create demo file
        # 'demo/certification_project_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
