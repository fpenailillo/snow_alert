"""
Reprocesamiento retroactivo v4 — AndesAI (REQ-01 a REQ-04 implementados)

Genera nuevas predicciones para las fechas de validación usando el código
actualizado y las guarda en clima.boletines_riesgo (upsert, reemplaza v3.2).

Procesamiento CRONOLÓGICO para que REQ-01 (persistencia temporal) pueda
leer la cadena de predicciones v4 anteriores al evaluar calma sostenida.

Fechas procesadas:
  H1/H3 Suiza : 3 estaciones × 10 fechas = 30 runs
  H4 Snowlab  : 3 sectores   × 30 fechas = 90 runs
  Total       : 120 runs × ~100s ≈ 3.5 horas

Uso:
    python notebooks_validacion/reprocesar_retroactivo.py
    python notebooks_validacion/reprocesar_retroactivo.py --solo-suiza
    python notebooks_validacion/reprocesar_retroactivo.py --solo-snowlab
    python notebooks_validacion/reprocesar_retroactivo.py --dry-run
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from google.cloud import bigquery

from agentes.orquestador.agente_principal import OrquestadorAvalancha
from agentes.salidas.almacenador import guardar_boletin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

GCP_PROJECT = "climas-chileno"

# ── Fechas de validación ──────────────────────────────────────────────────────

FECHAS_SUIZA = [
    "2023-12-01", "2023-12-15",
    "2024-01-01", "2024-01-15",
    "2024-02-01", "2024-02-15",
    "2024-03-01", "2024-03-15",
    "2024-04-01", "2024-04-15",
]
ESTACIONES_SUIZA = ["Interlaken", "Matterhorn Zermatt", "St Moritz"]

# fecha_inicio de cada boletín Snowlab → fecha de referencia para AndesAI
FECHAS_SNOWLAB = [
    "2024-06-15", "2024-06-21", "2024-06-28",
    "2024-07-05", "2024-07-12", "2024-07-19", "2024-07-26",
    "2024-08-02", "2024-08-09", "2024-08-16", "2024-08-23",
    "2024-08-30", "2024-09-06", "2024-09-13",
    "2025-06-06", "2025-06-14", "2025-06-21", "2025-06-27",
    "2025-07-04", "2025-07-11", "2025-07-18", "2025-07-25",
    "2025-08-01", "2025-08-08", "2025-08-15", "2025-08-22",
    "2025-08-29", "2025-09-05", "2025-09-12", "2025-09-19",
]
SECTORES_LAPARVA = [
    "La Parva Sector Alto",
    "La Parva Sector Medio",
    "La Parva Sector Bajo",
]


def ya_procesado_v4(cliente: bigquery.Client, ubicacion: str, fecha_str: str) -> bool:
    """Retorna True si ya existe un boletín v4 para esta (ubicacion, fecha)."""
    q = f"""
        SELECT COUNT(*) AS n
        FROM `{GCP_PROJECT}.clima.boletines_riesgo`
        WHERE nombre_ubicacion = @loc
          AND DATE(fecha_emision) = @fecha
          AND STARTS_WITH(version_prompts, 'v4')
    """
    job = cliente.query(
        q,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("loc",   "STRING", ubicacion),
            bigquery.ScalarQueryParameter("fecha",  "DATE",   fecha_str),
        ]),
    )
    return list(job.result())[0]["n"] > 0


def construir_lista_runs(solo_suiza: bool, solo_snowlab: bool) -> list[tuple[str, str]]:
    """
    Construye la lista de (ubicacion, fecha_str) a procesar, ordenada
    cronológicamente para que REQ-01 pueda leer la cadena de predicciones v4.
    """
    runs: list[tuple[str, str]] = []

    if not solo_snowlab:
        for fecha in FECHAS_SUIZA:
            for est in ESTACIONES_SUIZA:
                runs.append((est, fecha))

    if not solo_suiza:
        for fecha in FECHAS_SNOWLAB:
            for sector in SECTORES_LAPARVA:
                runs.append((sector, fecha))

    # Ordenar cronológicamente (por fecha, luego por ubicacion)
    runs.sort(key=lambda x: (x[1], x[0]))
    return runs


def ejecutar_replay(dry_run: bool, solo_suiza: bool, solo_snowlab: bool) -> None:
    cliente = bigquery.Client(project=GCP_PROJECT)
    orquestador = OrquestadorAvalancha()

    runs = construir_lista_runs(solo_suiza, solo_snowlab)
    total = len(runs)

    print(f"\n{'='*65}")
    print(f"REPROCESAMIENTO RETROACTIVO v4 — {total} ejecuciones")
    print(f"Estimado: ~{round(total * 100 / 60)} min ({round(total * 100 / 3600, 1)}h)")
    print(f"Dry-run: {dry_run}")
    print(f"{'='*65}\n")

    ok = 0
    skip = 0
    err = 0
    t0_total = time.time()

    for i, (ubicacion, fecha_str) in enumerate(runs, start=1):
        prefijo = f"[{i:3d}/{total}]"

        # Saltar si ya procesado con v4
        if ya_procesado_v4(cliente, ubicacion, fecha_str):
            logger.info(f"{prefijo} SKIP (ya v4) — {ubicacion} {fecha_str}")
            skip += 1
            continue

        if dry_run:
            logger.info(f"{prefijo} DRY-RUN — {ubicacion} {fecha_str}")
            ok += 1
            continue

        fecha_ref = datetime.fromisoformat(f"{fecha_str}T12:00:00+00:00")
        logger.info(f"\n{prefijo} INICIANDO — {ubicacion} {fecha_str}")

        t0 = time.time()
        try:
            resultado = orquestador.generar_boletin(
                nombre_ubicacion=ubicacion,
                fecha_referencia=fecha_ref,
            )
            nivel = resultado.get("nivel_eaws_24h", "?")
            dur   = round(time.time() - t0, 1)

            guardado = guardar_boletin(resultado)

            estado_guardado = "BQ+GCS" if guardado.get("guardado_bigquery") and guardado.get("guardado_gcs") else \
                              "BQ"     if guardado.get("guardado_bigquery") else \
                              "GCS"    if guardado.get("guardado_gcs")      else "ERROR"

            logger.info(
                f"{prefijo} OK — nivel={nivel} dur={dur}s guardado={estado_guardado} "
                f"({ubicacion} {fecha_str})"
            )
            ok += 1

        except Exception as exc:
            dur = round(time.time() - t0, 1)
            logger.error(f"{prefijo} ERROR — {ubicacion} {fecha_str} ({dur}s): {exc}")
            err += 1

        # Progreso parcial cada 10 ejecuciones
        if i % 10 == 0:
            elapsed = round(time.time() - t0_total)
            restantes = total - i
            eta_s = round(elapsed / i * restantes) if i > 0 else 0
            eta_m = round(eta_s / 60)
            logger.info(
                f"\n--- Progreso: {i}/{total} — "
                f"ok={ok} skip={skip} err={err} — "
                f"elapsed={elapsed}s ETA={eta_m}min ---\n"
            )

    elapsed_total = round(time.time() - t0_total)
    print(f"\n{'='*65}")
    print(f"COMPLETADO en {elapsed_total}s ({round(elapsed_total/60)}min)")
    print(f"  OK:   {ok}")
    print(f"  Skip: {skip} (ya v4)")
    print(f"  Err:  {err}")
    print(f"{'='*65}")

    if err > 0:
        print(f"\nWARNING: {err} ejecuciones fallaron — revisar logs")

    if not dry_run and ok > 0:
        print("\nPróximo paso: re-ejecutar scripts de validación:")
        print("  python notebooks_validacion/07_validacion_slf_suiza.py")
        print("  python notebooks_validacion/08_validacion_snowlab.py")


def main():
    parser = argparse.ArgumentParser(description="Reprocesamiento retroactivo v4")
    parser.add_argument("--dry-run", action="store_true",
                        help="Lista runs sin ejecutar")
    parser.add_argument("--solo-suiza", action="store_true",
                        help="Solo H1/H3 (30 runs Swiss)")
    parser.add_argument("--solo-snowlab", action="store_true",
                        help="Solo H4 (90 runs La Parva)")
    args = parser.parse_args()

    ejecutar_replay(
        dry_run=args.dry_run,
        solo_suiza=args.solo_suiza,
        solo_snowlab=args.solo_snowlab,
    )


if __name__ == "__main__":
    main()
