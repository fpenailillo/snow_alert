"""
ETL de Relatos de Montañistas — Andeshandbook → BigQuery

Carga relatos históricos de montañistas desde archivos JSON/CSV locales
a la tabla clima.relatos_montanistas en BigQuery.

El scraping de Andeshandbook se debe hacer previamente y guardar los
resultados como JSON en datos/relatos/raw/. Este script:
1. Lee los archivos raw (JSON/CSV)
2. Normaliza ubicaciones para matching con el sistema
3. Detecta términos de avalancha en el texto
4. Carga en BigQuery con deduplicación por id_relato

Schema BQ: ver schema_relatos.json (12 campos)

Requisitos:
    pip install google-cloud-bigquery
    gcloud auth application-default login

Uso:
    # Cargar desde directorio de JSONs
    python datos/relatos/cargar_relatos.py --raw-dir datos/relatos/raw/

    # Cargar desde CSV exportado
    python datos/relatos/cargar_relatos.py --csv datos/relatos/relatos_andeshandbook.csv

    # Solo verificar la tabla (sin cargar)
    python datos/relatos/cargar_relatos.py --verificar

    # Crear tabla si no existe
    python datos/relatos/cargar_relatos.py --crear-tabla
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Configuración ────────────────────────────────────────────────────────────

GCP_PROJECT = "climas-chileno"
DATASET = "clima"
TABLA = "relatos_montanistas"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_relatos.json")

# Términos que indican contenido relevante a avalanchas
TERMINOS_AVALANCHA = {
    "avalancha", "alud", "placa", "cornisa", "grieta", "nieve inestable",
    "desprendimiento", "colapso", "whumpf", "whoompf", "capa débil",
    "viento cargado", "placa de viento", "purga", "flujo", "debris",
    "riesgo", "peligro", "inestable", "fractura", "propagación",
    "enterrado", "rescate", "beacon", "arva", "sonda", "pala",
}

# Zonas conocidas del sistema para normalización
ZONAS_SISTEMA = [
    "Portillo", "La Parva", "Valle Nevado", "Farellones", "El Colorado",
    "Yerba Loca", "Juncal", "Plomo", "San Francisco", "Altar",
    "Tupungato", "Aconcagua", "Lo Valdés", "Baños Morales",
    "Cajón del Maipo", "Volcán San José", "Laguna del Inca",
    "Paso Los Libertadores", "Paso Cristo Redentor",
    "Nevados de Chillán", "Volcán Lonquimay", "Volcán Villarrica",
    "Volcán Osorno", "Torres del Paine",
]


# ─── Funciones de normalización ───────────────────────────────────────────────

def generar_id_relato(titulo: str, fecha: str, url: str = "") -> str:
    """Genera ID único para un relato basado en título + fecha + URL."""
    contenido = f"{titulo.strip()}|{fecha}|{url}".lower()
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


def normalizar_texto(texto: str) -> str:
    """Elimina tildes y normaliza caracteres para búsqueda."""
    normalizado = unicodedata.normalize('NFKD', texto)
    normalizado = ''.join(c for c in normalizado if not unicodedata.combining(c))
    return normalizado.lower()


def normalizar_zona(ubicacion: str) -> Optional[str]:
    """
    Intenta mapear una ubicación mencionada en un relato a una zona del sistema.

    Returns:
        Nombre de zona normalizada o None si no hay match
    """
    if not ubicacion:
        return None

    ubicacion_norm = normalizar_texto(ubicacion)

    for zona in ZONAS_SISTEMA:
        zona_norm = normalizar_texto(zona)
        if zona_norm in ubicacion_norm or ubicacion_norm in zona_norm:
            return zona

    # Búsqueda por palabras clave
    palabras_clave = {
        "parva": "La Parva",
        "colorado": "El Colorado",
        "nevado": "Valle Nevado",
        "farellones": "Farellones",
        "portillo": "Portillo",
        "juncal": "Juncal",
        "plomo": "Plomo",
        "yerba loca": "Yerba Loca",
        "cajon del maipo": "Cajón del Maipo",
        "lo valdes": "Lo Valdés",
        "aconcagua": "Aconcagua",
        "tupungato": "Tupungato",
        "chillan": "Nevados de Chillán",
        "villarrica": "Volcán Villarrica",
        "osorno": "Volcán Osorno",
    }

    for clave, zona in palabras_clave.items():
        if clave in ubicacion_norm:
            return zona

    return None


def contiene_terminos_avalancha(texto: str) -> bool:
    """Detecta si el texto contiene términos relacionados a avalanchas."""
    if not texto:
        return False
    texto_lower = texto.lower()
    return any(termino in texto_lower for termino in TERMINOS_AVALANCHA)


def parsear_fecha(fecha_str: str) -> Optional[str]:
    """Parsea fecha desde varios formatos a YYYY-MM-DD."""
    if not fecha_str:
        return None

    formatos = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d de %B de %Y",  # español
        "%B %d, %Y",       # inglés
    ]

    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Intentar extraer año al menos
    match = re.search(r'(\d{4})', fecha_str)
    if match:
        return f"{match.group(1)}-01-01"

    return None


# ─── Carga desde archivos ────────────────────────────────────────────────────

def cargar_desde_json_dir(directorio: str) -> list:
    """
    Carga relatos desde archivos JSON en un directorio.

    Formato esperado por archivo:
    {
        "titulo": "...",
        "texto": "...",
        "fecha": "YYYY-MM-DD",
        "ubicacion": "...",
        "url": "https://...",
        "actividad": "...",
        "autor": "..."
    }

    O una lista de objetos con el mismo formato.
    """
    directorio_path = Path(directorio)
    if not directorio_path.exists():
        logger.error(f"Directorio no existe: {directorio}")
        return []

    relatos = []
    archivos = list(directorio_path.glob("*.json"))
    logger.info(f"Encontrados {len(archivos)} archivos JSON en {directorio}")

    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                datos = json.load(f)

            # Puede ser un solo relato o una lista
            if isinstance(datos, dict):
                datos = [datos]

            for item in datos:
                relato = _normalizar_relato(item)
                if relato:
                    relatos.append(relato)

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error procesando {archivo.name}: {e}")

    logger.info(f"Cargados {len(relatos)} relatos desde JSON")
    return relatos


def cargar_desde_csv(ruta_csv: str) -> list:
    """
    Carga relatos desde CSV.

    Columnas esperadas: titulo, texto, fecha, ubicacion, url, actividad, autor
    """
    relatos = []
    try:
        with open(ruta_csv, 'r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                relato = _normalizar_relato(fila)
                if relato:
                    relatos.append(relato)
    except FileNotFoundError:
        logger.error(f"Archivo CSV no encontrado: {ruta_csv}")
    except Exception as e:
        logger.error(f"Error leyendo CSV: {e}")

    logger.info(f"Cargados {len(relatos)} relatos desde CSV")
    return relatos


def _normalizar_relato(item: dict) -> Optional[dict]:
    """Normaliza un relato crudo al formato de la tabla BQ."""
    titulo = (item.get("titulo") or item.get("title") or "").strip()
    texto = (item.get("texto") or item.get("texto_completo") or item.get("text") or "").strip()
    fecha_raw = item.get("fecha") or item.get("fecha_relato") or item.get("date") or ""
    ubicacion = (item.get("ubicacion") or item.get("ubicacion_mencionada") or item.get("location") or "").strip()
    url = (item.get("url") or item.get("url_fuente") or "").strip()
    actividad = (item.get("actividad") or item.get("activity") or "").strip()
    autor = (item.get("autor") or item.get("author") or "").strip()

    if not titulo:
        return None

    fecha = parsear_fecha(fecha_raw)
    id_relato = generar_id_relato(titulo, fecha or "", url)
    zona = normalizar_zona(ubicacion)

    return {
        "id_relato": id_relato,
        "titulo": titulo,
        "texto_completo": texto or None,
        "fecha_relato": fecha,
        "ubicacion_mencionada": ubicacion or None,
        "zona_normalizada": zona,
        "url_fuente": url or None,
        "fuente": "andeshandbook",
        "actividad": actividad or None,
        "autor": autor or None,
        "fecha_carga": datetime.now(timezone.utc).isoformat(),
        "contiene_terminos_avalancha": contiene_terminos_avalancha(texto),
    }


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

    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_json = json.load(f)

    schema = [
        bigquery.SchemaField(
            name=campo['name'],
            field_type=campo['type'],
            mode=campo.get('mode', 'NULLABLE'),
            description=campo.get('description', '')
        )
        for campo in schema_json
    ]

    tabla = bigquery.Table(tabla_ref, schema=schema)
    tabla.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="fecha_carga"
    )
    tabla.clustering_fields = ["zona_normalizada", "fuente"]

    cliente.create_table(tabla)
    logger.info(f"Tabla {tabla_ref} creada exitosamente")


def cargar_en_bigquery(relatos: list, lote_size: int = 500) -> dict:
    """
    Carga relatos en BigQuery con deduplicación.

    Args:
        relatos: Lista de relatos normalizados
        lote_size: Tamaño del lote para insert

    Returns:
        Dict con estadísticas de carga
    """
    from google.cloud import bigquery

    if not relatos:
        return {"insertados": 0, "errores": 0, "duplicados": 0}

    cliente = bigquery.Client(project=GCP_PROJECT)
    tabla_ref = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

    # Obtener IDs existentes para deduplicar
    try:
        sql = f"SELECT id_relato FROM `{tabla_ref}`"
        existentes = {row["id_relato"] for row in cliente.query(sql).result()}
        logger.info(f"Relatos existentes en BQ: {len(existentes)}")
    except Exception:
        existentes = set()
        logger.info("Tabla vacía o no accesible — cargando todos")

    # Filtrar duplicados
    nuevos = [r for r in relatos if r["id_relato"] not in existentes]
    duplicados = len(relatos) - len(nuevos)

    if duplicados > 0:
        logger.info(f"Omitidos {duplicados} relatos duplicados")

    if not nuevos:
        logger.info("No hay relatos nuevos para cargar")
        return {"insertados": 0, "errores": 0, "duplicados": duplicados}

    # Insertar en lotes
    total_errores = 0
    total_insertados = 0

    for i in range(0, len(nuevos), lote_size):
        lote = nuevos[i:i + lote_size]
        errores = cliente.insert_rows_json(tabla_ref, lote)

        if errores:
            total_errores += len(errores)
            logger.error(f"Errores en lote {i//lote_size + 1}: {errores[:3]}")
        else:
            total_insertados += len(lote)
            logger.info(
                f"Lote {i//lote_size + 1}: {len(lote)} relatos insertados "
                f"({total_insertados}/{len(nuevos)})"
            )

    return {
        "insertados": total_insertados,
        "errores": total_errores,
        "duplicados": duplicados,
        "total_procesados": len(relatos),
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

    # Contar registros
    sql = f"""
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT zona_normalizada) as zonas_unicas,
            COUNTIF(contiene_terminos_avalancha) as con_terminos_avalancha,
            MIN(fecha_relato) as fecha_mas_antigua,
            MAX(fecha_relato) as fecha_mas_reciente,
            MAX(fecha_carga) as ultima_carga
        FROM `{tabla_ref}`
    """
    resultado = list(cliente.query(sql).result())[0]

    # Distribución por zona
    sql_zonas = f"""
        SELECT zona_normalizada, COUNT(*) as n
        FROM `{tabla_ref}`
        WHERE zona_normalizada IS NOT NULL
        GROUP BY zona_normalizada
        ORDER BY n DESC
        LIMIT 20
    """
    zonas = {row["zona_normalizada"]: row["n"] for row in cliente.query(sql_zonas).result()}

    return {
        "existe": True,
        "total": resultado["total"],
        "zonas_unicas": resultado["zonas_unicas"],
        "con_terminos_avalancha": resultado["con_terminos_avalancha"],
        "fecha_mas_antigua": str(resultado["fecha_mas_antigua"]),
        "fecha_mas_reciente": str(resultado["fecha_mas_reciente"]),
        "ultima_carga": str(resultado["ultima_carga"]),
        "distribucion_zonas": zonas,
        "campos": len(tabla.schema),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ETL de relatos Andeshandbook → BigQuery"
    )
    parser.add_argument('--raw-dir', help='Directorio con archivos JSON de relatos')
    parser.add_argument('--csv', help='Archivo CSV con relatos')
    parser.add_argument('--crear-tabla', action='store_true', help='Crear tabla BQ si no existe')
    parser.add_argument('--verificar', action='store_true', help='Verificar estado de la tabla')
    parser.add_argument('--dry-run', action='store_true', help='Procesar sin cargar en BQ')
    args = parser.parse_args()

    print("=" * 60)
    print("ETL RELATOS ANDESHANDBOOK → BIGQUERY")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print(f"Tabla: {GCP_PROJECT}.{DATASET}.{TABLA}")
    print("=" * 60)

    if args.verificar:
        print("\nVerificando tabla...")
        estado = verificar_tabla()
        if estado["existe"]:
            print(f"  Total relatos:           {estado['total']:,}")
            print(f"  Zonas únicas:            {estado['zonas_unicas']}")
            print(f"  Con términos avalancha:  {estado['con_terminos_avalancha']:,}")
            print(f"  Fecha más antigua:       {estado['fecha_mas_antigua']}")
            print(f"  Fecha más reciente:      {estado['fecha_mas_reciente']}")
            print(f"  Última carga:            {estado['ultima_carga']}")
            if estado['distribucion_zonas']:
                print(f"\n  Relatos por zona:")
                for zona, n in estado['distribucion_zonas'].items():
                    print(f"    {zona}: {n}")
        else:
            print("  ⚠ Tabla no existe. Usar --crear-tabla para crearla.")
        return

    if args.crear_tabla:
        print("\nCreando tabla...")
        crear_tabla_bigquery()
        return

    # Cargar relatos
    relatos = []
    if args.raw_dir:
        relatos = cargar_desde_json_dir(args.raw_dir)
    elif args.csv:
        relatos = cargar_desde_csv(args.csv)
    else:
        print("\n⚠ Especificar fuente de datos:")
        print("  --raw-dir datos/relatos/raw/   (directorio con JSONs)")
        print("  --csv relatos.csv              (archivo CSV)")
        print("  --verificar                    (solo verificar tabla)")
        print("  --crear-tabla                  (crear tabla vacía)")
        return

    if not relatos:
        print("\n⚠ No se encontraron relatos para cargar.")
        return

    # Estadísticas pre-carga
    con_avalancha = sum(1 for r in relatos if r.get("contiene_terminos_avalancha"))
    con_zona = sum(1 for r in relatos if r.get("zona_normalizada"))
    print(f"\nRelatos procesados:          {len(relatos)}")
    print(f"Con términos de avalancha:   {con_avalancha} ({con_avalancha/len(relatos)*100:.1f}%)")
    print(f"Con zona normalizada:        {con_zona} ({con_zona/len(relatos)*100:.1f}%)")

    if args.dry_run:
        print("\n[DRY-RUN] No se cargó en BigQuery.")
        print("Muestra de 3 relatos:")
        for r in relatos[:3]:
            print(f"  - {r['titulo'][:60]}...")
            print(f"    Zona: {r['zona_normalizada'] or 'N/A'} | Avalancha: {r['contiene_terminos_avalancha']}")
        return

    # Crear tabla si no existe
    crear_tabla_bigquery()

    # Cargar
    print(f"\nCargando {len(relatos)} relatos en BigQuery...")
    resultado = cargar_en_bigquery(relatos)
    print(f"\nResultado:")
    print(f"  Insertados:  {resultado['insertados']}")
    print(f"  Duplicados:  {resultado['duplicados']}")
    print(f"  Errores:     {resultado['errores']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
