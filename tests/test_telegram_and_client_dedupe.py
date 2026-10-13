import json
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from backend.main import (
    calcular_indice_cancelamento,
    calcular_media_solicitacoes,
    completar_serie_diaria_reservas,
    conectar_banco,
    criar_link_whatsapp_reserva,
    criar_agendamento,
    enviar_extrato_diario_telegram,
    enviar_notificacao_telegram_reserva,
    normalizar_contato_cliente,
    normalizar_nome_cliente,
    normalizar_telefone_whatsapp,
    NovoAgendamento,
    obter_ou_criar_cliente,
)


class TelegramNotificationTests(unittest.TestCase):
    def setUp(self):
        self.data = datetime(2026, 10, 1, 19, 30)

    @patch("backend.main.enviar_notificacao_telegram_reserva")
    @patch("backend.main.criar_link_whatsapp_reserva", return_value="https://wa.me/")
    @patch("backend.main.obter_ou_criar_cliente", return_value=(5, True))
    @patch("backend.main.obter_configuracao")
    @patch("backend.main.conectar_banco")
    def test_solicitacao_e_salva_mesmo_quando_telegram_falha(
        self,
        conectar,
        obter_config,
        obter_cliente,
        criar_link,
        enviar_telegram
    ):
        conexao = MagicMock()
        cursor = conexao.cursor.return_value
        conectar.return_value = conexao
        cursor.fetchone.side_effect = [
            (1, "Quadra", "Sintético", 100, 1, 0, "5511999999999"),
            None,
            None,
            (0,),
            ("Dispensado",)
        ]
        cursor.lastrowid = 123
        obter_config.side_effect = lambda _cursor, chave: {
            "horario_abertura_semana": "00:00",
            "horario_fechamento_semana": "23:59",
            "permitir_fila": "false"
        }[chave]
        enviar_telegram.side_effect = HTTPException(
            status_code=502,
            detail="Telegram indisponível"
        )

        resultado = criar_agendamento(
            NovoAgendamento(
                nome="Ana Silva",
                contato="41999998888",
                quadra_id=1,
                data="2099-10-01",
                horario="10:00"
            )
        )

        conexao.commit.assert_called_once_with()
        conexao.rollback.assert_not_called()
        enviar_telegram.assert_called_once_with(cursor, date(2099, 10, 1))
        self.assertEqual(resultado["id"], 123)
        self.assertFalse(resultado["telegram_notificado"])

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ADMIN_CHAT_ID": "12345"
        },
        clear=True
    )
    @patch("backend.main.urlopen")
    def test_envia_lista_consolidada_somente_para_chat_privado(self, abrir_url):
        resposta = MagicMock()
        resposta.__enter__.return_value.read.return_value = b'{"ok": true}'
        abrir_url.return_value = resposta
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (
                2,
                "Sintético G",
                "19:30:00",
                "Pendente",
                40.0,
                "ana silva",
                "(41) 99999-8888",
                "Obrigatório",
                0
            ),
            (
                2,
                "Sintético G",
                "19:30:00",
                "Confirmado",
                25.0,
                "Bruno Lima",
                "41988887777",
                "Dispensado",
                0
            )
        ]

        enviar_notificacao_telegram_reserva(
            cursor,
            self.data.date()
        )

        requisicao = abrir_url.call_args.args[0]
        self.assertEqual(
            requisicao.full_url,
            "https://api.telegram.org/bottest-token/sendMessage"
        )
        self.assertEqual(abrir_url.call_args.kwargs["timeout"], 10)
        dados = json.loads(requisicao.data)
        self.assertEqual(dados["chat_id"], "12345")
        self.assertIn("📋 <b>Fila de Reservas — 01/10/2026</b>", dados["text"])
        self.assertIn("🏟️ <b>Sintético G</b>", dados["text"])
        self.assertIn("<b>Horário 19:30</b>", dados["text"])
        self.assertNotIn("Horário com solicitações PENDENTES", dados["text"])
        self.assertIn("• <b>1 — ANA SILVA</b>", dados["text"])
        self.assertIn("ANA SILVA", dados["text"])
        self.assertIn(
            "Taxa de Reserva: 💰 <b>R$ 40,00 (pendente)</b> (Obrigatória)",
            dados["text"]
        )
        self.assertIn(
            "Taxa de Reserva: Não (Não obrigatória)",
            dados["text"]
        )
        self.assertIn(
            '<a href="https://wa.me/5541999998888">📱 WhatsApp</a>',
            dados["text"]
        )
        self.assertIn("Status: ⏳ Pendente", dados["text"])
        self.assertIn("Status: ✅ Confirmado", dados["text"])
        self.assertIn("──────────────", dados["text"])
        self.assertEqual(dados["parse_mode"], "HTML")
        consulta = cursor.execute.call_args.args[0]
        self.assertIn("NULLIF(a.taxa_reserva, 0)", consulta)
        self.assertIn("q.taxa_reserva", consulta)

    @patch.dict("os.environ", {}, clear=True)
    def test_nao_aceita_notificacao_sem_configuracao_do_bot(self):
        with self.assertRaises(HTTPException) as erro:
            enviar_notificacao_telegram_reserva(
                MagicMock(),
                self.data.date()
            )
        self.assertEqual(erro.exception.status_code, 503)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ADMIN_CHAT_ID": "12345"
        },
        clear=True
    )
    @patch("backend.main.urlopen")
    def test_falha_do_telegram_impede_confirmar_a_solicitacao(self, abrir_url):
        resposta = MagicMock()
        resposta.__enter__.return_value.read.return_value = b'{"ok": false}'
        abrir_url.return_value = resposta

        with self.assertRaises(HTTPException) as erro:
            enviar_notificacao_telegram_reserva(MagicMock(), self.data.date())
        self.assertEqual(erro.exception.status_code, 502)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_GROUP_CHAT_ID": "-10012345"
        },
        clear=True
    )
    @patch("backend.main.urlopen")
    def test_extrato_do_grupo_usa_apenas_confirmados_de_hoje(
        self,
        abrir_url
    ):
        resposta = MagicMock()
        resposta.__enter__.return_value.read.return_value = b'{"ok": true}'
        abrir_url.return_value = resposta
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("Sintético G", "19:30:00", "Ana Silva", "Confirmado"),
            ("Sintético G", "19:30:00", "Bruno Lima", "Confirmado")
        ]
        enviar_extrato_diario_telegram(
            cursor,
            "https://bosque.example/"
        )

        dados = json.loads(abrir_url.call_args.args[0].data)
        self.assertEqual(dados["chat_id"], "-10012345")
        self.assertEqual(dados["parse_mode"], "HTML")
        self.assertIn(
            f"📋 <b>Extrato do Dia — {date.today().strftime('%d/%m/%Y')}</b>",
            dados["text"]
        )
        self.assertIn("🏟️ <b>Sintético G</b>", dados["text"])
        self.assertIn("🕒 <b>19:30</b>", dados["text"])
        self.assertIn("✅ Confirmado", dados["text"])
        self.assertIn("ANA SILVA", dados["text"])
        self.assertIn("BRUNO LIMA", dados["text"])
        self.assertNotIn("PENDENTE", dados["text"])
        self.assertNotIn("MENSALISTA", dados["text"])
        self.assertEqual(cursor.execute.call_args.args[1], (date.today(),))
        consulta = cursor.execute.call_args.args[0]
        self.assertIn("a.status = 'Confirmado'", consulta)
        self.assertNotIn("UNION", consulta)
        self.assertNotIn("mensalidade", consulta.lower())
        self.assertIn('href="https://bosque.example"', dados["text"])
        self.assertIn("sistema web do Bosque Esportes", dados["text"])


