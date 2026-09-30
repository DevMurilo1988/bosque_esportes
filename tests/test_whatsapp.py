import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from backend.main import criar_link_whatsapp_reserva


class LinkWhatsAppReservaTests(unittest.TestCase):
    def setUp(self):
        self.data = datetime(2026, 10, 1, 19, 30)

    def test_cria_link_com_mensagem_e_telefone_brasileiro(self):
        link = criar_link_whatsapp_reserva(
            "(41) 3333-2222",
            "Ana Silva",
            "(41) 99999-8888",
            "Sintético G",
            self.data,
            self.data
        )

        url = urlparse(link)
        self.assertEqual(url.netloc, "wa.me")
        self.assertEqual(url.path, "/554133332222")
        mensagem = parse_qs(url.query)["text"][0]
        self.assertIn("Quadra: Sintético G", mensagem)
        self.assertIn("Data: 01/10/2026", mensagem)
        self.assertIn("Horário: 19:30", mensagem)
        self.assertIn("Nome: Ana Silva", mensagem)
        self.assertIn("WhatsApp: (41) 99999-8888", mensagem)

    def test_preserva_codigo_internacional_informado(self):
        link = criar_link_whatsapp_reserva(
            "+1 415 555 2671",
            "Ana",
            "123",
            "Quadra 1",
            self.data,
            self.data
        )

        self.assertEqual(urlparse(link).path, "/14155552671")

    def test_nao_cria_link_sem_destinatario_valido(self):
        for telefone in ("", "123", "abc"):
            with self.subTest(telefone=telefone):
                self.assertIsNone(
                    criar_link_whatsapp_reserva(
                        telefone,
                        "Ana",
                        "123",
                        "Quadra 1",
                        self.data,
                        self.data
                    )
                )


if __name__ == "__main__":
    unittest.main()
