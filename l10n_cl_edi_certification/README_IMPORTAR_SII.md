# Importar Set de Pruebas desde Archivo del SII

## Descripción

Esta funcionalidad permite importar automáticamente los casos de prueba desde el archivo `.txt` descargado directamente del sitio del SII.

## Cómo Usar

### 1. Descargar el archivo del SII

1. Ingresa a tu cuenta en el SII (maullin.sii.cl)
2. Descarga el archivo de set de pruebas (ej: `SIISetDePruebas776976598.txt`)

### 2. Importar desde Odoo

1. Abre tu **Proyecto de Certificación** (debe estar en estado **Borrador**)
2. Haz clic en el botón **"📁 Importar desde Archivo SII"**
3. Carga el archivo `.txt` descargado
4. Revisa la **Vista Previa** que muestra:
   - Número de atención
   - Casos detectados
   - Items por caso
   - Referencias entre casos
5. Haz clic en **"Importar Casos"**

## ¿Qué se Importa?

El parser automáticamente detecta y crea:

### ✅ Facturas Electrónicas (33)
- Items afectos y exentos
- Descuentos por línea (%)
- Descuentos globales (%)
- Cantidades y precios unitarios

### ✅ Notas de Crédito (61)
- Referencia al documento original
- Razón de la referencia
- Items (si aplica)

### ✅ Notas de Débito (56)
- Referencia al documento original
- Razón de la referencia

## Formato del Archivo SII

El parser reconoce este formato:

```
SET BASICO - NUMERO DE ATENCION: 4606904

CASO 4606904-1
==============
DOCUMENTO    FACTURA ELECTRONICA

ITEM                CANTIDAD    PRECIO UNITARIO
Cajón AFECTO            144           2125
Relleno AFECTO           61           3506
```

## Ejemplo Real

Archivo: `SIISetDePruebas776976598.txt` incluido en el módulo

**Detecta automáticamente:**
- SET BÁSICO con 8 casos
- Número de atención: 4606904
- Casos 4606904-1 al 4606904-8
- Referencias entre documentos (NC → Factura, ND → NC)

## Limitaciones

- El proyecto debe estar en estado **Borrador**
- No puede tener casos existentes (debe eliminarlos primero)
- Solo importa el **SET BÁSICO** del archivo
- No importa SET LIBRO DE VENTAS ni SET LIBRO DE COMPRAS

## Ventajas vs Importación Manual

| Manual (Botón SET BÁSICO) | Desde Archivo SII |
|---------------------------|-------------------|
| Usa plantillas predefinidas | Usa TU archivo del SII |
| Número de atención genérico | Tu número de atención real |
| Valores estándar | Valores exactos del SII |

## Archivo de Ejemplo Incluido

El módulo incluye `SIISetDePruebas776976598.txt` como ejemplo para pruebas.

## Soporte

Para reportar errores o sugerencias, contacta al desarrollador.
