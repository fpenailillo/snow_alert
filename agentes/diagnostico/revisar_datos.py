"""
Diagnóstico de datos BigQuery para el sistema de predicción de avalanchas.

Verifica el estado de las tablas criticas:
- imagenes_satelitales: porcentaje de nulos por columna clave
- zonas_avalancha: cobertura de ubicaciones y nulos

Uso:
    python agentes/diagnostico/revisar_datos.py
    python agentes/diagnostico/revisar_datos.py --tabla imagenes_satelitales
    python agentes/diagnostico/revisar_datos.py --umbral-nulos 30
"""

import argparse
import logging
import sys
import os
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

ID_PROYECTO = "climas-chileno"
DATASET = "clima"

# Columnas clave a verificar en cada tabla
COLUMNAS_SATELITAL = [
    "nombre_ubicacion",
    "fecha_captura",
    "fuente_principal",
    "pct_cobertura_nieve",
    "ndsi_medio",
    "lst_dia_celsius",
    "lst_noche_celsius",
    "ciclo_diurno_amplitud",
    "snowline_elevacion_m",
    "delta_pct_nieve_24h",
    "era5_snow_depth_m",
]

COLUMNAS_TOPOGRAFICO = [
    "nombre_ubicacion",
    "fecha_analisis",
    "zona_inicio_ha",
    "pendiente_media_inicio",
    "pendiente_max_inicio",
    "aspecto_predominante_inicio",
    "indice_riesgo_topografico",
    "clasificacion_riesgo",
    "peligro_eaws_base",
    "frecuencia_estimada_eaws",
    "tamano_estimado_eaws",
]

UMBRAL_NULOS_ALERTA = 20  # % de nulos que dispara alerta


def verificar_tabla_satelital(cliente) -> dict:
    """Diagnostica la tabla imagenes_satelitales."""
    logger.info("=== Diagnosticando imagenes_satelitales ===")

    # Total de registros y rango de fechas
    query_total = f"""
    SELECT
        COUNT(*) as total_registros,
        MIN(fecha_captura) as primera_fecha,
        MAX(fecha_captura) as ultima_fecha,
        COUNT(DISTINCT nombre_ubicacion) as ubicaciones_distintas
    FROM `{ID_PROYECTO}.{DATASET}.imagenes_satelitales`
    """
    try:
        resultado_total = list(cliente.query(query_total).result())[0]
    except Exception as e:
        return {"error": str(e), "disponible": False, "tabla": "imagenes_satelitales"}

    total = resultado_total.total_registros
    logger.info(f"  Total registros: {total}")
    logger.info(f"  Ubicaciones distintas: {resultado_total.ubicaciones_distintas}")
    logger.info(f"  Rango fechas: {resultado_total.primera_fecha} → {resultado_total.ultima_fecha}")

    if total == 0:
        return {
            "tabla": "imagenes_satelitales",
            "total_registros": 0,
            "problema": "TABLA VACÍA",
            "accion_requerida": "Forzar ejecución de monitor-satelital-nieve"
        }

    # Porcentaje de nulos por columna clave
    expresiones_nulos = ",\n        ".join(
        f"ROUND(100.0 * COUNTIF({col} IS NULL) / COUNT(*), 1) as pct_nulos_{col}"
        for col in COLUMNAS_SATELITAL
        if col not in ("nombre_ubicacion", "fecha_captura", "fuente_principal")
    )

    query_nulos = f"""
    SELECT
        {expresiones_nulos}
    FROM `{ID_PROYECTO}.{DATASET}.imagenes_satelitales`
    """
    resultado_nulos = list(cliente.query(query_nulos).result())[0]

    columnas_con_problemas = []
    informe_nulos = {}
    for col in COLUMNAS_SATELITAL:
        campo = f"pct_nulos_{col}"
        if hasattr(resultado_nulos, campo):
            pct = getattr(resultado_nulos, campo)
            informe_nulos[col] = pct
            nivel = "🔴 CRÍTICO" if pct > 80 else "🟡 ALTO" if pct > UMBRAL_NULOS_ALERTA else "✅ OK"
            logger.info(f"  {nivel} {col}: {pct}% nulos")
            if pct > UMBRAL_NULOS_ALERTA:
                columnas_con_problemas.append(col)

    # Últimas 3 capturas para diagnóstico visual
    query_muestra = f"""
    SELECT
        nombre_ubicacion,
        fecha_captura,
        fuente_principal,
        ROUND(pct_cobertura_nieve, 1) as cobertura,
        ROUND(ndsi_medio, 3) as ndsi,
        ROUND(lst_dia_celsius, 1) as lst_dia,
        ROUND(era5_snow_depth_m, 3) as snow_depth_era5
    FROM `{ID_PROYECTO}.{DATASET}.imagenes_satelitales`
    ORDER BY fecha_captura DESC
    LIMIT 5
    """
    muestra = [dict(row) for row in cliente.query(query_muestra).result()]

    return {
        "tabla": "imagenes_satelitales",
        "total_registros": total,
        "ubicaciones_distintas": resultado_total.ubicaciones_distintas,
        "primera_fecha": str(resultado_total.primera_fecha),
        "ultima_fecha": str(resultado_total.ultima_fecha),
        "pct_nulos_por_columna": informe_nulos,
        "columnas_con_problemas": columnas_con_problemas,
        "muestra_reciente": muestra,
        "requiere_atencion": len(columnas_con_problemas) > 0
    }


