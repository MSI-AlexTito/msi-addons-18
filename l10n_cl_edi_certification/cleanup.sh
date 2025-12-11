#!/bin/bash
# =============================================================================
# Script para limpiar datos de certificación
# =============================================================================

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================="
echo "LIMPIEZA DE DATOS DE CERTIFICACIÓN"
echo -e "==================================${NC}"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "cleanup_certification_data.sql" ]; then
    echo -e "${RED}❌ Error: No se encontró cleanup_certification_data.sql${NC}"
    echo "Ejecuta este script desde el directorio del módulo l10n_cl_edi_certification"
    exit 1
fi

# Pedir confirmación
echo -e "${YELLOW}⚠️  ADVERTENCIA:${NC}"
echo "Este script eliminará:"
echo "  - Todos los casos de prueba del proyecto"
echo "  - Todos los documentos generados (DTEs)"
echo "  - Todos los sobres de envío"
echo "  - Todas las respuestas del SII"
echo ""
echo -e "${GREEN}Se mantendrán:${NC}"
echo "  - El proyecto de certificación"
echo "  - La información del cliente"
echo "  - Los templates de casos (catálogo)"
echo "  - Las asignaciones de folios (CAF)"
echo ""
read -p "¿Deseas continuar? (si/no): " -r
echo

if [[ ! $REPLY =~ ^[Ss][Ii]$ ]]; then
    echo -e "${YELLOW}❌ Operación cancelada${NC}"
    exit 0
fi

# Pedir nombre de la base de datos
read -p "Nombre de la base de datos (ejemplo: bd_angol): " DB_NAME

if [ -z "$DB_NAME" ]; then
    echo -e "${RED}❌ Error: Debes proporcionar el nombre de la base de datos${NC}"
    exit 1
fi

# Pedir usuario de PostgreSQL (por defecto: odoo)
read -p "Usuario de PostgreSQL [odoo]: " DB_USER
DB_USER=${DB_USER:-odoo}

echo ""
echo -e "${BLUE}Ejecutando limpieza...${NC}"
echo ""

# Ejecutar el SQL
psql -U "$DB_USER" -d "$DB_NAME" -f cleanup_certification_data.sql

# Verificar el resultado
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Limpieza completada exitosamente${NC}"
    echo ""
    echo -e "${YELLOW}Próximos pasos:${NC}"
    echo "1. Actualiza el módulo en Odoo:"
    echo "   Apps > l10n_cl_edi_certification > Actualizar"
    echo ""
    echo "2. Ve al proyecto de certificación"
    echo ""
    echo "3. Importa los casos de prueba nuevamente"
    echo ""
    echo "4. Genera los documentos"
    echo ""
    echo "5. Crea un nuevo sobre y verifica los logs"
    echo ""
else
    echo ""
    echo -e "${RED}❌ Error al ejecutar la limpieza${NC}"
    echo "Verifica:"
    echo "  - Que la base de datos existe"
    echo "  - Que el usuario tiene permisos"
    echo "  - Que PostgreSQL está corriendo"
    exit 1
fi
