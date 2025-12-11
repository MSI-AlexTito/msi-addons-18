# Análisis del Módulo: Certificación SII Chile - Facturación Electrónica

**Fecha**: 2025-12-04
**Módulo**: `l10n_cl_edi_certification`
**Versión**: 18.0.1.0.0

---

## 1. PROPÓSITO DEL MÓDULO

Este módulo permite a **consultores/empresas de software** gestionar el proceso completo de certificación de facturación electrónica de sus **empresas clientes** ante el **Servicio de Impuestos Internos (SII)** de Chile.

### ¿Qué es la Certificación SII?

Antes de que una empresa pueda emitir Documentos Tributarios Electrónicos (DTEs) en Chile, debe pasar por un proceso de certificación ante el SII que consiste en:

1. Generar un conjunto de **casos de prueba específicos** (definidos por el SII)
2. Enviar estos documentos al **ambiente de certificación** (maullin.sii.cl)
3. Recibir la aprobación del SII para cada caso
4. Obtener la autorización final para operar en **producción** (palena.sii.cl)

### ¿Para quién es este módulo?

- **Consultores/Integradores** que certifican empresas ante el SII
- **Empresas de Software** que ofrecen servicios de facturación electrónica
- **Casas de Software** que implementan Odoo con localización chilena

### Valor del módulo

- Gestiona múltiples proyectos de certificación simultáneamente
- Catálogo de **50+ casos de prueba oficiales** del SII precargados
- Generación automática de DTEs según especificaciones SII
- Validación local antes de enviar (ahorra tiempo y errores)
- Seguimiento completo del proceso de certificación
- Histórico inmutable de certificaciones completadas

---

## 2. FLUJO COMPLETO DE CERTIFICACIÓN

### FASE 1: Preparación del Proyecto

#### Paso 1.1: Crear Proyecto de Certificación
**Dónde**: Menú → Certificación SII → Proyectos → Crear

**Datos requeridos**:
- Nombre del proyecto (ej: "Certificación Empresa XYZ 2025")
- Empresa cliente (res.partner)
- Responsable del proyecto
- Fechas de inicio y vencimiento

**Estado**: `draft` (Borrador)

---

#### Paso 1.2: Configurar Información del Cliente
**Dónde**: Proyecto → Pestaña "Información del Cliente"

**Datos a ingresar**:

##### Datos Tributarios:
- **RUT**: 76.XXX.XXX-X
- **Razón Social**: Nombre legal de la empresa
- **Giro/Actividad**: Descripción de actividad económica
- **Código ACTECO**: Código oficial del SII

##### Dirección:
- Dirección completa
- Ciudad/Comuna
- Región

##### Contacto:
- Email de contacto
- Teléfono

##### **Certificado Digital** (CRÍTICO):
- **Archivo**: Cargar archivo `.pfx` o `.p12`
  - Este es el certificado digital que la empresa obtuvo del SII o entidad certificadora
  - Se carga como archivo binario (attachment)
- **Contraseña**: Ingresar contraseña del certificado
  - Se encripta con Fernet antes de guardar
  - Requiere configurar `encryption_key` en `odoo.conf`
- **Ambiente**: Seleccionar "Certificación" (maullin.sii.cl)

**Botón**: "Probar Certificado" para validar que el archivo y contraseña son correctos

**Modelo**: `l10n_cl_edi.certification.client`
**Snapshot**: Los datos se copian y quedan inmutables para mantener histórico

---

#### Paso 1.3: Cargar Folios (CAF)
**Dónde**: Proyecto → Pestaña "Folios Asignados"

**¿Qué es un CAF?**
- **CAF** = Código de Autorización de Folios
- Es un archivo XML firmado por el SII que autoriza rangos de folios
- Se obtiene desde el portal del SII (www.sii.cl)
- Cada tipo de documento tiene su propio CAF

**Datos a ingresar** (por cada tipo de documento):
- **Tipo de Documento**: Factura Electrónica (33), Nota de Crédito (56), etc.
- **CAF**: Seleccionar el archivo CAF previamente cargado en Odoo
  - Los CAF se cargan en: Contabilidad → Configuración → DTEs CAF
  - Modelo: `l10n_cl.dte.caf` (del módulo l10n_cl_edi)
