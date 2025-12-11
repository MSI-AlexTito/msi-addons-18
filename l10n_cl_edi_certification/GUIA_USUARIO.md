# Guía de Usuario - Módulo de Certificación SII

## 📋 Propósito del PDF417

El **código de barras PDF417** es **OBLIGATORIO** en las representaciones impresas de los DTEs según la normativa del SII.

### ¿Para qué sirve?

1. **Validación Offline**: Permite verificar la autenticidad del documento sin internet
2. **Contiene el TED**: Codifica el Timbre Electrónico del Documento que incluye:
   - RUT emisor y receptor
   - Tipo y folio del documento
   - Fecha de emisión
   - Monto total
   - Firma digital

3. **Requisito de Certificación**: El SII valida que el PDF417:
   - Esté presente en el PDF
   - Contenga la información correcta
   - Sea legible con lectores estándar

### Dónde aparece

- En el PDF impreso de cada factura/nota/guía
- Usualmente en la parte inferior del documento
- Se genera automáticamente al crear cada DTE

---

## 🔐 Certificado Digital

### Obtención del Certificado

El certificado digital **NO se crea en Odoo**, lo proporciona:
- La empresa que se va a certificar
- Debe ser emitido por una entidad certificadora autorizada por el SII
- Formato: `.pfx` o `.p12`
- Incluye clave privada y certificado público

### Cómo usar el certificado en el módulo

1. **Al crear el proyecto**, en la pestaña "Información del Cliente"
2. Cargar el archivo `.pfx` o `.p12`
3. El sistema pedirá la contraseña (se encripta automáticamente)
4. Usar botón "Probar Certificado" para validar

---

## 📊 SET BÁSICO de Certificación (3660207)

El módulo incluye los **8 casos oficiales** del SET BÁSICO del SII:

### Casos Incluidos

| Código | Tipo | Descripción |
|--------|------|-------------|
| 3660207-1 | Factura 33 | 2 items afectos |
| 3660207-2 | Factura 33 | Con descuentos por item (7% y 16%) |
| 3660207-3 | Factura 33 | Items afectos + servicio exento |
| 3660207-4 | Factura 33 | Items mixtos + descuento global 16% |
| 3660207-5 | NC 56 | Corrige giro del receptor |
| 3660207-6 | NC 56 | Devolución parcial de mercadería |
| 3660207-7 | NC 56 | Anula factura completa |
| 3660207-8 | ND 61 | Anula nota de crédito |

### Indicaciones Importantes (del SII)

1. **Separador de miles**: Usar punto (.) en las cifras
2. **Descuentos**: Deben indicarse claramente en representaciones impresas
3. **Giro**: No usar abreviaciones, no agregar textos de contratos
4. **Documentos requeridos**: Incluir ejemplar tributario y cedible

---

## 🚀 Flujo de Uso

### 1. Preparación

```
1. Obtener de la empresa cliente:
   - RUT, Razón Social, Giro (sin abreviaciones)
   - Dirección completa
   - Certificado digital (.pfx/.p12) + contraseña
   - CAF (Código de Autorización de Folios) del SII para cada tipo de documento

2. Verificar en "Mi SII" del cliente:
   - Datos tributarios actualizados
   - Sucursales y direcciones
   - Actividad económica (ACTECO)
```

### 2. Crear Proyecto

```
Certificación SII → Proyectos → Crear

1. Nombre: "Certificación [Empresa] 2024"
2. Cliente: Seleccionar partner
3. Fecha inicio y vencimiento
4. Guardar
```

### 3. Configurar Cliente

```
Pestaña "Información del Cliente" → Crear/Editar

1. Datos Tributarios:
   - RUT (formato: 12345678-9)
   - Razón Social (completa, sin abreviaciones)
   - Giro (sin abreviaciones)
   - Código ACTECO

2. Ubicación:
   - Dirección completa
   - Ciudad/Comuna
   - Región

3. Certificado Digital:
   - Cargar archivo .pfx/.p12
   - Ingresar contraseña (se encripta)
   - Clic en "Probar Certificado"

4. Ambiente:
   - Seleccionar "Certificación (maullin.sii.cl)"

5. Guardar
```

### 4. Asignar Folios

```
Pestaña "Folios Asignados" → Agregar línea

Para cada tipo de documento:
1. Tipo de Documento: Factura (33), NC (56), ND (61)
2. CAF: Seleccionar CAF cargado previamente
3. Folio Inicio: Primer número del rango
4. Folio Fin: Último número del rango
5. Guardar
```

### 5. Agregar Casos de Prueba

