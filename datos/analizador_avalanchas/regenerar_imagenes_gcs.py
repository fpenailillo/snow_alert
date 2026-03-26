"""
Backfill: regenera imágenes PNG/thumbnail en GCS para fechas anteriores al fix de desnivel.

Problema: visualizacion.py usaba desnivel_inicio_deposito sin abs(), mostrando valores
negativos (ej: "-494 m"). Fix aplicado 2026-03-25 (commit 7c44eb7).

Este script lee los datos ya correctos de zonas_avalancha en BQ y regenera las
imágenes con la visualización corregida. No requiere re-ejecutar GEE.

Uso:
  python regenerar_imagenes_gcs.py [--fecha YYYY-MM-DD] [--dry-run]

  --fecha    Regenera solo esa fecha (default: todas las fechas anteriores a 2026-03-25)
  --dry-run  Solo muestra qué se generaría sin subir a GCS
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone, date

from google.cloud import bigquery, storage

# Agregar directorio padre al path para importar visualizacion.py
sys.path.insert(0, os.path.dirname(__file__))
from visualizacion import (
    crear_mapa_zonas_png,
    crear_thumbnail_riesgo,
    crear_geojson_zonas,
    guardar_visualizaciones_gcs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ID_PROYECTO = os.environ.get('GCP_PROJECT', os.environ.get('GOOGLE_CLOUD_PROJECT', 'climas-chileno'))
BUCKET_BRONCE = f'{ID_PROYECTO}-datos-clima-bronce'
TABLA_ZONAS = f'{ID_PROYECTO}.clima.zonas_avalancha'

# Fecha desde la que el fix está activo — solo regenerar fechas anteriores
FECHA_FIX = date(2026, 3, 25)


def obtener_filas_bq(cliente_bq: bigquery.Client, fecha_filtro: date | None) -> list:
    """Lee filas de zonas_avalancha para las fechas afectadas."""
    if fecha_filtro:
        condicion = "AND DATE(fecha_analisis) = @fecha"
        params = [bigquery.ScalarQueryParameter('fecha', 'DATE', fecha_filtro.isoformat())]
    else:
        condicion = "AND DATE(fecha_analisis) < @fecha_fix"
        params = [bigquery.ScalarQueryParameter('fecha_fix', 'DATE', FECHA_FIX.isoformat())]

    query = f"""
        SELECT
            nombre_ubicacion, latitud, longitud, fecha_analisis,
            zona_inicio_ha, zona_transito_ha, zona_deposito_ha,
            zona_inicio_pct, zona_transito_pct, zona_deposito_pct,
            pendiente_max_inicio, desnivel_inicio_deposito,
            indice_riesgo_topografico, clasificacion_riesgo,
            peligro_eaws_base, descripcion_riesgo,
            radio_analisis_metros
        FROM `{TABLA_ZONAS}`
        WHERE TRUE {condicion}
        ORDER BY fecha_analisis, nombre_ubicacion
    """
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return list(cliente_bq.query(query, job_config=job_config).result())


def regenerar_ubicacion(
    row,
    cliente_gcs: storage.Client,
    dry_run: bool,
) -> bool:
    """Regenera y sube imágenes para una fila de zonas_avalancha."""
    nombre = row.nombre_ubicacion
    fecha = row.fecha_analisis
    if isinstance(fecha, datetime) and fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    cubicacion = {
        'zona_inicio_ha': row.zona_inicio_ha or 0,
        'zona_transito_ha': row.zona_transito_ha or 0,
        'zona_deposito_ha': row.zona_deposito_ha or 0,
        'zona_inicio_pct': row.zona_inicio_pct or 0,
        'zona_transito_pct': row.zona_transito_pct or 0,
        'zona_deposito_pct': row.zona_deposito_pct or 0,
        'pendiente_max_inicio': row.pendiente_max_inicio or 0,
        'desnivel_inicio_deposito': row.desnivel_inicio_deposito,
    }
    indice_dict = {
        'indice_riesgo_topografico': row.indice_riesgo_topografico or 0,
        'clasificacion_riesgo': row.clasificacion_riesgo or 'bajo',
        'peligro_eaws_base': row.peligro_eaws_base or 1,
        'descripcion_riesgo': row.descripcion_riesgo or '',
    }

    logger.info(f"  {nombre} — {fecha.date()} — desnivel={row.desnivel_inicio_deposito}")

    # Generar imágenes con visualización corregida (abs() aplicado internamente)
    mapa_png = crear_mapa_zonas_png(nombre, cubicacion, indice_dict)
    thumb_png = crear_thumbnail_riesgo(
        nombre,
        indice_dict['indice_riesgo_topografico'],
        indice_dict['clasificacion_riesgo'],
    )
    geojson = crear_geojson_zonas(
        nombre_ubicacion=nombre,
        latitud=row.latitud,
        longitud=row.longitud,
        radio_metros=row.radio_analisis_metros or 5000,
        cubicacion=cubicacion,
        indice_dict=indice_dict,
        fecha_analisis=fecha,
    )

    if dry_run:
        logger.info(f"    [DRY RUN] mapa={'ok' if mapa_png else 'None'} "
                    f"thumb={'ok' if thumb_png else 'None'} geojson=ok")
        return True

    try:
        uris = guardar_visualizaciones_gcs(
            cliente_gcs=cliente_gcs,
            bucket_nombre=BUCKET_BRONCE,
            nombre_ubicacion=nombre,
            fecha_analisis=fecha,
            mapa_png=mapa_png,
            thumbnail_png=thumb_png,
            geojson_data=geojson,
        )
        logger.info(f"    Subido: {list(uris.keys())}")
        return True
    except Exception as e:
        logger.error(f"    Error subiendo {nombre}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Regenera imágenes GCS post-fix desnivel")
    parser.add_argument('--fecha', type=str, default=None,
                        help='Fecha específica YYYY-MM-DD (default: todas < 2026-03-25)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo muestra qué se generaría sin subir a GCS')
    args = parser.parse_args()

    fecha_filtro = date.fromisoformat(args.fecha) if args.fecha else None

    if args.dry_run:
        logger.info("=== MODO DRY RUN — sin cambios en GCS ===")
    else:
        logger.info("=== MODO EJECUCIÓN REAL ===")

    cliente_bq = bigquery.Client(project=ID_PROYECTO)
    cliente_gcs = storage.Client(project=ID_PROYECTO) if not args.dry_run else None

    filas = obtener_filas_bq(cliente_bq, fecha_filtro)
    logger.info(f"Filas a procesar: {len(filas)}")

    exitosos = 0
    fallidos = 0
    for row in filas:
        ok = regenerar_ubicacion(row, cliente_gcs, args.dry_run)
        if ok:
            exitosos += 1
        else:
            fallidos += 1

    logger.info(f"\nResumen: {exitosos} exitosos, {fallidos} fallidos de {len(filas)} total")


if __name__ == '__main__':
    main()