- **Folio Inicio**: Primer número de folio disponible (ej: 1)
- **Folio Fin**: Último número de folio disponible (ej: 100)

**Ejemplo**:
```
Tipo Documento    | CAF                | Folios
------------------|--------------------|------------
Factura Elec (33) | CAF_33_1_100.xml   | 1 - 100
Nota Crédito (56) | CAF_56_1_50.xml    | 1 - 50
Nota Débito (61)  | CAF_61_1_50.xml    | 1 - 50
```

**Modelo**: `l10n_cl_edi.certification.folio.assignment`
**Auto-cálculo**: El sistema calcula automáticamente folios usados/disponibles

---

#### Paso 1.4: Seleccionar Casos de Prueba
**Dónde**: Proyecto → Pestaña "Casos de Prueba" → Agregar

**Opciones**:

##### A) Importar desde Catálogo (RECOMENDADO):
- Wizard de importación de SET BÁSICO SII
- 8 casos precargados del número de atención 3660207:
  - **3660207-1**: Factura Simple - 2 Items Afectos
  - **3660207-2**: Factura con Descuentos por Item
  - **3660207-3**: Factura con Items Afectos y Exentos
  - **3660207-4**: Factura con Descuento Global 16%
  - **3660207-5**: NC - Corrige Giro del Receptor
  - **3660207-6**: NC - Devolución de Mercaderías
  - **3660207-7**: NC - Anula Factura Completa
  - **3660207-8**: ND - Anula Nota de Crédito

##### B) Importar desde TXT del SII:
- **PENDIENTE DE IMPLEMENTAR**
- El SII proporciona archivos .txt con casos de prueba específicos
- Formato: cada línea representa un item del documento
- El wizard parseará el txt y creará los casos automáticamente

##### C) Crear Manualmente:
- Crear caso desde cero
- Definir tipo de documento
- Agregar líneas de detalle manualmente

**Modelo Template**: `l10n_cl_edi.test.case.template`
**Modelo Caso**: `l10n_cl_edi.certification.case`

---

#### Paso 1.5: Iniciar Proyecto
**Acción**: Botón "Iniciar" en el formulario del proyecto

**Validaciones**:
- ✓ Información de cliente completa y certificado cargado
- ✓ Al menos un caso de prueba agregado
- ✓ Folios asignados para los tipos de documentos requeridos

**Estado**: `in_progress` (En Progreso)

---

### FASE 2: Generación de Documentos

#### Paso 2.1: Generar DTEs
**Dónde**: Proyecto → Botón "Generar Documentos"

**Wizard de Generación**:
- Seleccionar casos a generar (individual o masivo)
- Configurar datos del receptor (para certificación: SII - RUT 60803000-K)
- Configurar fechas de emisión

**Proceso interno**:
1. Asignar folio automáticamente desde `folio_assignment`
2. Generar XML del DTE según estructura SII
3. Firmar digitalmente con el certificado del cliente
4. Generar TED (Timbre Electrónico)
5. Crear código de barras PDF417
6. Crear registro `l10n_cl_edi.certification.generated.document`

**Campos generados**:
- `xml_dte_file`: XML sin firmar
- `xml_dte_signed`: XML firmado digitalmente
- `ted_xml`: Timbre electrónico
- `barcode_image`: Imagen PDF417
- `folio`: Número de folio asignado

**Estado Caso**: `ready` → `generated`

---

#### Paso 2.2: Validar Localmente
**Dónde**: Documento → Botón "Validar"

**Validaciones**:
1. **Esquema XSD**: Validar contra esquemas oficiales del SII
2. **Firma Digital**: Verificar firma electrónica
3. **Montos**: Verificar cálculos (subtotales, IVA, descuentos)
4. **Referencias**: Para NC/ND, validar referencias a documentos originales
5. **Reglas de Negocio**: Verificar reglas específicas del SII

**Resultado**:
- Mensajes de validación guardados en `validation_messages`
- Estado: `validated` si es exitoso
- Si hay errores, se puede regenerar el documento

