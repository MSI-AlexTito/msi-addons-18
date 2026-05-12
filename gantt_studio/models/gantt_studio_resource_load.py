"""Resource leveling + histogram engine (Sprint 3.4).

AbstractModel polimórfico que calcula utilización de recursos para
cualquier modelo destino, igual que el resto del core gantt_studio.

Diseño Community-friendly:
* El módulo `resource` es opcional en este AbstractModel: si no está
  instalado, devolvemos {} (la UI esconde la fila de histograma).
* La inferencia de "campo de recurso" se hace al runtime probando los
  field names más comunes (`user_ids`, `user_id`, `resource_id`,
  `employee_id`, `workcenter_id`). El integrador puede sobreescribir
  pasando `resource_field` explícito a `get_resource_histogram`.
* Capacity: si el recurso tiene un `resource_calendar_id`, usamos
  `_work_intervals_batch`. Si no, asumimos `default_capacity_hours_per_day`
  (configurable, defecto 8h) como horas laborales por día.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from odoo import api, fields, models


# Campos M2M / M2O candidatos en los modelos más comunes de Odoo.
# Probados en orden; el primero que exista en el modelo destino se usa.
_DEFAULT_RESOURCE_FIELD_CANDIDATES = (
    "user_ids", "user_id",
    "resource_id", "employee_id",
    "workcenter_id",
)


def _to_dt(value):
    """Convierte cualquier date-like a datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year"):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        s = value.strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _bucket_iter(start, stop, period):
    """Iterador de buckets [start_dt, end_dt) en períodos dados.

    period ∈ {'day', 'week', 'month'}.
    """
    cur = start
    while cur < stop:
        if period == "day":
            nxt = cur + timedelta(days=1)
        elif period == "week":
            nxt = cur + timedelta(days=7)
        elif period == "month":
            # Approx: 30 días para evitar relativedelta y dependencia
            nxt = cur + timedelta(days=30)
        else:
            nxt = cur + timedelta(days=1)
        yield cur, min(nxt, stop)
        cur = nxt


