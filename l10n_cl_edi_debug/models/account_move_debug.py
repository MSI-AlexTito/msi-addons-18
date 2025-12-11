# -*- coding: utf-8 -*-
from odoo import models
import logging
import base64

_logger = logging.getLogger(__name__)


class AccountMoveDebug(models.Model):
    _inherit = 'account.move'

    def l10n_cl_send_dte_to_sii(self, retry_send=True):
        """Log completo del envío del DTE"""
        self.ensure_one()

        initial_status = self.l10n_cl_dte_status

        _logger.info(f'\n{"#"*100}')
        _logger.info(f'ENVIANDO DTE AL SII')
        _logger.info(f'{"#"*100}')
        _logger.info(f'Factura: {self.name} (ID: {self.id})')
        _logger.info(f'Tipo de documento: {self.l10n_latam_document_type_id.name} ({self.l10n_latam_document_type_id.code})')
        _logger.info(f'Estado inicial: {initial_status}')
        _logger.info(f'Cliente: {self.partner_id.name} (RUT: {self.partner_id.vat})')
        _logger.info(f'Total: {self.amount_total} {self.currency_id.name}')
        _logger.info(f'Proveedor de servicio: {self.company_id.l10n_cl_dte_service_provider}')
        _logger.info(f'Retry send: {retry_send}')

        # Información del archivo DTE
        if self.l10n_cl_sii_send_file:
            dte_file = self.sudo().l10n_cl_sii_send_file
            _logger.info(f'\nArchivo DTE:')
            _logger.info(f'  Nombre: {dte_file.name}')
            _logger.info(f'  Tamaño: {len(dte_file.datas)} caracteres (base64)')
            _logger.info(f'  Tamaño decodificado: {len(base64.b64decode(dte_file.datas))} bytes')

        try:
            result = super().l10n_cl_send_dte_to_sii(retry_send=retry_send)

            _logger.info(f'\n{"="*80}')
            _logger.info(f'RESULTADO ENVÍO DTE')
            _logger.info(f'{"="*80}')
            _logger.info(f'Estado inicial: {initial_status}')
            _logger.info(f'Estado final: {self.l10n_cl_dte_status}')
            _logger.info(f'Track ID: {self.l10n_cl_sii_send_ident}')

            if self.l10n_cl_dte_status != initial_status:
                _logger.info(f'✓ Estado cambió de {initial_status} a {self.l10n_cl_dte_status}')
            else:
                _logger.info(f'⚠ Estado no cambió (se mantiene en {initial_status})')

            _logger.info(f'{"#"*100}\n')

            return result
        except Exception as e:
            _logger.info(f'\n{"!"*80}')
            _logger.info(f'ERROR AL ENVIAR DTE')
            _logger.info(f'{"!"*80}')
            _logger.info(f'Factura: {self.name}')
            _logger.info(f'Tipo de error: {type(e).__name__}')
            _logger.info(f'Mensaje: {str(e)}')
            _logger.info(f'{"!"*80}\n')
            raise

    def l10n_cl_verify_dte_status(self, send_dte_to_partner=True):
        """Log completo de verificación de estado"""
        self.ensure_one()

        initial_status = self.l10n_cl_dte_status

        _logger.info(f'\n{"#"*100}')
        _logger.info(f'VERIFICANDO ESTADO DTE')
        _logger.info(f'{"#"*100}')
        _logger.info(f'Factura: {self.name} (ID: {self.id})')
        _logger.info(f'Estado actual: {initial_status}')
        _logger.info(f'Track ID: {self.l10n_cl_sii_send_ident}')
        _logger.info(f'Enviar al partner: {send_dte_to_partner}')

        try:
            result = super().l10n_cl_verify_dte_status(send_dte_to_partner=send_dte_to_partner)

            _logger.info(f'\n{"="*80}')
            _logger.info(f'RESULTADO VERIFICACIÓN')
            _logger.info(f'{"="*80}')
            _logger.info(f'Estado inicial: {initial_status}')
            _logger.info(f'Estado final: {self.l10n_cl_dte_status}')

            if self.l10n_cl_dte_status != initial_status:
                _logger.info(f'✓ Estado cambió de {initial_status} a {self.l10n_cl_dte_status}')

                # Mapeo de estados
                status_description = {
                    'not_sent': 'No enviado',
                    'ask_for_status': 'Pendiente de verificación',
                    'accepted': 'Aceptado por el SII',
                    'objected': 'Objetado por el SII',
                    'rejected': 'Rechazado por el SII',
                    'cancelled': 'Anulado',
                }
                if self.l10n_cl_dte_status in status_description:
                    _logger.info(f'  Descripción: {status_description[self.l10n_cl_dte_status]}')
            else:
                _logger.info(f'⚠ Estado no cambió (se mantiene en {initial_status})')

            _logger.info(f'{"#"*100}\n')

            return result
        except Exception as e:
            _logger.info(f'\n{"!"*80}')
            _logger.info(f'ERROR AL VERIFICAR ESTADO')
            _logger.info(f'{"!"*80}')
            _logger.info(f'Factura: {self.name}')
            _logger.info(f'Tipo de error: {type(e).__name__}')
            _logger.info(f'Mensaje: {str(e)}')
            _logger.info(f'{"!"*80}\n')
            raise
