"""Planning algorithms (CPM, auto-reschedule) exposed as a stateless model."""

from collections import defaultdict, deque
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _to_dt(value):
    """Convert any date-like value to a Python datetime (or None).

    Accepts: None, datetime, date, and ISO strings (with or without time,
    "T" or space separator). Returns None for anything unparseable.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    # Date field → datetime at 00:00
    if hasattr(value, "year") and hasattr(value, "month") and not isinstance(value, str):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        s = value.strip().replace("T", " ")
        # Try common formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


class GanttStudioPlanner(models.AbstractModel):
    """Stateless planner used from JS for CPM and dependency-aware drag.

    Living in an AbstractModel keeps these algorithms unit-testable and
    exposed via RPC without bloating ir.ui.view or the dependency model.
    """

    _name = "gantt.studio.planner"
    _description = "Gantt Studio Planner"

    # ----------------------------------------------------------------------
    # Critical Path Method (CPM)
    # ----------------------------------------------------------------------

    @api.model
    def compute_critical_path(self, res_model, record_ids, date_start_field, date_stop_field):
        """Return record_ids on the critical path AND critical dependency IDs.

        Classic Critical Path Method:
          1. Forward pass: compute Earliest Start / Finish (ES, EF)
             from a virtual project start = min(date_start) of all records.
          2. Backward pass: compute Latest Start / Finish (LS, LF)
             from a virtual project end = max(date_stop) of all records.
          3. Slack = LS - ES (in seconds). A record is critical when slack == 0.
          4. A dependency is critical iff both its endpoints are critical AND
             the predecessor's EF + lag equals the successor's ES (no float).
        """
        if not record_ids:
            return {"critical_record_ids": [], "critical_dependency_ids": []}

        Records = self.env[res_model].browse(record_ids).exists()
        if not Records:
            return {"critical_record_ids": [], "critical_dependency_ids": []}

        # 1. Snapshot of dates as dicts
        nodes = {}
        for r in Records:
            ds = _to_dt(r[date_start_field])
            de = _to_dt(r[date_stop_field])
            if not ds or not de:
                continue
            nodes[r.id] = {"start": ds, "stop": de, "duration": (de - ds).total_seconds()}

        if not nodes:
            return {"critical_record_ids": [], "critical_dependency_ids": []}

        # 2. Pull dependencies among these records
        deps = self.env["gantt.studio.dependency"].search_read(
            [
                ("res_model", "=", res_model),
                ("predecessor_id", "in", list(nodes.keys())),
                ("successor_id", "in", list(nodes.keys())),
            ],
            ["id", "predecessor_id", "successor_id", "dep_type", "lag_days"],
        )

        # Build adjacency: successors and predecessors per node
        succ = defaultdict(list)  # node → list of (other_id, dep, dep_type, lag_seconds)
        pred = defaultdict(list)
        for d in deps:
            lag = (d["lag_days"] or 0.0) * 86400.0
            succ[d["predecessor_id"]].append((d["successor_id"], d["id"], d["dep_type"], lag))
            pred[d["successor_id"]].append((d["predecessor_id"], d["id"], d["dep_type"], lag))

        # 3. Forward pass — topological order via Kahn
        in_degree = {n: len(pred[n]) for n in nodes}
        topo = []
        q = deque([n for n, deg in in_degree.items() if deg == 0])
        while q:
            n = q.popleft()
            topo.append(n)
            for (m, _did, _dt, _lag) in succ[n]:
                in_degree[m] -= 1
                if in_degree[m] == 0:
                    q.append(m)
        if len(topo) != len(nodes):
            # Cycle detected — fall back to "no critical path"
            return {
                "critical_record_ids": [],
                "critical_dependency_ids": [],
                "error": "cycle_detected",
            }

        # ES / EF — start from declared dates (anchored to the plan)
        es = {n: nodes[n]["start"] for n in topo}
        ef = {n: nodes[n]["stop"] for n in topo}
        for n in topo:
            for (p, _did, dt, lag) in pred[n]:
                # Earliest the successor n can start, given predecessor p
                lag_td = timedelta(seconds=lag)
                if dt == "FS":
                    candidate_start = ef[p] + lag_td
                elif dt == "SS":
                    candidate_start = es[p] + lag_td
                elif dt == "FF":
                    candidate_finish = ef[p] + lag_td
                    candidate_start = candidate_finish - timedelta(seconds=nodes[n]["duration"])
                elif dt == "SF":
                    candidate_finish = es[p] + lag_td
                    candidate_start = candidate_finish - timedelta(seconds=nodes[n]["duration"])
                else:
                    continue
                if candidate_start > es[n]:
                    es[n] = candidate_start
                    ef[n] = candidate_start + timedelta(seconds=nodes[n]["duration"])

        # 4. Backward pass
        project_end = max(ef.values())
        ls = {n: ef[n] - timedelta(seconds=nodes[n]["duration"]) for n in topo}
        lf = {n: ef[n] for n in topo}
        # Initialize sinks (no successors) at project_end
        for n in topo:
            if not succ[n]:
                lf[n] = project_end
                ls[n] = lf[n] - timedelta(seconds=nodes[n]["duration"])
        # Walk in reverse topo
        for n in reversed(topo):
            for (s, _did, dt, lag) in succ[n]:
                lag_td = timedelta(seconds=lag)
                if dt == "FS":
                    candidate_finish = ls[s] - lag_td
                elif dt == "SS":
                    candidate_start = ls[s] - lag_td
                    candidate_finish = candidate_start + timedelta(seconds=nodes[n]["duration"])
                elif dt == "FF":
                    candidate_finish = lf[s] - lag_td
                elif dt == "SF":
                    candidate_start = lf[s] - lag_td
                    candidate_finish = candidate_start + timedelta(seconds=nodes[n]["duration"])
                else:
                    continue
                if candidate_finish < lf[n]:
                    lf[n] = candidate_finish
                    ls[n] = lf[n] - timedelta(seconds=nodes[n]["duration"])

        # 5. Slack & critical detection
        EPSILON = 1.0  # seconds
        critical_records = set()
        for n in topo:
            slack = (ls[n] - es[n]).total_seconds()
            if abs(slack) <= EPSILON:
                critical_records.add(n)

        # 6. Critical dependencies — both endpoints critical AND no float
        critical_deps = set()
        for d in deps:
            p, s, dt, lag = d["predecessor_id"], d["successor_id"], d["dep_type"], (d["lag_days"] or 0) * 86400
            if p not in critical_records or s not in critical_records:
                continue
            lag_td = timedelta(seconds=lag)
            if dt == "FS" and abs((es[s] - (ef[p] + lag_td)).total_seconds()) <= EPSILON:
                critical_deps.add(d["id"])
            elif dt == "SS" and abs((es[s] - (es[p] + lag_td)).total_seconds()) <= EPSILON:
                critical_deps.add(d["id"])
            elif dt == "FF" and abs((ef[s] - (ef[p] + lag_td)).total_seconds()) <= EPSILON:
                critical_deps.add(d["id"])
            elif dt == "SF" and abs((ef[s] - (es[p] + lag_td)).total_seconds()) <= EPSILON:
                critical_deps.add(d["id"])

        return {
            "critical_record_ids": sorted(critical_records),
            "critical_dependency_ids": sorted(critical_deps),
        }

    # ----------------------------------------------------------------------
    # Auto-reschedule on drag (cascades through dependencies)
    # ----------------------------------------------------------------------

    def _earliest_start_from_predecessors(
        self, res_model, record_id, date_start_field, date_stop_field, duration,
        date_overrides=None,
    ):
        """Return the earliest start datetime allowed for `record_id` given
        every INCOMING dependency (FS, SS, FF, SF + lag). Returns None when
        the record has no incoming deps.

        `date_overrides` is an optional mapping {record_id: (start_dt, stop_dt)}
        which lets the caller use *pending* dates (e.g. mid-cascade) instead
        of the database snapshot.
        """
        deps = self.env["gantt.studio.dependency"].search_read(
            [("res_model", "=", res_model), ("successor_id", "=", record_id)],
            ["predecessor_id", "dep_type", "lag_days"],
        )
        if not deps:
            return None
        earliest = None
        for d in deps:
            pid = d["predecessor_id"]
            if date_overrides and pid in date_overrides:
                ps, pe = date_overrides[pid]
            else:
                p_rec = self.env[res_model].browse(pid)
                ps = _to_dt(p_rec[date_start_field])
                pe = _to_dt(p_rec[date_stop_field])
            if not ps or not pe:
                continue
            lag = timedelta(days=d["lag_days"] or 0)
            dt = d["dep_type"]
            if dt == "FS":
                candidate = pe + lag
            elif dt == "SS":
                candidate = ps + lag
            elif dt == "FF":
                candidate = (pe + lag) - duration
            elif dt == "SF":
                candidate = (ps + lag) - duration
            else:
                continue
            if earliest is None or candidate > earliest:
                earliest = candidate
        return earliest

    @api.model
    def reschedule_with_dependencies(
        self, res_model, record_id, new_start, date_start_field, date_stop_field, cascade=True,
    ):
        """Move record_id's start to new_start (preserving duration), then
        cascade dependents respecting FS/SS/FF/SF + lag.

        BI-DIRECTIONAL VALIDATION: if the requested `new_start` would violate
        an INCOMING dependency (i.e. the user tried to drag a successor
        before its predecessor allows), we CLAMP `new_start` to the earliest
        valid date. The response includes a `constrained: True` flag so the
        client can notify the user that the drag was limited.

        Returns:
            {
                "updates":     [{id, date_start, date_stop}, ...],
                "constrained": bool,
                "constraint_reason": str | None,
            }
        """
        record = self.env[res_model].browse(record_id)
        if not record.exists():
            raise UserError(_("Record not found: %s/%s", res_model, record_id))

        requested_start = _to_dt(new_start)
        if not requested_start:
            raise UserError(_("Invalid new start: %s", new_start))

        current_start = _to_dt(record[date_start_field])
        current_stop = _to_dt(record[date_stop_field])
        if not current_start or not current_stop:
            duration = timedelta(days=1)
        else:
            duration = current_stop - current_start

        # Bi-directional constraint check on the dragged record
        earliest = self._earliest_start_from_predecessors(
            res_model, record_id, date_start_field, date_stop_field, duration,
        )
        constrained = False
        constraint_reason = None
        if earliest is not None and requested_start < earliest:
            constrained = True
            constraint_reason = (
                _("This task can't start before %(date)s due to a predecessor dependency."
                  , date=earliest.strftime("%Y-%m-%d %H:%M"))
            )
            new_start_dt = earliest
        else:
            new_start_dt = requested_start

        new_stop = new_start_dt + duration
        updates = {record_id: (new_start_dt, new_stop)}

        if cascade:
            # BFS through successors (forward propagation)
            visited = {record_id}
            queue = deque([record_id])
            while queue:
                cur = queue.popleft()
                deps = self.env["gantt.studio.dependency"].search_read(
                    [("res_model", "=", res_model), ("predecessor_id", "=", cur)],
                    ["successor_id", "dep_type", "lag_days"],
                )
                cur_start, cur_stop = updates[cur]
                for d in deps:
                    sid = d["successor_id"]
                    if sid in visited:
                        continue
                    visited.add(sid)
                    s_rec = self.env[res_model].browse(sid)
                    s_start = _to_dt(s_rec[date_start_field])
                    s_stop = _to_dt(s_rec[date_stop_field])
                    if not s_start or not s_stop:
                        continue
                    s_dur = s_stop - s_start
                    lag = timedelta(days=d["lag_days"] or 0)
                    dt = d["dep_type"]
                    if dt == "FS":
                        candidate_start = cur_stop + lag
                    elif dt == "SS":
                        candidate_start = cur_start + lag
                    elif dt == "FF":
                        candidate_start = (cur_stop + lag) - s_dur
                    elif dt == "SF":
                        candidate_start = (cur_start + lag) - s_dur
                    else:
                        continue
                    # Only push the successor LATER if needed — never pull it
                    # earlier than its current date (keeps the plan stable).
                    if candidate_start > s_start:
                        updates[sid] = (candidate_start, candidate_start + s_dur)
                        queue.append(sid)

        # Apply all writes
        for rid, (ns, ne) in updates.items():
            self.env[res_model].browse(rid).write({
                date_start_field: ns,
                date_stop_field: ne,
            })

        return {
            "updates": [
                {"id": rid, "date_start": ns.isoformat(sep=" "), "date_stop": ne.isoformat(sep=" ")}
                for rid, (ns, ne) in updates.items()
            ],
            "constrained": constrained,
            "constraint_reason": constraint_reason,
        }
