"""
Demo Gantt Studio — Proyecto de Construcción (Casa Demo)
=========================================================

Carga un proyecto realista en `project.project` con tareas en cadena para
demostrar TODAS las capacidades del módulo `gantt_studio`:

  1. Vista <gantt_studio> sobre `project.task`.
  2. Agrupado por etapas (stage_id).
  3. Color por responsable (user_ids).
  4. Dependencias tipadas FS / SS / FF / SF + lag.
  5. CPM (Critical Path Method) sobre la ruta crítica.
  6. Baseline activo (plan original) vs reales modificados (ghost bars).
  7. Auto-reschedule con cascada al arrastrar.
  8. Clamp bi-direccional si se intenta arrastrar contra un predecesor.
  9. Virtualización: el dataset tiene suficientes tareas para verla actuar.

Uso
---
    cd /Users/alexminjo/developer_msi/local-odoo/odoo18-server
    source venv-odoo18/bin/activate
    cat /Users/alexminjo/developer_msi/addons_odoo/odoo18/msi-addons-18/\
gantt_studio/examples/cargar_demo_construccion.py \
        | ./odoo-bin shell -c odoo18.conf -d faroco --no-http --stop-after-init

Al terminar imprime el ID del proyecto y de las tareas creadas, además del
nombre del menú al que navegar desde la UI.
"""

from datetime import datetime, timedelta

print("=" * 78)
print("  GANTT STUDIO — DEMO: Construcción Casa Demo")
print("=" * 78)

Project = env["project.project"]
Stage = env["project.task.type"]
Task = env["project.task"]
User = env["res.users"]
Dep = env["gantt.studio.dependency"]
Baseline = env["gantt.studio.baseline"]

# ─────────────────────────────────────────────────────────────────────────
# 1) Limpiar demo previa (idempotente)
# ─────────────────────────────────────────────────────────────────────────
prev = Project.search([("name", "=", "Construcción Casa Demo (Gantt Studio)")])
if prev:
    print(f"  ⚠️  Limpiando demo previa (project id={prev.id})...")
    # Soltar dependencias del modelo polimórfico que tocan tareas viejas
    old_task_ids = prev.task_ids.ids
    if old_task_ids:
        Dep.search([
            ("res_model", "=", "project.task"),
            "|",
            ("predecessor_id", "in", old_task_ids),
            ("successor_id", "in", old_task_ids),
        ]).unlink()
    # Soltar baselines viejos del proyecto demo
    old_baselines = Baseline.search([("res_model", "=", "project.task")])
    if old_baselines:
        # Filtrar solo los que tengan líneas hacia tareas de la demo previa
        for b in old_baselines:
            if any(l.record_id in old_task_ids for l in b.line_ids):
                b.unlink()
    prev.task_ids.unlink()
    prev.unlink()
    print(f"  ✓ Limpieza completa.")

# ─────────────────────────────────────────────────────────────────────────
# 2) Etapas (stages)
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Creando etapas del proyecto…")

def _ensure_stage(name, seq):
    s = Stage.search([("name", "=", name)], limit=1)
    if not s:
        s = Stage.create({"name": name, "sequence": seq})
    return s

stage_design   = _ensure_stage("01 Diseño",        10)
stage_permits  = _ensure_stage("02 Permisos",      20)
stage_found    = _ensure_stage("03 Cimentación",   30)
stage_struct   = _ensure_stage("04 Estructura",    40)
stage_mep      = _ensure_stage("05 Instalaciones", 50)
stage_finish   = _ensure_stage("06 Terminaciones", 60)
stage_handover = _ensure_stage("07 Entrega",       70)

print(f"  ✓ 7 etapas listas.")

# ─────────────────────────────────────────────────────────────────────────
# 3) Equipo (usuarios) — usamos los ya existentes para evitar inflar la BD
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Asignando equipo…")
team = User.search([("share", "=", False), ("active", "=", True)], limit=5)
if not team:
    raise RuntimeError("No hay usuarios internos en esta BD para asignar.")
print(f"  ✓ Equipo de {len(team)} miembros: {', '.join(team.mapped('name'))}")

def assign(idx):
    """Asigna ciclicamente del equipo."""
    return [(6, 0, [team[idx % len(team)].id])]