**Beneficio**: Detectar errores ANTES de enviar al SII

---

### FASE 3: Envío al SII

#### Paso 3.1: Crear Sobre de Envío (EnvioDTE)
**Dónde**: Menú → Certificación SII → Documentos → Sobres de Envío → Crear

**¿Qué es un Sobre?**
- Contenedor XML que agrupa múltiples DTEs
- Estructura: `<EnvioDTE>` que contiene varios `<DTE>`
- Se firma digitalmente el sobre completo
- Se envía al SII como una sola petición

**Configuración**:
- Nombre del sobre (ej: "Envío Certificación - Lote 1")
- Seleccionar documentos a incluir (Many2many)
- Los documentos deben estar en estado `validated`

**Acciones**:
1. **Crear Sobre**: Botón "Crear Sobre" → genera XML del EnvioDTE
2. **Firmar Sobre**: Botón "Firmar" → firma digital del sobre completo
3. **Validar Sobre**: Verifica esquema XSD del EnvioDTE

**Modelo**: `l10n_cl_edi.certification.envelope`

---

#### Paso 3.2: Enviar al SII
**Dónde**: Sobre → Botón "Enviar al SII"

**Proceso**:
1. Validación final del sobre
2. Conexión con webservice del SII (maullin.sii.cl)
3. Autenticación con certificado digital
4. Envío del XML firmado
5. Recepción de **Track ID** (identificador de seguimiento)

**Respuesta inmediata del SII**:
- Track ID: Ej: "123456789012345" (15 dígitos)
- Fecha de recepción
- Estado inicial: "Recibido"

**Actualización de estados**:
- Sobre: `sent`
- Documentos incluidos: `sent`
- Se guarda `sii_track_id`

**Modelo**: `l10n_cl_edi.certification.sii.response`

---

#### Paso 3.3: Consultar Estado en el SII
**Dónde**: Sobre → Botón "Consultar Estado SII"

**¿Por qué consultar?**
- El SII procesa los documentos de forma asíncrona
- Puede tomar minutos u horas procesar
- Se debe consultar periódicamente el estado

**Estados posibles**:
- `EPR` - En Proceso de Revisión
- `REC` - Recibido Conforme
- `RCT` - Rechazado (con errores)
- `RPT` - Reparo (con observaciones no bloqueantes)

**Respuesta del SII incluye**:
- Estado general del sobre
- Estado individual de cada DTE
- Mensajes de error (si hay rechazo)
- Glosas descriptivas

**Actualización automática**:
- Si `accepted`: Sobre y documentos → `accepted`
- Si `rejected`: Sobre y documentos → `rejected`
- Los casos vinculados actualizan su estado

---

### FASE 4: Resolución y Cierre

#### Paso 4.1: Revisar Casos Rechazados
**Dónde**: Proyecto → Pestaña "Casos de Prueba" → Filtrar por rechazados

**Si hay rechazos**:
1. Revisar mensajes de error del SII
2. Corregir el caso (datos, cálculos, referencias)
3. Regenerar el documento
4. Crear nuevo sobre con documentos corregidos
5. Reenviar al SII

**Errores comunes**:
- Montos mal calculados
- Referencias incorrectas (NC/ND)
- Datos del receptor erróneos
- Problemas de firma digital

---

#### Paso 4.2: Completar Proyecto
**Dónde**: Proyecto → Botón "Completar"

**Validaciones**:
- ✓ Todos los casos deben estar `accepted`
- ✓ No debe haber casos rechazados sin resolver

**Estado final**: `completed`
**Fecha**: Se registra `completion_date`

**Entregables**:
- Reporte PDF de certificación
- XMLs firmados de todos los DTEs
- Constancia de aceptación del SII
- Histórico completo del proceso

---

## 3. PROBLEMAS DE MODELADO IDENTIFICADOS

### 🔴 Problema 1: Campos de Folio en Modelo Incorrecto

**Ubicación**: `certification_project.py` líneas 36-69