class ClientNormalizationTests(unittest.TestCase):
    def test_normaliza_nome_e_telefone(self):
        self.assertEqual(normalizar_nome_cliente("  Ana   Silva "), "ANA SILVA")
        self.assertEqual(normalizar_contato_cliente("(41) 99999-8888"), "41999998888")
        self.assertEqual(
            normalizar_contato_cliente("+55 41 99999-8888"),
            "41999998888"
        )

    def test_normaliza_telefone_do_link_whatsapp_com_codigo_do_pais(self):
        self.assertEqual(
            normalizar_telefone_whatsapp("(11) 99999-8888"),
            "5511999998888"
        )
        self.assertEqual(
            normalizar_telefone_whatsapp("+1 (415) 555-2671"),
            "14155552671"
        )
        self.assertEqual(
            normalizar_telefone_whatsapp("0044 20 7946 0958"),
            "442079460958"
        )
        self.assertIsNone(normalizar_telefone_whatsapp("contato inválido"))

    def test_reutiliza_cliente_existente_com_nome_e_telefone_equivalentes(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (9, "ana silva", "+55 (41) 99999-8888")
        ]

        cliente_id, novo = obter_ou_criar_cliente(
            cursor,
            " Ana   Silva ",
            "41999998888"
        )

        self.assertEqual(cliente_id, 9)
        self.assertFalse(novo)
        cursor.execute.assert_any_call(
            "UPDATE cliente SET nome = %s WHERE id = %s",
            ("ANA SILVA", 9)
        )
        self.assertFalse(
            any(
                "INSERT INTO cliente" in str(call.args[0])
                for call in cursor.execute.call_args_list
            )
        )

    def test_nao_reutiliza_cliente_quando_o_nome_for_diferente(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            (9, "ANA SILVA", "41999998888")
        ]
        cursor.lastrowid = 15

        cliente_id, novo = obter_ou_criar_cliente(
            cursor,
            "Maria Silva",
            "(41) 99999-8888"
        )

        self.assertEqual(cliente_id, 15)
        self.assertTrue(novo)
        insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO cliente" in str(call.args[0])
        )
        self.assertEqual(insert_call.args[1][0], "MARIA SILVA")

    def test_link_existente_do_whatsapp_continua_com_nome_em_maiusculas(self):
        link = criar_link_whatsapp_reserva(
            "(41) 3333-2222",
            "Ana Silva",
            "(41) 99999-8888",
            "Sintético G",
            datetime(2026, 10, 1, 19, 30),
            datetime(2026, 10, 1, 19, 30)
        )

        self.assertIn("https://wa.me/554133332222?", link)
        self.assertIn("Nome%3A+ANA+SILVA", link)


