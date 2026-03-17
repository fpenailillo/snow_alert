"""
Script CLI para generar un boletín de riesgo de avalanchas por ubicación.

Uso:
    python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"
    python agentes/scripts/generar_boletin.py --ubicacion "Valle Nevado" --solo-imprimir
    python agentes/scripts/generar_boletin.py --listar-ubicaciones
"""

import argparse
import json
import logging
import sys
import os

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha
from agentes.salidas.almacenador import guardar_boletin
from agentes.datos.consultor_bigquery import ConsultorBigQuery


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parsear_argumentos() -> argparse.Namespace:
    """Parsea los argumentos de línea de comando."""
    parser = argparse.ArgumentParser(
        description="Genera boletines de riesgo de avalanchas EAWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python agentes/scripts/generar_boletin.py --ubicacion "La Parva Sector Bajo"
  python agentes/scripts/generar_boletin.py --ubicacion "Valle Nevado" --solo-imprimir
  python agentes/scripts/generar_boletin.py --listar-ubicaciones
        """
    )
    parser.add_argument(
        '--ubicacion',
        type=str,
        help='Nombre exacto de la ubicación'
    )
    parser.add_argument(
        '--solo-imprimir',
        action='store_true',
        help='Solo imprimir el boletín, sin guardar en BigQuery/GCS'
    )
    parser.add_argument(
        '--listar-ubicaciones',
        action='store_true',
        help='Listar ubicaciones con datos disponibles'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Imprimir salida en formato JSON'
    )
    return parser.parse_args()


def listar_ubicaciones() -> None:
    """Lista todas las ubicaciones con datos recientes."""
    print("Consultando ubicaciones con datos en las últimas 24h...")
    consultor = ConsultorBigQuery()
    ubicaciones = consultor.listar_ubicaciones_con_datos()

    if not ubicaciones:
        print("No hay ubicaciones con datos recientes.")
        return

    print(f"\n{len(ubicaciones)} ubicaciones disponibles:\n")
    for i, ub in enumerate(ubicaciones, 1):
        print(f"  {i:3d}. {ub}")


def generar_y_mostrar(
    ubicacion: str,
    solo_imprimir: bool = False,
    formato_json: bool = False
) -> int:
    """
    Genera un boletín y lo muestra/guarda según las opciones.

    Args:
        ubicacion: Nombre de la ubicación
        solo_imprimir: Si True, no guarda en BigQuery/GCS
        formato_json: Si True, imprime en formato JSON

    Returns:
        int: 0 si exitoso, 1 si error
    """
    logger.info(f"Iniciando generación de boletín para: {ubicacion}")

    try:
        agente = AgenteRiesgoAvalancha()
        resultado = agente.generar_boletin(ubicacion)

        if formato_json:
            print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
        else:
            print("\n" + "=" * 60)
            print(resultado.get("boletin", "Sin boletín generado"))
            print("=" * 60)
            print(f"\nNivel EAWS 24h: {resultado.get('nivel_eaws_24h')}")
            print(f"Iteraciones: {resultado.get('iteraciones')}")
            print(f"Duración: {resultado.get('duracion_segundos')}s")
            print(f"Tools llamadas: {[t['tool'] for t in resultado.get('tools_llamadas', [])]}")

        if not solo_imprimir:
            print("\nGuardando en BigQuery y GCS...")
            estado_guardado = guardar_boletin(resultado)

            if formato_json:
                print(json.dumps(estado_guardado, ensure_ascii=False, indent=2))
            else:
                if estado_guardado.get("guardado"):
                    print(f"✓ Guardado en BigQuery: {estado_guardado.get('guardado_bigquery')}")
                    if estado_guardado.get("uri_gcs"):
                        print(f"✓ Guardado en GCS: {estado_guardado.get('uri_gcs')}")
                else:
                    print("✗ Error al guardar")
                    for dest, err in estado_guardado.get("errores", []):
                        print(f"  - {dest}: {err}")
        else:
            print("\n(Modo solo-imprimir: no se guardó en BigQuery/GCS)")

        return 0

    except Exception as e:
        logger.error(f"Error generando boletín para {ubicacion}: {e}")
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Punto de entrada principal del script."""
    args = parsear_argumentos()

    if args.listar_ubicaciones:
        listar_ubicaciones()
        return 0

    if not args.ubicacion:
        print("Error: debe especificar --ubicacion o --listar-ubicaciones", file=sys.stderr)
        return 1

    return generar_y_mostrar(
        ubicacion=args.ubicacion,
        solo_imprimir=args.solo_imprimir,
        formato_json=args.json
    )


if __name__ == "__main__":
    sys.exit(main())