# ─────────────────────────────────────────────────────────────────────────
# 4) Proyecto
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Creando proyecto…")
project = Project.create({
    "name": "Construcción Casa Demo (Gantt Studio)",
})
print(f"  ✓ Proyecto id={project.id}")

# ─────────────────────────────────────────────────────────────────────────
# 5) Tareas — calendarizadas para que las dependencias sean BINDING
#    (es decir, terminen quedando exactamente "encadenadas" sin huecos),
#    así el CPM marca varias tareas y deps como críticas.
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Creando tareas (24 en total)…")

# Fecha base: hoy + 10 días. Trabajamos en horas laborales 08:00-17:00.
BASE = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=10)

def D(days_from_base, hours=8):
    return BASE + timedelta(days=days_from_base, hours=hours - 8)

def mktask(name, start_day, dur_days, stage, idx, progress=0):
    return Task.create({
        "name": name,
        "project_id": project.id,
        "stage_id": stage.id,
        "user_ids": assign(idx),
        "planned_date_begin": D(start_day, 8),
        "date_deadline": D(start_day + dur_days, 17),
    })

# Sprint 3.3 — WBS: creamos 7 PADRES (uno por fase) con fechas amplias
# y las 24 tareas detalladas como hijos. El renderer las muestra indentadas
# y el padre como "summary bar" envolviendo el rango de hijos.

def mkparent(name, start_day, end_day, stage, idx):
    return Task.create({
        "name": name,
        "project_id": project.id,
        "stage_id": stage.id,
        "user_ids": assign(idx),
        "planned_date_begin": D(start_day, 8),
        "date_deadline": D(end_day, 17),
    })

def mkchild(name, start_day, dur_days, stage, idx, parent):
    return Task.create({
        "name": name,
        "project_id": project.id,
        "stage_id": stage.id,
        "parent_id": parent.id,
        "user_ids": assign(idx),
        "planned_date_begin": D(start_day, 8),
        "date_deadline": D(start_day + dur_days, 17),
    })

# Padres
phase_design   = mkparent("FASE Diseño",        0,  13, stage_design,   0)
phase_permits  = mkparent("FASE Permisos",      14, 21, stage_permits,  1)
phase_found    = mkparent("FASE Cimentación",   22, 36, stage_found,    2)
phase_struct   = mkparent("FASE Estructura",    37, 55, stage_struct,   3)
phase_mep      = mkparent("FASE Instalaciones", 56, 62, stage_mep,      4)
phase_finish   = mkparent("FASE Terminaciones", 63, 89, stage_finish,   0)
phase_handover = mkparent("FASE Entrega",       90, 93, stage_handover, 1)

# ── FASE 1: DISEÑO (paralelo entre arquitectura e ingeniería) ────────
t01 = mkchild("01 Levantamiento topográfico", 0, 3, stage_design, 0, phase_design)
t02 = mkchild("02 Anteproyecto arquitectónico", 3, 6, stage_design, 1, phase_design)
t03 = mkchild("03 Proyecto eléctrico", 9, 4, stage_design, 2, phase_design)
t04 = mkchild("04 Proyecto sanitario", 9, 4, stage_design, 3, phase_design)
t05 = mkchild("05 Proyecto estructural", 9, 5, stage_design, 4, phase_design)

# ── FASE 2: PERMISOS ─────────────────────────────────────────────────
t06 = mkchild("06 Permiso municipal de edificación", 14, 8, stage_permits, 0, phase_permits)
t07 = mkchild("07 Aprobación servicios sanitarios", 14, 6, stage_permits, 1, phase_permits)

# ── FASE 3: CIMENTACIÓN ──────────────────────────────────────────────
t08 = mkchild("08 Despeje de terreno y movimientos", 22, 3, stage_found, 2, phase_found)
t09 = mkchild("09 Excavación y zanjas", 25, 4, stage_found, 3, phase_found)
t10 = mkchild("10 Armado de fierros (fundación)", 29, 5, stage_found, 4, phase_found)
t11 = mkchild("11 Hormigonado cimientos", 34, 3, stage_found, 0, phase_found)

