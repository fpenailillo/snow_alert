"""
ETL Rutas Andeshandbook → BigQuery

Carga los registros finales exportados desde Databricks (dos CSVs) a la
tabla climas-chileno.clima.relatos_montanistas en BigQuery.

Archivos de entrada:
    - andes_handbook_routes.csv      : datos estructurados de cada ruta/cerro
    - andes_handbook_routes_llm.csv  : análisis LLM por ruta (misma fuente)

Los dos CSVs se unen por nombre de ruta: el campo `name` del routes CSV
coincide con el prefijo del campo `data` del LLM CSV (hasta " Presentacion").

Schema BQ: ver schema_relatos.json (37 campos)

Requisitos:
    pip install google-cloud-bigquery
    gcloud auth application-default login

Uso:
    # Carga normal (routes + LLM)
    python datos/relatos/cargar_relatos.py \\
        --routes datos/relatos/andes_handbook_routes.csv \\
        --llm    datos/relatos/andes_handbook_routes_llm.csv

    # Solo routes (sin enriquecimiento LLM)
    python datos/relatos/cargar_relatos.py \\
        --routes datos/relatos/andes_handbook_routes.csv

    # Verificar tabla
    python datos/relatos/cargar_relatos.py --verificar

    # Crear tabla vacía
    python datos/relatos/cargar_relatos.py --crear-tabla

    # Dry-run (no carga en BQ)
    python datos/relatos/cargar_relatos.py \\
        --routes andes_handbook_routes.csv \\
        --llm    andes_handbook_routes_llm.csv \\
        --dry-run
"""

import argparse
import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Configuración ────────────────────────────────────────────────────────────

GCP_PROJECT = os.environ.get("GCP_PROJECT") or os.environ.get("ID_PROYECTO", "climas-chileno")
DATASET = os.environ.get("DATASET_ID", "clima")
TABLA = "relatos_montanistas"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_relatos.json")

# ─── Parseo del CSV de rutas ──────────────────────────────────────────────────

def _parsear_bool(valor: str) -> Optional[bool]:
    """Convierte 'true'/'false'/'null' → bool o None."""
    if not valor or valor.lower() in ("null", "none", ""):
        return None
    return valor.lower() == "true"


def _parsear_float(valor: str) -> Optional[float]:
    """Convierte string numérico → float o None."""
    if not valor or valor.lower() in ("null", "none", ""):
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _parsear_int(valor: str) -> Optional[int]:
    """Convierte string numérico → int o None."""
    if not valor or valor.lower() in ("null", "none", ""):
        return None
    try:
        return int(float(valor))
    except ValueError:
        return None


def _parsear_timestamp(valor: str) -> Optional[str]:
    """Normaliza timestamp ISO a formato BigQuery."""
    if not valor or valor.lower() in ("null", "none", ""):
        return None
    # BigQuery acepta ISO 8601; limpiar espacios
    return valor.strip()


