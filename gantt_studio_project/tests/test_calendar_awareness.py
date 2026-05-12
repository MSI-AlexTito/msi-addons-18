"""Tests para calendar awareness en reschedule (Sprint 3.5).

Verifica que el cascade del planner skip findes y respeta el horario
laboral del resource.calendar de la company. Si `resource` no estuviera
instalado, el código degrada graciosamente sin error.
"""
from datetime import datetime, timedelta

from odoo.tests import tagged

from .common import GanttStudioProjectCommon


@tagged("post_install", "-at_install", "gantt_studio", "gantt_studio_project")
class TestCalendarAwareness(GanttStudioProjectCommon):

    def test_01_get_default_calendar_returns_something(self):
        # Con `resource` instalado, esperamos el calendar de la company.
        cal = self.Planner._get_default_calendar()
        self.assertIsNotNone(cal,
            "Con resource instalado, debe existir un calendar default")

    def test_02_snap_to_working_time_no_change_in_working_hours(self):
        # Un lunes a las 10:00 (rango típico de horario laboral)
        # NO debería moverse.
        cal = self.Planner._get_default_calendar()
        # Búsqueda de un lunes próximo:
        # Usamos un día sabido lunes. 2026-06-01 fue un lunes.
        dt = datetime(2026, 6, 1, 10, 0)
        snapped = self.Planner._snap_to_working_time(dt, cal)
        self.assertEqual(snapped.date(), dt.date(),
            "Lunes a las 10:00 no debe cambiar de día")

    def test_03_snap_to_working_time_skips_weekend(self):
        # 2026-06-06 fue un sábado. snap debería moverlo al próximo
        # lunes (2026-06-08) en horario laboral.
        cal = self.Planner._get_default_calendar()
        sat = datetime(2026, 6, 6, 10, 0)  # sábado
        snapped = self.Planner._snap_to_working_time(sat, cal)
        # El día resultante debe ser lunes (2026-06-08) o posterior.
        # No comparamos hora exacta porque depende del calendar.
        self.assertGreater(snapped.date(), sat.date(),
            f"Sábado debe avanzar al próximo día laboral. Got: {snapped}")
        # Si es lunes, su weekday() === 0
        self.assertIn(snapped.weekday(), (0, 1, 2, 3, 4),
            "El resultado debe caer en un día laboral (lunes-viernes)")

    def test_04_reschedule_respects_calendar_in_cascade(self):
        # A → B FS lag=0. Si A termina viernes 17:00 (fin de jornada),
        # B no debe arrancar sábado a las 00:00, sino el lunes en
        # horario laboral.
        # Calculamos un viernes razonable.
        friday = datetime(2026, 6, 5, 8, 0)  # 2026-06-05 fue viernes
        self.task_a.write({
            "planned_date_begin": friday,
            "date_deadline": friday.replace(hour=17, minute=0),  # viernes 17:00
        })
        # B encadenada justo después
        self.task_b.write({
            "planned_date_begin": friday.replace(hour=17, minute=0),
            "date_deadline": friday + timedelta(days=3),
        })
        self.Dep.link("project.task", self.task_a.id, self.task_b.id, "FS")

        # Movemos A al miércoles previo. Cascade debe avanzar B al
        # próximo laboral después del nuevo fin de A.
        new_a_start = datetime(2026, 6, 3, 8, 0)  # miércoles
        self.Planner.reschedule_with_dependencies(
            "project.task", self.task_a.id,
            new_a_start.strftime("%Y-%m-%d %H:%M:%S"),
            "planned_date_begin", "date_deadline",
        )
        self.task_b.invalidate_recordset()
        # B debe arrancar en día laboral (no sábado/domingo).
        self.assertIn(self.task_b.planned_date_begin.weekday(), (0, 1, 2, 3, 4),
            f"B arrancó en weekday={self.task_b.planned_date_begin.weekday()}; "
            "debería ser lunes-viernes")

    def test_05_respect_calendar_can_be_disabled(self):
        # Si respect_calendar=False, vuelve al comportamiento de antes
        # (sin snap). Útil para sistemas legacy o cuando el user prefiere
        # raw datetime.
        # Verificamos que NO lanza error y devuelve el caso simple.
        res = self.Planner.reschedule_with_dependencies(
            "project.task", self.task_d.id,
            "2026-06-06 10:00:00",   # sábado
            "planned_date_begin", "date_deadline",
            cascade=False,
            respect_calendar=False,
        )
        self.assertFalse(res["constrained"])
        self.task_d.invalidate_recordset()
        # Sin calendar, se respeta la fecha textual.
        self.assertEqual(self.task_d.planned_date_begin,
                         datetime(2026, 6, 6, 10, 0))