# ── FASE 4: ESTRUCTURA ───────────────────────────────────────────────
t12 = mkchild("12 Pilares y vigas planta baja", 37, 6, stage_struct, 1, phase_struct)
t13 = mkchild("13 Losa primer piso", 43, 4, stage_struct, 2, phase_struct)
t14 = mkchild("14 Pilares planta alta", 47, 5, stage_struct, 3, phase_struct)
t15 = mkchild("15 Losa cubierta", 52, 4, stage_struct, 4, phase_struct)

# ── FASE 5: INSTALACIONES (paralelo) ─────────────────────────────────
t16 = mkchild("16 Tendido eléctrico interior", 56, 6, stage_mep, 0, phase_mep)
t17 = mkchild("17 Cañerías agua + alcantarillado", 56, 7, stage_mep, 1, phase_mep)
t18 = mkchild("18 Climatización", 58, 5, stage_mep, 2, phase_mep)

# ── FASE 6: TERMINACIONES ────────────────────────────────────────────
t19 = mkchild("19 Albañilería interior (tabiques)", 63, 8, stage_finish, 3, phase_finish)
t20 = mkchild("20 Estucos y enlucidos", 71, 6, stage_finish, 4, phase_finish)
t21 = mkchild("21 Cerámicos y pavimentos", 77, 7, stage_finish, 0, phase_finish)
t22 = mkchild("22 Pintura interior y exterior", 84, 6, stage_finish, 1, phase_finish)

# ── FASE 7: ENTREGA ──────────────────────────────────────────────────
t23 = mkchild("23 Limpieza final y aseo de obra", 90, 2, stage_handover, 2, phase_handover)
t24 = mkchild("24 Recepción municipal y entrega", 92, 2, stage_handover, 3, phase_handover)

all_tasks = (
    phase_design | phase_permits | phase_found | phase_struct
    | phase_mep | phase_finish | phase_handover
    | t01 | t02 | t03 | t04 | t05 | t06 | t07 | t08 | t09 | t10
    | t11 | t12 | t13 | t14 | t15 | t16 | t17 | t18 | t19 | t20
    | t21 | t22 | t23 | t24
)
print(f"  ✓ {len(all_tasks)} tareas creadas (7 padres + 24 hijos, ids {all_tasks[0].id}..{all_tasks[-1].id}).")

# ─────────────────────────────────────────────────────────────────────────
# 6) Dependencias — los 4 tipos para demostrar visualmente
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Creando dependencias (FS / SS / FF / SF + lag)…")

def link(p, s, t="FS", lag=0.0, comment=""):
    Dep.link("project.task", p.id, s.id, t, lag)
    tag = f"{t}{'+' if lag > 0 else ''}{lag:g}d" if lag else t
    print(f"  • {p.name[:35]:35} → {s.name[:35]:35} [{tag}] {comment}")

# Cadena principal (FS, secuencial)
link(t01, t02, "FS", 0, "  topo terminada → empieza anteproyecto")
link(t02, t03, "FS", 0)
link(t02, t04, "FS", 0)
link(t02, t05, "FS", 0)

# SS: permisos arrancan EN PARALELO con la entrega del estructural
link(t05, t06, "SS", 2.0, "  ▲ SS+2d: el permiso arranca 2 días después de iniciar estructural")

# FS estándar (cadena de permisos → obra)
link(t06, t08, "FS", 0)
link(t07, t08, "FS", 0)

# FS encadenado en cimentación + estructura
link(t08, t09, "FS", 0)
link(t09, t10, "FS", 0)
link(t10, t11, "FS", 0)
link(t11, t12, "FS", 0)
link(t12, t13, "FS", 0)
link(t13, t14, "FS", 0)
link(t14, t15, "FS", 0)

# Instalaciones empiezan tras losa cubierta
link(t15, t16, "FS", 0)
link(t15, t17, "FS", 0)
link(t15, t18, "FS", 0)

# FF: climatización debe TERMINAR cuando termina cañería sanitaria
link(t17, t18, "FF", 0, "  ▲ FF: climatización debe terminar a la par que sanitaria")

# Albañilería tras las instalaciones (lag negativo = arranca antes que termine MEP)
link(t16, t19, "FS", -1.0, "  ▲ FS-1d: tabiques arrancan 1 día ANTES de que termine eléctrico (lead time)")

