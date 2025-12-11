# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError


class FolioService(models.AbstractModel):
    """
    Servicio para Gestión de Folios.
    Maneja la asignación y control de folios CAF.
    """
    _name = 'l10n_cl_edi.folio.service'
    _description = 'Servicio de Gestión de Folios'

    @api.model
    def get_next_folio(self, project, document_type):
        """
        Obtiene el próximo folio disponible para un tipo de documento.

        Args:
            project: l10n_cl_edi.certification.project
            document_type: l10n_latam.document.type

        Returns:
            int: Próximo folio disponible
        """
        # Buscar asignación de folios para este tipo de documento
        assignment = self.env['l10n_cl_edi.certification.folio.assignment'].search([
            ('project_id', '=', project.id),
            ('document_type_id', '=', document_type.id),
        ], limit=1)

        if not assignment:
            raise UserError(_(
                'No hay asignación de folios para el tipo de documento %s en este proyecto.\n'
                'Por favor configure los folios primero.'
            ) % document_type.name)

        # Obtener próximo folio
        next_folio = assignment.get_next_folio()

        return next_folio

    @api.model
    def validate_folio_availability(self, assignment):
        """
        Valida que haya folios disponibles en una asignación.

        Args:
            assignment: l10n_cl_edi.certification.folio.assignment

        Returns:
            tuple: (bool, str) - (hay_disponibles, mensaje)
        """
        if assignment.folios_available <= 0:
            return False, _('No hay folios disponibles')

        if assignment.folios_available < 5:
            return True, _('Advertencia: Quedan solo %d folios disponibles') % assignment.folios_available

        return True, _('OK')

    @api.model
    def mark_folio_used(self, assignment, folio):
        """
        Marca un folio como usado.
        Nota: Esto se hace automáticamente con el compute de folio_next,
        pero este método está disponible para casos especiales.

        Args:
            assignment: l10n_cl_edi.certification.folio.assignment
            folio (int): Folio usado
        """
        if folio < assignment.folio_start or folio > assignment.folio_end:
            raise UserError(_(
                'El folio %d está fuera del rango asignado (%d - %d)'
            ) % (folio, assignment.folio_start, assignment.folio_end))

        # El folio_next se actualizará automáticamente
        pass

    @api.model
    def validate_caf(self, caf, folio):
        """
        Valida que un folio esté dentro del rango del CAF.

        Args:
            caf: l10n_cl.dte.caf
            folio (int): Folio a validar

        Returns:
            bool: True si es válido
        """
        # Aquí deberías verificar contra el CAF real
        # Por ahora retornamos True
        return True

    @api.model
    def get_folio_statistics(self, project):
        """
        Obtiene estadísticas de uso de folios para un proyecto.

        Args:
            project: l10n_cl_edi.certification.project

        Returns:
            dict: Estadísticas por tipo de documento
        """
        stats = []

        for assignment in project.folio_assignment_ids:
            stats.append({
                'document_type': assignment.document_type_id.name,
                'document_code': assignment.document_type_id.code,
                'total': assignment.folios_total,
                'used': assignment.folios_used,
                'available': assignment.folios_available,
                'percentage': assignment.usage_percentage,
            })

        return stats
