import json
import os
import unittest
from datetime import datetime
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from backend.main import enviar_notificacao_whatsapp_reserva


class NotificacaoWhatsAppTests(unittest.TestCase):
    def setUp(self):
        self.configuracao = {
            "WHATSAPP_ACCESS_TOKEN": "token-de-teste",
            "WHATSAPP_PHONE_NUMBER_ID": "123456789",
            "WHATSAPP_AGENT_PHONE": "+55 (11) 99999-8888",
            "WHATSAPP_TEMPLATE_NAME": "solicitacao_reserva",
            "WHATSAPP_TEMPLATE_LANGUAGE": "pt_BR",
            "WHATSAPP_GRAPH_API_VERSION": "v99.0",
        }
        self.data = datetime(2026, 10, 1, 19, 30)

    @patch.dict(os.environ, {}, clear=True)
    def test_sem_configuracao_mantem_notificacao_desativada(self):
        resultado = enviar_notificacao_whatsapp_reserva(
            42, "Ana", "11999998888", "Quadra 1", self.data, self.data
        )

        self.assertEqual(resultado, "desativada")

    @patch("backend.main.urlopen")
    @patch.dict(os.environ, {})
    def test_envia_modelo_para_agente_com_dados_da_reserva(self, urlopen):
        os.environ.update(self.configuracao)
        resposta = MagicMock()
        resposta.status = 200
        resposta.__enter__.return_value = resposta
        urlopen.return_value = resposta

        resultado = enviar_notificacao_whatsapp_reserva(
            42, "Ana", "(11) 99999-8888", "Quadra 1", self.data, self.data
        )

        self.assertEqual(resultado, "aceita")
        requisicao = urlopen.call_args.args[0]
        self.assertEqual(
            requisicao.full_url,
            "https://graph.facebook.com/v99.0/123456789/messages"
        )
        self.assertEqual(
            requisicao.get_header("Authorization"),
            f"Bearer {self.configuracao['WHATSAPP_ACCESS_TOKEN']}"
        )
        payload = json.loads(requisicao.data)
        self.assertEqual(payload["to"], "5511999998888")
        self.assertEqual(
            [
                parametro["text"]
                for parametro in payload["template"]["components"][0]["parameters"]
            ],
            ["Ana", "(11) 99999-8888", "Quadra 1", "01/10/2026", "19:30"]
        )

    @patch("backend.main.urlopen")
    @patch.dict(os.environ, {})
    def test_falha_do_provedor_nao_gera_excecao(self, urlopen):
        os.environ.update(self.configuracao)
        urlopen.side_effect = HTTPError(
            "https://graph.facebook.com/",
            400,
            "Bad Request",
            Message(),
            None
        )

        resultado = enviar_notificacao_whatsapp_reserva(
            42, "Ana", "11999998888", "Quadra 1", self.data, self.data
        )

        self.assertEqual(resultado, "falhou")


if __name__ == "__main__":
    unittest.main()