# Cadena de terminaciones
link(t19, t20, "FS", 0)
link(t20, t21, "FS", 0)
link(t21, t22, "FS", 0)

# Entrega
link(t22, t23, "FS", 0)
link(t23, t24, "FS", 0)

# SF (Start-to-Finish, el menos frecuente de los 4 tipos).
# Semánticamente: "el sucesor TERMINA cuando el predecesor EMPIEZA".
# Caso típico: relevos de turno, donde un turno antiguo debe estar concluido
# justo cuando el nuevo empieza. En construcción no hay un caso natural sin
# inducir ciclos en la cadena principal, así que lo aplicamos al par de
# tareas paralelas del diseño: el proyecto sanitario (t04) debe quedar
# CERRADO cuando arranca el permiso de servicios sanitarios (t07).
#   pred = t07 (empieza permiso) → succ = t04 (cierra sanitario)
# OJO: el módulo soporta los 4 tipos (lo prueban los tests), aquí solo
# elegimos UN ejemplo cuya semántica sea legible.
link(t07, t04, "SF", 0, "  ▲ SF: sanitario debe quedar terminado cuando arranca el trámite")

print(f"  ✓ Dependencias creadas (FS encadenadas + 1 SS + 1 FF + 1 SF + 1 FS con lag negativo).")

# ─────────────────────────────────────────────────────────────────────────
# 7) Baseline — capturar el plan original y activarlo
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Capturando BASELINE (plan original)…")
bid = Baseline.snapshot(
    "project.task", all_tasks.ids,
    "planned_date_begin", "date_deadline",
    name="Plan original Casa Demo",
)
baseline = Baseline.browse(bid)
baseline.action_activate()
print(f"  ✓ Baseline id={bid} ACTIVO. Se verá como barras 'fantasma' punteadas detrás.")

# ─────────────────────────────────────────────────────────────────────────
# 8) Desviación real — corremos algunas tareas para que el ghost se vea
# ─────────────────────────────────────────────────────────────────────────
print("\n→ Simulando desviación real (cimentación atrasada 4 días)…")
# La excavación se atrasa 4 días — propagamos en cascada usando el planner.
Planner = env["gantt.studio.planner"]
new_start = (D(29, 8)).strftime("%Y-%m-%d %H:%M:%S")   # antes era día 25
res = Planner.reschedule_with_dependencies(
    "project.task", t09.id, new_start,
    "planned_date_begin", "date_deadline", cascade=True,
)
print(f"  ✓ {len(res['updates'])} tareas movidas en cascada por el atraso.")
print(f"     Ahora 09 y siguientes están DESPUÉS del baseline → ghost bars visibles.")

# ─────────────────────────────────────────────────────────────────────────
# 9) Resumen + cómo navegar a la vista
# ─────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
print("  RESULTADO")
print("=" * 78)
print(f"  Proyecto:        '{project.name}' (id={project.id})")
print(f"  Tareas creadas:  {len(all_tasks)}")
print(f"  Dependencias:    {Dep.search_count([('res_model','=','project.task'), '|', ('predecessor_id','in',all_tasks.ids), ('successor_id','in',all_tasks.ids)])}")
print(f"  Baseline activo: id={bid} ('{baseline.name}')")
print()
print("  CÓMO ABRIR LA VISTA")
print("  -------------------")
print("  Menú → Proyecto → Gantt Studio Demo")
print(f"  (filtrar por proyecto '{project.name}' si tienes otros datos)")
print()
print("  Si conoces el ID, puedes ir directo a la URL:")
db = env.cr.dbname
print(f"    http://localhost:8069/odoo/action-gantt_studio.action_project_task_gantt_studio_demo")
print()
print("=" * 78)
print("  QUÉ MIRAR EN LA VISTA — ver README en examples/")
print("=" * 78)

# IMPORTANTE: `odoo-bin shell` lee desde stdin y NO commitea al salir.
# Si no llamamos commit aquí, el proyecto + tareas + deps + baseline se
# pierden cuando el shell termine. Si corres esto desde dentro de un shell
# interactivo, este commit es inofensivo (idempotente).
env.cr.commit()
print("\n  ✓ Cambios commiteados a la base de datos.")

