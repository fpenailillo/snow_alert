"""
Migración GCS: reorganiza el storage de climas-chileno-datos-clima-bronce
pasando de estructura por tipo-de-dato a estructura por ubicación.

Transformaciones:
  {ubicacion}/YYYY/...                          → {ubicacion}/clima/YYYY/...
  pronostico_horas/{ubicacion}/YYYY/...         → {ubicacion}/pronostico_horas/YYYY/...
  pronostico_dias/{ubicacion}/YYYY/...          → {ubicacion}/pronostico_dias/YYYY/...
  boletines/{ubicacion}/YYYY/...                → {ubicacion}/boletines/YYYY/...
  satelital/geotiff/{ubicacion}/YYYY-MM-DD/...  → {ubicacion}/satelital/geotiff/YYYY-MM-DD/...
  satelital/preview/{ubicacion}/YYYY-MM-DD/...  → {ubicacion}/satelital/preview/YYYY-MM-DD/...
  satelital/thumbnail/{ubicacion}/...           → {ubicacion}/satelital/thumbnail/...

topografia/ no se migra (es transversal).

Uso:
  python migrar_gcs.py [--dry-run] [--delete-old]
"""
import argparse
import logging
import sys
from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET = "climas-chileno-datos-clima-bronce"
PROJECT = "climas-chileno"

# Prefijos a NO migrar (se dejan intactos)
PREFIJOS_IGNORAR = ("topografia/",)

# Reglas de migración: (prefijo_origen, fn_nueva_ruta)
# Cada función recibe la ruta completa y devuelve la nueva ruta.
def _nueva_ruta(ruta: str) -> str | None:
    """Devuelve la nueva ruta o None si no necesita migración."""

    # 1. condiciones_actuales: {ubicacion}/YYYY/... → {ubicacion}/clima/YYYY/...
    #    Se detecta por: primer segmento NO es prefijo conocido + segundo segmento es año (4 dígitos)
    partes = ruta.split("/")
    if len(partes) >= 2 and partes[1].isdigit() and len(partes[1]) == 4:
        primer = partes[0]
        if not any(ruta.startswith(p) for p in (
            "pronostico_horas/", "pronostico_dias/", "boletines/",
            "satelital/", "topografia/", "ubicaciones/"
        )):
            return f"{primer}/clima/" + "/".join(partes[1:])

    # 2. pronostico_horas/{ubicacion}/... → {ubicacion}/pronostico_horas/...
    if ruta.startswith("pronostico_horas/"):
        resto = ruta[len("pronostico_horas/"):]  # {ubicacion}/...
        partes2 = resto.split("/", 1)
        ubicacion = partes2[0]
        sufijo = partes2[1] if len(partes2) > 1 else ""
        return f"{ubicacion}/pronostico_horas/{sufijo}"

    # 3. pronostico_dias/{ubicacion}/... → {ubicacion}/pronostico_dias/...
    if ruta.startswith("pronostico_dias/"):
        resto = ruta[len("pronostico_dias/"):]
        partes2 = resto.split("/", 1)
        ubicacion = partes2[0]
        sufijo = partes2[1] if len(partes2) > 1 else ""
        return f"{ubicacion}/pronostico_dias/{sufijo}"

    # 4. boletines/{ubicacion}/... → {ubicacion}/boletines/...
    if ruta.startswith("boletines/"):
        resto = ruta[len("boletines/"):]
        partes2 = resto.split("/", 1)
        ubicacion = partes2[0]
        sufijo = partes2[1] if len(partes2) > 1 else ""
        return f"{ubicacion}/boletines/{sufijo}"

    # 5. satelital/{tipo}/{ubicacion}/... → {ubicacion}/satelital/{tipo}/...
    if ruta.startswith("satelital/"):
        resto = ruta[len("satelital/"):]  # {tipo}/{ubicacion}/...
        partes2 = resto.split("/", 2)
        if len(partes2) >= 2:
            tipo = partes2[0]      # geotiff | preview | thumbnail
            ubicacion = partes2[1]
            sufijo = partes2[2] if len(partes2) > 2 else ""
            return f"{ubicacion}/satelital/{tipo}/{sufijo}"

    return None  # no aplica migración


def migrar(dry_run: bool = True, delete_old: bool = False):
    cliente = storage.Client(project=PROJECT)
    bucket = cliente.bucket(BUCKET)

    blobs = list(bucket.list_blobs())
    logger.info(f"Total objetos en bucket: {len(blobs)}")

    copiados = 0
    omitidos = 0
    errores = 0

    for blob in blobs:
        ruta_actual = blob.name

        # Ignorar prefijos transversales
        if any(ruta_actual.startswith(p) for p in PREFIJOS_IGNORAR):
            omitidos += 1
            continue

        nueva = _nueva_ruta(ruta_actual)
        if nueva is None or nueva == ruta_actual:
            omitidos += 1
            continue

        logger.info(f"  {ruta_actual}\n  → {nueva}")

        if not dry_run:
            try:
                bucket.copy_blob(blob, bucket, nueva)
                copiados += 1
            except Exception as e:
                logger.error(f"ERROR copiando {ruta_actual}: {e}")
                errores += 1
        else:
            copiados += 1

    logger.info(f"\nResumen {'(DRY RUN)' if dry_run else ''}:")
    logger.info(f"  A migrar : {copiados}")
    logger.info(f"  Omitidos : {omitidos}")
    logger.info(f"  Errores  : {errores}")

    if not dry_run and delete_old and errores == 0:
        logger.info("\nEliminando objetos en rutas antiguas...")
        eliminados = 0
        for blob in list(bucket.list_blobs()):
            ruta_actual = blob.name
            if any(ruta_actual.startswith(p) for p in PREFIJOS_IGNORAR):
                continue
            nueva = _nueva_ruta(ruta_actual)
            if nueva is not None and nueva != ruta_actual:
                blob.delete()
                eliminados += 1
        logger.info(f"  Eliminados: {eliminados}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra estructura GCS por ubicación")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Solo muestra qué se migraría (default: True)")
    parser.add_argument("--ejecutar", action="store_true",
                        help="Ejecuta la migración real (desactiva dry-run)")
    parser.add_argument("--delete-old", action="store_true",
                        help="Elimina rutas antiguas tras migración exitosa")
    args = parser.parse_args()

    dry = not args.ejecutar
    if dry:
        logger.info("=== MODO DRY RUN — sin cambios en GCS ===")
    else:
        logger.info("=== MODO EJECUCIÓN REAL ===")

    migrar(dry_run=dry, delete_old=args.delete_old)
