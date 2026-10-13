import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from backend.main import NovoRecebimento, registrar_recebimento


def criar_request_admin():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/pagamentos/1/recebimentos",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "query_string": b""
    })
    request.state.usuario_admin_id = 7
    request.state.nome_usuario_admin = "Admin Teste"
    return request


class IncrementalPaymentTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value

    @patch("backend.main.conectar_banco")
    def test_registra_parcelas_somando_ao_acumulado_e_auditando(self, conectar):
        conectar.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            ("Pendente", Decimal("100.00"), Decimal("50.00"), Decimal("0.00"), 22),
            ("Pendente", Decimal("100.00"), Decimal("70.00"), Decimal("0.00"), 22)
        ]
        request = criar_request_admin()

        primeira = registrar_recebimento(
            1,
            NovoRecebimento(
                valor_recebido=20,
                data_pagamento="2026-10-13",
                metodo_pagamento="PIX",
                observacoes="Primeira parcela"
            ),
            request
        )
        segunda = registrar_recebimento(
            1,
            NovoRecebimento(
                valor_recebido=30,
                data_pagamento="2026-10-13",
                metodo_pagamento="Dinheiro"
            ),
            request
        )

        self.assertEqual(primeira["total_recebido"], 70)
        self.assertEqual(primeira["saldo_pendente"], 30)
        self.assertEqual(primeira["status"], "Pendente")
        self.assertEqual(segunda["total_recebido"], 100)
        self.assertEqual(segunda["saldo_pendente"], 0)
        self.assertEqual(segunda["status"], "Recebido")
        insert_recebimentos = [
            chamada for chamada in self.cursor.execute.call_args_list
            if "INSERT INTO pagamento_recebimento" in chamada.args[0]
        ]
        self.assertEqual(len(insert_recebimentos), 2)
        self.assertEqual(insert_recebimentos[0].args[1][1], Decimal("20.00"))
        self.assertEqual(insert_recebimentos[0].args[1][4], "Admin Teste")
        self.assertEqual(insert_recebimentos[0].args[1][5], "PIX")
        self.assertEqual(self.connection.commit.call_count, 2)

    @patch("backend.main.conectar_banco")
    def test_recusa_parcela_maior_que_saldo_sem_alterar_pagamento(self, conectar):
        conectar.return_value = self.connection
        self.cursor.fetchone.return_value = (
            "Pendente", Decimal("100.00"), Decimal("50.00"), Decimal("0.00"), 22
        )

        with self.assertRaises(HTTPException) as erro:
            registrar_recebimento(
                1,
                NovoRecebimento(
                    valor_recebido=50.01,
                    metodo_pagamento="PIX"
                ),
                criar_request_admin()
            )

        self.assertEqual(erro.exception.status_code, 409)
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.cursor.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
