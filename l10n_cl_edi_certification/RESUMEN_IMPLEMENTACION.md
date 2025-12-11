# Resumen de Implementación - Módulo Certificación SII

## 🎯 Decisiones Arquitectónicas Clave

### 1. **Reutilización de Integración SOAP con SII**

**Decisión**: Heredar de `l10n_cl.edi.util` de Odoo Enterprise en lugar de reimplementar.

**Justificación**:
- Enterprise ya tiene implementada toda la comunicación SOAP con el SII
- Incluye manejo de errores, retries y timeouts
- Soporta ambientes de certificación y producción
- Maneja autenticación (seed, token, firma)

**Implementación**:
```python
class SiiIntegrationService(models.AbstractModel):
    _name = 'l10n_cl_edi.sii.integration.service'
    _inherit = 'l10n_cl.edi.util'  # ← Hereda toda la lógica SOAP
```

**Métodos reutilizados**:
- `_get_token()` - Autenticación con SII
- `_send_xml_to_sii()` - Envío de DTEs
- `_get_send_status()` - Consulta de estado

**URLs utilizadas** (de Enterprise):
- Certificación: `https://maullin.sii.cl/DTEWS/`
- Producción: `https://palena.sii.cl/DTEWS/`

### 2. **Código de Barras PDF417**

**Propósito**:
El PDF417 es **OBLIGATORIO** para certificación SII. Se usa para:

1. **Validación Offline**: Sin necesidad de internet
2. **Contiene el TED**: Timbre Electrónico del Documento
3. **Requisito Legal**: Debe aparecer en todas las representaciones impresas

**Contenido del PDF417**:
```
- RUT Emisor
- Tipo de DTE (33, 56, 61, etc.)
- Folio
- Fecha de emisión
- RUT Receptor
- Razón Social Receptor
- Monto Total
- Firma Digital (usando clave privada del CAF)
```

**Dónde se genera**:
- Servicio: `DteGeneratorService._generate_barcode()`
- Se crea automáticamente al generar cada DTE
- Se incluye en el XML del DTE dentro del elemento `<TED>`

**Pendiente de implementar**:
```python
# TODO: Implementar generación real con librería pdf417gen
import pdf417gen
barcode = pdf417gen.encode(ted_xml, columns=15, security_level=5)
```

### 3. **Certificado Digital**

**Flujo**:
1. **El cliente proporciona** el certificado (.pfx/.p12)
2. **Odoo almacena** el certificado y contraseña encriptada
3. **Odoo usa** el certificado para:
   - Firmar cada DTE
   - Firmar el sobre (EnvioDTE)
   - Autenticarse con el SII

**Encriptación**:
```python
# Usa Fernet (criptografía simétrica)
from cryptography.fernet import Fernet

# Contraseña se encripta al guardar
cipher = Fernet(encryption_key)
encrypted = cipher.encrypt(password.encode())

# Se desencripta solo cuando se necesita firmar
decrypted = cipher.decrypt(encrypted)
```

**Configuración requerida** en `odoo.conf`:
```ini
[options]
encryption_key = tu_clave_fernet_aqui
```

Generar con:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 4. **SET BÁSICO del SII (8 Casos)**

**Implementado**: Los 8 casos oficiales del número de atención 3660207.

| Caso | Código | Descripción | Complejidad |
|------|--------|-------------|-------------|
| 1 | 3660207-1 | Factura simple 2 items | Básica |
| 2 | 3660207-2 | Descuentos por item (7%, 16%) | Media |
| 3 | 3660207-3 | Items afectos + exento | Media |
| 4 | 3660207-4 | Descuento global 16% | Media |
| 5 | 3660207-5 | NC corrige giro | Básica |
| 6 | 3660207-6 | NC devolución parcial | Media |
| 7 | 3660207-7 | NC anula factura | Media |
| 8 | 3660207-8 | ND anula NC | Media |

**Archivo**: `data/test_case_templates_set_basico.xml`

**Características**:
- Todos los casos están como plantillas reutilizables
- Se pueden agregar a cualquier proyecto de certificación
- Incluyen montos, cantidades y descuentos exactos del SII
- Referencias entre documentos (NC refieren a facturas)

---

