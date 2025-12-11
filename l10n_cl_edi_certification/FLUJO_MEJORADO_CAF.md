# Flujo Mejorado: Gestión de CAF y Casos de Prueba

**Fecha**: 2025-12-04
**Versión**: 18.0.1.0.0

---

## 🎯 MEJORAS IMPLEMENTADAS

### 1. Importación Automática del SET BÁSICO

**Ubicación**: Botón "⚡ Importar SET BÁSICO" en la cabecera del Proyecto

**¿Qué hace?**
- Importa automáticamente los 8 casos de prueba del SET BÁSICO del SII (Número de atención: 3660207)
- Crea los casos desde plantillas pre-configuradas
- Solo disponible cuando el proyecto está en estado 'Borrador'

**Flujo de uso**:

```
1. Crear nuevo Proyecto de Certificación
2. Estado: Borrador
3. Click en botón "⚡ Importar SET BÁSICO"
4. Sistema crea automáticamente 8 casos:
   - 3660207-01: Factura Electrónica Afecta
   - 3660207-02: Factura Electrónica Exenta
   - 3660207-03: Factura con descuento global
   - 3660207-04: Factura con referencias
   - 3660207-05: Nota de Crédito Electrónica
   - 3660207-06: Nota de Débito Electrónica
   - 3660207-07: Factura con múltiples impuestos
   - 3660207-08: Factura con ILA (impuesto específico)
5. Notificación de éxito muestra casos creados
6. Pestaña "Casos de Prueba" ahora muestra los 8 casos listos
```

**Validaciones**:
- ❌ No permite importar si ya existen casos en el proyecto
- ❌ Muestra error si las plantillas no están cargadas en el sistema

**Código relevante**: `certification_project.py:305-356`

---

## 2. Gestión Dual de CAF (Solución al Problema de Confusión)

### 🔴 PROBLEMA ANTERIOR

En la versión anterior:
- Solo se podía referenciar CAF del sistema (`l10n_cl.dte.caf`)
- **CONFUSIÓN**: Los CAF de la empresa consultora se mezclaban con los CAF del cliente a certificar
- Riesgo de usar folios incorrectos

### ✅ SOLUCIÓN IMPLEMENTADA

**Ahora existen DOS opciones para proporcionar CAF**:

#### Opción 1: CAF del Sistema (Campo: `caf_id`)
**Cuándo usar**: Solo si el cliente ya está usando Odoo para facturación y tiene CAF cargados en el sistema

**Ventajas**:
- ✅ Reutiliza CAF ya cargados
- ✅ No requiere volver a subir archivos

**Desventajas**:
- ⚠️ Puede confundirse con CAF de la consultora
- ⚠️ Requiere que el cliente tenga CAF pre-cargados

---

#### Opción 2: Archivo CAF del Cliente (Campo: `caf_file`) ⭐ **RECOMENDADO**
**Cuándo usar**: Para certificación de nuevos clientes (caso más común)

**Ventajas**:
- ✅ No se confunde con CAF de la consultora
- ✅ Cliente proporciona su archivo CAF directamente
- ✅ Extracción automática de información
- ✅ Validación automática de datos

**Cómo funciona**:

```
1. Cliente envía archivo CAF (ejemplo: CAF_F33_1-100.xml)
2. Consultora abre el Proyecto de Certificación
3. Va a pestaña "Folios Asignados"
4. Crea nueva línea:
   - Tipo de Documento: Factura Electrónica (33)
   - Deja "CAF del Sistema" vacío
   - En "Archivo CAF del Cliente": Sube CAF_F33_1-100.xml
5. Sistema extrae automáticamente:
   ✓ RUT del Emisor (del cliente)
   ✓ Tipo de Documento (33)
   ✓ Folio Inicio (1)
   ✓ Folio Fin (100)
6. Sistema valida que el tipo de documento coincida
7. Listo para generar documentos con esos folios
```

**Estructura del archivo CAF**:
```xml
<AUTORIZACION>
  <CAF>
    <DA>
      <RE>76123456-7</RE>              <!-- RUT del Emisor -->
      <TD>33</TD>                       <!-- Tipo Documento -->
      <RNG>
        <D>1</D>                        <!-- Folio Inicio -->
        <H>100</H>                      <!-- Folio Fin -->
      </RNG>
      <!-- Firma digital y otros datos -->
    </DA>
  </CAF>
</AUTORIZACION>
```

