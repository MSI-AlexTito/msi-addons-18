-- =============================================================================
-- LIMPIAR CASOS DE CERTIFICACIÓN Y DOCUMENTOS GENERADOS
-- =============================================================================
-- Este script elimina todos los registros de casos, documentos generados,
-- sobres y respuestas del SII, pero mantiene:
-- - El proyecto de certificación
-- - La información del cliente
-- - Los templates de casos de prueba (catálogo)
-- - Las asignaciones de folios (CAF)
-- =============================================================================
-- IMPORTANTE: Conectarse a la base de datos correcta antes de ejecutar
-- Ejemplo: psql -U odoo -d bd_angol -f cleanup_certification_data.sql
-- =============================================================================

\echo '=================================='
\echo 'INICIANDO LIMPIEZA DE DATOS'
\echo '=================================='

BEGIN;

-- Mostrar estado ANTES de la limpieza
\echo ''
\echo 'Estado ANTES de la limpieza:'
\echo '----------------------------'

SELECT
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_case) as casos,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_generated_document) as documentos,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_envelope) as sobres,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_sii_response) as respuestas_sii;

\echo ''
\echo 'Eliminando registros...'
\echo ''

-- 1. Eliminar tabla many2many de relación sobre-documentos
DELETE FROM certification_envelope_document_rel;
\echo '✓ Relaciones sobre-documentos eliminadas'

-- 2. Eliminar respuestas del SII
DELETE FROM l10n_cl_edi_certification_sii_response;
\echo '✓ Respuestas del SII eliminadas'

-- 3. Eliminar sobres de envío
DELETE FROM l10n_cl_edi_certification_envelope;
\echo '✓ Sobres eliminados'

-- 4. Eliminar documentos generados (DTEs)
DELETE FROM l10n_cl_edi_certification_generated_document;
\echo '✓ Documentos generados eliminados'

-- 5. Eliminar líneas de casos de prueba
DELETE FROM l10n_cl_edi_certification_case_line;
\echo '✓ Líneas de casos eliminadas'

-- 6. Eliminar casos de prueba (instancias usadas en el proyecto)
DELETE FROM l10n_cl_edi_certification_case;
\echo '✓ Casos de prueba eliminados'

-- 7. OPCIONAL: Resetear asignaciones de folios
-- DESCOMENTAR LA SIGUIENTE LÍNEA SI QUIERES REINICIAR LOS FOLIOS:
-- UPDATE l10n_cl_edi_certification_folio_assignment
-- SET next_folio = folio_start,
--     used_count = 0,
--     available_count = (folio_end - folio_start + 1);
-- \echo '✓ Folios reseteados'

\echo ''
\echo 'Estado DESPUÉS de la limpieza:'
\echo '------------------------------'

SELECT
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_case) as casos,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_generated_document) as documentos,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_envelope) as sobres,
    (SELECT COUNT(*) FROM l10n_cl_edi_certification_sii_response) as respuestas_sii;

\echo ''
\echo 'Datos que permanecen intactos:'
\echo '------------------------------'

SELECT 'Proyectos:' as info, COUNT(*)::text as cantidad
FROM l10n_cl_edi_certification_project
UNION ALL
SELECT 'Clientes:', COUNT(*)::text
FROM l10n_cl_edi_certification_client
UNION ALL
SELECT 'Templates (catálogo):', COUNT(*)::text
FROM l10n_cl_edi_certification_test_case_template
UNION ALL
SELECT 'Asignaciones de folios:', COUNT(*)::text
FROM l10n_cl_edi_certification_folio_assignment;

\echo ''
\echo 'Detalle de folios disponibles:'
\echo '------------------------------'

SELECT
    dt.name as tipo_documento,
    fa.folio_start as desde,
    fa.folio_end as hasta,
    fa.next_folio as proximo,
    fa.used_count as usados,
    fa.available_count as disponibles
FROM l10n_cl_edi_certification_folio_assignment fa
JOIN l10n_latam_document_type dt ON fa.document_type_id = dt.id
ORDER BY dt.code;

-- Aplicar cambios
COMMIT;

\echo ''
\echo '=================================='
\echo '✅ LIMPIEZA COMPLETADA EXITOSAMENTE'
\echo '=================================='
\echo ''
\echo 'Ahora puedes:'
\echo '1. Ir al proyecto de certificación en Odoo'
\echo '2. Importar los casos de prueba nuevamente'
\echo '3. Generar los documentos'
\echo '4. Crear un nuevo sobre'
\echo '5. Verificar los logs antes de enviar'
\echo ''