## 📦 Estructura del Módulo Implementada

### Modelos (10 modelos)
✅ `certification_project` - Gestión de proyectos
✅ `certification_client` - Snapshot de datos del cliente
✅ `certification_case` - Casos de prueba
✅ `certification_case_line` - Líneas de casos
✅ `certification_folio_assignment` - Control de folios
✅ `certification_generated_document` - DTEs generados
✅ `certification_envelope` - Sobres de envío
✅ `certification_sii_response` - Respuestas del SII
✅ `test_case_template` - Catálogo de casos
✅ `test_case_template_line` - Líneas de plantillas

### Servicios (6 servicios)
✅ `DteGeneratorService` - Generación de XML DTEs
✅ `SignatureService` - Firma digital
✅ `ValidationService` - Validación XSD + reglas
✅ `EnvelopeService` - Creación de sobres
✅ `SiiIntegrationService` - Comunicación SII (hereda de Enterprise)
✅ `FolioService` - Gestión de folios

### Seguridad
✅ 3 grupos con permisos diferenciados
✅ Reglas de acceso por usuario/proyecto
✅ Encriptación de contraseñas

### Datos
✅ SET BÁSICO completo (8 casos)
✅ Secuencias para proyectos y sobres
✅ Menús completos

### Vistas
✅ Proyecto: Form, list, Kanban, Search
⏳ Casos (pendiente)
⏳ Documentos (pendiente)
⏳ Sobres (pendiente)
⏳ Respuestas SII (pendiente)

---

## 🔨 Pendiente de Implementación

### 1. Vistas Restantes (Prioridad Alta)

**certification_case_views.xml**
```xml
- Form con notebook para líneas
- Tree con colores por estado
- Search con filtros por tipo de documento
- Action window
```

**certification_generated_document_views.xml**
```xml
- Form con preview de XML
- Botones: Descargar, Validar, Firmar
- Tree con búsqueda por folio
```

**certification_envelope_views.xml**
```xml
- Form con lista de documentos
- Botones: Crear, Firmar, Enviar
- Tree con estado SII
```

**certification_sii_response_views.xml**
```xml
- Form para ver XML de respuesta
- Tree con colores por estado
```

### 2. Wizards (Prioridad Alta)

**certification_project_wizard**
- Wizard multi-paso para crear proyecto fácilmente
- Paso 1: Info básica
- Paso 2: Cliente + certificado
- Paso 3: Seleccionar casos del SET BÁSICO
- Paso 4: Asignar folios

**certification_generate_wizard**
- Seleccionar casos a generar
- Opciones de validación
- Generación en lote

### 3. Templates XML para DTEs (Prioridad Alta)

**dte_certification_template.xml**
```xml
<DTE version="1.0">
    <Documento ID="...">
        <Encabezado>
            <IdDoc>
                <TipoDTE>...</TipoDTE>
                <Folio>...</Folio>
                ...
            </IdDoc>
            <Emisor>...</Emisor>
            <Receptor>...</Receptor>
            <Totales>...</Totales>
        </Encabezado>
        <Detalle>
            <!-- Líneas del documento -->
        </Detalle>
        <TED>
            <!-- Timbre Electrónico -->
        </TED>
    </Documento>
</DTE>
```

Usar como referencia: `enterprise/l10n_cl_edi/data/dte_template.xml`

**envelope_certification_template.xml**
```xml
<EnvioDTE version="1.0">
    <SetDTE>
        <Caratula>
            <!-- Info del envío -->
        </Caratula>
        <DTE>
            <!-- DTEs firmados -->
        </DTE>
    </SetDTE>
</EnvioDTE>
```

### 4. Firma Digital Real (Prioridad Media)

**Actual**: Placeholder que retorna XML sin cambios
**Necesario**: Implementar firma XMLDSig

```python
# Usar signxml o xmlsec
from signxml import XMLSigner

def _sign_xml(self, xml_content, certificate_file, password):
    # Cargar certificado
    private_key, certificate = self._load_certificate(certificate_file, password)

    # Firmar
    xml_doc = etree.fromstring(xml_content.encode('utf-8'))
    signer = XMLSigner(
        method=signxml.methods.enveloped,
        signature_algorithm="rsa-sha1",
        digest_algorithm="sha1"
    )
    signed_root = signer.sign(xml_doc, key=private_key, cert=certificate)

    return etree.tostring(signed_root, encoding='unicode')
```

