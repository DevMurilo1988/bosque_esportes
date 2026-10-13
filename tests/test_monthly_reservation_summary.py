import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from backend.main import (
    NovaMensalidade,
    obter_resumo_reservas_admin,
    resolver_valor_mensal
)


class MonthlyReservationPriceTests(unittest.TestCase):
    def nova_mensalidade(self, **overrides):
        dados = {
            "nome": "Cliente",
            "contato": "41999999999",
            "quadra_id": 1,
            "dia_semana": 1,
            "horario": "19:00",
            "data_inicio": "2026-10-19"
        }
        dados.update(overrides)
        return NovaMensalidade(**dados)

    def test_permite_valor_mensal_editavel_ou_ausente(self):
        self.assertEqual(
            self.nova_mensalidade(valor_mensal=1250.50).valor_mensal,
            1250.50
        )
        self.assertIsNone(self.nova_mensalidade().valor_mensal)

    def test_rejeita_valor_mensal_negativo_ou_nao_finito(self):
        for value in (-1, float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    self.nova_mensalidade(valor_mensal=value)

    def test_usa_valor_da_quadra_ou_excecao_editavel(self):
        self.assertEqual(resolver_valor_mensal(1500, None), 1500)
        self.assertEqual(resolver_valor_mensal(1500, 1200.50), 1200.50)
        self.assertEqual(resolver_valor_mensal(0, 100), 100)
        with self.assertRaises(HTTPException):
            resolver_valor_mensal(0, None)
        with self.assertRaises(HTTPException):
            resolver_valor_mensal(1500, float("inf"))

    @patch("backend.main.conectar_banco")
    def test_resumo_separa_todos_os_status_por_modalidade(self, conectar):
        conexao = MagicMock()
        cursor = conexao.cursor.return_value
        cursor.fetchall.side_effect = [
            [("Pendente", 2), ("Confirmado", 3), ("Cancelado", 1),
             ("Não atendido", 4)],
            [("Pendente", 1), ("Ativa", 5), ("Encerrada", 2)]
        ]
        conectar.return_value = conexao
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/admin/resumo-reservas",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "query_string": b""
        })
        request.state.nivel_admin = "root"
        request.state.quadras_permitidas = []

        resumo = obter_resumo_reservas_admin(request)

        self.assertEqual(resumo["total"], 18)
        self.assertEqual(resumo["avulsas"]["total"], 10)
        self.assertEqual(resumo["avulsas"]["nao_atendido"], 4)
        self.assertEqual(resumo["mensais"]["ativa"], 5)
        self.assertEqual(resumo["mensais"]["encerrada"], 2)
        conexao.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
