# gantt_studio_project — Project integration for Gantt Studio.
#
# Aporta UN SOLO campo (`planned_date_begin`) a project.task para que la
# vista Gantt Studio sobre project.task funcione en Odoo 18 Community
# puro. Si project_enterprise está instalado, ambos módulos coexisten
# sin conflicto porque el nombre y el tipo del campo coinciden.
from . import models