**Campos problemáticos**:
```python
folio_assigned = fields.Integer(...)      # ❌ No debería estar aquí
total_amount = fields.Float(...)          # ❌ No debería estar aquí
folio_start = fields.Integer(...)         # ❌ No debería estar aquí
folio_end = fields.Integer(...)           # ❌ No debería estar aquí
folio_next = fields.Integer(...)          # ❌ No debería estar aquí
caf_id = fields.Many2one(...)             # ❌ No debería estar aquí
document_type_id = fields.Many2one(...)   # ❌ No debería estar aquí
```

**Problema**:
- Estos campos pertenecen a `certification_folio_assignment`, no al proyecto
- Un proyecto puede tener MÚLTIPLES asignaciones de folios (uno por tipo de documento)
- La vista usa correctamente `folio_assignment_ids` pero el modelo tiene campos duplicados

**Solución**:
✅ ELIMINAR estos campos del modelo `certification_project`
✅ La gestión de folios debe ser EXCLUSIVAMENTE a través de `certification_folio_assignment`

---

### 🔴 Problema 2: Campo `folio_assigned` en Modelo Proyecto

**Ubicación**: `certification_project.py` línea 36-39

```python
folio_assigned = fields.Integer(
    string='Folio Asignado',
    readonly=True,
    help='Folio que se asignó a este caso al generar el documento'
)
```

**Problema**:
- Este campo es de un CASO específico, no del proyecto
- Ya existe correctamente en `certification_case.py` línea 64-68
- Es información que varía por caso, no es del proyecto

**Solución**:
✅ ELIMINAR del modelo `certification_project`
✅ Ya existe correctamente en `certification_case`

---

### 🔴 Problema 3: Campo `total_amount` en Modelo Proyecto

**Ubicación**: `certification_project.py` línea 41-45

```python
total_amount = fields.Float(
    string='Monto Total',
    readonly=True,
    help='Monto total del documento'
)
```

**Problema**:
- El monto total es de cada CASO/DOCUMENTO, no del proyecto
- Ya existe correctamente en `certification_case.py` línea 145-150
- El proyecto no tiene un "monto total" único

**Solución**:
✅ ELIMINAR del modelo `certification_project`
✅ Si se quiere un total agregado, crear campo computado que sume `certification_case_ids.total_amount`

---

### 🟡 Problema 4: Falta Wizard de Importación de TXT

**Funcionalidad descrita pero no implementada**:
- El SII proporciona casos de prueba en formato TXT
- Debería haber un wizard para parsear estos archivos
- Actualmente solo hay templates precargados

**Archivos faltantes**:
- `wizards/certification_import_testset_wizard.py`
- `wizards_views/certification_import_testset_wizard_views.xml`

**Solución**:
✅ Implementar wizard que:
1. Reciba archivo TXT del SII
2. Parsee el formato (cada línea = un item)
3. Cree automáticamente los casos con sus líneas
4. Los agregue al proyecto

---

### 🟡 Problema 5: Servicios de Integración No Implementados

**Referencias en el código a servicios que no existen**:

1. **`l10n_cl_edi.dte.generator.service`** (línea 241 de `certification_case.py`)
   - Debería generar el XML del DTE

2. **`l10n_cl_edi.validation.service`** (línea 260 de `certification_case.py`)
   - Debería validar contra XSD

3. **`l10n_cl_edi.signature.service`** (línea 218 de `certification_generated_document.py`)
   - Debería firmar digitalmente

4. **`l10n_cl_edi.envelope.service`** (línea 138 de `certification_envelope.py`)
   - Debería crear el XML del EnvioDTE

5. **`l10n_cl_edi.sii.integration.service`** (línea 194 de `certification_envelope.py`)
   - Debería conectar con webservices del SII

**Solución**:
✅ Implementar estos servicios O
✅ Reutilizar servicios existentes del módulo `l10n_cl_edi`

---

## 4. RECOMENDACIONES DE CORRECCIÓN

### Corrección 1: Limpiar Modelo Proyecto

**Archivo**: `models/certification_project.py`

**ELIMINAR** líneas 36-75:
- `folio_assigned`
- `total_amount`
- `folio_start`
- `folio_end`
- `folio_next`
- `caf_id`
- `document_type_id`
- `_compute_folio_next` (método asociado)