def verificar_tabla_topografico(cliente) -> dict:
    """Diagnostica la tabla zonas_avalancha."""
    logger.info("=== Diagnosticando zonas_avalancha ===")

    query_total = f"""
    SELECT
        COUNT(*) as total_registros,
        MIN(fecha_analisis) as primera_fecha,
        MAX(fecha_analisis) as ultima_fecha,
        COUNT(DISTINCT nombre_ubicacion) as ubicaciones_distintas,
        COUNTIF(indice_riesgo_topografico IS NULL) as filas_sin_indice
    FROM `{ID_PROYECTO}.{DATASET}.zonas_avalancha`
    """
    try:
        resultado_total = list(cliente.query(query_total).result())[0]
    except Exception as e:
        return {"error": str(e), "disponible": False, "tabla": "zonas_avalancha"}

    total = resultado_total.total_registros
    logger.info(f"  Total registros: {total}")
    logger.info(f"  Ubicaciones distintas: {resultado_total.ubicaciones_distintas}")
    logger.info(f"  Filas sin índice de riesgo: {resultado_total.filas_sin_indice}")

    if total == 0:
        return {
            "tabla": "zonas_avalancha",
            "total_registros": 0,
            "problema": "TABLA VACÍA",
            "accion_requerida": "Forzar ejecución de analizador-satelital-zonas-riesgosas-avalanchas"
        }

    # Nulos por columna
    expresiones_nulos = ",\n        ".join(
        f"ROUND(100.0 * COUNTIF({col} IS NULL) / COUNT(*), 1) as pct_nulos_{col}"
        for col in COLUMNAS_TOPOGRAFICO
        if col not in ("nombre_ubicacion", "fecha_analisis")
    )

    query_nulos = f"""
    SELECT {expresiones_nulos}
    FROM `{ID_PROYECTO}.{DATASET}.zonas_avalancha`
    """
    resultado_nulos = list(cliente.query(query_nulos).result())[0]

    columnas_con_problemas = []
    informe_nulos = {}
    for col in COLUMNAS_TOPOGRAFICO:
        campo = f"pct_nulos_{col}"
        if hasattr(resultado_nulos, campo):
            pct = getattr(resultado_nulos, campo)
            informe_nulos[col] = pct
            nivel = "🔴 CRÍTICO" if pct > 80 else "🟡 ALTO" if pct > UMBRAL_NULOS_ALERTA else "✅ OK"
            logger.info(f"  {nivel} {col}: {pct}% nulos")
            if pct > UMBRAL_NULOS_ALERTA:
                columnas_con_problemas.append(col)

    # Muestra de distribución de riesgo
    query_distribucion = f"""
    SELECT
        clasificacion_riesgo,
        peligro_eaws_base,
        COUNT(*) as registros
    FROM `{ID_PROYECTO}.{DATASET}.zonas_avalancha`
    WHERE indice_riesgo_topografico IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 3 DESC
    LIMIT 10
    """
    distribucion = [dict(row) for row in cliente.query(query_distribucion).result()]

    return {
        "tabla": "zonas_avalancha",
        "total_registros": total,
        "ubicaciones_distintas": resultado_total.ubicaciones_distintas,
        "primera_fecha": str(resultado_total.primera_fecha),
        "ultima_fecha": str(resultado_total.ultima_fecha),
        "filas_sin_indice": resultado_total.filas_sin_indice,
        "pct_nulos_por_columna": informe_nulos,
        "columnas_con_problemas": columnas_con_problemas,
        "distribucion_riesgo": distribucion,
        "requiere_atencion": len(columnas_con_problemas) > 0 or resultado_total.filas_sin_indice > 0
    }