**Validación automática**:
- ⚠️ Advierte si el tipo de documento del CAF no coincide con el tipo seleccionado
- ❌ Error si el archivo no es XML válido
- ❌ Error si no se proporciona ni CAF del sistema ni archivo CAF

**Código relevante**: `certification_folio_assignment.py:39-213`

---

## 3. Vista Mejorada de Folios Asignados

### Nueva Lista con Campos Adicionales

**Campos visibles por defecto**:
- `document_type_id`: Tipo de Documento
- `caf_id`: CAF del Sistema (opcional, visible)
- `caf_file`: Archivo CAF del Cliente ⭐ **NUEVO**
- `caf_rut_emisor`: RUT Emisor extraído ⭐ **NUEVO**
- `folio_start`: Folio Inicio
- `folio_end`: Folio Fin
- `folio_next`: Próximo Folio
- `folios_used`: Folios Usados
- `folios_available`: Folios Disponibles
- `usage_percentage`: % de Uso (barra de progreso)

**Campos opcionales** (se pueden mostrar/ocultar):
- `caf_type_code`: Código del Tipo de Documento (del CAF)

**Funcionalidad**:
- ✅ Edición en línea (`editable="bottom"`)
- ✅ Crear y eliminar asignaciones de folios
- ✅ Al subir archivo CAF, extrae información automáticamente

**Código relevante**: `certification_project_views.xml:160-177`

---

## 📊 FLUJO COMPLETO DE CERTIFICACIÓN (ACTUALIZADO)

### FASE 1: Configuración del Proyecto

```
1. Crear Proyecto de Certificación
   - Nombre: "Certificación Empresa XYZ 2024"
   - Empresa Cliente: XYZ S.A.
   - Responsable: [Usuario]

2. Completar "Información del Cliente"
   - RUT, razón social, dirección
   - Subir certificado digital (.pfx/.p12)
   - Contraseña del certificado (encriptada)

3. ⚡ Importar SET BÁSICO (NUEVO)
   - Click en botón "Importar SET BÁSICO"
   - Sistema crea 8 casos de prueba automáticamente

4. Asignar Folios por Tipo de Documento
   OPCIÓN A - CAF del Cliente (RECOMENDADO):
   - Factura (33): Subir CAF_F33.xml → Sistema extrae folios 1-100
   - Nota Crédito (56): Subir CAF_NC56.xml → Sistema extrae folios 1-50
   - Nota Débito (61): Subir CAF_ND61.xml → Sistema extrae folios 1-50

   OPCIÓN B - CAF del Sistema:
   - Seleccionar CAF pre-cargado (solo si ya existe)

5. Click en "Iniciar" → Estado: En Progreso
```

### FASE 2: Generación de Documentos

```
1. Estado: En Progreso
2. Click en "Generar Documentos"
3. Wizard permite:
   - Seleccionar casos a generar
   - Validar que haya folios disponibles
4. Sistema genera:
   - XML del DTE (según estructura SII)
   - Firma con certificado del cliente
   - Asigna folio del rango del CAF del cliente ⭐
   - Valida contra XSD del SII
5. Casos pasan a estado "Generado"
```

### FASE 3: Envío y Validación (Sin cambios)

### FASE 4: Finalización (Sin cambios)

---

## 🔐 SEGURIDAD Y SEPARACIÓN DE DATOS

### Antes de las Mejoras:
```
❌ CAF de Consultora ABC (RUT: 76111111-1)
   ├── Factura 33: Folios 1-1000
   └── Nota Crédito 56: Folios 1-500

❌ CAF de Cliente XYZ (RUT: 76222222-2)
   ├── Factura 33: Folios 1-100  ← ¿Cómo distinguir?
   └── Nota Crédito 56: Folios 1-50

⚠️ Riesgo: Usar folios de la consultora para el cliente
```

### Después de las Mejoras:
```
✅ CAF del Sistema (Consultora ABC - RUT: 76111111-1)
   ├── Factura 33: Folios 1-1000
   └── Nota Crédito 56: Folios 1-500
   └── [Usado por la consultora para su facturación propia]

✅ CAF Subido del Cliente XYZ (RUT: 76222222-2)
   ├── Factura 33: Folios 1-100 (archivo CAF_F33.xml)
   │   └── RUT Emisor: 76222222-2 (extraído automáticamente)
   └── Nota Crédito 56: Folios 1-50 (archivo CAF_NC56.xml)
       └── RUT Emisor: 76222222-2 (extraído automáticamente)
   └── [Usado exclusivamente para certificación del cliente]

🛡️ Seguridad: Separación clara, sin confusión posible
```