**MANTENER**:
- `folio_assignment_ids` (relación One2many)
- Todos los campos estadísticos y computados de casos

---

### Corrección 2: Agregar Campos Computados Útiles

**En `certification_project.py`**, agregar:

```python
# Monto total agregado de todos los casos
total_amount_all_cases = fields.Monetary(
    string='Monto Total Todos los Casos',
    compute='_compute_total_amount_all_cases',
    store=True,
    currency_field='currency_id'
)

@api.depends('certification_case_ids.total_amount')
def _compute_total_amount_all_cases(self):
    for project in self:
        project.total_amount_all_cases = sum(
            project.certification_case_ids.mapped('total_amount')
        )
```

---

### Corrección 3: Implementar Wizard de Importación TXT

**Crear**: `wizards/certification_import_testset_wizard.py`

**Funcionalidad**:
```python
class CertificationImportTestsetWizard(models.TransientModel):
    _name = 'l10n_cl_edi.certification.import.testset.wizard'

    project_id = fields.Many2one('l10n_cl_edi.certification.project')
    txt_file = fields.Binary(string='Archivo TXT del SII', required=True)
    txt_filename = fields.Char(string='Nombre Archivo')

    def action_import(self):
        # 1. Parsear TXT
        # 2. Crear casos y líneas
        # 3. Vincular al proyecto
        pass
```

---

### Corrección 4: Implementar o Reutilizar Servicios

**Opción A - Reutilizar `l10n_cl_edi`**:
- Usar clases existentes de `l10n_cl_edi` para firma y validación
- Adaptar para el contexto de certificación

**Opción B - Implementar desde LibreDTE**:
- Portar lógica de `libredte-lib-core-master`
- Crear servicios específicos para certificación

---

## 5. CAMPOS REQUERIDOS POR PANTALLA

### Formulario de Proyecto

**Pestaña Principal**:
- ✅ `name` - Nombre del proyecto
- ✅ `partner_id` - Empresa cliente
- ✅ `company_id` - Compañía consultora
- ✅ `user_id` - Responsable
- ✅ `start_date` - Fecha inicio
- ✅ `due_date` - Fecha vencimiento
- ✅ `completion_date` - Fecha completado (auto)
- ✅ `state` - Estado
- ✅ `description` - Descripción

**Pestaña Estadísticas**:
- ✅ `progress_percentage`
- ✅ `cases_total_count`
- ✅ `cases_accepted_count`
- ✅ `cases_rejected_count`
- ✅ `cases_draft_count`
- ✅ `cases_ready_count`
- ✅ `cases_generated_count`
- ✅ `cases_validated_count`
- ✅ `cases_sent_count`

**Pestaña Información del Cliente** (embedded):
- ✅ `client_info_id` (One2one con certification_client)
  - ✅ `rut`
  - ✅ `social_reason`
  - ✅ `activity_description`
  - ✅ `acteco_code`
  - ✅ `address`
  - ✅ `city`
  - ✅ `state_id`
  - ✅ `country_id`
  - ✅ `email`
  - ✅ `phone`
  - ✅ `certificate_file` ⭐
  - ✅ `certificate_filename`
  - ✅ `environment`
  - ✅ `snapshot_date`
  - ✅ `notes`

**Pestaña Casos de Prueba**:
- ✅ `certification_case_ids` (One2many)

**Pestaña Folios Asignados**:
- ✅ `folio_assignment_ids` (One2many)
  - ✅ `document_type_id`
  - ✅ `caf_id` ⭐
  - ✅ `folio_start`
  - ✅ `folio_end`
  - ✅ `folio_next` (compute)
  - ✅ `folios_used` (compute)
  - ✅ `folios_available` (compute)
  - ✅ `usage_percentage` (compute)

---

## 6. ARQUITECTURA DE DATOS