class GanttStudioResourceLoad(models.AbstractModel):
    """API polimórfica de carga de recursos para gantt_studio.

    Métodos pensados para ser invocados vía RPC desde el JS del renderer.
    Toda la lógica es agnóstica al modelo destino — solo necesita saber
    el nombre del campo recurso (lo infiere o lo recibe).
    """
    _name = "gantt.studio.resource_load"
    _description = "Gantt Studio Resource Load"

    # ── Helpers ───────────────────────────────────────────────────────

    def _detect_resource_field(self, res_model):
        """Adivina el field de recurso del modelo destino.

        Devuelve (field_name, field_descriptor) o (None, None) si nada
        de la lista de candidatos existe en el modelo.
        """
        Model = self.env[res_model]
        for candidate in _DEFAULT_RESOURCE_FIELD_CANDIDATES:
            if candidate in Model._fields:
                return candidate, Model._fields[candidate]
        return None, None

    def _resource_ids_of_record(self, record, field_name, field_desc):
        """Lista de ids res.users/res.partner/... que tiene `record` en su
        campo de recurso. Para M2M devuelve la lista de ids; para M2O,
        un singleton; si está vacío, [].
        """
        v = record[field_name]
        if not v:
            return []
        if field_desc.type == "many2one":
            return [v.id]
        # many2many / one2many
        return list(v.ids)

    def _resource_label(self, env, res_model_target, res_id):
        """Para mostrar en el histograma. Si el recurso es res.users,
        devolvemos su nombre; si es res.partner, su nombre; etc.
        """
        rec = env[res_model_target].browse(res_id).exists()
        return rec.display_name if rec else f"#{res_id}"

    # ── Capacity calculation ──────────────────────────────────────────

    def _default_daily_capacity_hours(self):
        """Horas laborales por día cuando no hay calendar.
        Configurable vía system parameter `gantt_studio.default_capacity_h`.
        """
        param = self.env["ir.config_parameter"].sudo().get_param(
            "gantt_studio.default_capacity_h", "8"
        )
        try:
            return float(param)
        except (TypeError, ValueError):
            return 8.0

    def _resource_capacity_hours(self, resource_record, bucket_start, bucket_end):
        """Capacidad (horas) del recurso en el bucket [bucket_start, bucket_end).

        Si el recurso es res.users (o res.partner) sin acceso a
        resource.calendar, retornamos el default daily * días del bucket.
        Si tiene resource_calendar_id (vía resource_id m2o), usamos
        `_work_intervals_batch`. La inferencia es defensiva — cualquier
        error silenciosamente cae al default.
        """
        default_h = self._default_daily_capacity_hours()
        days = max(1.0, (bucket_end - bucket_start).total_seconds() / 86400.0)

        # Intento 1: el record tiene resource_calendar_id directo
        calendar = None
        if "resource_calendar_id" in resource_record._fields:
            calendar = resource_record.resource_calendar_id
        elif "calendar_id" in resource_record._fields:
            calendar = resource_record.calendar_id

        if not calendar and "resource_ids" in resource_record._fields:
            # res.users / employees pueden tener uno via resource.resource
            res = resource_record.resource_ids[:1]
            if res and "calendar_id" in res._fields:
                calendar = res.calendar_id

        if calendar and "resource" in self.env.registry:
            try:
                # _work_intervals_batch firma: (start, stop, resources, ...)
                # devuelve dict por resource → intervals.
                if hasattr(calendar, "_work_intervals_batch"):
                    intervals_by_res = calendar._work_intervals_batch(
                        bucket_start, bucket_end,
                    )
                    # Sin filtrar por recurso específico (calendar global).
                    intervals = intervals_by_res.get(False, []) \
                        if False in intervals_by_res else \
                        next(iter(intervals_by_res.values()), [])
                    total_s = 0.0
                    for iv in intervals:
                        # Cada intervalo es típicamente (start, stop, ...)
                        # — tomamos los dos primeros campos.
                        if isinstance(iv, tuple) and len(iv) >= 2:
                            total_s += (iv[1] - iv[0]).total_seconds()
                    return total_s / 3600.0
            except Exception:
                pass

        # Fallback: días × default daily.
        return days * default_h

    def _record_allocated_hours(self, record, date_start_field, date_stop_field,
                                bucket_start, bucket_end):
        """Horas que `record` consume del recurso durante el bucket.

        Estrategia: prorrateamos la duración total del record en función
        de la intersección de su [start, stop] con el bucket. Si tiene
        N recursos asignados (M2M), las horas se DIVIDEN entre ellos
        (modelo simple, mejorable en v2 con allocation explícita).
        """
        ds = _to_dt(record[date_start_field])
        de = _to_dt(record[date_stop_field])
        if not ds or not de or de <= ds:
            return 0.0
        # Intersección con el bucket
        i_start = max(ds, bucket_start)
        i_end = min(de, bucket_end)
        if i_end <= i_start:
            return 0.0
        return (i_end - i_start).total_seconds() / 3600.0

    # ── RPC API ───────────────────────────────────────────────────────

    @api.model
    def get_resource_histogram(self, res_model, record_ids, date_from, date_to,
                               period="week", resource_field=None,
                               date_start_field=None, date_stop_field=None):
        """Devuelve la utilización de cada recurso en buckets.

        Args:
            res_model: nombre del modelo (e.g. 'project.task')
            record_ids: lista de ids a considerar
            date_from / date_to: strings ISO o Datetime
            period: 'day' | 'week' | 'month'
            resource_field: opcional, sobreescribe la detección automática
            date_start_field / date_stop_field: campos de fechas; obligatorios

        Returns:
            {
                'resource_field': <str|None>,
                'resource_model': <str|None>,   # modelo destino del field
                'period': <str>,
                'buckets': [
                    {'start': iso, 'stop': iso, 'label': 'YYYY-MM-DD'},
                    ...
                ],
                'resources': [
                    {
                        'id': <int>,
                        'label': <str>,
                        'data': [
                            {'allocated': <h>, 'capacity': <h>, 'ratio': <0-2.0>},
                            ...
                        ],
                    },
                    ...
                ],
            }

        Si el modelo no tiene un campo de recurso reconocible o
        date_*_field falta, devolvemos un payload "vacío" (la UI lo
        respeta y oculta la fila de histograma).
        """
        empty = {"resource_field": None, "resource_model": None,
                 "period": period, "buckets": [], "resources": []}
        if not date_start_field or not date_stop_field:
            return empty
        if not record_ids:
            return empty

        # Inferir campo si no se pasó.
        rfield_name = resource_field
        rfield_desc = None
        if rfield_name:
            rfield_desc = self.env[res_model]._fields.get(rfield_name)
        if not rfield_desc:
            rfield_name, rfield_desc = self._detect_resource_field(res_model)
        if not rfield_desc:
            return empty

        ResourceModel = self.env[rfield_desc.comodel_name]

        # Bucketización
        d_from = _to_dt(date_from)
        d_to = _to_dt(date_to)
        if not d_from or not d_to or d_to <= d_from:
            return empty
        buckets = [
            {"start": bs, "stop": be}
            for bs, be in _bucket_iter(d_from, d_to, period)
        ]
        if not buckets:
            return empty

        # Records y agrupado por recurso
        records = self.env[res_model].browse(record_ids).exists()
        records_by_resource = defaultdict(list)
        for r in records:
            for res_id in self._resource_ids_of_record(r, rfield_name, rfield_desc):
                records_by_resource[res_id].append(r)

        # Para cada recurso, calcular cada bucket
        resources_out = []
        for res_id in sorted(records_by_resource.keys()):
            resource_rec = ResourceModel.browse(res_id).exists()
            if not resource_rec:
                continue
            recs_here = records_by_resource[res_id]
            bucket_data = []
            for bucket in buckets:
                bs, be = bucket["start"], bucket["stop"]
                allocated = 0.0
                for r in recs_here:
                    # Si tiene N recursos asignados, dividimos las horas.
                    n_res = max(1, len(self._resource_ids_of_record(
                        r, rfield_name, rfield_desc)))
                    allocated += self._record_allocated_hours(
                        r, date_start_field, date_stop_field, bs, be
                    ) / n_res
                capacity = self._resource_capacity_hours(resource_rec, bs, be)
                ratio = (allocated / capacity) if capacity > 0 else 0.0
                bucket_data.append({
                    "allocated": round(allocated, 2),
                    "capacity": round(capacity, 2),
                    "ratio": round(ratio, 3),
                })
            resources_out.append({
                "id": res_id,
                "label": self._resource_label(self.env, rfield_desc.comodel_name, res_id),
                "data": bucket_data,
            })

        return {
            "resource_field": rfield_name,
            "resource_model": rfield_desc.comodel_name,
            "period": period,
            "buckets": [
                {"start": b["start"].isoformat(),
                 "stop": b["stop"].isoformat(),
                 "label": b["start"].strftime("%Y-%m-%d")}
                for b in buckets
            ],
            "resources": resources_out,
        }

    @api.model
    def detect_overallocations(self, res_model, record_ids,
                               date_start_field, date_stop_field,
                               resource_field=None, threshold=1.0):
        """Devuelve ids de records sobreasignados.

        Un record está sobreasignado si su recurso (al menos uno) tiene
        ratio > threshold en algún bucket que el record overlappea.

        Returns: list[int] de record ids.
        """
        if not record_ids:
            return []
        records = self.env[res_model].browse(record_ids).exists()
        # Bucketización al nivel diario para precisión
        starts = [_to_dt(r[date_start_field]) for r in records]
        stops = [_to_dt(r[date_stop_field]) for r in records]
        starts = [s for s in starts if s]
        stops = [s for s in stops if s]
        if not starts or not stops:
            return []
        global_from = min(starts)
        global_to = max(stops)
        histo = self.get_resource_histogram(
            res_model, record_ids,
            global_from.isoformat(), global_to.isoformat(),
            period="day",
            resource_field=resource_field,
            date_start_field=date_start_field,
            date_stop_field=date_stop_field,
        )
        if not histo["resources"]:
            return []

        # Lista de (bucket_start, bucket_stop) para mapear
        bucket_intervals = [
            (_to_dt(b["start"]), _to_dt(b["stop"]))
            for b in histo["buckets"]
        ]
        # Lookup ratio over-threshold por (resource_id, bucket_idx)
        over_buckets_by_res = defaultdict(set)
        for res in histo["resources"]:
            for i, data in enumerate(res["data"]):
                if data["ratio"] > threshold:
                    over_buckets_by_res[res["id"]].add(i)

        if not over_buckets_by_res:
            return []

        # Detectar campo resource (lo necesitamos para mapear record→resources)
        rfield_name = resource_field
        rfield_desc = None
        if rfield_name:
            rfield_desc = self.env[res_model]._fields.get(rfield_name)
        if not rfield_desc:
            rfield_name, rfield_desc = self._detect_resource_field(res_model)
        if not rfield_desc:
            return []

        result = []
        for r in records:
            r_start = _to_dt(r[date_start_field])
            r_stop = _to_dt(r[date_stop_field])
            if not r_start or not r_stop:
                continue
            res_ids = self._resource_ids_of_record(r, rfield_name, rfield_desc)
            for res_id in res_ids:
                over_set = over_buckets_by_res.get(res_id, set())
                if not over_set:
                    continue
                # ¿Algún bucket sobreasignado overlapea con este record?
                for i, (bs, be) in enumerate(bucket_intervals):
                    if i not in over_set:
                        continue
                    if r_stop <= bs or r_start >= be:
                        continue
                    result.append(r.id)
                    break
                else:
                    continue
                break
        return list(set(result))