---

## 📝 EJEMPLO PRÁCTICO COMPLETO

### Escenario: Certificar empresa "Comercial Los Andes Ltda."

**Cliente proporciona**:
- Certificado digital: `comercial_los_andes.pfx` + contraseña
- CAF Factura: `CAF_33_1-100_Los_Andes.xml`
- CAF Nota Crédito: `CAF_56_1-50_Los_Andes.xml`
- CAF Nota Débito: `CAF_61_1-50_Los_Andes.xml`

**Pasos del consultor**:

```python
# 1. Crear proyecto
Proyecto: "Certificación Comercial Los Andes 2024"
Cliente: Comercial Los Andes Ltda. (RUT: 76333333-3)
Estado: Borrador

# 2. Información del Cliente
client_info:
  rut: "76333333-3"
  social_reason: "Comercial Los Andes Ltda."
  certificate_file: [upload comercial_los_andes.pfx]
  certificate_password: "******" → Encriptada automáticamente
  environment: "certificacion"

# 3. Importar SET BÁSICO
Click "⚡ Importar SET BÁSICO"
→ Crea 8 casos de prueba automáticamente

# 4. Asignar Folios (NUEVO MÉTODO)
folio_assignments:
  - document_type: Factura Electrónica (33)
    caf_id: [vacío]
    caf_file: [upload CAF_33_1-100_Los_Andes.xml]
    → Sistema extrae:
      caf_rut_emisor: "76333333-3"
      caf_type_code: "33"
      folio_start: 1
      folio_end: 100

  - document_type: Nota de Crédito (56)
    caf_id: [vacío]
    caf_file: [upload CAF_56_1-50_Los_Andes.xml]
    → Sistema extrae:
      caf_rut_emisor: "76333333-3"
      caf_type_code: "56"
      folio_start: 1
      folio_end: 50

  - document_type: Nota de Débito (61)
    caf_id: [vacío]
    caf_file: [upload CAF_61_1-50_Los_Andes.xml]
    → Sistema extrae:
      caf_rut_emisor: "76333333-3"
      caf_type_code: "61"
      folio_start: 1
      folio_end: 50

# 5. Iniciar proyecto
Click "Iniciar" → Estado: En Progreso

# 6. Generar documentos
Click "Generar Documentos"
Sistema genera 8 DTEs:
  - Caso 1: F33 con folio 1 (del CAF del cliente)
  - Caso 2: F33 con folio 2 (del CAF del cliente)
  - ...
  - Caso 5: NC56 con folio 1 (del CAF del cliente)
  - Caso 6: ND61 con folio 1 (del CAF del cliente)

Cada DTE:
  ✓ Firmado con certificado de Los Andes
  ✓ Folio del rango autorizado para Los Andes
  ✓ RUT emisor: 76333333-3
  ✓ XML validado contra XSD del SII

# 7. Continuar con envío y validación...
```

---

## 🔧 MÉTODOS TÉCNICOS NUEVOS

### `certification_project.py`

#### `action_import_basic_testset()`
**Propósito**: Importa automáticamente los 8 casos del SET BÁSICO del SII

**Lógica**:
```python
1. Verificar que no haya casos existentes
2. Buscar plantillas con código 3660207-* (category='standard')
3. Para cada plantilla:
   - Crear caso usando create_from_template()
4. Registrar en chatter los casos creados
5. Mostrar notificación de éxito
```

**Retorna**: Notificación tipo 'success' con cantidad de casos importados

---

### `certification_folio_assignment.py`

#### `_onchange_caf_file()`
**Propósito**: Extrae automáticamente información del archivo CAF subido

**Lógica**:
```python
1. Decodificar archivo Binary (base64)
2. Parsear XML con lxml
3. Extraer con XPath:
   - //RE → RUT del emisor (caf_rut_emisor)
   - //TD → Tipo de documento (caf_type_code)
   - //RNG/D → Folio inicio (folio_start)
   - //RNG/H → Folio fin (folio_end)
4. Validar coincidencia con document_type_id seleccionado
5. Si no coincide, mostrar warning
6. Si error de parseo, mostrar error con detalle
```

