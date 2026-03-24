"""
Orquestador de generación masiva de boletines históricos de invierno.

Genera boletines de riesgo de avalanchas para las fechas clave de los
inviernos 2024 y 2025 (hemisferio sur: junio-septiembre) para las 3
zonas de La Parva.

Para cada (ubicacion, fecha):
1. Ejecuta el backfill para insertar datos históricos en BigQuery
2. Genera el boletín con fecha_referencia = fecha
3. Guarda en BigQuery y GCS (salvo que se use --dry-run)

Al finalizar imprime un resumen con exitosos, fallidos y nivel EAWS promedio.

Uso:
    # Ejecución completa (backfill + generación + guardado)
    python agentes/scripts/generar_boletines_invierno.py

    # Solo backfill (insertar datos históricos sin generar boletines)
    python agentes/scripts/generar_boletines_invierno.py --solo-backfill

    # Dry-run (genera boletines pero no guarda en BigQuery/GCS)
    python agentes/scripts/generar_boletines_invierno.py --dry-run

    # Subset de fechas
    python agentes/scripts/generar_boletines_invierno.py \\
        --fechas 2024-06-15 2024-07-01
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agentes.datos.backfill.backfill_clima_historico import (
    ejecutar_backfill,
    UBICACIONES_LA_PARVA,
    FECHAS_INVIERNO_DEFAULT,
)
from agentes.orquestador.agente_principal import AgenteRiesgoAvalancha, ErrorOrquestador
from agentes.salidas.almacenador import guardar_boletin


# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parsear_argumentos() -> argparse.Namespace:
    """Parsea los argumentos de línea de comando."""
    parser = argparse.ArgumentParser(
        description=(
            "Genera boletines históricos de avalanchas para los inviernos 2024 y 2025 "
            "en las zonas de La Parva. Incluye backfill de datos desde Open-Meteo."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Ejecución completa
  python agentes/scripts/generar_boletines_invierno.py

  # Solo backfill
  python agentes/scripts/generar_boletines_invierno.py --solo-backfill

  # Dry-run con subset de fechas
  python agentes/scripts/generar_boletines_invierno.py \\
      --dry-run --fechas 2024-06-15 2024-07-01

  # Solo ubicaciones específicas
  python agentes/scripts/generar_boletines_invierno.py \\
      --ubicaciones "La Parva Sector Bajo"
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help=(
            'Genera boletines pero NO guarda en BigQuery/GCS. '
            'El backfill sí se ejecuta (para insertar datos históricos).'
        )
    )
    parser.add_argument(
        '--solo-backfill',
        action='store_true',
        help=(
            'Solo ejecuta el backfill de datos históricos en BigQuery. '
            'No genera boletines.'
        )
    )
    parser.add_argument(
        '--fechas',
        nargs='+',
        default=FECHAS_INVIERNO_DEFAULT,
        metavar='YYYY-MM-DD',
        help=(
            'Fechas a procesar. '
            'Default: todas las fechas de invierno 2024 y 2025.'
        )
    )
    parser.add_argument(
        '--ubicaciones',
        nargs='+',
        default=list(UBICACIONES_LA_PARVA.keys()),
        help=(
            'Nombres de ubicaciones a procesar. '
            'Default: las 3 zonas de La Parva.'
        )
    )
    parser.add_argument(
        '--pausa-entre-boletines',
        type=float,
        default=2.0,
        metavar='SEGUNDOS',
        help=(
            'Pausa en segundos entre boletines consecutivos '
            'para evitar saturar la API. Default: 2.0'
        )
    )
    return parser.parse_args()


def convertir_fecha_a_datetime(fecha_str: str) -> Optional[datetime]:
    """
    Convierte una fecha YYYY-MM-DD a datetime UTC con hora 18:00 (15:00 local -03:00).

    Args:
        fecha_str: Fecha en formato YYYY-MM-DD

    Returns:
        datetime en UTC o None si el formato es inválido
    """
    try:
        fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d")
        # 18:00 UTC = 15:00 hora local de Santiago (-03:00), representativa del día
        return fecha_dt.replace(hour=18, minute=0, second=0, tzinfo=timezone.utc)
    except ValueError:
        logger.warning(f"Fecha con formato inválido (ignorada): '{fecha_str}'")
        return None


def ejecutar_backfill_para_ubicaciones(
    ubicaciones: dict,
    fechas: list,
) -> dict:
    """
    Ejecuta el backfill de datos históricos para las ubicaciones y fechas dadas.

    Args:
        ubicaciones: Dict {nombre: {latitud, longitud}}
        fechas: Lista de fechas en formato YYYY-MM-DD

    Returns:
        Dict con resumen del backfill
    """
    logger.info(
        f"[Invierno] Iniciando backfill para {len(ubicaciones)} ubicaciones "
        f"y {len(fechas)} fechas"
    )
    resumen = ejecutar_backfill(
        ubicaciones=ubicaciones,
        fechas=fechas,
    )
    logger.info(
        f"[Invierno] Backfill completado — "
        f"exitosas: {resumen['exitosas']}, "
        f"fallidas: {resumen['fallidas']}, "
        f"omitidas: {resumen['omitidas_ya_existian']}"
    )
    return resumen


def generar_boletin_historico(
    agente: AgenteRiesgoAvalancha,
    nombre_ubicacion: str,
    fecha: str,
    fecha_referencia: datetime,
    dry_run: bool = False,
) -> dict:
    """
    Genera y opcionalmente guarda un boletín histórico para una ubicación y fecha.

    Args:
        agente: Instancia del agente orquestador
        nombre_ubicacion: Nombre exacto de la ubicación
        fecha: Fecha en formato YYYY-MM-DD (para logs)
        fecha_referencia: datetime de referencia para consultas BigQuery
        dry_run: Si True, no guarda en BigQuery/GCS

    Returns:
        Dict con resultado de la generación:
        {
            "ubicacion": str,
            "fecha": str,
            "exitoso": bool,
            "nivel_eaws_24h": int|None,
            "guardado": bool,
            "error": str|None
        }
    """
    logger.info(f"[Invierno] Generando boletín: {nombre_ubicacion} | {fecha}")

    try:
        resultado = agente.generar_boletin(
            nombre_ubicacion=nombre_ubicacion,
            fecha_referencia=fecha_referencia,
        )
    except ErrorOrquestador as exc:
        logger.error(
            f"[Invierno] Error generando boletín para {nombre_ubicacion} {fecha}: {exc}"
        )
        return {
            "ubicacion": nombre_ubicacion,
            "fecha": fecha,
            "exitoso": False,
            "nivel_eaws_24h": None,
            "guardado": False,
            "error": str(exc),
        }
    except Exception as exc:
        logger.error(
            f"[Invierno] Error inesperado para {nombre_ubicacion} {fecha}: {exc}"
        )
        return {
            "ubicacion": nombre_ubicacion,
            "fecha": fecha,
            "exitoso": False,
            "nivel_eaws_24h": None,
            "guardado": False,
            "error": str(exc),
        }

    nivel = resultado.get("nivel_eaws_24h")
    logger.info(
        f"[Invierno] Boletín generado — {nombre_ubicacion} | {fecha} | "
        f"nivel EAWS: {nivel}"
    )

    # Guardar en BigQuery y GCS (salvo dry-run)
    guardado = False
    if not dry_run:
        try:
            estado_guardado = guardar_boletin(resultado)
            guardado = estado_guardado.get("guardado", False)
            if guardado:
                uri_gcs = estado_guardado.get("uri_gcs", "")
                logger.info(
                    f"[Invierno] Boletín guardado — "
                    f"BQ: {estado_guardado.get('guardado_bigquery')}, "
                    f"GCS: {uri_gcs}"
                )
            else:
                logger.warning(
                    f"[Invierno] No se pudo guardar el boletín para "
                    f"{nombre_ubicacion} {fecha}: {estado_guardado.get('errores')}"
                )
        except Exception as exc_guardar:
            logger.error(
                f"[Invierno] Error al guardar boletín para "
                f"{nombre_ubicacion} {fecha}: {exc_guardar}"
            )
    else:
        logger.info(
            f"[Invierno] Dry-run: boletín no guardado para {nombre_ubicacion} {fecha}"
        )

    return {
        "ubicacion": nombre_ubicacion,
        "fecha": fecha,
        "exitoso": True,
        "nivel_eaws_24h": nivel,
        "guardado": guardado,
        "error": None,
    }


def imprimir_resumen(
    resultados_boletines: list,
    resumen_backfill: Optional[dict],
    dry_run: bool,
    solo_backfill: bool,
) -> None:
    """
    Imprime el resumen final de la ejecución.

    Args:
        resultados_boletines: Lista de resultados de generación de boletines
        resumen_backfill: Resumen del backfill o None si no se ejecutó
        dry_run: Si True, indica que fue modo dry-run
        solo_backfill: Si True, indica que solo se ejecutó backfill
    """
    separador = "=" * 60
    print(f"\n{separador}")
    print("RESUMEN — BOLETINES HISTÓRICOS DE INVIERNO")
    print(separador)

    if resumen_backfill is not None:
        print("\n[Backfill de datos históricos]")
        print(f"  Operaciones totales:  {resumen_backfill['total_operaciones']}")
        print(f"  Exitosas:             {resumen_backfill['exitosas']}")
        print(f"  Fallidas:             {resumen_backfill['fallidas']}")
        print(f"  Ya existían (skip):   {resumen_backfill['omitidas_ya_existian']}")

    if solo_backfill:
        print("\n(Modo --solo-backfill: no se generaron boletines)")
        print(separador)
        return

    if not resultados_boletines:
        print("\n(No se generaron boletines)")
        print(separador)
        return

    exitosos = [r for r in resultados_boletines if r["exitoso"]]
    fallidos = [r for r in resultados_boletines if not r["exitoso"]]
    guardados = [r for r in resultados_boletines if r.get("guardado")]

    # Calcular nivel EAWS promedio
    niveles = [r["nivel_eaws_24h"] for r in exitosos if r.get("nivel_eaws_24h") is not None]
    nivel_promedio = round(sum(niveles) / len(niveles), 1) if niveles else None

    print(f"\n[Boletines generados]")
    print(f"  Total:                {len(resultados_boletines)}")
    print(f"  Exitosos:             {len(exitosos)}")
    print(f"  Fallidos:             {len(fallidos)}")
    if not dry_run:
        print(f"  Guardados en BQ/GCS: {len(guardados)}")
    else:
        print(f"  (Dry-run: no se guardó ningún boletín)")
    print(f"  Nivel EAWS promedio:  {nivel_promedio if nivel_promedio else 'N/A'}")

    # Tabla de resultados
    print("\n[Detalle por ubicación y fecha]")
    print(f"  {'Ubicación':<35} {'Fecha':<12} {'Nivel':>6} {'Estado'}")
    print(f"  {'-'*35} {'-'*12} {'-'*6} {'-'*10}")
    for r in resultados_boletines:
        estado = "OK" if r["exitoso"] else "ERROR"
        if r["exitoso"] and r.get("guardado"):
            estado = "OK+guardado"
        nivel_str = str(r["nivel_eaws_24h"]) if r.get("nivel_eaws_24h") else "-"
        nombre_corto = r["ubicacion"][-35:] if len(r["ubicacion"]) > 35 else r["ubicacion"]
        print(f"  {nombre_corto:<35} {r['fecha']:<12} {nivel_str:>6} {estado}")

    # Errores
    if fallidos:
        print(f"\n[Errores ({len(fallidos)})]")
        for r in fallidos:
            print(f"  - {r['ubicacion']} | {r['fecha']}: {r.get('error', 'error desconocido')}")

    print(separador)


def main() -> int:
    """Punto de entrada principal del orquestador de invierno."""
    args = parsear_argumentos()

    # Validar ubicaciones
    ubicaciones_validas = {}
    for nombre in args.ubicaciones:
        if nombre in UBICACIONES_LA_PARVA:
            ubicaciones_validas[nombre] = UBICACIONES_LA_PARVA[nombre]
        else:
            logger.warning(
                f"[Invierno] Ubicación sin coordenadas registradas (ignorada): '{nombre}'"
            )

    if not ubicaciones_validas:
        print("Error: no hay ubicaciones válidas para procesar.", file=sys.stderr)
        return 1

    # Validar y convertir fechas
    fechas_validas = []
    fechas_datetime = {}
    for fecha_str in args.fechas:
        fecha_ref = convertir_fecha_a_datetime(fecha_str)
        if fecha_ref is not None:
            fechas_validas.append(fecha_str)
            fechas_datetime[fecha_str] = fecha_ref

    if not fechas_validas:
        print("Error: no hay fechas válidas para procesar.", file=sys.stderr)
        return 1

    logger.info(
        f"[Invierno] Configuración: "
        f"{len(ubicaciones_validas)} ubicaciones × {len(fechas_validas)} fechas = "
        f"{len(ubicaciones_validas) * len(fechas_validas)} operaciones"
    )
    logger.info(
        f"[Invierno] Modo: "
        f"{'dry-run' if args.dry_run else 'guardado completo'}"
        f"{' | solo-backfill' if args.solo_backfill else ''}"
    )

    # ─── Fase 1: Backfill de datos históricos ────────────────────────────────
    resumen_backfill = ejecutar_backfill_para_ubicaciones(
        ubicaciones=ubicaciones_validas,
        fechas=fechas_validas,
    )

    if args.solo_backfill:
        imprimir_resumen(
            resultados_boletines=[],
            resumen_backfill=resumen_backfill,
            dry_run=args.dry_run,
            solo_backfill=True,
        )
        return 0 if resumen_backfill["fallidas"] == 0 else 1

    # ─── Fase 2: Generación de boletines ─────────────────────────────────────
    logger.info("[Invierno] Iniciando generación de boletines históricos...")

    agente = AgenteRiesgoAvalancha()
    resultados_boletines = []
    total_boletines = len(ubicaciones_validas) * len(fechas_validas)
    contador = 0

    for fecha_str in fechas_validas:
        fecha_ref = fechas_datetime[fecha_str]

        for nombre_ub in ubicaciones_validas:
            contador += 1
            logger.info(
                f"[Invierno] Boletín {contador}/{total_boletines}: "
                f"{nombre_ub} | {fecha_str}"
            )

            resultado = generar_boletin_historico(
                agente=agente,
                nombre_ubicacion=nombre_ub,
                fecha=fecha_str,
                fecha_referencia=fecha_ref,
                dry_run=args.dry_run,
            )
            resultados_boletines.append(resultado)

            # Pausa para no saturar la API entre boletines consecutivos
            if contador < total_boletines:
                time.sleep(args.pausa_entre_boletines)

    # ─── Resumen final ────────────────────────────────────────────────────────
    imprimir_resumen(
        resultados_boletines=resultados_boletines,
        resumen_backfill=resumen_backfill,
        dry_run=args.dry_run,
        solo_backfill=False,
    )

    # Código de salida: 0 si todos exitosos, 1 si hubo algún fallo
    fallidos = [r for r in resultados_boletines if not r["exitoso"]]
    return 0 if not fallidos else 1


if __name__ == "__main__":
    sys.exit(main())