def verificar_tabla_relatos(cliente) -> dict:
    """Verifica si la tabla relatos_montanistas existe y tiene datos."""
    logger.info("=== Verificando relatos_montanistas ===")

    query = f"""
    SELECT COUNT(*) as total
    FROM `{ID_PROYECTO}.{DATASET}.relatos_montanistas`
    """
    try:
        resultado = list(cliente.query(query).result())[0]
        total = resultado.total
        if total > 0:
            logger.info(f"  ✅ {total} relatos disponibles")
        else:
            logger.warning("  ⚠️ Tabla existe pero está vacía — ejecutar FASE 1")
        return {"tabla": "relatos_montanistas", "total_registros": total, "existe": True}
    except Exception as e:
        if "Not found" in str(e) or "not found" in str(e):
            logger.warning("  ❌ Tabla no existe — ejecutar FASE 1 para crearla y cargar datos")
            return {"tabla": "relatos_montanistas", "existe": False, "total_registros": 0}
        return {"tabla": "relatos_montanistas", "error": str(e), "existe": False}


def imprimir_resumen(resultados: list) -> bool:
    """Imprime resumen y retorna True si todo está OK."""
    print("\n" + "=" * 60)
    print("RESUMEN DEL DIAGNÓSTICO DE DATOS")
    print("=" * 60)

    todo_ok = True

    for r in resultados:
        tabla = r.get("tabla", "desconocida")
        total = r.get("total_registros", 0)
        problemas = r.get("columnas_con_problemas", [])
        error = r.get("error")

        if error:
            print(f"❌ {tabla}: ERROR — {error}")
            todo_ok = False
        elif total == 0:
            accion = r.get("accion_requerida", "verificar")
            print(f"🔴 {tabla}: VACÍA → {accion}")
            todo_ok = False
        elif problemas:
            print(f"🟡 {tabla}: {total} registros, columnas con >20% nulos: {', '.join(problemas)}")
            todo_ok = False
        else:
            print(f"✅ {tabla}: {total} registros OK")

    print("=" * 60)

    if not todo_ok:
        print("\nACCIONES RECOMENDADAS:")
        for r in resultados:
            if r.get("requiere_atencion") or r.get("total_registros", 0) == 0:
                tabla = r.get("tabla")
                if "satelital" in tabla:
                    print(f"  • Forzar: gcloud functions call monitor-satelital-nieve --gen2 --region=us-central1")
                    print(f"  • Revisar logs: gcloud functions logs read monitor-satelital-nieve --gen2 --limit=50")
                elif "avalancha" in tabla:
                    print(f"  • Forzar: gcloud functions call analizador-satelital-zonas-riesgosas-avalanchas --gen2 --region=us-central1")
                elif "relatos" in tabla:
                    print(f"  • Ejecutar FASE 1: exportar relatos de Databricks a BigQuery")
    else:
        print("\n✓ Datos listos para el sistema de agentes")

    return todo_ok


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostica datos nulos en BigQuery para el sistema de avalanchas"
    )
    parser.add_argument(
        "--tabla",
        choices=["imagenes_satelitales", "zonas_avalancha", "relatos_montanistas", "todas"],
        default="todas",
        help="Tabla específica a diagnosticar (default: todas)"
    )
    parser.add_argument(
        "--umbral-nulos",
        type=int,
        default=UMBRAL_NULOS_ALERTA,
        help=f"Porcentaje de nulos que dispara alerta (default: {UMBRAL_NULOS_ALERTA})"
    )
    args = parser.parse_args()

    global UMBRAL_NULOS_ALERTA
    UMBRAL_NULOS_ALERTA = args.umbral_nulos

    try:
        from google.cloud import bigquery
    except ImportError:
        logger.error("google-cloud-bigquery no instalado. Ejecutar: pip install google-cloud-bigquery")
        sys.exit(1)

    try:
        cliente = bigquery.Client(project=ID_PROYECTO)
        logger.info(f"Conectado a BigQuery: {ID_PROYECTO}.{DATASET}")
    except Exception as e:
        logger.error(f"Error conectando a BigQuery: {e}")
        logger.error("Verificar: gcloud auth application-default login")
        sys.exit(1)

    resultados = []

    if args.tabla in ("imagenes_satelitales", "todas"):
        resultados.append(verificar_tabla_satelital(cliente))

    if args.tabla in ("zonas_avalancha", "todas"):
        resultados.append(verificar_tabla_topografico(cliente))

    if args.tabla in ("relatos_montanistas", "todas"):
        resultados.append(verificar_tabla_relatos(cliente))

    todo_ok = imprimir_resumen(resultados)
    sys.exit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
