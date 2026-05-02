#!/bin/bash
# Despliega el Cloud Function extractor_historico en GCP.
# Uso: ./desplegar.sh [REGION]

set -e

PROYECTO="${GCP_PROJECT:-climas-chileno}"
REGION="${1:-us-central1}"
NOMBRE_FUNCION="extractor_historico"

echo "Desplegando ${NOMBRE_FUNCION} en ${PROYECTO} (${REGION})..."

gcloud functions deploy "${NOMBRE_FUNCION}" \
    --project="${PROYECTO}" \
    --region="${REGION}" \
    --runtime=python311 \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=512MB \
    --timeout=540s \
    --entry-point=extractor_historico \
    --set-env-vars="GCP_PROJECT=${PROYECTO}" \
    --source=.

echo ""
echo "Función desplegada. Para invocar el backfill completo:"
echo ""
echo "gcloud functions call ${NOMBRE_FUNCION} --region=${REGION} \\"
echo "  --data='{\"ubicaciones\":[\"La Parva Sector Bajo\",\"La Parva Sector Medio\",\"La Parva Sector Alto\",\"Interlaken\",\"Matterhorn Zermatt\",\"St Moritz\"],\"fecha_inicio\":\"2024-06-15\",\"fecha_fin\":\"2025-09-21\"}'"
