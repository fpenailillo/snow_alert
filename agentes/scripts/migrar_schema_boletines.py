#!/usr/bin/env python3
"""
Migración del schema de boletines_riesgo: 27 → 33 campos.

Agrega 6 campos de ablación y trazabilidad que fueron añadidos
en la fase C4 (2026-03-17) pero que no existían cuando la tabla
fue creada originalmente con 27 campos.

Campos nuevos:
  - datos_topograficos_ok (BOOL)
  - datos_meteorologicos_ok (BOOL)
  - version_prompts (STRING)
  - fuente_gradiente_pinn (STRING)
  - fuente_tamano_eaws (STRING)
  - viento_kmh (FLOAT64)
  - subagentes_degradados (STRING)

Uso:
  python migrar_schema_boletines.py [--dry-run] [--verificar]

Requiere: gcloud auth application-default login
"""

import argparse
import json
import logging
import os
import sys

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT") or os.environ.get("ID_PROYECTO", "climas-chileno")
DATASET = os.environ.get("DATASET_ID", "clima")
TABLA = "boletines_riesgo"
TABLA_COMPLETA = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'salidas', 'schema_boletines.json'
)

# Los 7 campos nuevos de C4 + degradación graceful
CAMPOS_NUEVOS = {
    "datos_topograficos_ok",
    "datos_meteorologicos_ok",
    "version_prompts",
    "fuente_gradiente_pinn",
    "fuente_tamano_eaws",
    "viento_kmh",
    "subagentes_degradados",
}


def obtener_campos_actuales(cliente: bigquery.Client) -> set:
    """Obtiene los nombres de campos actuales de la tabla en BQ."""
    try:
        tabla = cliente.get_table(TABLA_COMPLETA)
        return {campo.name for campo in tabla.schema}
    except NotFound:
        logger.error(f"Tabla {TABLA_COMPLETA} no existe")
        sys.exit(1)


def cargar_schema_objetivo() -> list:
    """Carga el schema objetivo desde schema_boletines.json."""
    ruta = os.path.abspath(SCHEMA_PATH)
    if not os.path.exists(ruta):
        logger.error(f"Schema no encontrado: {ruta}")
        sys.exit(1)

    with open(ruta, 'r') as f:
        campos_json = json.load(f)

    schema = []
    for campo in campos_json:
        schema.append(bigquery.SchemaField(
            name=campo["name"],
            field_type=campo["type"],
            mode=campo.get("mode", "NULLABLE"),
            description=campo.get("description", ""),
        ))
    return schema


def verificar(cliente: bigquery.Client):
    """Muestra el estado actual de la tabla vs schema objetivo."""
    campos_bq = obtener_campos_actuales(cliente)
    schema_obj = cargar_schema_objetivo()
    campos_objetivo = {c.name for c in schema_obj}

    faltantes = campos_objetivo - campos_bq
    extras = campos_bq - campos_objetivo

    print(f"\n{'='*60}")
    print(f"  Tabla: {TABLA_COMPLETA}")
    print(f"  Campos en BQ:     {len(campos_bq)}")
    print(f"  Campos objetivo:  {len(campos_objetivo)}")
    print(f"{'='*60}")

    if faltantes:
        print(f"\n  ⚠️  Campos FALTANTES ({len(faltantes)}):")
        for c in sorted(faltantes):
            marcador = " ← C4" if c in CAMPOS_NUEVOS else ""
            print(f"    - {c}{marcador}")
    else:
        print("\n  ✅ Todos los campos del schema están presentes")

    if extras:
        print(f"\n  ℹ️  Campos EXTRA en BQ (no en schema):")
        for c in sorted(extras):
            print(f"    - {c}")

    print()


def migrar(cliente: bigquery.Client, dry_run: bool = False):
    """Ejecuta la migración agregando campos faltantes."""
    campos_bq = obtener_campos_actuales(cliente)
    schema_obj = cargar_schema_objetivo()
    campos_objetivo = {c.name for c in schema_obj}

    faltantes = campos_objetivo - campos_bq
    if not faltantes:
        logger.info("✅ No hay campos faltantes — tabla ya tiene 33 campos")
        return

    logger.info(f"Campos a agregar: {sorted(faltantes)}")

    if dry_run:
        logger.info("[DRY RUN] No se ejecutarán cambios")
        for campo in schema_obj:
            if campo.name in faltantes:
                logger.info(f"  + {campo.name} ({campo.field_type}, {campo.mode}): {campo.description}")
        return

    # BigQuery solo permite agregar campos NULLABLE al final
    tabla = cliente.get_table(TABLA_COMPLETA)
    schema_actual = list(tabla.schema)

    for campo in schema_obj:
        if campo.name in faltantes:
            if campo.mode == "REQUIRED":
                logger.warning(
                    f"Campo {campo.name} es REQUIRED — BQ no permite agregar "
                    f"REQUIRED a tabla existente. Cambiando a NULLABLE."
                )
                campo = bigquery.SchemaField(
                    name=campo.name,
                    field_type=campo.field_type,
                    mode="NULLABLE",
                    description=campo.description,
                )
            schema_actual.append(campo)
            logger.info(f"  + {campo.name} ({campo.field_type})")

    tabla.schema = schema_actual
    cliente.update_table(tabla, ["schema"])

    # Verificar
    tabla_actualizada = cliente.get_table(TABLA_COMPLETA)
    logger.info(
        f"✅ Migración completada: {len(tabla_actualizada.schema)} campos "
        f"(+{len(faltantes)} nuevos)"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Migrar schema boletines_riesgo de 27 a 33 campos"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Mostrar cambios sin ejecutarlos'
    )
    parser.add_argument(
        '--verificar', action='store_true',
        help='Solo verificar estado actual vs objetivo'
    )
    args = parser.parse_args()

    cliente = bigquery.Client(project=GCP_PROJECT)

    if args.verificar:
        verificar(cliente)
    else:
        migrar(cliente, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
