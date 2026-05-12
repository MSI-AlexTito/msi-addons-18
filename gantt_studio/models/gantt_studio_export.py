"""Export to MS Project XML 2003 schema (Sprint 3.6).

Generates a MS Project compatible XML document for the records visible
in a Gantt Studio view. Includes:
  * Tasks (UID, ID, Name, Start, Finish, Duration, OutlineLevel, WBS)
  * Predecessor links (FS/SS/FF/SF + lag days)
  * Resources (basic Name + UID)
  * Assignments (TaskUID → ResourceUID)

Modelo-agnóstico, igual que el resto del core gantt_studio. Recibe
`res_model + record_ids + field names` y trabaja sobre eso.

Limitaciones conocidas
----------------------
- WBS code: deriva de outline position (1, 1.1, 1.2, 2, 2.1...). MS
  Project lo acepta pero algunos importadores prefieren codes custom.
- Calendar: no exportado todavía (MS Project asume "Standard" si falta).
- Earned value / cost / base calendar: omitidos (MVP).

El consumidor del XML típico es MS Project Desktop "File > Open" que
acepta XML 2003 schema directamente.
"""
from datetime import datetime, timedelta
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
