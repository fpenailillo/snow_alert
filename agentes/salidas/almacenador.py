"""
Almacenador de Boletines de Riesgo de Avalanchas

Guarda los boletines generados en:
1. BigQuery — tabla clima.boletines_riesgo (creada si no existe)
2. GCS — bucket climas-chileno-datos-clima-bronce/boletines/

Formato GCS:
gs://climas-chileno-datos-clima-bronce/boletines/{ubicacion_normalizada}/{YYYY/MM/DD}/{timestamp}.json
"""

import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError


# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constantes — leen de env vars para compatibilidad con Cloud Run Job (ID_PROYECTO)
GCP_PROJECT = os.environ.get("GCP_PROJECT") or os.environ.get("ID_PROYECTO", "climas-chileno")
DATASET = os.environ.get("DATASET_ID", "clima")
TABLA_BOLETINES = "boletines_riesgo"
NOMBRE_BUCKET = "climas-chileno-datos-clima-bronce"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_boletines.json")


class ErrorAlmacenamiento(Exception):
    """Excepción levantada cuando falla el almacenamiento de boletines."""
    pass


def _normalizar_ubicacion(nombre: str) -> str:
    """
    Normaliza el nombre de ubicación para uso en rutas de archivo.

    Args:
        nombre: Nombre de la ubicación

    Returns:
        str: Nombre normalizado (sin tildes, minúsculas, guiones)
    """
    # Eliminar tildes y caracteres especiales
    normalizado = unicodedata.normalize('NFKD', nombre)
    normalizado = ''.join(c for c in normalizado if not unicodedata.combining(c))

    # Convertir a minúsculas y reemplazar espacios/caracteres especiales
    normalizado = normalizado.lower()
    normalizado = re.sub(r'[^a-z0-9]+', '_', normalizado)
    normalizado = normalizado.strip('_')

    return normalizado


def _extraer_confianza(boletin_texto: str) -> Optional[str]:
    """
    Extrae el nivel de confianza del texto del boletín.

    Args:
        boletin_texto: Texto completo del boletín

    Returns:
        str: 'Alta', 'Media' o 'Baja', o None si no se encuentra
    """
    if not boletin_texto:
        return None

    match = re.search(r'CONFIANZA:\s*(Alta|Media|Baja)', boletin_texto, re.IGNORECASE)
    return match.group(1).capitalize() if match else None


def _extraer_nivel(boletin_texto: str, patron: str) -> Optional[int]:
    """
    Extrae un nivel EAWS del boletín usando el patrón dado.

    Args:
        boletin_texto: Texto del boletín
        patron: Patrón regex con grupo de captura del nivel

    Returns:
        int: Nivel EAWS (1-5) o None
    """
    if not boletin_texto:
        return None
    match = re.search(patron, boletin_texto)
    if match:
        nivel = int(match.group(1))
        return nivel if 1 <= nivel <= 5 else None
    return None


def _datos_satelitales_disponibles(tools_llamadas: list) -> bool:
    """
    Determina si había datos satelitales disponibles en la sesión.

    Args:
        tools_llamadas: Lista de llamadas a tools con sus resultados

    Returns:
        bool: True si se obtuvo datos satelitales disponibles
    """
    nombres_tools = [t.get("tool", "") for t in tools_llamadas]
    return "monitorear_nieve" in nombres_tools or "procesar_ndsi" in nombres_tools


def _extraer_resultado_tool(tools_llamadas: list, nombre_tool: str) -> dict:
    """
    Extrae el resultado de una tool específica desde tools_llamadas.

    Busca la última ejecución del tool indicado y retorna su resultado.
    Compatible con el campo 'resultado' añadido en base_subagente v3.1.

    Args:
        tools_llamadas: Lista de dicts con {tool, resultado, ...}
        nombre_tool: Nombre del tool a buscar

    Returns:
        dict con el resultado, o {} si no se encontró o no tiene resultado
    """
    for entrada in reversed(tools_llamadas):
        if entrada.get("tool") == nombre_tool:
            resultado = entrada.get("resultado", {})
            if isinstance(resultado, dict):
                return resultado
    return {}


