# Módulo de Certificación SII para Odoo 18

## Estado del Proyecto

### ✅ Completado

1. **Estructura de carpetas** - Todas las carpetas creadas
2. **__manifest__.py** - Configuración completa del módulo
3. **Modelos** - 10 modelos principales implementados:
   - `certification_project.py` - Gestión de proyectos
   - `certification_client.py` - Información del cliente (snapshot)
   - `certification_case.py` - Casos de prueba
   - `certification_case_line.py` - Líneas de casos
   - `certification_folio_assignment.py` - Asignación de folios
   - `certification_generated_document.py` - Documentos DTE generados
   - `certification_envelope.py` - Sobres de envío
   - `certification_sii_response.py` - Respuestas del SII
   - `test_case_template.py` - Catálogo de casos de prueba
   - `test_case_template_line.py` - Líneas de plantillas

4. **Servicios** - 6 servicios especializados:
   - `dte_generator_service.py` - Generación de DTEs
   - `signature_service.py` - Firma digital
   - `validation_service.py` - Validación XSD y reglas de negocio
   - `envelope_service.py` - Creación de sobres
   - `sii_integration_service.py` - Integración con SII
   - `folio_service.py` - Gestión de folios

5. **Seguridad**:
   - `certification_security.xml` - 3 grupos con reglas de acceso
   - `ir.model.access.csv` - Permisos CRUD completos

6. **Datos**:
   - `ir_sequence.xml` - Secuencias para proyectos y sobres

7. **Vistas**:
   - `menus.xml` - Menú completo del módulo
   - `certification_project_views.xml` - Vistas Form, list, Kanban y Search

### 🔨 Pendiente de Implementación

Para completar el módulo, necesita crear los siguientes archivos:

#### 1. Vistas Restantes

**certification_client_views.xml**
- Vista form para editar información del cliente
- Vista tree para listar clientes
- Action window

**certification_case_views.xml**
- Vista form con notebook para líneas
- Vista tree con colores por estado
- Action window

**certification_folio_assignment_views.xml**
- Vista tree editable
- Vista form simple

**certification_generated_document_views.xml**
- Vista form con preview de XML
- Vista tree con búsqueda por tipo y folio
- Botones para descargar XML, validar, firmar

**certification_envelope_views.xml**
- Vista form con lista de documentos
- Botones para crear, firmar, enviar
- Vista tree con estado

**certification_sii_response_views.xml**
- Vista form para ver detalles de respuesta
- Vista tree con colores por estado

**test_case_template_views.xml**
- Vista form para plantillas
- Vista tree agrupada por tipo de documento
- Action para duplicar a custom

#### 2. Wizards

**certification_project_wizard.py** y su vista
- Wizard multi-paso para crear proyecto
- Paso 1: Información básica
- Paso 2: Cliente y certificado
- Paso 3: Selección de casos de prueba
- Paso 4: Asignación de folios

**certification_generate_wizard.py** y su vista
- Selección de casos a generar
- Opciones de validación
- Opción de envío automático
- Generación en lote

**certification_import_testset_wizard.py** y su vista
- Importar casos desde YAML/JSON (formato LibreDTE)
- Crear plantillas personalizadas

#### 3. Templates XML para DTEs

**templates/dte_certification_template.xml**
- Template QWeb para generar XML de DTE
- Estructura según especificación SII
- Variables: dte_data, case

**templates/envelope_certification_template.xml**
- Template para EnvioDTE
- Carátula + lista de DTEs
- Variables: envelope_data

#### 4. Datos de Casos de Prueba

Crear archivos en `data/` con los 50+ casos de prueba basados en LibreDTE:

- `test_case_templates_033.xml` - 16 casos Factura Afecta
- `test_case_templates_034.xml` - 5 casos Factura Exenta
- `test_case_templates_039.xml` - 5 casos Boleta Afecta
- `test_case_templates_041.xml` - 4 casos Boleta Exenta
- `test_case_templates_056.xml` - Casos Nota de Crédito
- `test_case_templates_061.xml` - Casos Nota de Débito
- `test_case_templates_052.xml` - Casos Guía de Despacho