```
Opción A - Usar SET BÁSICO predefinido:
   Pestaña "Casos de Prueba" → Agregar caso existente
   - Buscar "3660207" para ver los 8 casos
   - Seleccionar todos los casos del SET BÁSICO

Opción B - Crear caso personalizado:
   Crear nuevo → Completar datos manualmente
```

### 6. Iniciar Proyecto

```
Botón "Iniciar" en el header

El sistema valida:
- Información del cliente completa
- Al menos un caso de prueba
- Folios asignados para tipos de documento

Estado cambia a: "En Progreso"
```

### 7. Generar Documentos

```
Botón "Generar Documentos"

Wizard:
1. Seleccionar casos a generar (o todos)
2. Opciones:
   - Validar localmente: ✓ (recomendado)
   - Enviar automáticamente a SII: ☐ (opcional)
3. Generar

El sistema:
- Asigna folios automáticamente
- Genera XML de cada DTE
- Calcula montos (neto, IVA, total)
- Genera TED y PDF417
- Firma digitalmente
- Valida contra esquema XSD
```

### 8. Revisar y Validar

```
Ver documentos generados:
1. Clic en "X Documentos" (smart button)
2. Revisar cada documento:
   - Estado: "Generado" o "Validado"
   - Montos correctos
   - Folio asignado
3. Descargar XML si necesario
```

### 9. Crear Sobre de Envío

```
Pestaña "Sobres de Envío" → Crear

1. Nombre: "Envío SET BÁSICO 3660207"
2. Agregar documentos:
   - Seleccionar todos los documentos generados
3. Acciones:
   - "Crear Sobre" (genera EnvioDTE XML)
   - "Firmar Sobre" (firma digital)
   - "Validar Sobre" (valida esquema)
```

### 10. Enviar al SII

```
Desde el sobre:
1. Botón "Enviar a SII"
2. Sistema:
   - Autentica con SII (obtiene token)
   - Envía EnvioDTE
   - Recibe Track ID
3. Estado cambia a "Enviado"
```

### 11. Consultar Estado

```
Botón "Consultar Estado en SII"

El sistema consulta y actualiza:
- Estado actual (Recibido/En Validación/Aceptado/Rechazado)
- Mensajes del SII
- Errores o reparos (si los hay)

Repetir hasta que estado sea "Aceptado"
```

### 12. Completar Certificación

```
Cuando TODOS los casos estén aceptados:
1. Estado del proyecto: "En Validación"
2. Botón "Completar"
3. Generar reporte PDF final
4. Entregar al cliente
```

---

## ⚠️ Errores Comunes

### Error: "Token inválido"
**Solución**: El certificado puede estar vencido o la contraseña incorrecta. Verificar con "Probar Certificado".

### Error: "Folio fuera de rango"
**Solución**: Verificar que los folios en CAF coincidan con los asignados en el proyecto.

### Error: "Schema validation failed"
**Solución**: Revisar datos del caso (RUT, montos, etc.). Todos los montos deben ser enteros (sin decimales).

### Error: "Firma digital inválida"
**Solución**: Certificado corrupto o contraseña incorrecta. Recargar certificado.

### Estado: "Rechazado por SII"
**Solución**: Ver mensajes de error en "Respuestas SII". Corregir datos y reenviar.

---

## 📧 Soporte

Para consultas sobre el proceso de certificación:
- SII: https://www.sii.cl
- Sección: Factura Electrónica → Certificación
- Centro de ayuda SII: 223951028

---

## 📝 Notas Importantes

1. **Ambiente de Certificación**: Usar siempre `maullin.sii.cl` hasta aprobar
2. **Producción**: Solo cambiar a `palena.sii.cl` cuando SII apruebe certificación
3. **Backup**: Guardar todos los XMLs y respuestas del SII
4. **Tiempo**: El proceso de certificación puede tomar varios días
5. **Documentación**: El SII puede pedir documentación adicional del cliente

---

## ✅ Checklist de Certificación

- [ ] Empresa cliente registrada con datos completos
- [ ] Certificado digital cargado y probado
- [ ] CAF obtenidos del SII para todos los tipos de documento
- [ ] 8 casos del SET BÁSICO agregados al proyecto
- [ ] Folios asignados correctamente
- [ ] Documentos generados y validados localmente
- [ ] Sobre creado, firmado y validado
- [ ] Sobre enviado al SII (ambiente certificación)
- [ ] Track ID recibido
- [ ] Estado consultado y "Aceptado" para todos
- [ ] Proyecto marcado como "Completado"
- [ ] Reporte PDF generado y entregado
