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


# Constantes
GCP_PROJECT = "climas-chileno"
DATASET = "clima"
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
    # Esta info no está directamente en tools_llamadas (solo inputs),
    # usamos heurística: si se llamó monitorear_nieve, asumimos True
    # (si hubiese fallado, Claude lo habría indicado en el boletín)
    nombres_tools = [t.get("tool", "") for t in tools_llamadas]
    return "monitorear_nieve" in nombres_tools


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

    # Extraer datos del boletín
    nivel_24h = resultado_boletin.get("nivel_eaws_24h") or _extraer_nivel(
        boletin_texto, r'24h\s*[→\-]\s*(\d)'
    )
    nivel_48h = _extraer_nivel(boletin_texto, r'48h\s*[→\-]\s*(\d)')
    nivel_72h = _extraer_nivel(boletin_texto, r'72h\s*[→\-]\s*(\d)')
    confianza = _extraer_confianza(boletin_texto)

    # Extraer nombre del nivel desde las tools_llamadas
    nombre_nivel_24h = None
    for tool_info in tools_llamadas:
        if tool_info.get("tool") == "clasificar_riesgo_eaws":
            # El nombre del nivel viene en el resultado de la tool, no en los inputs
            break

    errores = []

    # ===== GUARDAR EN BIGQUERY =====
    try:
        cliente_bq = bigquery.Client(project=GCP_PROJECT)
        _asegurar_tabla_bigquery(cliente_bq)

        # Extraer resultados de subagentes para campos v3
        resultados_sa = resultado_boletin.get("resultados_subagentes", {})
        res_topo = resultados_sa.get("topografico", {})
        res_sat = resultados_sa.get("satelital", {})
        res_meteo = resultados_sa.get("meteorologico", {})
        res_nlp = resultados_sa.get("nlp", {})

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
            "estado_pinn": res_topo.get("estado_pinn"),
            "factor_seguridad_pinn": res_topo.get("factor_seguridad_pinn"),
            "estado_vit": res_sat.get("estado_vit"),
            "score_anomalia_vit": res_sat.get("score_anomalia_vit"),
            "factor_meteorologico": res_meteo.get("factor_meteorologico"),
            "ventanas_criticas": res_meteo.get("ventanas_criticas"),
            "relatos_analizados": res_nlp.get("total_relatos_analizados"),
            "indice_riesgo_historico": res_nlp.get("indice_riesgo_historico"),
            "tipo_alud_predominante": res_nlp.get("tipo_alud_predominante"),
            "patrones_nlp": json.dumps(res_nlp.get("patrones", []), ensure_ascii=False, default=str) if res_nlp.get("patrones") else None,
            "confianza_historica": res_nlp.get("confianza"),
            "subagentes_ejecutados": json.dumps(resultado_boletin.get("subagentes_ejecutados", []), ensure_ascii=False),
            "duracion_por_subagente": json.dumps(resultado_boletin.get("duracion_por_subagente", {}), ensure_ascii=False, default=str),
            # Campos de ablación y trazabilidad
            "datos_topograficos_ok": res_topo.get("disponible"),
            "datos_meteorologicos_ok": res_meteo.get("disponible"),
            "version_prompts": resultado_boletin.get("version_prompts"),
            "fuente_gradiente_pinn": res_topo.get("fuente_gradiente"),
            "fuente_tamano_eaws": resultado_boletin.get("fuente_tamano_eaws"),
            "viento_kmh": res_meteo.get("viento_kmh"),
            "subagentes_degradados": json.dumps(
                resultado_boletin.get("subagentes_degradados", [])
            ),
        }

        tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA_BOLETINES}"
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
            f"boletines/{ubicacion_normalizada}/"
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