def _construir_campos_subagentes(tools_llamadas: list, resultado_boletin: dict) -> dict:
    """
    Extrae campos estructurados de subagentes desde tools_llamadas.

    Combina datos de tools_llamadas (con resultado) y resultados_subagentes
    (resumen sin datos estructurados) para poblar los campos v3 de BigQuery.

    Returns:
        dict con todos los campos estructurados para la fila BQ
    """
    # Intentar desde tools_llamadas (fuente primaria — v3.1+)
    # Nombres de tools exactos como están registrados en _cargar_ejecutores()
    res_dem = _extraer_resultado_tool(tools_llamadas, "analizar_dem")
    res_pinn = _extraer_resultado_tool(tools_llamadas, "calcular_pinn")
    res_vit = _extraer_resultado_tool(tools_llamadas, "analizar_vit")
    res_ventanas = _extraer_resultado_tool(tools_llamadas, "detectar_ventanas_criticas")
    res_condiciones = _extraer_resultado_tool(tools_llamadas, "obtener_condiciones_actuales_meteo")
    res_nlp_sint = _extraer_resultado_tool(tools_llamadas, "sintetizar_conocimiento_historico")
    res_patrones = _extraer_resultado_tool(tools_llamadas, "extraer_patrones_riesgo")

    # Extraer viento_kmh desde condiciones (viene en m/s → convertir)
    viento_ms = (res_condiciones.get("condiciones") or {}).get("velocidad_viento_ms")
    viento_kmh = round(viento_ms * 3.6, 1) if viento_ms is not None else None

    # estado_pinn: 'calcular_pinn' retorna 'estado_manto' (nombre del estado)
    estado_pinn = res_pinn.get("estado_manto")

    # factor_seguridad: 'calcular_pinn' retorna 'factor_seguridad_mohr_coulomb'
    fs = res_pinn.get("factor_seguridad_mohr_coulomb")

    # fuente_gradiente: viene en metricas_pinn dentro de analizar_dem
    metricas_pinn = res_dem.get("metricas_pinn") or {}
    fuente_gradiente = metricas_pinn.get("fuente_gradiente")

    # factor_meteorologico: 'detectar_ventanas_criticas' retorna 'factor_meteorologico_eaws'
    factor_meteo = res_ventanas.get("factor_meteorologico_eaws")

    # num_ventanas_criticas: campo directo en ventanas
    num_ventanas = res_ventanas.get("num_ventanas_criticas")

    # score_anomalia_vit: 'analizar_vit' retorna 'score_anomalia'
    score_vit = res_vit.get("score_anomalia")

    return {
        "estado_pinn": estado_pinn,
        "factor_seguridad_pinn": fs,
        "fuente_gradiente_pinn": fuente_gradiente,
        "datos_topograficos_ok": res_dem.get("disponible"),
        "estado_vit": res_vit.get("estado_vit"),
        "score_anomalia_vit": score_vit,
        "factor_meteorologico": factor_meteo,
        "ventanas_criticas": num_ventanas,
        "datos_meteorologicos_ok": res_condiciones.get("disponible"),
        "viento_kmh": viento_kmh,
        "relatos_analizados": res_nlp_sint.get("total_relatos_analizados"),
        "indice_riesgo_historico": res_nlp_sint.get("indice_riesgo_ajustado"),
        "tipo_alud_predominante": res_nlp_sint.get("tipo_alud_predominante"),
        "confianza_historica": res_nlp_sint.get("confianza"),
        "patrones_nlp": json.dumps(
            res_patrones.get("frecuencias_terminos") or [],
            ensure_ascii=False, default=str
        ),
    }


def _cargar_schema_bigquery() -> list:
    """
    Carga el schema de BigQuery desde el archivo JSON.

    Returns:
        Lista de SchemaField de BigQuery
    """
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_json = json.load(f)

    schema = []
    tipos_bigquery = {
        'STRING': bigquery.enums.SqlTypeNames.STRING,
        'INT64': bigquery.enums.SqlTypeNames.INT64,
        'FLOAT64': bigquery.enums.SqlTypeNames.FLOAT64,
        'BOOL': bigquery.enums.SqlTypeNames.BOOL,
        'TIMESTAMP': bigquery.enums.SqlTypeNames.TIMESTAMP,
    }

    for campo in schema_json:
        schema.append(bigquery.SchemaField(
            name=campo['name'],
            field_type=campo['type'],
            mode=campo.get('mode', 'NULLABLE'),
            description=campo.get('description', '')
        ))

    return schema


def _asegurar_tabla_bigquery(cliente_bq: bigquery.Client) -> None:
    """
    Crea la tabla boletines_riesgo si no existe.

    Args:
        cliente_bq: Cliente de BigQuery inicializado
    """
    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA_BOLETINES}"

    try:
        cliente_bq.get_table(tabla_ref)
        logger.info(f"Tabla {tabla_ref} ya existe")
    except NotFound:
        logger.info(f"Creando tabla {tabla_ref}...")
        schema = _cargar_schema_bigquery()
        tabla = bigquery.Table(tabla_ref, schema=schema)
        tabla.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="fecha_emision"
        )
        cliente_bq.create_table(tabla)
        logger.info(f"Tabla {tabla_ref} creada exitosamente")