def cargar_routes_csv(ruta_csv: str) -> dict:
    """
    Lee andes_handbook_routes.csv y retorna dict {name → registro normalizado}.

    Columnas esperadas:
        url, route_id, scraped_timestamp, name, location, sector,
        nearest_city, elevation, first_ascent_year, first_ascensionists,
        latitude, longitude, access_type, mountain_characteristics,
        nearby_excursions, description, avalanche_info, has_avalanche_info,
        is_alta_montana, has_glacier, is_volcano, avalanche_priority
    """
    registros = {}
    try:
        with open(ruta_csv, "r", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                nombre = fila.get("name", "").strip()
                if not nombre:
                    continue

                route_id = _parsear_int(fila.get("route_id", ""))
                if route_id is None:
                    logger.warning(f"route_id inválido para '{nombre}', omitiendo.")
                    continue

                registros[nombre] = {
                    "route_id": route_id,
                    "url": fila.get("url", "").strip() or None,
                    "scraped_timestamp": _parsear_timestamp(fila.get("scraped_timestamp", "")),
                    "name": nombre,
                    "location": fila.get("location", "").strip() or None,
                    "sector": fila.get("sector", "").strip() or None,
                    "nearest_city": fila.get("nearest_city", "").strip() or None,
                    "elevation": _parsear_float(fila.get("elevation", "")),
                    "first_ascent_year": fila.get("first_ascent_year", "").strip() or None,
                    "first_ascensionists": fila.get("first_ascensionists", "").strip() or None,
                    "latitude": fila.get("latitude", "").strip() or None,
                    "longitude": fila.get("longitude", "").strip() or None,
                    "access_type": fila.get("access_type", "").strip() or None,
                    "mountain_characteristics": fila.get("mountain_characteristics", "").strip() or None,
                    "nearby_excursions": fila.get("nearby_excursions", "").strip() or None,
                    "description": fila.get("description", "").strip() or None,
                    "avalanche_info": fila.get("avalanche_info", "").strip() or None,
                    "has_avalanche_info": _parsear_bool(fila.get("has_avalanche_info", "")),
                    "is_alta_montana": _parsear_bool(fila.get("is_alta_montana", "")),
                    "has_glacier": _parsear_bool(fila.get("has_glacier", "")),
                    "is_volcano": _parsear_bool(fila.get("is_volcano", "")),
                    "avalanche_priority": _parsear_bool(fila.get("avalanche_priority", "")),
                    # Campos LLM se rellenan después
                    "llm_tipo_actividad": None,
                    "llm_modalidad": None,
                    "llm_nivel_riesgo": None,
                    "llm_puntuacion_riesgo": None,
                    "llm_experiencia_requerida": None,
                    "llm_resumen": None,
                    "llm_confianza_extraccion": None,
                    "llm_factores_riesgo": [],
                    "llm_tipos_terreno": [],
                    "llm_equipamiento_tecnico": [],
                    "llm_palabras_clave": [],
                    "analisis_llm_json": None,
                    "fuente": "andeshandbook",
                    "fecha_carga": datetime.now(timezone.utc).isoformat(),
                }

    except FileNotFoundError:
        logger.error(f"Archivo no encontrado: {ruta_csv}")
    except Exception as e:
        logger.error(f"Error leyendo routes CSV: {e}")

    logger.info(f"Routes CSV: {len(registros)} rutas cargadas desde '{ruta_csv}'")
    return registros


# ─── Parseo del CSV LLM ───────────────────────────────────────────────────────

def _extraer_nombre_desde_data(texto_data: str) -> str:
    """
    Extrae el nombre de la ruta desde el campo `data` del LLM CSV.

    El campo `data` tiene el formato:
        "Cerro La Paloma (4910m) - Andeshandbook Presentacion ..."

    El nombre corresponde a todo lo que precede a " Presentacion ".
    Si no hay "Presentacion", se toma hasta el primer salto de línea o
    los primeros 120 caracteres.
    """
    texto = texto_data.strip()
    sep = " Presentacion "
    if sep in texto:
        return texto.split(sep)[0].strip()
    # Fallback: hasta salto de línea
    if "\n" in texto:
        return texto.split("\n")[0].strip()
    return texto[:120].strip()


def _enriquecer_con_llm(registros: dict, ruta_llm_csv: str) -> int:
    """
    Lee andes_handbook_routes_llm.csv y enriquece los registros con los
    campos del análisis LLM, uniendo por nombre de ruta.

    Retorna el número de rutas enriquecidas.
    """
    enriquecidos = 0
    no_encontrados = 0

    try:
        with open(ruta_llm_csv, "r", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                data_texto = fila.get("data", "")
                analisis_str = fila.get("analisis_ruta", "")

                if not data_texto or not analisis_str:
                    continue

                nombre = _extraer_nombre_desde_data(data_texto)

                if nombre not in registros:
                    no_encontrados += 1
                    if no_encontrados <= 5:
                        logger.debug(f"Sin match LLM para: '{nombre[:60]}'")
                    continue

                try:
                    analisis = json.loads(analisis_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON LLM inválido para '{nombre[:60]}': {e}")
                    continue

                reg = registros[nombre]

                # resumen
                resumen = analisis.get("resumen", {})
                reg["llm_resumen"] = resumen.get("descripcion_breve") or None
                reg["llm_tipo_actividad"] = resumen.get("tipo_actividad") or None
                reg["llm_modalidad"] = resumen.get("modalidad") or None

                # evaluacion_riesgo
                riesgo = analisis.get("evaluacion_riesgo", {})
                reg["llm_nivel_riesgo"] = riesgo.get("nivel_riesgo") or None
                reg["llm_experiencia_requerida"] = riesgo.get("experiencia_requerida") or None
                puntuacion = riesgo.get("puntuacion_numerica")
                reg["llm_puntuacion_riesgo"] = _parsear_float(str(puntuacion)) if puntuacion is not None else None
                reg["llm_factores_riesgo"] = [
                    str(f) for f in riesgo.get("factores_riesgo", []) if f
                ]

                # caracteristicas_tecnicas
                tecnicas = analisis.get("caracteristicas_tecnicas", {})
                reg["llm_tipos_terreno"] = [
                    str(t) for t in tecnicas.get("tipos_terreno", []) if t
                ]

                # equipamiento
                equipamiento = analisis.get("equipamiento_requerido", {})
                reg["llm_equipamiento_tecnico"] = [
                    str(e) for e in equipamiento.get("equipamiento_tecnico", []) if e
                ]

                # metadatos
                metadatos = analisis.get("metadatos_analisis", {})
                confianza = metadatos.get("confianza_extraccion")
                reg["llm_confianza_extraccion"] = _parsear_float(str(confianza)) if confianza is not None else None
                reg["llm_palabras_clave"] = [
                    str(p) for p in metadatos.get("palabras_clave_tecnicas", []) if p
                ]

                # JSON completo serializado
                reg["analisis_llm_json"] = json.dumps(analisis, ensure_ascii=False)

                enriquecidos += 1

    except FileNotFoundError:
        logger.error(f"Archivo LLM CSV no encontrado: {ruta_llm_csv}")
    except Exception as e:
        logger.error(f"Error leyendo LLM CSV: {e}")

    logger.info(
        f"LLM CSV: {enriquecidos} rutas enriquecidas, "
        f"{no_encontrados} sin match en routes CSV"
    )
    return enriquecidos


# ─── BigQuery ─────────────────────────────────────────────────────────────────

def crear_tabla_bigquery():
    """Crea la tabla relatos_montanistas si no existe."""
    from google.cloud import bigquery
    from google.cloud.exceptions import NotFound

    cliente = bigquery.Client(project=GCP_PROJECT)
    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

    try:
        cliente.get_table(tabla_ref)
        logger.info(f"Tabla {tabla_ref} ya existe")
        return
    except NotFound:
        pass

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_json = json.load(f)

    schema = [
        bigquery.SchemaField(
            name=campo["name"],
            field_type=campo["type"],
            mode=campo.get("mode", "NULLABLE"),
            description=campo.get("description", ""),
        )
        for campo in schema_json
    ]

    tabla = bigquery.Table(tabla_ref, schema=schema)
    tabla.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="fecha_carga",
    )
    tabla.clustering_fields = ["location", "is_alta_montana", "avalanche_priority"]

    cliente.create_table(tabla)
    logger.info(f"Tabla {tabla_ref} creada exitosamente")


def cargar_en_bigquery(registros: dict, lote_size: int = 500) -> dict:
    """
    Carga los registros en BigQuery con deduplicación por route_id.

    Args:
        registros : dict {name → registro} producido por cargar_routes_csv
        lote_size : tamaño de cada lote de inserción

    Returns:
        Dict con estadísticas de carga.
    """
    from google.cloud import bigquery

    filas = list(registros.values())
    if not filas:
        return {"insertados": 0, "errores": 0, "duplicados": 0}

    cliente = bigquery.Client(project=GCP_PROJECT)
    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

    # Obtener route_ids existentes para deduplicar
    try:
        sql = f"SELECT route_id FROM `{tabla_ref}`"
        existentes = {row["route_id"] for row in cliente.query(sql).result()}
        logger.info(f"Rutas existentes en BQ: {len(existentes)}")
    except Exception:
        existentes = set()
        logger.info("Tabla vacía o no accesible — cargando todo")

    nuevas = [r for r in filas if r["route_id"] not in existentes]
    duplicados = len(filas) - len(nuevas)
    if duplicados:
        logger.info(f"Omitidas {duplicados} rutas ya existentes en BQ")

    if not nuevas:
        logger.info("No hay rutas nuevas para cargar")
        return {"insertados": 0, "errores": 0, "duplicados": duplicados}

    total_errores = 0
    total_insertados = 0

    for i in range(0, len(nuevas), lote_size):
        lote = nuevas[i : i + lote_size]
        errores = cliente.insert_rows_json(tabla_ref, lote)

        if errores:
            total_errores += len(errores)
            logger.error(f"Errores en lote {i // lote_size + 1}: {errores[:3]}")
        else:
            total_insertados += len(lote)
            logger.info(
                f"Lote {i // lote_size + 1}: {len(lote)} rutas insertadas "
                f"({total_insertados}/{len(nuevas)})"
            )

    return {
        "insertados": total_insertados,
        "errores": total_errores,
        "duplicados": duplicados,
        "total_procesados": len(filas),
    }


def verificar_tabla() -> dict:
    """Verifica el estado de la tabla relatos_montanistas."""
    from google.cloud import bigquery
    from google.cloud.exceptions import NotFound

    cliente = bigquery.Client(project=GCP_PROJECT)
    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

    try:
        tabla = cliente.get_table(tabla_ref)
    except NotFound:
        return {"existe": False, "total": 0}

    sql = f"""
        SELECT
            COUNT(*) as total,
            COUNTIF(has_avalanche_info) as con_info_avalancha,
            COUNTIF(avalanche_priority) as prioridad_avalancha,
            COUNTIF(is_alta_montana) as alta_montana,
            COUNTIF(analisis_llm_json IS NOT NULL) as con_analisis_llm,
            ROUND(AVG(llm_puntuacion_riesgo), 2) as riesgo_promedio,
            MAX(fecha_carga) as ultima_carga
        FROM `{tabla_ref}`
    """
    resultado = list(cliente.query(sql).result())[0]

    sql_paises = f"""
        SELECT
            REGEXP_EXTRACT(location, r'^([^,]+)') as pais,
            COUNT(*) as n
        FROM `{tabla_ref}`
        WHERE location IS NOT NULL
        GROUP BY pais
        ORDER BY n DESC
        LIMIT 10
    """
    paises = {
        row["pais"]: row["n"]
        for row in cliente.query(sql_paises).result()
        if row["pais"]
    }

    return {
        "existe": True,
        "total": resultado["total"],
        "con_info_avalancha": resultado["con_info_avalancha"],
        "prioridad_avalancha": resultado["prioridad_avalancha"],
        "alta_montana": resultado["alta_montana"],
        "con_analisis_llm": resultado["con_analisis_llm"],
        "riesgo_promedio_llm": resultado["riesgo_promedio"],
        "ultima_carga": str(resultado["ultima_carga"]),
        "distribucion_paises": paises,
        "campos": len(tabla.schema),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ETL Rutas Andeshandbook (Databricks CSV) → BigQuery"
    )
    parser.add_argument("--routes", help="CSV de rutas: andes_handbook_routes.csv")
    parser.add_argument("--llm", help="CSV con análisis LLM: andes_handbook_routes_llm.csv")
    parser.add_argument("--crear-tabla", action="store_true", help="Crear tabla BQ si no existe")
    parser.add_argument("--verificar", action="store_true", help="Verificar estado de la tabla")
    parser.add_argument("--dry-run", action="store_true", help="Procesar sin cargar en BQ")
    args = parser.parse_args()

    print("=" * 60)
    print("ETL RUTAS ANDESHANDBOOK → BIGQUERY")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print(f"Tabla: {GCP_PROJECT}.{DATASET}.{TABLA}")
    print("=" * 60)

    if args.verificar:
        print("\nVerificando tabla...")
        estado = verificar_tabla()
        if estado["existe"]:
            print(f"  Total rutas:             {estado['total']:,}")
            print(f"  Con info avalancha:      {estado['con_info_avalancha']:,}")
            print(f"  Prioridad avalancha:     {estado['prioridad_avalancha']:,}")
            print(f"  Alta montaña:            {estado['alta_montana']:,}")
            print(f"  Con análisis LLM:        {estado['con_analisis_llm']:,}")
            print(f"  Riesgo promedio LLM:     {estado['riesgo_promedio_llm']}")
            print(f"  Última carga:            {estado['ultima_carga']}")
            print(f"  Campos en schema:        {estado['campos']}")
            if estado["distribucion_paises"]:
                print("\n  Rutas por país:")
                for pais, n in estado["distribucion_paises"].items():
                    print(f"    {pais}: {n:,}")
        else:
            print("  Tabla no existe. Usar --crear-tabla para crearla.")
        return

    if args.crear_tabla:
        print("\nCreando tabla...")
        crear_tabla_bigquery()
        return

    if not args.routes:
        print("\nEspecificar fuente de datos:")
        print("  --routes andes_handbook_routes.csv      (requerido)")
        print("  --llm    andes_handbook_routes_llm.csv  (opcional, enriquece con LLM)")
        print("  --verificar                             (solo verificar tabla)")
        print("  --crear-tabla                           (crear tabla vacía)")
        return

    # Cargar routes CSV
    registros = cargar_routes_csv(args.routes)
    if not registros:
        print("\nNo se encontraron rutas para cargar.")
        return

    # Enriquecer con LLM si se provee
    if args.llm:
        _enriquecer_con_llm(registros, args.llm)

    # Estadísticas pre-carga
    filas = list(registros.values())
    con_llm = sum(1 for r in filas if r.get("analisis_llm_json"))
    con_avalancha = sum(1 for r in filas if r.get("has_avalanche_info"))
    prioridad = sum(1 for r in filas if r.get("avalanche_priority"))
    alta_montana = sum(1 for r in filas if r.get("is_alta_montana"))

    print(f"\nRutas cargadas:              {len(filas):,}")
    print(f"Con análisis LLM:            {con_llm:,} ({con_llm/len(filas)*100:.1f}%)")
    print(f"Con info de avalanchas:      {con_avalancha:,} ({con_avalancha/len(filas)*100:.1f}%)")
    print(f"Prioridad avalancha:         {prioridad:,} ({prioridad/len(filas)*100:.1f}%)")
    print(f"Alta montaña:                {alta_montana:,} ({alta_montana/len(filas)*100:.1f}%)")

    if args.dry_run:
        print("\n[DRY-RUN] No se cargó en BigQuery. Muestra de 3 rutas:")
        for r in filas[:3]:
            print(f"  [{r['route_id']}] {r['name'][:60]}")
            print(f"    Elevación: {r['elevation']}m | País: {r['location']}")
            print(f"    LLM riesgo: {r['llm_nivel_riesgo']} | Actividad: {r['llm_tipo_actividad']}")
        return

    # Crear tabla si no existe y cargar
    crear_tabla_bigquery()

    print(f"\nCargando {len(filas):,} rutas en BigQuery...")
    resultado = cargar_en_bigquery(registros)

    print(f"\nResultado:")
    print(f"  Insertadas:  {resultado['insertados']:,}")
    print(f"  Duplicadas:  {resultado['duplicados']:,}")
    print(f"  Errores:     {resultado['errores']:,}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
