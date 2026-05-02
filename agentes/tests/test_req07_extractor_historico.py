"""
Tests para REQ-07 — Extractor histórico Open-Meteo.

Cubre:
- _generar_chunks: partición correcta del rango de fechas
- _parsear_respuesta: conversión Open-Meteo → schema condiciones_actuales
- _llamar_open_meteo: petición con parámetros correctos (mock HTTP)
- _insertar_filas: idempotencia — filas existentes no se reinsertan
- extractor_historico: handler HTTP con payload válido e inválido
"""

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Tests _generar_chunks ─────────────────────────────────────────────────────

class TestGenerarChunks:

    def _fn(self):
        from datos.extractor_historico.main import _generar_chunks
        return _generar_chunks

    def test_un_chunk_cuando_rango_menor_chunk_dias(self):
        chunks = self._fn()(date(2024, 6, 1), date(2024, 6, 10), 30)
        assert len(chunks) == 1
        assert chunks[0] == (date(2024, 6, 1), date(2024, 6, 10))

    def test_exactamente_dos_chunks(self):
        # Jun-1 → Jul-30 = 60 días = exactamente 2 chunks de 30
        chunks = self._fn()(date(2024, 6, 1), date(2024, 7, 30), 30)
        assert len(chunks) == 2
        assert chunks[0][0] == date(2024, 6, 1)
        assert chunks[-1][1] == date(2024, 7, 30)

    def test_ultimo_chunk_no_supera_fecha_fin(self):
        chunks = self._fn()(date(2024, 6, 1), date(2024, 8, 15), 30)
        assert chunks[-1][1] == date(2024, 8, 15)

    def test_chunks_sin_solapamiento(self):
        chunks = self._fn()(date(2024, 6, 1), date(2024, 9, 30), 30)
        for i in range(len(chunks) - 1):
            fin_actual  = chunks[i][1]
            ini_sgte    = chunks[i + 1][0]
            assert (ini_sgte - fin_actual).days == 1

    def test_un_solo_dia(self):
        chunks = self._fn()(date(2024, 6, 15), date(2024, 6, 15), 30)
        assert len(chunks) == 1
        assert chunks[0] == (date(2024, 6, 15), date(2024, 6, 15))


# ── Tests _parsear_respuesta ──────────────────────────────────────────────────

class TestParsearRespuesta:

    def _respuesta_minima(self) -> dict:
        return {
            'hourly': {
                'time':                  ['2024-06-15T00:00', '2024-06-15T01:00'],
                'temperature_2m':        [-2.5, -3.1],
                'precipitation':         [0.0, 0.0],
                'snowfall':              [0.0, 0.0],
                'snow_depth':            [0.45, 0.45],
                'wind_speed_10m':        [15.2, 12.8],
                'wind_direction_10m':    [270, 280],
                'relative_humidity_2m':  [82, 85],
                'surface_pressure':      [740.0, 739.5],
                'cloud_cover':           [20, 25],
                'weather_code':          [1, 1],
            }
        }

    def test_retorna_una_fila_por_hora(self):
        from datos.extractor_historico.main import _parsear_respuesta
        filas = _parsear_respuesta(
            self._respuesta_minima(),
            'La Parva Sector Bajo',
            {'latitud': -33.363, 'longitud': -70.301},
        )
        assert len(filas) == 2

    def test_campos_obligatorios_presentes(self):
        from datos.extractor_historico.main import _parsear_respuesta
        filas = _parsear_respuesta(
            self._respuesta_minima(),
            'La Parva Sector Bajo',
            {'latitud': -33.363, 'longitud': -70.301},
        )
        fila = filas[0]
        assert fila['nombre_ubicacion'] == 'La Parva Sector Bajo'
        assert fila['latitud'] == pytest.approx(-33.363)
        assert fila['temperatura'] == pytest.approx(-2.5)
        assert fila['fuente'] == 'openmeteo_historical'

    def test_hora_actual_en_formato_iso_utc(self):
        from datos.extractor_historico.main import _parsear_respuesta
        filas = _parsear_respuesta(
            self._respuesta_minima(),
            'Interlaken',
            {'latitud': 46.686, 'longitud': 7.863},
        )
        assert 'Z' in filas[0]['hora_actual'] or '+00:00' in filas[0]['hora_actual']

    def test_sin_tiempos_retorna_lista_vacia(self):
        from datos.extractor_historico.main import _parsear_respuesta
        datos = {'hourly': {}}
        filas = _parsear_respuesta(datos, 'La Parva Sector Bajo', {'latitud': -33.363, 'longitud': -70.301})
        assert filas == []

    def test_datos_json_crudo_contiene_snowfall(self):
        from datos.extractor_historico.main import _parsear_respuesta
        resp = self._respuesta_minima()
        resp['hourly']['snowfall'] = [0.5, 0.0]
        resp['hourly']['weather_code'] = [73, 1]
        filas = _parsear_respuesta(resp, 'Matterhorn Zermatt', {'latitud': 45.976, 'longitud': 7.659})
        crudo = json.loads(filas[0]['datos_json_crudo'])
        assert 'snowfall_cm' in crudo
        assert crudo['snowfall_cm'] == pytest.approx(0.5)


# ── Tests _llamar_open_meteo ──────────────────────────────────────────────────