def _ya_existe_boletin(cliente_bq: bigquery.Client, nombre_ubicacion: str, fecha: datetime) -> bool:
    """Verifica si ya existe un boletín para la misma ubicación y fecha."""
    sql = f"""
        SELECT COUNT(*) AS total
        FROM `{GCP_PROJECT}.{DATASET}.{TABLA_BOLETINES}`
        WHERE nombre_ubicacion = @ubicacion
          AND DATE(fecha_emision) = @fecha
    """
    job = cliente_bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("ubicacion", "STRING", nombre_ubicacion),
                bigquery.ScalarQueryParameter("fecha", "DATE", fecha.date().isoformat()),
            ]
        )
    )
    filas = list(job.result())
    return filas[0]["total"] > 0


def _eliminar_boletin_existente(
    cliente_bq: bigquery.Client, nombre_ubicacion: str, fecha: datetime
) -> None:
    """Elimina boletines existentes para la ubicación en la misma fecha (para upsert)."""
    sql = f"""
        DELETE FROM `{GCP_PROJECT}.{DATASET}.{TABLA_BOLETINES}`
        WHERE nombre_ubicacion = @ubicacion
          AND DATE(fecha_emision) = @fecha
    """
    job = cliente_bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("ubicacion", "STRING", nombre_ubicacion),
                bigquery.ScalarQueryParameter("fecha", "DATE", fecha.date().isoformat()),
            ]
        )
    )
    job.result()  # Esperar a que el DELETE termine antes de insertar
    logger.info(f"Boletín previo eliminado para {nombre_ubicacion} ({fecha.date()}) — upsert")