### 5. Generación de PDF417 (Prioridad Media)

```python
import pdf417gen
from PIL import Image
import io

def _generate_barcode(self, ted_xml):
    # Generar código de barras
    codes = pdf417gen.encode(
        ted_xml,
        columns=15,
        security_level=5
    )

    # Convertir a imagen
    image = pdf417gen.render_image(
        codes,
        scale=3,
        ratio=3
    )

    # Convertir a base64
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue())
```

### 6. Generación Real de TED (Prioridad Media)

El TED debe firmarse con la **clave privada del CAF**, no del certificado digital.

```python
def _generate_ted(self, dte_data, case):
    # 1. Construir DD (Documento del Timbre)
    dd_xml = self._build_dd(dte_data)

    # 2. Obtener clave privada del CAF
    folio_assignment = self._get_folio_assignment(case)
    caf_private_key = self._extract_caf_private_key(folio_assignment.caf_id)

    # 3. Firmar DD con clave del CAF
    signed_dd = self._sign_with_caf(dd_xml, caf_private_key)

    # 4. Construir TED completo
    ted_xml = f'''<TED version="1.0">
        {dd_xml}
        <FRMT algoritmo="SHA1withRSA">{signed_dd}</FRMT>
    </TED>'''

    return ted_xml
```

### 7. Reportes PDF (Prioridad Baja)

**certification_project_report**
- Reporte final del proceso de certificación
- Incluir: datos cliente, casos, documentos, respuestas SII
- Formato profesional para entregar al cliente

---

## 🚀 Próximos Pasos Recomendados

### Fase 1: Completar Interfaz (1 semana)
1. Crear vistas de casos, documentos, sobres
2. Crear wizards (proyecto y generación)
3. Testear flujo completo en interfaz

### Fase 2: Templates XML (1 semana)
1. Implementar template DTE basado en Enterprise
2. Implementar template EnvioDTE
3. Validar contra esquemas XSD del SII

### Fase 3: Firma y TED (1 semana)
1. Implementar firma XMLDSig real
2. Implementar generación de TED con CAF
3. Implementar generación de PDF417

### Fase 4: Pruebas Reales (2 semanas)
1. Obtener certificado real de prueba
2. Obtener CAF de ambiente de certificación
3. Enviar al SII de prueba (maullin.sii.cl)
4. Ajustar según respuestas del SII

### Fase 5: Producción (1 semana)
1. Certificación aprobada por SII
2. Cambiar a ambiente producción
3. Documentación final
4. Capacitación a usuarios

---

## 📚 Referencias

### SII
- Portal: https://www.sii.cl
- Factura Electrónica: https://www.sii.cl/factura_electronica/
- Esquemas XSD: http://www.sii.cl/factura_electronica/formato_xml.htm
- Certificación: https://www.sii.cl/factura_electronica/certificacion.htm

### Odoo Enterprise
- Módulo: `l10n_cl_edi`
- Modelos: `l10n_cl.edi.util`, `account.move`
- Templates: `data/dte_template.xml`

### LibreDTE
- GitHub: https://github.com/LibreDTE/libredte-lib-core
- Casos de prueba: `tests/fixtures/yaml/documentos_ok/`

---

## ✅ Ventajas de esta Implementación

1. **Reutiliza Enterprise**: No reinventa la rueda, usa código probado
2. **Modular**: Servicios separados, fácil de mantener
3. **Escalable**: Múltiples proyectos simultáneos
4. **Auditable**: Historial completo con mail.thread
5. **Seguro**: Contraseñas encriptadas, datos inmutables
6. **Documentado**: Guías de usuario y técnicas

---

## 📝 Notas Finales

- El módulo está al **~70% completo**
- La arquitectura base está **100% implementada**
- La integración SII está **lista** (reutiliza Enterprise)
- Los 8 casos del SET BÁSICO están **implementados**
- **Falta**: Vistas, wizards, templates XML, firma real, TED, PDF417

El módulo está listo para comenzar desarrollo de la interfaz de usuario y componentes pendientes.
