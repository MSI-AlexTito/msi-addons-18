# Gantt Studio — Ejemplo de prueba (Construcción Casa Demo)

Este ejemplo carga un proyecto realista de obra civil con **24 tareas en 7 etapas**, los **4 tipos de dependencias** (FS / SS / FF / SF), **lag positivo y negativo**, un **baseline activo** y una **desviación real simulada** (cimentación atrasada 4 días que se propagó en cascada). Sirve para validar de un vistazo todas las integraciones del módulo.

---

## 1. Cómo cargar la demo

Desde una terminal:

```bash
cd /Users/alexminjo/developer_msi/local-odoo/odoo18-server
source venv-odoo18/bin/activate

# (Si la base no tiene gantt_studio instalado todavía)
./odoo-bin -c odoo18.conf -d faroco --http-port=8079 --no-http \
    --stop-after-init -i gantt_studio

# Cargar la demo
cat /Users/alexminjo/developer_msi/addons_odoo/odoo18/msi-addons-18/\
gantt_studio/examples/cargar_demo_construccion.py \
    | ./odoo-bin shell -c odoo18.conf -d faroco --http-port=8079 \
                       --no-http --stop-after-init
```

> **Nota**: el `--http-port=8079` es solo por si tienes otra instancia de Odoo corriendo en `:8069` (típicamente la que usas en el navegador). Con `--no-http` no levanta servidor, simplemente evita la colisión de chequeo de puerto.

El script es **idempotente**: si lo corres dos veces, borra la demo anterior antes de crear la nueva. No toca otros proyectos.

---

## 2. Cómo abrir la vista

En el navegador, una vez logueado en `faroco`:

1. **Menú → Proyecto → Gantt Studio Demo**
2. Filtra/agrupa o ya verás directamente las 24 tareas (la demo es el dataset más grande del proyecto).

URL directa (si conoces tu sesión):

```
http://localhost:8069/odoo/action-gantt_studio_project.action_project_task_gantt_studio_demo
```

---

## 3. Qué deberías ver — recorrido feature por feature

### 3.1 Vista `<gantt_studio>` operativa

El módulo declara la vista demo así (`views/gantt_studio_views.xml`):

```xml
<gantt_studio date_start="planned_date_begin"
              date_stop="date_deadline"
              default_scale="week"
              default_group_by="stage_id"
              color_field="user_ids"
              bar_text="name"
              string="Gantt Studio (Tareas)">
    <field name="name"/>
    <field name="user_ids"/>
    <field name="stage_id"/>
    <field name="project_id"/>
    <field name="priority"/>
</gantt_studio>
```

Al abrir la vista deberías ver:

- Cabecera con escalas **Day / Week / Month / Quarter / Year** (botones arriba a la izquierda).
- Filas agrupadas por las 7 etapas (Diseño → Permisos → Cimentación → Estructura → Instalaciones → Terminaciones → Entrega).
- Barras coloreadas por responsable (los 2 usuarios internos de la BD se alternan).
- Botones extra: **Critical Path**, **Save Baseline**, **Export PDF**.

### 3.2 Dependencias tipadas (FS / SS / FF / SF + lag)

Después de cargar la demo, hay **25 dependencias** que cubren los 4 tipos:

| Tipo | Cuántas | Significado | Dónde verlo |
|---|---|---|---|
| **FS** (Finish → Start) | 22 | El sucesor empieza cuando el predecesor termina | Toda la cadena principal de la obra |
| **SS+2d** (Start → Start con lag 2 días) | 1 | El permiso municipal arranca 2 días después de iniciar el proyecto estructural | Etapa 02 → Etapa 02 |
| **FF** (Finish → Finish) | 1 | Climatización debe terminar a la par que la cañería sanitaria | Cañería → Climatización |
| **SF** (Start → Finish) | 1 | Proyecto sanitario debe estar cerrado al arrancar el trámite | Aprobación → Proyecto sanitario |
| **FS-1d** (FS con lead time) | 1 | Tabiques arrancan **1 día antes** de que termine el tendido eléctrico (solape controlado) | Eléctrico → Albañilería |

Visualmente, las dependencias se ven como **flechas grises** entre las barras. Hay 4 caminos por barra (left/right de origen × left/right de destino) según el tipo.

### 3.3 CPM — Ruta crítica

Pulsa el botón **`⚡ Critical Path`**. Deberías ver:

- **21 tareas** se vuelven **rojas con sombra roja pulsante** (cadena: 01→02→05→06→07→08→09→10→11→12→13→14→15→16→17→19→20→21→22→23→24).
- Las **flechas de las dependencias críticas** se vuelven rojas y gruesas.
- Las 3 tareas que **no** quedan rojas son las que tienen holgura (`slack > 0`): 03 (Proyecto eléctrico), 04 (Proyecto sanitario), 18 (Climatización).

Pulsa el botón otra vez para apagar el resaltado.

### 3.4 Baseline + ghost bars (plan vs real)

Cuando se cargó la demo, se hizo lo siguiente:

1. Se tomó un **snapshot** (`Baseline id=N`, "Plan original Casa Demo") con las fechas planificadas originales.
2. Se **activó** ese baseline (sólo uno puede estar activo a la vez por modelo).
3. Se simuló un **atraso de 4 días** moviendo la tarea **09 Excavación y zanjas** hacia adelante, y el `gantt.studio.planner` propagó el cambio a las 16 tareas siguientes.

Resultado visible en la vista:

- Detrás de cada barra "real" hay una **silueta punteada gris** = la fecha del baseline.
- En las 16 tareas movidas, el contorno punteado queda **a la izquierda** de la barra real → el plan original está antes que la realidad → se ve cuánto se atrasó cada una.