class ReportMetricTests(unittest.TestCase):
    def test_calcula_media_semanal_por_ocorrencia_no_periodo(self):
        self.assertEqual(calcular_media_solicitacoes(13, 2), 6.5)
        self.assertEqual(calcular_media_solicitacoes(13, 0), 0)

    def test_calcula_indice_de_cancelamento_sobre_solicitacoes(self):
        self.assertEqual(calcular_indice_cancelamento(13, 4), 30.77)
        self.assertEqual(calcular_indice_cancelamento(0, 0), 0)

    def test_serie_diaria_preserva_todos_os_status_e_inclui_dias_sem_reservas(self):
        inicio = date(2026, 10, 12)
        fim = date(2026, 10, 14)
        serie = completar_serie_diaria_reservas(
            inicio,
            fim,
            [
                {
                    "dia": "2026-10-12",
                    "total": 13,
                    "confirmadas": 4,
                    "pendentes": 6,
                    "canceladas": 2,
                    "nao_atendidas": 1
                }
            ]
        )

        self.assertEqual([item["dia"] for item in serie], [
            "2026-10-12", "2026-10-13", "2026-10-14"
        ])
        self.assertEqual(
            sum(item["total"] for item in serie),
            13
        )
        self.assertEqual(
            sum(item["pendentes"] for item in serie),
            6
        )
        self.assertEqual(serie[1]["total"], 0)


class DatabaseConnectionTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "DB_HOST": "mysql.example.net",
            "DB_PORT": "23841",
            "DB_NAME": "bosque",
            "DB_USER": "app",
            "DB_PASSWORD": "test-secret",
            "DB_CONNECT_TIMEOUT": "15",
            "DB_SSL_DISABLED": "false",
            "DB_SSL_VERIFY_CERT": "true",
            "DB_SSL_CA": "C:\\certs\\aiven-ca.pem"
        },
        clear=True
    )
    @patch("backend.main.mysql.connector.connect")
    def test_mysql_usa_env_e_habilita_validacao_tls(self, conectar):
        conectar_banco()

        conectar.assert_called_once_with(
            host="mysql.example.net",
            port=23841,
            user="app",
            password="test-secret",
            database="bosque",
            connection_timeout=15,
            ssl_disabled=False,
            ssl_ca="C:\\certs\\aiven-ca.pem",
            ssl_verify_cert=True,
            ssl_verify_identity=True
        )


if __name__ == "__main__":
    unittest.main()
