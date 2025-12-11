# Esquemas XSD del SII para Validación

Este módulo utiliza el **mismo sistema que Odoo Enterprise** para validar XML contra esquemas XSD.

## ¿Cómo Funciona?

Los esquemas XSD se almacenan como **adjuntos (`ir.attachment`)** en la base de datos, NO como archivos físicos. Esto es exactamente como lo hace `l10n_cl_edi` de Odoo Enterprise.

## Instalación de Esquemas XSD (Opcional)

### Paso 1: Descargar Esquemas del SII

Obtén los esquemas XSD oficiales desde:
- **Sitio SII**: https://www.sii.cl/factura_electronica/
- **Esquemas necesarios**:
  - `DTE_v10.xsd` - Documento Tributario Electrónico
  - `EnvioDTE_v10.xsd` - Sobre de Envío
  - `RespuestaDTE_v10.xsd` - Respuesta del SII
  - `SiiTypes_v10.xsd` - Tipos comunes (dependencia)

### Paso 2: Subir a Odoo como Adjuntos

**Opción A: Interfaz de Odoo (Recomendado)**

1. Ve a: **Configuración → Técnico → Estructura de la Base de Datos → Adjuntos**
2. Crea un nuevo adjunto para cada esquema:
   - **Nombre**: `l10n_cl_edi_certification.DTE_v10.xsd`
   - **Tipo**: Archivo binario
   - **Archivo**: Selecciona el archivo XSD descargado
   - **Público**: ✓ (marcado)

3. Repite para cada esquema:
   - `l10n_cl_edi_certification.DTE_v10.xsd`
   - `l10n_cl_edi_certification.EnvioDTE_v10.xsd`
   - `l10n_cl_edi_certification.RespuestaDTE_v10.xsd`
   - `l10n_cl_edi_certification.SiiTypes_v10.xsd`

**⚠️ IMPORTANTE**: El nombre debe empezar con `l10n_cl_edi_certification.` (prefijo del módulo)

**Opción B: Código Python (Avanzado)**

```python
import base64

# Leer archivo XSD
with open('/ruta/a/DTE_v10.xsd', 'rb') as f:
    xsd_content = f.read()

# Crear adjunto
self.env['ir.attachment'].create({
    'name': 'l10n_cl_edi_certification.DTE_v10.xsd',
    'raw': xsd_content,
    'public': True,
})
```

### Paso 3: Verificar Instalación

1. Ve a un documento generado
2. Haz clic en "Validar"
3. Si el mensaje NO dice "esquema no encontrado", ¡está funcionando! ✓

## ¿Es Obligatorio?

**NO.** La validación XSD es completamente opcional:

### Sin XSD (por defecto):
- ✓ Validación de reglas de negocio (RUT, folios, montos, fechas)
- ✓ Validación de firma digital
- ⚠️ Se omite validación de estructura XML
- ✓ El SII valida al enviar (validación definitiva)

### Con XSD (recomendado):
- ✓ Todas las validaciones anteriores
- ✓ Validación de estructura XML contra esquema oficial
- ✓ Detección temprana de errores de formato
- ✓ Reduce rechazos en el SII

## Ventajas del Enfoque de Odoo (ir.attachment)

1. **Portabilidad**: Los esquemas se exportan/importan con la base de datos
2. **Versionamiento**: Fácil actualizar esquemas sin tocar archivos
3. **Multi-empresa**: Diferentes empresas pueden usar diferentes versiones
4. **Seguridad**: Odoo gestiona permisos de acceso automáticamente
5. **Consistencia**: Mismo enfoque que `l10n_cl_edi` de Odoo Enterprise

## Versiones de Esquemas

- **v10**: Versión actual (2023+) - Recomendada
- Asegúrate de descargar la versión correcta del SII

## Esquemas Relacionados

Los esquemas XSD del SII tienen dependencias entre sí. Si un esquema importa otro (con `xs:import` o `xs:include`), ambos deben estar en `ir.attachment` con el prefijo correcto:

```xml
<!-- Ejemplo: DTE_v10.xsd importa SiiTypes_v10.xsd -->
<xs:import schemaLocation="SiiTypes_v10.xsd" .../>
```

Por eso debes subir **todos** los esquemas relacionados.