Para crear otro baseline desde la UI: pulsa **`📑 Save Baseline`**. El nuevo se activa solo (los anteriores se desactivan automáticamente).

### 3.5 Drag con auto-reschedule + clamp bi-direccional

Prueba:

1. **Arrastrar la tarea 09 hacia la derecha** (más al futuro). Al soltar, las tareas 10, 11, 12... se mueven en cascada para mantener las dependencias.
2. **Intentar arrastrar la tarea 13 hacia atrás (al pasado), antes de que termine la 12**. El módulo detecta la violación, **clampa** el movimiento a la fecha mínima permitida y muestra una notificación amarilla *"Move constrained by dependency"*.
3. **Click sobre una barra** (sin arrastrar): abre el formulario del registro.

Si tienes la consola del navegador abierta, ejecuta `window.GANTT_STUDIO_DEBUG = true` para ver logs detallados de los eventos de drag.

### 3.6 Virtualización (SVG)

24 tareas no son suficientes para forzar la virtualización, pero **la lógica está activa**: solo se emiten nodos DOM para las filas cuya banda vertical intersecta el viewport (+ buffer del 30%). Para verlo en acción puedes:

```python
# Desde odoo-shell, multiplicar las tareas demo a 500:
project = env.ref(...)  # tu proyecto demo
plantillas = list(project.task_ids)
for i in range(20):
    for t in plantillas:
        t.copy({"name": f"{t.name} [clon {i}]"})
env.cr.commit()
```

Abre la vista; al hacer scroll vertical verás los logs de re-render solo cuando entran nuevas filas al rango visible. El renderer (`gantt_studio_renderer.js`) usa **`useVirtualGrid`** de `@web/core/virtual_grid_hook` (Community-compatible).

### 3.7 Export PDF

Pulsa **`📄 Export PDF`**: rasteriza el SVG actual con `<canvas>` a 2× DPI, lo trocea en hojas A4 horizontal y abre el diálogo de impresión del navegador. Puedes "Imprimir → Guardar como PDF" desde ahí.

---

## 4. Cómo limpiar la demo

```bash
cd /Users/alexminjo/developer_msi/local-odoo/odoo18-server
source venv-odoo18/bin/activate

cat <<'EOF' | ./odoo-bin shell -c odoo18.conf -d faroco --http-port=8079 --no-http --stop-after-init
Project = env["project.project"]
prev = Project.search([("name", "=", "Construcción Casa Demo (Gantt Studio)")])
if prev:
    Dep = env["gantt.studio.dependency"]
    tids = prev.task_ids.ids
    Dep.search([("res_model", "=", "project.task"),
                "|", ("predecessor_id", "in", tids), ("successor_id", "in", tids)]).unlink()
    for b in env["gantt.studio.baseline"].search([("res_model", "=", "project.task")]):
        if any(l.record_id in tids for l in b.line_ids):
            b.unlink()
    prev.task_ids.unlink()
    prev.unlink()
    env.cr.commit()
    print("✓ Demo eliminada.")
else:
    print("(nada que limpiar)")
EOF
```

---

## 5. Mapa rápido de integraciones probadas en esta demo

| Integración | Comprobado en | Botón / acción UI |
|---|---|---|
| Vista `<gantt_studio>` registrada | Carga del módulo | Menú → Proyecto → Gantt Studio Demo |
| `default_group_by="stage_id"` | Filas agrupadas por etapa | — |
| `color_field="user_ids"` | Barras coloreadas por responsable | — |
| Modelo polimórfico de deps tipadas | 25 dependencias en 4 tipos | flechas grises |
| CPM completo con ciclos | `gantt.studio.planner.compute_critical_path` | botón **Critical Path** |
| Auto-reschedule cascade | `gantt.studio.planner.reschedule_with_dependencies` | drag horizontal |
| Clamp bi-direccional | Mismo método con flag `constrained` | drag hacia atrás contra pred |
| Baseline snapshot + activate | `gantt.studio.baseline.snapshot / action_activate` | botón **Save Baseline** |
| Ghost bars (plan vs real) | `gantt.studio.baseline.get_active_lines` | render silueta punteada |
| Virtualización SVG | `useVirtualGrid` de `@web/core` | scroll vertical |
| Dirty-flag rendering | `onWillRender` + `_diffProps` en renderer | invisible (perfórmance) |
| Export PDF | `gantt_studio_pdf_export.js` | botón **Export PDF** |
| Validación de arch | `_validate_tag_gantt_studio` en `ir_ui_view.py` | error al guardar arch inválido |
| Tipo `gantt_studio` en selecciones | `ir.ui.view.type`, `act_window.view.view_mode` | dropdown en debug Studio |

---

## 6. Si algo falla

- **No aparece el menú "Gantt Studio Demo"**: el módulo no se instaló (revisa `--test-tags gantt_studio` para asegurar tests OK).
- **La vista carga vacía**: el dominio del action filtra registros con ambas fechas (`planned_date_begin` y `date_deadline`). Asegúrate de que las 24 tareas tengan ambas. La demo las crea con ambas siempre.
- **CPM dice "cycle_detected"**: hay un ciclo en las dependencias. Esto es deliberado del algoritmo (rechaza ciclos en vez de loopear). Revisa cuál dependencia es contradictoria. La demo está diseñada para NO tener ciclos.
- **Ghost bars no aparecen**: no hay baseline activo o se activó después de la desviación. Revisa con `env["gantt.studio.baseline"].search([("is_active","=",True),("res_model","=","project.task")])`.

---

## 7. Próximos pasos

Sprint 3.1 que viene agregará: decorations condicionales, milestones, date picker "ir a fecha", atajos de teclado y `display_unavailability` con calendario laboral. Cada feature tendrá su propia demo dentro de este mismo proyecto Casa Demo, así puedes comparar antes / después con el mismo set de tareas.
