"""Export engine: MS Project XML 2003 (Sprint 3.6) + Excel xlsx (Sprint 3.9).

Modelo-agnóstico — recibe res_model + record_ids + field names y trabaja
sobre eso sin tocar el schema del modelo destino.

MS Project XML
--------------
- Tasks con UID/ID/Name/Start/Finish/Duration/OutlineLevel/WBS
- Predecessor links (FS/SS/FF/SF + lag)
- Resources + Assignments
- Limitación: Calendar no exportado (MS Project asume "Standard").

Excel (xlsx) — Sprint 3.9
--------------------------
- Hoja "Tasks": WBS | Nombre | Inicio | Fin | Duración (d) | Recursos |
  Predecesores | Avance %
- Hoja "Dependencies": Pred WBS | Sucesor WBS | Tipo | Lag (d)
- Usa xlsxwriter vía dependencia report_xlsx (maneja chars especiales).
- Devuelve base64; el cliente OWL descarga sin round-trip de ir.actions.report.
"""
import base64
from datetime import datetime
from io import BytesIO
from xml.dom.minidom import getDOMImplementation

from odoo import api, models


# MS Project XML predecessor types
MSP_PREDECESSOR_TYPES = {
    "FF": 0,
    "FS": 1,
    "SF": 2,
    "SS": 3,
}


