"""
Script CLI para generar boletines para todas las ubicaciones con datos disponibles.

Procesa una ubicación a la vez y guarda inmediatamente si --guardar está activo.
Continúa aunque alguna ubicación falle.

Uso:
    python agentes/scripts/generar_todos.py
    python agentes/scripts/generar_todos.py --guardar
    python agentes/scripts/generar_todos.py --guardar --ubicaciones "La Parva Sector Bajo,Matterhorn Zermatt"
    python agentes/scripts/generar_todos.py --guardar --preset validacion
"""

import argparse
import json
import logging
import sys
import os
import time
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha, ErrorOrquestador
from agentes.salidas.almacenador import guardar_boletin
from agentes.datos.consultor_bigquery import ConsultorBigQuery


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PAUSA_ENTRE_UBICACIONES = 3  # segundos entre cada ubicación

# Ubicaciones de validación: La Parva (Chile) + Suiza
# Usadas para calcular métricas H1/H4 sin necesitar el LLM de producción
UBICACIONES_VALIDACION = [
    "La Parva Sector Alto",
    "La Parva Sector Bajo",
    "La Parva Sector Medio",
    "Matterhorn Zermatt",
    "Interlaken",
    "St Moritz",
]


def parsear_argumentos() -> argparse.Namespace:
    """Parsea los argumentos de línea de comando."""
    parser = argparse.ArgumentParser(
        description="Genera boletines de avalanchas para todas las ubicaciones"
    )
    parser.add_argument(
        '--guardar',
        action='store_true',
        help='Guardar boletines en BigQuery y GCS (por defecto solo genera)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Imprimir resumen en formato JSON al finalizar'
    )
    parser.add_argument(
        '--ubicaciones',
        type=str,
        default=None,
        help='Lista de ubicaciones separadas por coma (sobreescribe la lista automática)'
    )
    parser.add_argument(
        '--preset',
        choices=['validacion'],
        default=None,
        help='Preset de ubicaciones: "validacion" → La Parva + Suiza (6 ubicaciones)'
    )
    return parser.parse_args()


def main() -> int:
    """Punto de entrada principal."""
    args = parsear_argumentos()

    inicio = datetime.now(timezone.utc)
    logger.info("Iniciando generación masiva de boletines (modo incremental)")

    try:
        agente = AgenteRiesgoAvalancha()
    except Exception as e:
        logger.error(f"Error inicializando el agente: {e}")
        print(f"✗ Error fatal: {e}", file=sys.stderr)
        return 1

    # Determinar lista de ubicaciones
    if args.preset == 'validacion':
        ubicaciones = UBICACIONES_VALIDACION
        logger.info(f"Preset 'validacion': {len(ubicaciones)} ubicaciones (La Parva + Suiza)")
    elif args.ubicaciones:
        ubicaciones = [u.strip() for u in args.ubicaciones.split(',') if u.strip()]
        logger.info(f"Ubicaciones explícitas: {ubicaciones}")
    else:
        try:
            consultor = ConsultorBigQuery()
            ubicaciones = consultor.listar_ubicaciones_con_datos()[:50]
        except Exception as e:
            logger.error(f"Error obteniendo ubicaciones: {e}")
            print(f"✗ Error fatal: {e}", file=sys.stderr)
            return 1

    total = len(ubicaciones)
    logger.info(f"Procesando {total} ubicaciones")

    exitosos = []
    fallidos = []
    guardados = 0

    for idx, ubicacion in enumerate(ubicaciones, 1):
        logger.info(f"[{idx}/{total}] Iniciando: {ubicacion}")
        try:
            resultado = agente.generar_boletin(ubicacion)
            exitosos.append(resultado)
            nivel = resultado.get("nivel_eaws_24h", "?")
            duracion = resultado.get("duracion_segundos", "?")
            print(f"  ✓ [{idx}/{total}] {ubicacion} — Nivel {nivel} ({duracion}s)")

            if args.guardar:
                try:
                    estado = guardar_boletin(resultado)
                    if estado.get("guardado"):
                        guardados += 1
                        logger.info(f"  → Guardado en BQ/GCS: {ubicacion}")
                    else:
                        logger.error(
                            f"  → Error guardando {ubicacion}: "
                            f"{estado.get('errores')}"
                        )
                except Exception as e_guardar:
                    logger.error(f"  → Excepción guardando {ubicacion}: {e_guardar}")

        except ErrorOrquestador as exc:
            logger.error(f"✗ [{idx}/{total}] Error en {ubicacion}: {exc}")
            fallidos.append({"ubicacion": ubicacion, "error": str(exc)})
        except Exception as exc:
            logger.error(f"✗ [{idx}/{total}] Error inesperado en {ubicacion}: {exc}")
            fallidos.append({"ubicacion": ubicacion, "error": str(exc)})

        if idx < total:
            time.sleep(PAUSA_ENTRE_UBICACIONES)

    duracion_total = round((datetime.now(timezone.utc) - inicio).total_seconds(), 1)

    print(f"\n{'=' * 60}")
    print(f"RESUMEN DE GENERACIÓN MASIVA")
    print(f"{'=' * 60}")
    print(f"Total ubicaciones: {total}")
    print(f"Exitosos: {len(exitosos)}")
    print(f"Fallidos: {len(fallidos)}")
    if args.guardar:
        print(f"Guardados: {guardados}/{len(exitosos)}")

    if fallidos:
        print("\nErrores:")
        for r in fallidos:
            print(f"  ✗ {r['ubicacion']}: {r.get('error', 'desconocido')}")

    print(f"\nTiempo total: {duracion_total}s")

    if args.json:
        resumen = {
            "timestamp": inicio.isoformat(),
            "total": total,
            "exitosos": len(exitosos),
            "fallidos": len(fallidos),
            "guardados": guardados,
            "duracion_total_segundos": duracion_total,
            "boletines": exitosos + fallidos,
        }
        print("\n" + json.dumps(resumen, ensure_ascii=False, indent=2, default=str))

    return 0 if not fallidos else 1


if __name__ == "__main__":
    sys.exit(main())