**Retorna**: Warning/Error dict o None si OK

---

#### `get_caf_content()`
**Propósito**: Obtiene el contenido XML del CAF para generación de DTEs

**Lógica**:
```python
if caf_file:
    return decode(caf_file)  # Prioridad: archivo del cliente
elif caf_id:
    return decode(caf_id.caf_file)  # Fallback: CAF del sistema
else:
    raise UserError  # No hay CAF configurado
```

**Retorna**: String XML del CAF

---

#### `_check_caf_source()`
**Propósito**: Valida que al menos un método de CAF esté configurado

**Lógica**:
```python
if not caf_id and not caf_file:
    raise ValidationError('Debe proporcionar CAF por algún método')
```

---

## 📂 ARCHIVOS MODIFICADOS

### 1. `models/certification_project.py`
**Líneas agregadas**: 305-356
**Método nuevo**: `action_import_basic_testset()`

### 2. `models/certification_folio_assignment.py`
**Líneas modificadas**: 33-213
**Campos nuevos**:
- `caf_file` (línea 40)
- `caf_filename` (línea 45)
- `caf_rut_emisor` (línea 50)
- `caf_type_code` (línea 55)

**Métodos nuevos**:
- `_onchange_caf_file()` (línea 153)
- `_check_caf_source()` (línea 214)

**Métodos modificados**:
- `get_caf_content()` (línea 242)

### 3. `views/certification_project_views.xml`
**Líneas modificadas**:
- 25-31: Botón "Importar SET BÁSICO"
- 160-177: Lista de folios asignados con nuevos campos

---

## ✅ VALIDACIONES IMPLEMENTADAS

### En el Modelo

1. **`_check_caf_source`**: Al menos un método de CAF debe estar configurado
2. **`_check_folio_range`**: Folios válidos (inicio > 0, fin >= inicio)
3. **`_onchange_caf_file`**:
   - Archivo XML válido
   - Coincidencia de tipo de documento
   - Estructura XML correcta

### En la Vista

1. **Constraint único**: `(project_id, document_type_id)` - No duplicar tipo de documento
2. **Domain en caf_id**: Solo CAF del tipo de documento seleccionado
3. **Campo filename**: Manejo correcto de archivo Binary

---

## 🎓 PREGUNTAS FRECUENTES

### ¿Debo usar siempre el archivo CAF del cliente?
**R**: Para certificación, SÍ. Es la forma más clara y segura de separar folios.

### ¿Puedo usar ambos métodos al mismo tiempo?
**R**: Técnicamente sí, pero el sistema priorizará `caf_file` si ambos están configurados.

### ¿Qué pasa si subo un CAF con tipo de documento incorrecto?
**R**: El sistema te advertirá, pero no bloqueará. Verifica que el tipo coincida.

### ¿Se encripta el archivo CAF?
**R**: No, el CAF ya está firmado digitalmente por el SII. Se almacena como Binary con `attachment=True`.

### ¿Puedo eliminar el archivo CAF después de generar los documentos?
**R**: No recomendado. Se necesita para validaciones y auditoría.

### ¿El botón "Importar SET BÁSICO" sobrescribe casos existentes?
**R**: No. Si ya hay casos, muestra error. Debes eliminarlos manualmente primero.

### ¿Los casos importados tienen los montos correctos?
**R**: Sí, vienen desde las plantillas con los montos oficiales del SII para cada caso.

---

## 🚀 BENEFICIOS DE LAS MEJORAS

### Para Consultores:
✅ No más confusión entre folios propios y de clientes
✅ Importación rápida del SET BÁSICO (segundos vs. minutos)
✅ Validación automática de CAF
✅ Trazabilidad clara del origen de cada folio

### Para Clientes:
✅ Solo envían sus archivos CAF directamente
✅ No requieren tener Odoo configurado previamente
✅ Reducción de errores en certificación
✅ Proceso más transparente

### Para el Negocio:
✅ Menos tiempo en configuración de proyectos
✅ Menos riesgo de errores costosos
✅ Mejor experiencia de usuario
✅ Mayor confianza en el proceso

---

**FIN DEL DOCUMENTO DE FLUJO MEJORADO**
