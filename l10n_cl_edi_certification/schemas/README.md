# Esquemas XSD del SII para Validación

Este módulo incluye los **esquemas XSD oficiales del SII** para validar XML antes de enviar.

## ¿Cómo Funciona?

A diferencia de Odoo Enterprise que usa `ir.attachment`, este módulo usa los **archivos XSD directamente** desde la carpeta `schemas/`. Esto es más simple y no requiere configuración adicional.

## Esquemas XSD Incluidos

Los siguientes esquemas ya están incluidos en la carpeta `schemas/`:

### Libros de Compra/Venta (IECV)
- ✅ **LibroCV_v10.xsd** - Esquema principal de LibroCompraVenta
- ✅ **xmldsignature_v10.xsd** - Validación de firmas digitales
- ✅ **LceCoCertif_v10.xsd** - Estructuras para certificación
- ✅ **LceSiiTypes_v10.xsd** - Tipos comunes del SII
- ✅ **LceCal_v10.xsd** - Certificado de Autorización de Libros

### Para DTEs (Futuro)
- ⏳ **DTE_v10.xsd** - Documento Tributario Electrónico (por agregar)
- ⏳ **EnvioDTE_v10.xsd** - Sobre de Envío (por agregar)
- ⏳ **RespuestaDTE_v10.xsd** - Respuesta del SII (por agregar)

## Uso Automático

La validación XSD se ejecuta **automáticamente** al firmar un libro:

1. Usuario genera el libro → se crea XML
2. Usuario firma el libro → **se valida contra XSD primero**
3. Si hay errores → se muestra mensaje con detalles
4. Si es válido → se firma normalmente

**NO se requiere configuración adicional** - los esquemas se cargan desde `schemas/` automáticamente.

## Beneficios de la Validación XSD

✅ **Validación automática** antes de firmar:
- Valida estructura XML contra esquema oficial del SII
- Detecta errores tempranos (antes de enviar)
- Reduce rechazos del SII (STATUS 7)
- Muestra errores específicos con números de línea

✅ **Sin configuración**:
- Los esquemas ya están incluidos en el módulo
- Se cargan automáticamente desde `schemas/`
- No requiere subir archivos a Odoo

✅ **Opcional pero recomendado**:
- Si faltan los esquemas XSD → solo muestra advertencia
- La firma continúa normalmente
- El SII valida de todas formas al enviar

## Ventajas vs Odoo Enterprise

Este módulo usa archivos XSD directos en lugar de `ir.attachment`:

| Característica | Este Módulo | Odoo Enterprise |
|----------------|-------------|-----------------|
| Configuración | ✅ Ninguna | ⚠️ Subir XSD manualmente |
| Versionamiento | ✅ Con Git | ⚠️ En base de datos |
| Portabilidad | ✅ Con el módulo | ⚠️ Exportar/importar BD |
| Dependencias | ✅ Auto-resueltas | ⚠️ Gestión manual |

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
