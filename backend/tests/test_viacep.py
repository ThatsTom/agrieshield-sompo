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


if __name__ == "__main__":
    unittest.main()
