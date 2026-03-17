"""
Script CLI para generar boletines para todas las ubicaciones con datos disponibles.

Procesa en lotes de 5 con pausa de 3s entre lotes.
Continúa aunque alguna ubicación falle.

Uso:
    python agentes/scripts/generar_todos.py
    python agentes/scripts/generar_todos.py --guardar
"""

import argparse
import json
import logging
import sys
import os
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha
from agentes.salidas.almacenador import guardar_boletin


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    return parser.parse_args()


def main() -> int:
    """Punto de entrada principal."""
    args = parsear_argumentos()

    inicio = datetime.now(timezone.utc)
    logger.info("Iniciando generación masiva de boletines")

    try:
        agente = AgenteRiesgoAvalancha()
        resultados = agente.generar_boletines_masivos()
    except Exception as e:
        logger.error(f"Error inicializando el agente: {e}")
        print(f"✗ Error fatal: {e}", file=sys.stderr)
        return 1

    exitosos = [r for r in resultados if "boletin" in r]
    fallidos = [r for r in resultados if "error" in r]

    print(f"\n{'=' * 60}")
    print(f"RESUMEN DE GENERACIÓN MASIVA")
    print(f"{'=' * 60}")
    print(f"Total ubicaciones: {len(resultados)}")
    print(f"Exitosos: {len(exitosos)}")
    print(f"Fallidos: {len(fallidos)}")

    if exitosos:
        print("\nBoletines generados:")
        for r in exitosos:
            nivel = r.get("nivel_eaws_24h", "?")
            duracion = r.get("duracion_segundos", "?")
            print(f"  ✓ {r['ubicacion']} — Nivel {nivel} ({duracion}s)")

    if fallidos:
        print("\nErrores:")
        for r in fallidos:
            print(f"  ✗ {r['ubicacion']}: {r.get('error', 'desconocido')}")

    # Guardar en BigQuery y GCS si se solicitó
    if args.guardar and exitosos:
        print(f"\nGuardando {len(exitosos)} boletines...")
        guardados = 0
        for resultado in exitosos:
            try:
                estado = guardar_boletin(resultado)
                if estado.get("guardado"):
                    guardados += 1
                else:
                    logger.error(
                        f"Error guardando {resultado['ubicacion']}: "
                        f"{estado.get('errores')}"
                    )
            except Exception as e:
                logger.error(f"Error al guardar {resultado['ubicacion']}: {e}")

        print(f"✓ {guardados}/{len(exitosos)} boletines guardados")

    duracion_total = round((datetime.now(timezone.utc) - inicio).total_seconds(), 1)
    print(f"\nTiempo total: {duracion_total}s")

    if args.json:
        resumen = {
            "timestamp": inicio.isoformat(),
            "total": len(resultados),
            "exitosos": len(exitosos),
            "fallidos": len(fallidos),
            "duracion_total_segundos": duracion_total,
            "boletines": resultados
        }
        print("\n" + json.dumps(resumen, ensure_ascii=False, indent=2, default=str))

    return 0 if not fallidos else 1


if __name__ == "__main__":
    sys.exit(main())
