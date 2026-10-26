from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests


BACKEND = Path(__file__).resolve().parents[1]
for pasta in (BACKEND, BACKEND / "app", BACKEND / "etl"):
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))

import servicos_externos as servicos  # noqa: E402


class RespostaFake:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class ViaCepTests(unittest.TestCase):
    def test_consulta_viacep_mapeia_endereco_sem_inventar_coordenadas(self):
        getter = Mock(
            return_value=RespostaFake(
                {
                    "cep": "01001-000",
                    "logradouro": "Praça da Sé",
                    "complemento": "lado ímpar",
                    "bairro": "Sé",
                    "localidade": "São Paulo",
                    "uf": "SP",
                    "ibge": "3550308",
                }
            )
        )
        with patch.object(servicos, "resolver_cep_base_estatica", return_value=None):
            resultado = servicos.geocoding_por_cep("01001-000", http_get=getter)

        getter.assert_called_once_with(
            "https://viacep.com.br/ws/01001000/json/", timeout=(5, 10)
        )
        self.assertEqual("Praça da Sé", resultado["logradouro"])
        self.assertEqual("São Paulo", resultado["cidade"])
        self.assertEqual("SP", resultado["uf"])
        self.assertIsNone(resultado["latitude"])
        self.assertIsNone(resultado["longitude"])
        self.assertEqual("viacep", resultado["origem"])

    def test_cep_inexistente_nao_e_substituido_por_localizacao_generica(self):
        with patch.object(servicos, "resolver_cep_base_estatica", return_value=None):
            with self.assertRaises(servicos.CepNaoEncontrado):
                servicos.geocoding_por_cep(
                    "99999999", http_get=Mock(return_value=RespostaFake({"erro": True}))
                )

    def test_falha_de_rede_usa_apenas_correspondencia_local_exata(self):
        base = {
            "origem": "base_estatica",
            "logradouro": "Rodovia MT-242",
            "bairro": "Zona Rural",
            "cidade": "Sorriso",
            "uf": "MT",
            "latitude": "-12.545",
            "longitude": "-55.721",
        }
        getter = Mock(side_effect=requests.ConnectionError("sem rede"))
        with patch.object(servicos, "resolver_cep_base_estatica", return_value=base):
            resultado = servicos.geocoding_por_cep("78890000", http_get=getter)
        self.assertEqual("base_estatica_fallback", resultado["origem"])
        self.assertEqual(-12.545, resultado["latitude"])

    def test_cep_invalido_falha_antes_da_rede(self):
        getter = Mock()
        with self.assertRaises(servicos.CepInvalido):
            servicos.geocoding_por_cep("123", http_get=getter)
        getter.assert_not_called()

    def test_falha_da_base_local_nao_impede_consulta_ao_viacep(self):
        getter = Mock(
            return_value=RespostaFake(
                {
                    "cep": "01001-000",
                    "logradouro": "Praça da Sé",
                    "localidade": "São Paulo",
                    "uf": "SP",
                }
            )
        )
        with patch.object(
            servicos,
            "resolver_cep_base_estatica",
            side_effect=RuntimeError("banco local indisponível"),
        ):
            resultado = servicos.geocoding_por_cep("01001000", http_get=getter)

        self.assertEqual("viacep", resultado["origem"])
        self.assertEqual("Praça da Sé", resultado["logradouro"])
        self.assertIsNone(resultado["latitude"])