def _to_dt(value):
    """Convert a date-like value to datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year") and not isinstance(value, str):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        s = value.strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _iso(dt):
    """ISO 8601 sin timezone — el formato que MS Project XML acepta."""
    if not dt:
        return ""
    if not isinstance(dt, datetime):
        dt = _to_dt(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else ""


def _duration_iso8601(seconds):
    """ISO 8601 duration string (PnYnMnDTnHnMnS) — formato MS Project.
    Para Gantt sólo usamos horas: PT<n>H<m>M<s>S.
    """
    s = int(max(0, seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"PT{h}H{m}M{sec}S"


class GanttStudioExport(models.AbstractModel):
    """Export engine para MS Project XML (Sprint 3.6).

    Métodos RPC pensados para ser invocados desde el JS controller —
    devuelve un string con el XML; el client se encarga de descargarlo
    como archivo.
    """
    _name = "gantt.studio.export"
    _description = "Gantt Studio Export"

    @api.model
    def export_msproject_xml(self, res_model, record_ids,
                             date_start_field, date_stop_field,
                             name_field="name", parent_field=None,
                             resource_field=None,
                             project_name="Exported from Gantt Studio"):
        """Generate MS Project 2003 XML for the given records.

        Args:
            res_model: e.g. 'project.task'
            record_ids: ids to export
            date_start_field: field name for Start
            date_stop_field: field name for Finish
            name_field: field for Task Name (default 'name')
            parent_field: optional WBS parent (e.g. 'parent_id')
            resource_field: optional M2M/M2O to resource (e.g. 'user_ids')
            project_name: header value

        Returns:
            str: XML document
        """
        if not record_ids:
            return self._build_empty_xml(project_name)

        Model = self.env[res_model]
        records = Model.browse(record_ids).exists()
        if not records:
            return self._build_empty_xml(project_name)

        # 1) Build dom skeleton
        impl = getDOMImplementation()
        doc = impl.createDocument(None, "Project", None)
        root = doc.documentElement
        root.setAttribute("xmlns", "http://schemas.microsoft.com/project")

        def el(parent, tag, text=None):
            e = doc.createElement(tag)
            if text is not None:
                e.appendChild(doc.createTextNode(str(text)))
            parent.appendChild(e)
            return e

        # Header
        el(root, "Name", project_name)
        el(root, "Title", project_name)
        el(root, "Author", self.env.user.name)
        el(root, "CreationDate", _iso(datetime.now()))
        el(root, "ScheduleFromStart", "1")
        # Project start = min(start) de records
        starts = [_to_dt(r[date_start_field]) for r in records if r[date_start_field]]
        if starts:
            el(root, "StartDate", _iso(min(starts)))
        stops = [_to_dt(r[date_stop_field]) for r in records if r[date_stop_field]]
        if stops:
            el(root, "FinishDate", _iso(max(stops)))

        # 2) Tasks
        tasks_el = el(root, "Tasks")
        # task UID 0 reservado por MS Project como project summary task
        task0 = el(tasks_el, "Task")
        el(task0, "UID", "0")
        el(task0, "ID", "0")
        el(task0, "Name", project_name)
        el(task0, "Summary", "1")

        # Asignamos UIDs incrementales secuenciales para ser
        # determinísticos. UID interno != id de Odoo.
        uid_by_odoo_id = {}
        for i, rec in enumerate(records, start=1):
            uid_by_odoo_id[rec.id] = i

        # WBS / outline calculation usando parent_field si se pasa
        depth_by_id = {}
        wbs_by_id = {}
        if parent_field and parent_field in Model._fields:
            # BFS desde records sin parent en el set
            in_set = set(uid_by_odoo_id.keys())
            children = {}
            roots = []
            for rec in records:
                pid = rec[parent_field]
                pid = pid.id if pid and hasattr(pid, "id") else (pid[0] if isinstance(pid, (list, tuple)) else pid)
                if not pid or pid not in in_set:
                    roots.append(rec.id)
                else:
                    children.setdefault(pid, []).append(rec.id)
            # asignar wbs codes
            def assign_wbs(rid, depth, code):
                depth_by_id[rid] = depth
                wbs_by_id[rid] = code
                for i, ch in enumerate(children.get(rid, []), start=1):
                    assign_wbs(ch, depth + 1, f"{code}.{i}")
            for i, rid in enumerate(roots, start=1):
                assign_wbs(rid, 0, str(i))
        else:
            # Sin jerarquía: todo outline level 1.
            for i, rec in enumerate(records, start=1):
                depth_by_id[rec.id] = 0
                wbs_by_id[rec.id] = str(i)

        for rec in records:
            task_el = el(tasks_el, "Task")
            el(task_el, "UID", uid_by_odoo_id[rec.id])
            el(task_el, "ID", uid_by_odoo_id[rec.id])
            el(task_el, "Name", rec[name_field] or f"#{rec.id}")
            el(task_el, "Active", "1")
            el(task_el, "Type", "1")          # Fixed Duration
            el(task_el, "IsNull", "0")
            el(task_el, "Manual", "0")
            el(task_el, "OutlineLevel", depth_by_id.get(rec.id, 0) + 1)
            el(task_el, "OutlineNumber", wbs_by_id.get(rec.id, ""))
            el(task_el, "WBS", wbs_by_id.get(rec.id, ""))
            ds = _to_dt(rec[date_start_field])
            de = _to_dt(rec[date_stop_field])
            if ds:
                el(task_el, "Start", _iso(ds))
            if de:
                el(task_el, "Finish", _iso(de))
            if ds and de:
                dur = (de - ds).total_seconds()
                el(task_el, "Duration", _duration_iso8601(dur))
                el(task_el, "DurationFormat", "7")    # hours

            # Predecessors via gantt.studio.dependency
            deps = self.env["gantt.studio.dependency"].search([
                ("res_model", "=", res_model),
                ("successor_id", "=", rec.id),
                ("predecessor_id", "in", list(uid_by_odoo_id.keys())),
            ])
            for d in deps:
                link = el(task_el, "PredecessorLink")
                el(link, "PredecessorUID", uid_by_odoo_id[d.predecessor_id])
                el(link, "Type", MSP_PREDECESSOR_TYPES.get(d.dep_type, 1))
                # Lag time: MS Project usa "tenths of minutes" para tipo 4
                # (elapsed). Usamos elapsed days expresado en minutos.
                lag_days = d.lag_days or 0.0
                if lag_days:
                    lag_minutes = int(round(lag_days * 24 * 60))
                    el(link, "LinkLag", lag_minutes)
                    el(link, "LagFormat", "5")    # minutes

        # 3) Resources
        resources_el = el(root, "Resources")
        # res 0 = "Unassigned" reservado por MSP
        rsrc0 = el(resources_el, "Resource")
        el(rsrc0, "UID", "0")
        el(rsrc0, "ID", "0")
        el(rsrc0, "Name", "Unassigned")
        el(rsrc0, "Type", "1")

        rsrc_uid_by_id = {}
        assignments = []
        if resource_field and resource_field in Model._fields:
            rf_desc = Model._fields[resource_field]
            collected = {}
            for rec in records:
                v = rec[resource_field]
                if not v:
                    continue
                ids = [v.id] if rf_desc.type == "many2one" else list(v.ids)
                for rid in ids:
                    if rid not in collected:
                        collected[rid] = self.env[rf_desc.comodel_name].browse(rid)
                    assignments.append((uid_by_odoo_id[rec.id], rid))
            for i, (rid, rrec) in enumerate(collected.items(), start=1):
                rsrc_uid_by_id[rid] = i
                rsrc_el = el(resources_el, "Resource")
                el(rsrc_el, "UID", i)
                el(rsrc_el, "ID", i)
                el(rsrc_el, "Name", (rrec.display_name or f"#{rid}") if rrec.exists() else f"#{rid}")
                el(rsrc_el, "Type", "1")

        # 4) Assignments
        assignments_el = el(root, "Assignments")
        for i, (task_uid, res_id) in enumerate(assignments, start=1):
            ass_el = el(assignments_el, "Assignment")
            el(ass_el, "UID", i)
            el(ass_el, "TaskUID", task_uid)
            el(ass_el, "ResourceUID", rsrc_uid_by_id.get(res_id, 0))
            el(ass_el, "Units", "1.0")

        return doc.toprettyxml(indent="  ")

    # ─── Sprint 3.9 — Excel Export ───────────────────────────────────

    @api.model
    def export_xlsx(self, res_model, record_ids,
                    date_start_field, date_stop_field,
                    name_field="name", parent_field=None,
                    resource_field=None, progress_field=None,
                    project_name="Gantt Studio"):
        """Generate an Excel workbook for the visible records and return
        the result as a base64-encoded string so the OWL client can
        download it directly without going through ir.actions.report.

        Columns: WBS | Name | Start | Finish | Duration (d) |
                 Resources | Predecessors | Progress %

        Depends on ``report_xlsx`` (OCA) which guarantees xlsxwriter is
        installed and handles special-character sanitisation for us.
        """
        import xlsxwriter  # guaranteed by report_xlsx dependency

        if not record_ids:
            return False

        Model = self.env[res_model]
        records = Model.browse(record_ids).exists()
        if not records:
            return False

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        # ── Formats ──────────────────────────────────────────────────
        hdr = workbook.add_format({
            "bold": True, "bg_color": "#1e40af", "font_color": "white",
            "border": 1, "text_wrap": True, "valign": "vcenter",
            "align": "center",
        })
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1})
        num_fmt  = workbook.add_format({"num_format": "0.0", "border": 1})
        cell_fmt = workbook.add_format({"border": 1})
        par_fmt  = workbook.add_format({
            "bold": True, "bg_color": "#f3f4f6", "border": 1,
        })

        # ── Tasks sheet ───────────────────────────────────────────────
        ws = workbook.add_worksheet("Tasks")
        cols = ["WBS", "Nombre", "Inicio", "Fin",
                "Duración (d)", "Recursos", "Predecesores", "Avance %"]
        widths = [8, 42, 12, 12, 12, 28, 22, 10]
        for i, (c, w) in enumerate(zip(cols, widths)):
            ws.set_column(i, i, w)
            ws.write(0, i, c, hdr)
        ws.freeze_panes(1, 0)
        ws.set_row(0, 24)

        # ── WBS calculation ───────────────────────────────────────────
        in_set = set(r.id for r in records)
        depth_by_id = {}
        wbs_by_id   = {}
        children_of = {}

        if parent_field and parent_field in Model._fields:
            roots = []
            for rec in records:
                pid = rec[parent_field]
                pid_val = pid.id if pid and hasattr(pid, "id") else None
                if not pid_val or pid_val not in in_set:
                    roots.append(rec.id)
                else:
                    children_of.setdefault(pid_val, []).append(rec.id)

            def _assign(rid, depth, code):
                depth_by_id[rid] = depth
                wbs_by_id[rid] = code
                for j, ch in enumerate(children_of.get(rid, []), start=1):
                    _assign(ch, depth + 1, f"{code}.{j}")

            for k, rid in enumerate(roots, start=1):
                _assign(rid, 0, str(k))
        else:
            for k, rec in enumerate(records, start=1):
                depth_by_id[rec.id] = 0
                wbs_by_id[rec.id]   = str(k)

        # ── Predecessors map ──────────────────────────────────────────
        deps_by_succ = {}
        dep_rows = []
        all_deps = self.env["gantt.studio.dependency"].search([
            ("res_model", "=", res_model),
            ("successor_id",   "in", list(in_set)),
            ("predecessor_id", "in", list(in_set)),
        ])
        for d in all_deps:
            pred_wbs = wbs_by_id.get(d.predecessor_id, "?")
            succ_wbs = wbs_by_id.get(d.successor_id,   "?")
            lag_str = (
                f"+{d.lag_days}d" if d.lag_days and d.lag_days > 0 else
                f"{d.lag_days}d" if d.lag_days and d.lag_days < 0 else ""
            )
            label = f"{pred_wbs}{d.dep_type}{lag_str}"
            deps_by_succ.setdefault(d.successor_id, []).append(label)
            dep_rows.append((pred_wbs, succ_wbs, d.dep_type, d.lag_days or 0))

        # ── Resource field descriptor ─────────────────────────────────
        rf_desc = Model._fields.get(resource_field) if resource_field else None

        # ── Write rows ────────────────────────────────────────────────
        for row_i, rec in enumerate(records, start=1):
            depth    = depth_by_id.get(rec.id, 0)
            wbs      = wbs_by_id.get(rec.id, str(row_i))
            is_par   = bool(children_of.get(rec.id))
            fmt      = par_fmt if is_par else cell_fmt

            ds = _to_dt(rec[date_start_field]) if rec[date_start_field] else None
            de = _to_dt(rec[date_stop_field])  if rec[date_stop_field]  else None
            dur_d = round((de - ds).total_seconds() / 86400, 1) if ds and de else None

            # Resources
            resources = ""
            if rf_desc and resource_field and rec[resource_field]:
                v = rec[resource_field]
                if rf_desc.type == "many2one":
                    resources = v.display_name or ""
                else:
                    resources = ", ".join(r.display_name for r in v if r.display_name)

            preds   = ", ".join(deps_by_succ.get(rec.id, []))
            indent  = "  " * depth
            name    = indent + (rec[name_field] or f"#{rec.id}")
            progress = ""
            if progress_field and progress_field in Model._fields:
                progress = rec[progress_field] or 0

            ws.write(row_i, 0, wbs,  fmt)
            ws.write(row_i, 1, name, fmt)
            if ds:
                ws.write_datetime(row_i, 2, ds, date_fmt)
            if de:
                ws.write_datetime(row_i, 3, de, date_fmt)
            if dur_d is not None:
                ws.write_number(row_i, 4, dur_d, num_fmt)
            ws.write(row_i, 5, resources, fmt)
            ws.write(row_i, 6, preds,     fmt)
            if progress != "":
                ws.write_number(row_i, 7, float(progress), num_fmt)
            else:
                ws.write(row_i, 7, "", fmt)

        # ── Dependencies sheet ────────────────────────────────────────
        if dep_rows:
            ws2 = workbook.add_worksheet("Dependencias")
            dep_cols = ["Pred WBS", "Sucesor WBS", "Tipo", "Lag (d)"]
            dep_widths = [12, 12, 8, 10]
            for i, (c, w) in enumerate(zip(dep_cols, dep_widths)):
                ws2.set_column(i, i, w)
                ws2.write(0, i, c, hdr)
            ws2.freeze_panes(1, 0)
            for row_i, (pw, sw, dt, lag) in enumerate(dep_rows, start=1):
                ws2.write(row_i, 0, pw,  cell_fmt)
                ws2.write(row_i, 1, sw,  cell_fmt)
                ws2.write(row_i, 2, dt,  cell_fmt)
                ws2.write_number(row_i, 3, lag, num_fmt)

        workbook.close()
        output.seek(0)
        return base64.b64encode(output.read()).decode()

    def _build_empty_xml(self, project_name):
        """Mínimo válido para que MS Project no rechace el archivo."""
        impl = getDOMImplementation()
        doc = impl.createDocument(None, "Project", None)
        root = doc.documentElement
        root.setAttribute("xmlns", "http://schemas.microsoft.com/project")
        n = doc.createElement("Name")
        n.appendChild(doc.createTextNode(project_name))
        root.appendChild(n)
        root.appendChild(doc.createElement("Tasks"))
        root.appendChild(doc.createElement("Resources"))
        root.appendChild(doc.createElement("Assignments"))
        return doc.toprettyxml(indent="  ")