class TestLlamarOpenMeteo:

    @patch('datos.extractor_historico.main.requests.get')
    def test_llama_con_parametros_correctos(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'hourly': {}}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from datos.extractor_historico.main import _llamar_open_meteo
        _llamar_open_meteo(
            lat=-33.363, lon=-70.301,
            fecha_inicio=date(2024, 6, 15),
            fecha_fin=date(2024, 7, 15),
        )

        args, kwargs = mock_get.call_args
        params = kwargs.get('params', {})
        assert params['latitude'] == pytest.approx(-33.363)
        assert params['start_date'] == '2024-06-15'
        assert params['end_date'] == '2024-07-15'
        assert 'temperature_2m' in params['hourly']

    @patch('datos.extractor_historico.main.requests.get')
    def test_error_http_propaga_excepcion(self, mock_get):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("429 Too Many Requests")
        mock_get.return_value = mock_resp

        from datos.extractor_historico.main import _llamar_open_meteo
        with pytest.raises(req.HTTPError):
            _llamar_open_meteo(-33.363, -70.301, date(2024, 6, 1), date(2024, 6, 30))


# ── Tests _insertar_filas ─────────────────────────────────────────────────────

class TestInsertarFilas:

    def _fila(self, hora: str) -> dict:
        return {
            'nombre_ubicacion': 'La Parva Sector Bajo',
            'latitud': -33.363,
            'longitud': -70.301,
            'hora_actual': hora,
            'temperatura': -5.0,
            'fuente': 'openmeteo_historical',
        }

    def test_dry_run_no_llama_insert(self):
        from datos.extractor_historico.main import _insertar_filas
        mock_bq = MagicMock()
        mock_bq.query.return_value.result.return_value = []
        ins, omit = _insertar_filas(mock_bq, [self._fila('2024-06-15T00:00:00+00:00')], dry_run=True)
        mock_bq.insert_rows_json.assert_not_called()
        assert ins == 0

    def test_lista_vacia_retorna_cero_cero(self):
        from datos.extractor_historico.main import _insertar_filas
        mock_bq = MagicMock()
        ins, omit = _insertar_filas(mock_bq, [], dry_run=False)
        assert ins == 0
        assert omit == 0

    def test_fila_existente_no_se_reinserta(self):
        from datos.extractor_historico.main import _insertar_filas

        hora = '2024-06-15T00:00:00+00:00'
        mock_bq = MagicMock()
        # BQ dice que la fila ya existe
        fila_existente = MagicMock()
        fila_existente.__getitem__ = lambda self, k: datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc)
        mock_bq.query.return_value.result.return_value = [fila_existente]
        mock_bq.insert_rows_json.return_value = []

        ins, omit = _insertar_filas(mock_bq, [self._fila(hora)], dry_run=False)
        mock_bq.insert_rows_json.assert_not_called()
        assert ins == 0
        assert omit == 1

    def test_fila_nueva_se_inserta(self):
        from datos.extractor_historico.main import _insertar_filas
        mock_bq = MagicMock()
        mock_bq.query.return_value.result.return_value = []
        mock_bq.insert_rows_json.return_value = []

        hora = '2024-06-15T00:00:00+00:00'
        ins, omit = _insertar_filas(mock_bq, [self._fila(hora)], dry_run=False)
        mock_bq.insert_rows_json.assert_called_once()
        assert ins == 1
        assert omit == 0


# ── Tests handler HTTP ────────────────────────────────────────────────────────

class TestExtractorHistoricoHandler:

    def _mock_request(self, payload: dict):
        req = MagicMock()
        req.get_json.return_value = payload
        return req

    @patch('datos.extractor_historico.main.bigquery.Client')
    @patch('datos.extractor_historico.main._llamar_open_meteo')
    @patch('datos.extractor_historico.main._insertar_filas')
    def test_payload_valido_retorna_200(self, mock_insertar, mock_llamar, mock_bq_cls):
        mock_llamar.return_value = {'hourly': {}}
        mock_insertar.return_value = (0, 0)

        from datos.extractor_historico.main import extractor_historico
        req = self._mock_request({
            'ubicaciones': ['La Parva Sector Bajo'],
            'fecha_inicio': '2024-06-15',
            'fecha_fin':    '2024-06-16',
            'dry_run':      True,
        })
        body, code = extractor_historico(req)
        assert code == 200
        data = json.loads(body)
        assert 'resumen' in data
        assert data['dry_run'] is True

    @patch('datos.extractor_historico.main.bigquery.Client')
    def test_fecha_invalida_retorna_400(self, mock_bq_cls):
        from datos.extractor_historico.main import extractor_historico
        req = self._mock_request({'fecha_inicio': 'no-es-fecha', 'fecha_fin': '2024-06-30'})
        body, code = extractor_historico(req)
        assert code == 400

    @patch('datos.extractor_historico.main.bigquery.Client')
    def test_ubicacion_desconocida_retorna_400(self, mock_bq_cls):
        from datos.extractor_historico.main import extractor_historico
        req = self._mock_request({
            'ubicaciones': ['EstacionInventada XYZ'],
            'fecha_inicio': '2024-06-15',
            'fecha_fin':    '2024-06-30',
        })
        body, code = extractor_historico(req)
        assert code == 400
