"""
Carga los boletines Snowlab La Parva 2024-2025 a BigQuery.

Fuente: "BOLETINES DE AVALANCHAS — ZONA LA PARVA.pdf"
Autor técnico: Domingo Valdivieso Ducci — Avalanche Operations L2, CAA Member
Fuente original: Andes Consciente / SnowLab / pisteros La Parva

Tabla destino: climas-chileno.validacion_avalanchas.snowlab_boletines

Uso:
    python notebooks_validacion/cargar_snowlab_bq.py
    python notebooks_validacion/cargar_snowlab_bq.py --dry-run
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from google.cloud import bigquery

GCP_PROJECT = "climas-chileno"
DATASET = "validacion_avalanchas"
TABLA = "snowlab_boletines"
TABLA_COMPLETA = f"{GCP_PROJECT}.{DATASET}.{TABLA}"

SCHEMA = [
    bigquery.SchemaField("id_boletin",          "STRING",  "REQUIRED", description="Identificador único p.ej. '2024-01'"),
    bigquery.SchemaField("temporada",            "INTEGER", "REQUIRED", description="Año de la temporada (2024, 2025)"),
    bigquery.SchemaField("numero_boletin",       "INTEGER", "REQUIRED", description="Número correlativo dentro de la temporada"),
    bigquery.SchemaField("fecha_publicacion",    "DATE",    "REQUIRED", description="Fecha en que se publicó el boletín"),
    bigquery.SchemaField("fecha_inicio_validez", "DATE",    "REQUIRED", description="Primer día de validez del boletín"),
    bigquery.SchemaField("fecha_fin_validez",    "DATE",    "REQUIRED", description="Último día de validez del boletín"),
    bigquery.SchemaField("nivel_alta",           "INTEGER", "NULLABLE", description="Peligro máximo banda Alta 3000-4040 msnm (1-5)"),
    bigquery.SchemaField("nivel_media",          "INTEGER", "NULLABLE", description="Peligro máximo banda Media 2500-3000 msnm (1-5)"),
    bigquery.SchemaField("nivel_baja",           "INTEGER", "NULLABLE", description="Peligro máximo banda Baja 1500-2500 msnm (1-5)"),
    bigquery.SchemaField("nivel_max",            "INTEGER", "REQUIRED", description="Peligro máximo global del boletín (1-5)"),
    bigquery.SchemaField("problema_principal",   "STRING",  "NULLABLE", description="Tipo de problema de avalancha predominante"),
    bigquery.SchemaField("url_instagram",        "STRING",  "NULLABLE", description="URL Instagram del boletín original"),
    bigquery.SchemaField("fuente",               "STRING",  "REQUIRED", description="Fuente del boletín"),
]

# ─── Datos transcritos del PDF ──────────────────────────────────────────────
# nivel_alta/media/baja = peligro MÁXIMO de la banda durante el período válido
# None = no reportado en ese boletín

BOLETINES = [
    # ── Temporada 2024 (14 boletines) ───────────────────────────────────────
    {
        "id_boletin": "2024-01", "temporada": 2024, "numero_boletin": 1,
        "fecha_publicacion": "2024-06-14",
        "fecha_inicio_validez": "2024-06-15", "fecha_fin_validez": "2024-06-17",
        "nivel_alta": 5, "nivel_media": 4, "nivel_baja": 2, "nivel_max": 5,
        "problema_principal": "Placas de tormenta + Placas de viento",
        "url_instagram": "https://www.instagram.com/p/C8NfCthJW5I/",
    },
    {
        "id_boletin": "2024-02", "temporada": 2024, "numero_boletin": 2,
        "fecha_publicacion": "2024-06-20",
        "fecha_inicio_validez": "2024-06-21", "fecha_fin_validez": "2024-06-23",
        "nivel_alta": 4, "nivel_media": 4, "nivel_baja": 2, "nivel_max": 4,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C8dL7Jkp_O2/",
    },
    {
        "id_boletin": "2024-03", "temporada": 2024, "numero_boletin": 3,
        "fecha_publicacion": "2024-06-27",
        "fecha_inicio_validez": "2024-06-28", "fecha_fin_validez": "2024-06-30",
        "nivel_alta": 2, "nivel_media": 2, "nivel_baja": 2, "nivel_max": 2,
        "problema_principal": "Post-tormenta, condiciones en descenso",
        "url_instagram": "https://www.instagram.com/p/C8vO3A5pRJ9/",
    },
    {
        "id_boletin": "2024-04", "temporada": 2024, "numero_boletin": 4,
        "fecha_publicacion": "2024-07-04",
        "fecha_inicio_validez": "2024-07-05", "fecha_fin_validez": "2024-07-07",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C9BRiqotmCq/",
    },
    {
        "id_boletin": "2024-05", "temporada": 2024, "numero_boletin": 5,
        "fecha_publicacion": "2024-07-11",
        "fecha_inicio_validez": "2024-07-12", "fecha_fin_validez": "2024-07-14",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C9TNBH_pGgQ/",
    },
    {
        "id_boletin": "2024-06", "temporada": 2024, "numero_boletin": 6,
        "fecha_publicacion": "2024-07-18",
        "fecha_inicio_validez": "2024-07-19", "fecha_fin_validez": "2024-07-21",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C9lNjVpJTej/",
    },
    {
        "id_boletin": "2024-07", "temporada": 2024, "numero_boletin": 7,
        "fecha_publicacion": "2024-07-25",
        "fecha_inicio_validez": "2024-07-26", "fecha_fin_validez": "2024-07-28",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C93TWKoJPi1/",
    },
    {
        "id_boletin": "2024-08", "temporada": 2024, "numero_boletin": 8,
        "fecha_publicacion": "2024-08-01",
        "fecha_inicio_validez": "2024-08-02", "fecha_fin_validez": "2024-08-04",
        "nivel_alta": 3, "nivel_media": 3, "nivel_baja": 1, "nivel_max": 3,
        "problema_principal": "Placas de tormenta",
        "url_instagram": "https://www.instagram.com/p/C-JYbyNp37U/",
    },
    {
        "id_boletin": "2024-09", "temporada": 2024, "numero_boletin": 9,
        "fecha_publicacion": "2024-08-08",
        "fecha_inicio_validez": "2024-08-09", "fecha_fin_validez": "2024-08-11",
        "nivel_alta": 2, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 2,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C-bwNoANKsw/",
    },
    {
        "id_boletin": "2024-10", "temporada": 2024, "numero_boletin": 10,
        "fecha_publicacion": "2024-08-15",
        "fecha_inicio_validez": "2024-08-16", "fecha_fin_validez": "2024-08-18",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C-tdUWDpC1s/",
    },
    {
        "id_boletin": "2024-11", "temporada": 2024, "numero_boletin": 11,
        "fecha_publicacion": "2024-08-22",
        "fecha_inicio_validez": "2024-08-23", "fecha_fin_validez": "2024-08-25",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C-_e_5_t-ib/",
    },
    {
        "id_boletin": "2024-12", "temporada": 2024, "numero_boletin": 12,
        "fecha_publicacion": "2024-08-29",
        "fecha_inicio_validez": "2024-08-30", "fecha_fin_validez": "2024-09-01",
        "nivel_alta": 1, "nivel_media": None, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C_RXimSpy5j/",
    },
    {
        "id_boletin": "2024-13", "temporada": 2024, "numero_boletin": 13,
        "fecha_publicacion": "2024-09-05",
        "fecha_inicio_validez": "2024-09-06", "fecha_fin_validez": "2024-09-08",
        "nivel_alta": 1, "nivel_media": None, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C_jXbkwSuxl/",
    },
    {
        "id_boletin": "2024-14", "temporada": 2024, "numero_boletin": 14,
        "fecha_publicacion": "2024-09-12",
        "fecha_inicio_validez": "2024-09-13", "fecha_fin_validez": "2024-09-15",
        "nivel_alta": 1, "nivel_media": None, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": "https://www.instagram.com/p/C_1S2tTS_DA/",
    },
    # ── Temporada 2025 (16 boletines) ───────────────────────────────────────
    {
        "id_boletin": "2025-01", "temporada": 2025, "numero_boletin": 1,
        "fecha_publicacion": "2025-06-05",
        "fecha_inicio_validez": "2025-06-06", "fecha_fin_validez": "2025-06-08",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": "Sin problema específico",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-02", "temporada": 2025, "numero_boletin": 2,
        "fecha_publicacion": "2025-06-13",
        "fecha_inicio_validez": "2025-06-14", "fecha_fin_validez": "2025-06-16",
        "nivel_alta": 3, "nivel_media": 3, "nivel_baja": 2, "nivel_max": 3,
        "problema_principal": "Placas de tormenta + Placas de viento",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-03", "temporada": 2025, "numero_boletin": 3,
        "fecha_publicacion": "2025-06-20",
        "fecha_inicio_validez": "2025-06-21", "fecha_fin_validez": "2025-06-23",
        "nivel_alta": 2, "nivel_media": 2, "nivel_baja": 1, "nivel_max": 2,
        "problema_principal": "Post-tormenta, condiciones en descenso",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-04", "temporada": 2025, "numero_boletin": 4,
        "fecha_publicacion": "2025-06-26",
        "fecha_inicio_validez": "2025-06-27", "fecha_fin_validez": "2025-06-29",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-05", "temporada": 2025, "numero_boletin": 5,
        "fecha_publicacion": "2025-07-03",
        "fecha_inicio_validez": "2025-07-04", "fecha_fin_validez": "2025-07-06",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-06", "temporada": 2025, "numero_boletin": 6,
        "fecha_publicacion": "2025-07-10",
        "fecha_inicio_validez": "2025-07-11", "fecha_fin_validez": "2025-07-13",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-07", "temporada": 2025, "numero_boletin": 7,
        "fecha_publicacion": "2025-07-17",
        "fecha_inicio_validez": "2025-07-18", "fecha_fin_validez": "2025-07-20",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-08", "temporada": 2025, "numero_boletin": 8,
        "fecha_publicacion": "2025-07-24",
        "fecha_inicio_validez": "2025-07-25", "fecha_fin_validez": "2025-07-27",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 2, "nivel_max": 2,
        "problema_principal": "Inicio de ciclo nevoso",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-09", "temporada": 2025, "numero_boletin": 9,
        "fecha_publicacion": "2025-07-31",
        "fecha_inicio_validez": "2025-08-01", "fecha_fin_validez": "2025-08-03",
        "nivel_alta": 3, "nivel_media": 3, "nivel_baja": 2, "nivel_max": 3,
        "problema_principal": "Placas de tormenta",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-10", "temporada": 2025, "numero_boletin": 10,
        "fecha_publicacion": "2025-08-07",
        "fecha_inicio_validez": "2025-08-08", "fecha_fin_validez": "2025-08-10",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-11", "temporada": 2025, "numero_boletin": 11,
        "fecha_publicacion": "2025-08-14",
        "fecha_inicio_validez": "2025-08-15", "fecha_fin_validez": "2025-08-17",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-12", "temporada": 2025, "numero_boletin": 12,
        "fecha_publicacion": "2025-08-21",
        "fecha_inicio_validez": "2025-08-22", "fecha_fin_validez": "2025-08-24",
        "nivel_alta": 3, "nivel_media": 3, "nivel_baja": 1, "nivel_max": 3,
        "problema_principal": "Placas de tormenta",
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-13", "temporada": 2025, "numero_boletin": 13,
        "fecha_publicacion": "2025-08-28",
        "fecha_inicio_validez": "2025-08-29", "fecha_fin_validez": "2025-08-31",
        "nivel_alta": 2, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 2,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-14", "temporada": 2025, "numero_boletin": 14,
        "fecha_publicacion": "2025-09-04",
        "fecha_inicio_validez": "2025-09-05", "fecha_fin_validez": "2025-09-07",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 1, "nivel_max": 1,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-15", "temporada": 2025, "numero_boletin": 15,
        "fecha_publicacion": "2025-09-11",
        "fecha_inicio_validez": "2025-09-12", "fecha_fin_validez": "2025-09-14",
        "nivel_alta": 1, "nivel_media": 1, "nivel_baja": 2, "nivel_max": 2,
        "problema_principal": None,
        "url_instagram": None,
    },
    {
        "id_boletin": "2025-16", "temporada": 2025, "numero_boletin": 16,
        "fecha_publicacion": "2025-09-18",
        "fecha_inicio_validez": "2025-09-19", "fecha_fin_validez": "2025-09-21",
        "nivel_alta": 2, "nivel_media": 1, "nivel_baja": 2, "nivel_max": 2,
        "problema_principal": "Placa de viento + Placa persistente/profunda",
        "url_instagram": None,
    },
]

FUENTE = "Snowlab / Andes Consciente — Domingo Valdivieso Ducci (L2 CAA)"


def crear_o_recrear_tabla(cliente: bigquery.Client) -> None:
    tabla_ref = cliente.dataset(DATASET, project=GCP_PROJECT).table(TABLA)
    try:
        tabla_existente = cliente.get_table(tabla_ref)
        # Comparar schema: si difiere, eliminar y recrear
        nombres_actuales = {f.name for f in tabla_existente.schema}
        nombres_nuevos = {f.name for f in SCHEMA}
        if nombres_actuales != nombres_nuevos:
            cliente.delete_table(tabla_ref)
            print(f"  Tabla {TABLA_COMPLETA} eliminada (schema diferente).")
            raise Exception("recrear")
        print(f"  Tabla {TABLA_COMPLETA} ya existe con schema correcto.")
    except Exception:
        tabla = bigquery.Table(tabla_ref, schema=SCHEMA)
        tabla.description = (
            "Boletines Snowlab La Parva temporadas 2024 y 2025. "
            "Ground truth para validación H4 vs AndesAI."
        )
        cliente.create_table(tabla)
        print(f"  Tabla {TABLA_COMPLETA} creada.")


def preparar_filas() -> list:
    filas = []
    for b in BOLETINES:
        fila = dict(b)
        fila["fuente"] = FUENTE
        filas.append(fila)
    return filas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra los datos sin cargar a BQ")
    args = parser.parse_args()

    filas = preparar_filas()

    if args.dry_run:
        print(f"DRY RUN — {len(filas)} boletines a cargar:")
        for f in filas:
            print(f"  {f['id_boletin']} | {f['fecha_inicio_validez']}→{f['fecha_fin_validez']} "
                  f"| Alta={f['nivel_alta']} Media={f['nivel_media']} Baja={f['nivel_baja']} MAX={f['nivel_max']}")
        return

    import json, time, tempfile, pathlib

    cliente = bigquery.Client(project=GCP_PROJECT)

    print(f"\nCreando tabla {TABLA_COMPLETA} ...")
    crear_o_recrear_tabla(cliente)

    # Usar load job (WRITE_TRUNCATE) — más robusto que streaming para tablas pequeñas
    tabla_ref_obj = cliente.dataset(DATASET, project=GCP_PROJECT).table(TABLA)
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    # Serializar filas a NDJSON en un archivo temporal
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
        for fila in filas:
            tmp.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        tmp_path = tmp.name

    print(f"  Cargando {len(filas)} filas vía load job ...")
    with open(tmp_path, "rb") as f:
        job = cliente.load_table_from_file(f, tabla_ref_obj, job_config=job_config)

    job.result()  # espera hasta completar
    pathlib.Path(tmp_path).unlink(missing_ok=True)

    if job.errors:
        print(f"\nERRORES en load job:")
        for e in job.errors:
            print(f"  {e}")
        sys.exit(1)

    print(f"\n✓ {len(filas)} boletines cargados en {TABLA_COMPLETA}")
    print(f"  Temporada 2024: {sum(1 for f in filas if f['temporada'] == 2024)} boletines")
    print(f"  Temporada 2025: {sum(1 for f in filas if f['temporada'] == 2025)} boletines")


if __name__ == "__main__":
    main()