```
l10n_cl_edi.certification.project (PROYECTO)
  │
  ├─── client_info_id (One2one) → l10n_cl_edi.certification.client
  │    └── certificate_file (Binary) ⭐ CERTIFICADO DIGITAL
  │    └── certificate_password_encrypted (Char) ⭐
  │
  ├─── folio_assignment_ids (One2many) → l10n_cl_edi.certification.folio.assignment
  │    └── caf_id → l10n_cl.dte.caf ⭐ ARCHIVO CAF DEL SII
  │    └── folio_start, folio_end, folio_next
  │
  ├─── certification_case_ids (One2many) → l10n_cl_edi.certification.case
  │    ├── template_id → l10n_cl_edi.test.case.template ⭐ CATÁLOGO
  │    ├── line_ids (One2many) → l10n_cl_edi.certification.case.line
  │    └── generated_document_id → l10n_cl_edi.certification.generated.document
  │
  ├─── generated_document_ids (One2many) → l10n_cl_edi.certification.generated.document
  │    ├── xml_dte_file (Binary)
  │    ├── xml_dte_signed (Binary)
  │    ├── ted_xml (Text)
  │    ├── barcode_image (Binary)
  │    └── envelope_id → l10n_cl_edi.certification.envelope
  │
  ├─── envelope_ids (One2many) → l10n_cl_edi.certification.envelope
  │    ├── generated_document_ids (Many2many)
  │    ├── envelope_xml (Binary)
  │    ├── envelope_xml_signed (Binary)
  │    ├── sii_track_id (Char)
  │    └── sii_response_id → l10n_cl_edi.certification.sii.response
  │
  └─── sii_response_ids (One2many) → l10n_cl_edi.certification.sii.response
       ├── response_type (send/status)
       ├── track_id (Char)
       ├── response_xml (Binary)
       └── status (accepted/rejected)
```

---

## 7. RESPUESTAS A PREGUNTAS ESPECÍFICAS

### ¿Dónde se ingresarían los folios (CAF)?

**Respuesta**:
1. **Primero**: Los archivos CAF se cargan en el sistema Odoo en:
   - Menú: Contabilidad → Configuración → Chilean SII → DTEs CAF
   - Modelo: `l10n_cl.dte.caf` (del módulo `l10n_cl_edi`)
   - Se sube el archivo XML del CAF

2. **Después**: En el proyecto de certificación:
   - Pestaña "Folios Asignados" del proyecto
   - Botón "Agregar línea"
   - Seleccionar tipo de documento
   - **Seleccionar el CAF** previamente cargado (campo: `caf_id`)
   - Especificar rango de folios a usar (inicio y fin)

### ¿Dónde se cargaría el certificado digital?

**Respuesta**:
- Pestaña "Información del Cliente" del proyecto
- Campo `certificate_file` (tipo Binary)
- Clic en "Adjuntar" → Seleccionar archivo `.pfx` o `.p12`
- Ingresar contraseña en un diálogo (se encripta automáticamente)
- Botón "Probar Certificado" para validar

### ¿Cómo se adjuntarían los casos de prueba (TXT del SII)?

**Respuesta**:

**ACTUALMENTE** (implementado):
- Los casos del SET BÁSICO ya están precargados como templates
- Se agregan al proyecto desde el catálogo
- Modelo: `l10n_cl_edi.test.case.template`

**PENDIENTE** (por implementar):
- Wizard de importación de archivos TXT
- Ubicación: Proyecto → Botón "Importar Casos desde TXT"
- Se subirá archivo .txt del SII
- Parser automático creará los casos con sus líneas
- Formato TXT del SII (ejemplo):
  ```
  33|001|Cajón AFECTO|152|2548|0|N
  33|001|Relleno AFECTO|64|4221|0|N
  ```
  Donde: TipoDoc|NumCaso|Descripción|Qty|Precio|Descto|Exento

---

## 8. PRÓXIMOS PASOS RECOMENDADOS

1. **URGENTE**: Corregir modelo `certification_project` (eliminar campos incorrectos)
2. **PRIORITARIO**: Implementar wizard de importación TXT
3. **PRIORITARIO**: Implementar servicios de generación y firma
4. **IMPORTANTE**: Crear vistas faltantes para los otros modelos
5. **IMPORTANTE**: Integración con webservices del SII
6. **DESEABLE**: Reportes PDF de certificación
7. **DESEABLE**: Dashboard con estadísticas generales

---

**FIN DEL ANÁLISIS**