class GeocodificacaoEnderecoTests(unittest.TestCase):
    def test_endereco_com_numero_confirmado_retorna_coordenadas_e_precisao(self):
        getter = Mock(
            return_value=RespostaFake(
                [
                    {
                        "lat": "-23.5505200",
                        "lon": "-46.6333080",
                        "display_name": "Praça da Sé, 100, São Paulo, Brasil",
                        "address": {
                            "country_code": "br",
                            "house_number": "100",
                            "road": "Praça da Sé",
                            "city": "São Paulo",
                            "state": "São Paulo",
                        },
                    }
                ]
            )
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001-000",
            logradouro="Praça da Sé",
            numero_km="100",
            bairro="Sé",
            cidade="São Paulo",
            uf="sp",
            http_get=getter,
        )

        self.assertTrue(resultado["encontrado"])
        self.assertEqual("numero", resultado["precisao"])
        self.assertFalse(resultado["requer_confirmacao"])
        self.assertEqual(-23.55052, resultado["latitude"])
        self.assertEqual(-46.633308, resultado["longitude"])
        _, kwargs = getter.call_args
        self.assertEqual("100 Praça da Sé", kwargs["params"]["street"])
        self.assertEqual("01001000", kwargs["params"]["postalcode"])
        self.assertEqual("br", kwargs["params"]["countrycodes"])
        self.assertIn("AgriShield", kwargs["headers"]["User-Agent"])

    def test_sem_resultado_com_cep_relaxa_cep_e_marca_aproximado(self):
        getter = Mock(
            side_effect=[
                RespostaFake([]),
                RespostaFake(
                    [
                        {
                            "lat": "-23.5504",
                            "lon": "-46.6332",
                            "display_name": "Praça da Sé, São Paulo, Brasil",
                            "address": {
                                "country_code": "br",
                                "road": "Praça da Sé",
                                "city": "São Paulo",
                                "state": "São Paulo",
                            },
                        }
                    ]
                ),
                RespostaFake([]),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertEqual(3, getter.call_count)
        self.assertTrue(resultado["encontrado"])
        self.assertEqual("logradouro", resultado["precisao"])
        self.assertTrue(resultado["requer_confirmacao"])
        self.assertIn("aproximado", resultado["aviso"])
        segunda_consulta = getter.call_args_list[1].kwargs["params"]
        self.assertEqual("100 Praça da Sé", segunda_consulta["street"])
        self.assertNotIn("postalcode", segunda_consulta)

    def test_aceita_rua_cidade_uf_e_numero_quando_cep_do_mapa_diverge(self):
        getter = Mock(
            return_value=RespostaFake(
                [
                    {
                        "lat": "-23.6098639",
                        "lon": "-46.5952919",
                        "display_name": "Rua Maria Santíssima, 100, São Paulo, Brasil",
                        "address": {
                            "country_code": "br",
                            "postcode": "04231-030",
                            "house_number": "100",
                            "road": "Rua Maria Santissíma",
                            "city": "São Paulo",
                            "state": "São Paulo",
                            "ISO3166-2-lvl4": "BR-SP",
                        },
                    }
                ]
            )
        )

        resultado = servicos.geocoding_por_endereco(
            cep="04236-310",
            logradouro="Rua Maria Santíssima",
            numero_km="100",
            bairro="Cidade Nova Heliópolis",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertTrue(resultado["encontrado"])
        self.assertEqual("numero", resultado["precisao"])
        self.assertEqual("numero_confirmado_cep_divergente", resultado["motivo"])
        self.assertEqual(-23.6098639, resultado["latitude"])
        self.assertIn("CEP do ponto no mapa difere", resultado["aviso"])

    def test_nao_confunde_nome_curto_de_rua_com_prefixo_de_outra(self):
        candidato = RespostaFake(
            [
                {
                    "lat": "-23.5",
                    "lon": "-46.6",
                    "display_name": "Rua Antonio, 10, São Paulo, Brasil",
                    "address": {
                        "country_code": "br",
                        "postcode": "01001-001",
                        "house_number": "10",
                        "road": "Rua Antonio",
                        "city": "São Paulo",
                        "state": "São Paulo",
                        "ISO3166-2-lvl4": "BR-SP",
                    },
                }
            ]
        )
        getter = Mock(
            side_effect=[
                candidato,
                candidato,
                candidato,
                RespostaFake(
                    {
                        "cep": "01001000",
                        "city": "São Paulo",
                        "state": "SP",
                        "location": None,
                    }
                ),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Rua A",
            numero_km="10",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertFalse(resultado["encontrado"])

    def test_compara_todas_as_estrategias_antes_de_manter_ponto_aproximado(self):
        aproximado = RespostaFake(
            [
                {
                    "lat": "-23.51",
                    "lon": "-46.61",
                    "address": {
                        "country_code": "br",
                        "postcode": "01001-000",
                        "road": "Praça da Sé",
                        "city": "São Paulo",
                        "state": "São Paulo",
                    },
                }
            ]
        )
        numero_exato = RespostaFake(
            [
                {
                    "lat": "-23.5506",
                    "lon": "-46.6334",
                    "address": {
                        "country_code": "br",
                        "postcode": "01001-001",
                        "house_number": "100",
                        "road": "Praça da Sé",
                        "city": "São Paulo",
                        "state": "São Paulo",
                        "ISO3166-2-lvl4": "BR-SP",
                    },
                }
            ]
        )
        getter = Mock(
            side_effect=[aproximado, numero_exato, RespostaFake([])]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertEqual(2, getter.call_count)
        self.assertEqual("numero", resultado["precisao"])
        self.assertEqual(-23.5506, resultado["latitude"])

    def test_prefere_candidato_com_numero_exato_e_rejeita_cep_incompativel(self):
        getter = Mock(
            return_value=RespostaFake(
                [
                    {
                        "lat": "-23.1",
                        "lon": "-46.1",
                        "address": {
                            "country_code": "br",
                            "postcode": "99999-999",
                            "house_number": "100",
                            "road": "Praça da Sé",
                        },
                    },
                    {
                        "lat": "-23.55052",
                        "lon": "-46.633308",
                        "address": {
                            "country_code": "br",
                            "postcode": "01001-000",
                            "house_number": "98",
                            "road": "Praça da Sé",
                        },
                    },
                    {
                        "lat": "-23.5506",
                        "lon": "-46.6334",
                        "address": {
                            "country_code": "br",
                            "postcode": "01001-000",
                            "house_number": "100",
                            "road": "Praça da Sé",
                        },
                    },
                ]
            )
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertEqual("numero", resultado["precisao"])
        self.assertEqual(-23.5506, resultado["latitude"])

    def test_sem_cep_rejeita_homonimo_de_outra_cidade_sem_retornar_502(self):
        candidatos = RespostaFake(
            [
                {
                    "lat": "-22.9",
                    "lon": "-43.2",
                    "display_name": "Praça da Sé, 100, Rio de Janeiro",
                    "address": {
                        "country_code": "br",
                        "house_number": "100",
                        "road": "Praça da Sé",
                        "city": "Rio de Janeiro",
                        "state": "Rio de Janeiro",
                    },
                }
            ]
        )
        getter = Mock(
            side_effect=[
                candidatos,
                candidatos,
                candidatos,
                RespostaFake({"location": None}),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            bairro="Sé",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertFalse(resultado["encontrado"])
        self.assertEqual("indisponivel", resultado["precisao"])

    def test_sigla_uf_nao_casa_com_substring_de_outro_estado(self):
        candidatos = RespostaFake(
            [
                {
                    "lat": "-20.31",
                    "lon": "-40.31",
                    "display_name": "Praça da Sé, 100, São Paulo",
                    "address": {
                        "country_code": "br",
                        "house_number": "100",
                        "road": "Praça da Sé",
                        "city": "São Paulo",
                        "state": "Espírito Santo",
                        "ISO3166-2-lvl4": "BR-ES",
                    },
                }
            ]
        )
        getter = Mock(
            side_effect=[
                candidatos,
                candidatos,
                candidatos,
                RespostaFake({"location": None}),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertFalse(resultado["encontrado"])

    def test_bairro_participa_da_escolha_entre_candidatos_compativeis(self):
        getter = Mock(
            return_value=RespostaFake(
                [
                    {
                        "lat": "-23.51",
                        "lon": "-46.61",
                        "display_name": "Praça da Sé, 100, outro bairro",
                        "address": {
                            "country_code": "br",
                            "postcode": "01001-000",
                            "house_number": "100",
                            "road": "Praça da Sé",
                            "suburb": "Bela Vista",
                            "city": "São Paulo",
                            "state": "São Paulo",
                        },
                    },
                    {
                        "lat": "-23.5506",
                        "lon": "-46.6334",
                        "display_name": "Praça da Sé, 100, Sé",
                        "address": {
                            "country_code": "br",
                            "postcode": "01001-000",
                            "house_number": "100",
                            "road": "Praça da Sé",
                            "suburb": "Sé",
                            "city": "São Paulo",
                            "state": "São Paulo",
                        },
                    },
                ]
            )
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Praça da Sé",
            numero_km="100",
            bairro="Sé",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertEqual(-23.5506, resultado["latitude"])
        self.assertEqual("numero", resultado["precisao"])

    def test_endereco_nao_localizado_retorna_resultado_nulo_sem_inventar_ponto(self):
        getter = Mock(
            side_effect=[
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake({"location": None}),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="01001000",
            logradouro="Rua inexistente",
            numero_km="999",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertFalse(resultado["encontrado"])
        self.assertIsNone(resultado["latitude"])
        self.assertIsNone(resultado["longitude"])
        self.assertEqual("indisponivel", resultado["precisao"])
        self.assertEqual("sem_coordenadas_compativeis", resultado["motivo"])

    def test_sem_resultado_no_mapa_usa_coordenada_aproximada_do_cep(self):
        getter = Mock(
            side_effect=[
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake(
                    {
                        "cep": "30130010",
                        "state": "MG",
                        "city": "Belo Horizonte",
                        "neighborhood": "Centro",
                        "street": "Praça Sete de Setembro",
                        "location": {
                            "type": "Point",
                            "coordinates": {
                                "longitude": "-43.93778",
                                "latitude": "-19.92083",
                            },
                        },
                    }
                ),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="30130-010",
            logradouro="Praça Sete de Setembro",
            numero_km="100",
            bairro="Centro",
            cidade="Belo Horizonte",
            uf="MG",
            http_get=getter,
        )

        self.assertTrue(resultado["encontrado"])
        self.assertEqual("cep", resultado["precisao"])
        self.assertEqual("brasilapi_cep_v2", resultado["origem"])
        self.assertTrue(resultado["requer_confirmacao"])
        self.assertEqual(-19.92083, resultado["latitude"])
        self.assertEqual(-43.93778, resultado["longitude"])
        self.assertIn("aproximado pelo CEP", resultado["aviso"])
        self.assertEqual(
            "https://brasilapi.com.br/api/cep/v2/30130010",
            getter.call_args.args[0],
        )

    def test_fallback_de_cep_rejeita_cidade_e_uf_incompativeis(self):
        getter = Mock(
            side_effect=[
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake([]),
                RespostaFake(
                    {
                        "cep": "30130010",
                        "state": "MG",
                        "city": "Belo Horizonte",
                        "street": "Praça Sete de Setembro",
                        "location": {
                            "coordinates": {
                                "longitude": "-43.93778",
                                "latitude": "-19.92083",
                            },
                        },
                    }
                ),
            ]
        )

        resultado = servicos.geocoding_por_endereco(
            cep="30130010",
            logradouro="Rua Inexistente",
            numero_km="100",
            cidade="São Paulo",
            uf="SP",
            http_get=getter,
        )

        self.assertFalse(resultado["encontrado"])
        self.assertIsNone(resultado["latitude"])

    def test_falha_do_provedor_nao_expoe_erro_de_transporte(self):
        getter = Mock(side_effect=requests.Timeout("segredo de transporte"))
        with self.assertRaisesRegex(
            servicos.ErroConsultaEndereco,
            "Não foi possível consultar a localização automática agora",
        ):
            servicos.geocoding_por_endereco(
                cep="01001000",
                logradouro="Praça da Sé",
                numero_km="100",
                cidade="São Paulo",
                uf="SP",
                http_get=getter,
            )

    def test_endereco_incompleto_falha_antes_da_rede(self):
        getter = Mock()
        with self.assertRaisesRegex(ValueError, "Preencha CEP"):
            servicos.geocoding_por_endereco(
                cep="01001000",
                logradouro="",
                numero_km="100",
                cidade="São Paulo",
                uf="SP",
                http_get=getter,
            )
        getter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