Formato de cada registro:
```xml
<record id="test_case_033_001" model="l10n_cl_edi.test.case.template">
    <field name="code">033-001</field>
    <field name="name">Factura Simple</field>
    <field name="document_type_id" ref="l10n_cl.dt_33"/>
    <field name="description">Factura electrónica simple con un ítem</field>
    <field name="category">standard</field>
    <field name="global_discount">0</field>
</record>
<record id="test_case_033_001_line_1" model="l10n_cl_edi.test.case.template.line">
    <field name="template_id" ref="test_case_033_001"/>
    <field name="sequence">10</field>
    <field name="description">Producto de prueba</field>
    <field name="qty">1</field>
    <field name="price_unit">1000</field>
    <field name="discount">0</field>
    <field name="exempt" eval="False"/>
</record>
```

#### 5. Reportes

**report/certification_project_report.py**
- Clase Python para generar reporte PDF

**report/certification_project_report.xml**
- Definición del reporte

**report/certification_project_report_template.xml**
- Template QWeb para PDF del proyecto
- Incluir: datos cliente, casos, documentos, respuestas SII

#### 6. Tests

**tests/test_certification_project.py**
- Tests del flujo completo

**tests/test_dte_generator.py**
- Tests de generación de XML

**tests/test_validation_service.py**
- Tests de validación

#### 7. Demo Data

**demo/certification_project_demo.xml**
- Datos de demostración

#### 8. Archivos Adicionales

**static/description/icon.png**
- Icono del módulo (128x128)

**static/description/index.html**
- Descripción HTML del módulo

### 📋 Esquemas XSD del SII

Debe descargar los esquemas XSD oficiales del SII y colocarlos en:
`schemas/`

- DTE_v10.xsd
- EnvioDTE_v10.xsd
- RespuestaEnvioDTE_v10.xsd

Disponibles en: http://www.sii.cl/factura_electronica/

### 🔧 Configuración Requerida

1. **odoo.conf** - Agregar clave de encriptación:
```ini
[options]
encryption_key = YOUR_FERNET_KEY_HERE
```

Generar con Python:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

2. **Dependencias Python**:
```bash
pip install lxml xmlsec cryptography pytz PyYAML pdf417gen
```

3. **Certificados de Prueba**:
- Obtener certificado de prueba del SII
- Obtener CAF de prueba para ambiente de certificación

### 🚀 Instalación

1. Copiar el módulo a `addons/`
2. Actualizar lista de módulos
3. Instalar dependencias: `l10n_cl_edi`
4. Configurar clave de encriptación en odoo.conf
5. Instalar el módulo
6. Asignar grupos de seguridad a usuarios

### 📖 Uso

1. **Crear Proyecto**: Certificación SII > Proyectos > Crear
2. **Configurar Cliente**: Ingresar datos tributarios y certificado
3. **Seleccionar Casos**: Agregar casos de prueba del catálogo
4. **Asignar Folios**: Configurar CAF y rangos
5. **Generar DTEs**: Usar wizard de generación
6. **Validar**: Sistema valida contra XSD
7. **Enviar al SII**: Crear sobre y enviar
8. **Consultar Estado**: Verificar aceptación

### 🎯 Próximos Pasos

1. Implementar firma digital real (xmlsec)
2. Implementar generación de PDF417 (barcode)
3. Completar integración SOAP con SII
4. Agregar todos los casos de prueba de LibreDTE
5. Implementar generación de TED real
6. Tests automatizados completos

### 📚 Documentación

Ver el archivo `DISENO_MODULO_CERTIFICACION.md` para arquitectura completa.

### 🤝 Contribuciones

Este módulo está diseñado siguiendo las mejores prácticas de Odoo 18 y patrones de diseño modernos.

### 📄 Licencia

LGPL-3