def guardar_boletin(resultado_boletin: dict) -> dict:
    """
    Guarda un boletín en BigQuery y GCS.

    Args:
        resultado_boletin: Dict retornado por AgenteRiesgoAvalancha.generar_boletin()

    Returns:
        dict con rutas de almacenamiento y estado

    Raises:
        ErrorAlmacenamiento: Si falla el almacenamiento en ambos destinos
    """
    if resultado_boletin.get("error"):
        logger.warning(
            f"Boletín con error para {resultado_boletin.get('ubicacion')}: "
            f"{resultado_boletin.get('error')}"
        )
        return {"guardado": False, "razon": "Boletín con error no se guarda"}

    nombre_ubicacion = resultado_boletin.get("ubicacion", "desconocida")
    boletin_texto = resultado_boletin.get("boletin", "")
    tools_llamadas = resultado_boletin.get("tools_llamadas", [])
    timestamp_str = resultado_boletin.get("timestamp", datetime.now(timezone.utc).isoformat())

    logger.info(f"Guardando boletín para: {nombre_ubicacion}")

    # Parsear timestamp
    try:
        fecha_emision = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        fecha_emision = datetime.now(timezone.utc)

    # Extraer datos del boletín — fuente primaria: tool redactar_boletin_eaws
    res_boletin_tool = _extraer_resultado_tool(tools_llamadas, "redactar_boletin_eaws")
    res_clasificar_tool = _extraer_resultado_tool(tools_llamadas, "clasificar_riesgo_eaws_integrado")

    nivel_24h = (
        resultado_boletin.get("nivel_eaws_24h")
        or res_boletin_tool.get("nivel_eaws_24h")
        or _extraer_nivel(boletin_texto, r'24h\s*[→\-]\s*(\d)')
    )
    nivel_48h = (
        res_boletin_tool.get("nivel_eaws_48h")
        or _extraer_nivel(boletin_texto, r'48h\s*[→\-]\s*(\d)')
    )
    nivel_72h = (
        res_boletin_tool.get("nivel_eaws_72h")
        or _extraer_nivel(boletin_texto, r'72h\s*[→\-]\s*(\d)')
    )
    confianza = (
        res_boletin_tool.get("confianza")
        or _extraer_confianza(boletin_texto)
    )

    # Nombre del nivel desde la tool de clasificación
    nombre_nivel_24h = res_clasificar_tool.get("nombre_nivel_24h")

    errores = []

    # ===== GUARDAR EN BIGQUERY =====
    try:
        cliente_bq = bigquery.Client(project=GCP_PROJECT)
        _asegurar_tabla_bigquery(cliente_bq)

        # Extraer campos estructurados desde tools_llamadas (v3.1) o resumen (fallback)
        campos_sa = _construir_campos_subagentes(tools_llamadas, resultado_boletin)

        fila = {
            "nombre_ubicacion": nombre_ubicacion,
            "fecha_emision": fecha_emision.isoformat(),
            "nivel_eaws_24h": nivel_24h,
            "nivel_eaws_48h": nivel_48h,
            "nivel_eaws_72h": nivel_72h,
            "nombre_nivel_24h": nombre_nivel_24h,
            "boletin_texto": boletin_texto,
            "tools_llamadas": json.dumps(tools_llamadas, ensure_ascii=False, default=str),
            "iteraciones": resultado_boletin.get("iteraciones"),
            "duracion_segundos": resultado_boletin.get("duracion_segundos"),
            "datos_satelitales_disponibles": _datos_satelitales_disponibles(tools_llamadas),
            "confianza": confianza,
            "modelo": resultado_boletin.get("modelo"),
            # Campos v3 — arquitectura multi-agente
            "arquitectura": resultado_boletin.get("arquitectura"),
            "estado_pinn": campos_sa["estado_pinn"],
            "factor_seguridad_pinn": campos_sa["factor_seguridad_pinn"],
            "estado_vit": campos_sa["estado_vit"],
            "score_anomalia_vit": campos_sa["score_anomalia_vit"],
            "factor_meteorologico": campos_sa["factor_meteorologico"],
            "ventanas_criticas": campos_sa["ventanas_criticas"],
            "relatos_analizados": campos_sa["relatos_analizados"],
            "indice_riesgo_historico": campos_sa["indice_riesgo_historico"],
            "tipo_alud_predominante": campos_sa["tipo_alud_predominante"],
            "patrones_nlp": campos_sa["patrones_nlp"],
            "confianza_historica": campos_sa["confianza_historica"],
            "subagentes_ejecutados": json.dumps(resultado_boletin.get("subagentes_ejecutados", []), ensure_ascii=False),
            "duracion_por_subagente": json.dumps(resultado_boletin.get("duracion_por_subagente", {}), ensure_ascii=False, default=str),
            # Campos de ablación y trazabilidad
            "datos_topograficos_ok": campos_sa["datos_topograficos_ok"],
            "datos_meteorologicos_ok": campos_sa["datos_meteorologicos_ok"],
            "version_prompts": resultado_boletin.get("version_prompts"),
            "fuente_gradiente_pinn": campos_sa["fuente_gradiente_pinn"],
            "fuente_tamano_eaws": resultado_boletin.get("fuente_tamano_eaws"),
            "viento_kmh": campos_sa["viento_kmh"],
            "subagentes_degradados": json.dumps(
                resultado_boletin.get("subagentes_degradados", [])
            ),
        }

        tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA_BOLETINES}"

        # Upsert: eliminar boletín previo si existe para la misma ubicación+fecha
        if _ya_existe_boletin(cliente_bq, nombre_ubicacion, fecha_emision):
            _eliminar_boletin_existente(cliente_bq, nombre_ubicacion, fecha_emision)

        errores_bq = cliente_bq.insert_rows_json(tabla_ref, [fila])

        if errores_bq:
            msg = f"Error al insertar en BigQuery: {errores_bq}"
            logger.error(msg)
            errores.append(("bigquery", msg))
        else:
            logger.info(f"Boletín guardado en BigQuery: {tabla_ref}")

    except Exception as e:
        msg = f"Excepción al guardar en BigQuery: {e}"
        logger.error(msg)
        errores.append(("bigquery", msg))

    # ===== GUARDAR EN GCS =====
    uri_gcs = None
    try:
        cliente_gcs = storage.Client(project=GCP_PROJECT)
        bucket = cliente_gcs.bucket(NOMBRE_BUCKET)

        ubicacion_normalizada = _normalizar_ubicacion(nombre_ubicacion)
        fecha_path = fecha_emision.strftime("%Y/%m/%d")
        timestamp_archivo = fecha_emision.strftime("%Y%m%d_%H%M%S")

        ruta_gcs = (
            f"{ubicacion_normalizada}/boletines/"
            f"{fecha_path}/"
            f"{timestamp_archivo}.json"
        )

        contenido = json.dumps(resultado_boletin, ensure_ascii=False, default=str, indent=2)
        blob = bucket.blob(ruta_gcs)
        blob.upload_from_string(contenido, content_type="application/json")

        uri_gcs = f"gs://{NOMBRE_BUCKET}/{ruta_gcs}"
        logger.info(f"Boletín guardado en GCS: {uri_gcs}")

    except Exception as e:
        msg = f"Excepción al guardar en GCS: {e}"
        logger.error(msg)
        errores.append(("gcs", msg))

    # Resultado del almacenamiento
    guardado_bq = not any(d == "bigquery" for d, _ in errores)
    guardado_gcs = uri_gcs is not None

    return {
        "guardado": guardado_bq or guardado_gcs,
        "guardado_bigquery": guardado_bq,
        "guardado_gcs": guardado_gcs,
        "uri_gcs": uri_gcs,
        "errores": errores,
        "nivel_24h": nivel_24h,
        "confianza": confianza
    }
