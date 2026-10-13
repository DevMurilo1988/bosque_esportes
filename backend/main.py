import calendar
import hashlib
import hmac
import html
import json
import logging
import math
import os
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode
from urllib.request import Request as URLRequest, urlopen

import mysql.connector
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# =========================================================
# APLICAÇÃO
# =========================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
load_dotenv(PROJECT_DIR / ".env")

app = FastAPI(title="Bosque Esportes")
logger = logging.getLogger(__name__)

ADMIN_SESSION_COOKIE = "bosque_admin_session"
ADMIN_SESSION_HOURS = 12
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in {
    "1", "true", "yes", "sim"
}
MODULOS_ADMIN = {
    "agendamentos",
    "mensalistas",
    "pagamentos",
    "relatorios",
    "clientes",
    "quadras",
    "configuracoes"
}


def gerar_hash_senha(senha, salt=None):
    salt = salt or secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        bytes.fromhex(salt),
        310000
    )
    return f"pbkdf2_sha256$310000${salt}${derivada.hex()}"


def verificar_senha(senha, senha_hash):
    try:
        algoritmo, iteracoes, salt, hash_armazenado = senha_hash.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            bytes.fromhex(salt),
            int(iteracoes)
        ).hex()
        return hmac.compare_digest(derivada, hash_armazenado)
    except (ValueError, TypeError):
        return False


def hash_sessao(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def obter_permissoes_admin(cursor, usuario_admin_id, nivel):
    if nivel == "root":
        return {
            modulo: {"visualizar": True, "editar": True}
            for modulo in sorted(MODULOS_ADMIN)
        }

    cursor.execute(
        """
        SELECT modulo, pode_visualizar, pode_editar
        FROM admin_permissao
        WHERE usuario_admin_id = %s
        """,
        (usuario_admin_id,)
    )
    permissoes = {
        modulo: {
            "visualizar": bool(pode_visualizar or pode_editar),
            "editar": bool(pode_editar)
        }
        for modulo, pode_visualizar, pode_editar in cursor.fetchall()
    }
    return {
        modulo: permissoes.get(
            modulo,
            {"visualizar": False, "editar": False}
        )
        for modulo in sorted(MODULOS_ADMIN)
    }


def modulo_da_rota_admin(caminho):
    if caminho.startswith("/admin/quadras"):
        return "quadras"
    if caminho.startswith("/jogos"):
        return "agendamentos"
    if caminho == "/admin/resumo-reservas":
        return "agendamentos"
    if caminho.startswith("/admin/usuarios"):
        return "usuarios"
    if caminho.startswith("/admin/configuracoes") or caminho.startswith("/configuracoes/"):
        return "configuracoes"
    if caminho.startswith("/relatorios"):
        return "relatorios"
    if caminho.startswith("/agendamentos"):
        return "agendamentos"
    if caminho.startswith("/mensalidades/") and "/pagamentos" in caminho:
        return "pagamentos"
    if caminho.startswith("/mensalidades"):
        return "mensalistas"
    if caminho.startswith("/pagamentos"):
        return "pagamentos"
    if caminho.startswith("/clientes"):
        return "clientes"
    if caminho.startswith("/quadras/"):
        return "quadras"
    return None


def buscar_quadras_permitidas(cursor, usuario_admin_id):
    cursor.execute(
        """
        SELECT quadra_id
        FROM admin_quadra_permissao
        WHERE usuario_admin_id = %s
        ORDER BY quadra_id
        """,
        (usuario_admin_id,)
    )
    return [int(row[0]) for row in cursor.fetchall()]


def resolver_quadra_recurso(cursor, caminho, parametros, payload):
    partes = caminho.strip("/").split("/")
    if len(partes) >= 2 and partes[1].isdigit():
        item_id = int(partes[1])
        if partes[0] == "quadras":
            return item_id
        tabela = {
            "agendamentos": "agendamento",
            "mensalidades": "mensalidade"
        }.get(partes[0])
        if tabela:
            cursor.execute(
                f"SELECT quadra_id FROM {tabela} WHERE id = %s",
                (item_id,)
            )
            row = cursor.fetchone()
            return int(row[0]) if row else None
        if partes[0] == "pagamentos":
            cursor.execute(
                """
                SELECT COALESCE(a.quadra_id, m.quadra_id)
                FROM pagamento p
                LEFT JOIN agendamento a ON a.id = p.agendamento_id
                LEFT JOIN mensalidade m ON m.id = p.mensalidade_id
                WHERE p.id = %s
                """,
                (item_id,)
            )
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] else None

    if partes[0] == "agendamentos" or partes[0] == "mensalidades":
        if payload.get("quadra_id") is not None:
            return payload.get("quadra_id")
    if partes[0] == "pagamentos":
        if payload.get("agendamento_id"):
            cursor.execute(
                "SELECT quadra_id FROM agendamento WHERE id = %s",
                (payload["agendamento_id"],)
            )
        elif payload.get("mensalidade_id"):
            cursor.execute(
                "SELECT quadra_id FROM mensalidade WHERE id = %s",
                (payload["mensalidade_id"],)
            )
        else:
            return None
        row = cursor.fetchone()
        return int(row[0]) if row else None

    valor_query = parametros.get("quadra_id", [None])[0]
    if valor_query and str(valor_query).isdigit():
        return int(valor_query)
    return None


@app.middleware("http")
async def proteger_rotas_administrativas(request: Request, call_next):
    metodo = request.method
    caminho = request.url.path
    token = request.cookies.get(ADMIN_SESSION_COOKIE)

    rotas_publicas = {
        ("GET", "/"),
        ("GET", "/index.html"),
        ("GET", "/agendamento.html"),
        ("GET", "/admin.html"),
        ("GET", "/api/status"),
        ("GET", "/api/ready"),
        ("GET", "/quadras"),
        ("GET", "/configuracoes"),
        ("GET", "/disponibilidade"),
        ("POST", "/agendamentos"),
        ("POST", "/solicitacoes-mensais"),
        ("GET", "/admin/sessao"),
        ("POST", "/admin/login"),
        ("POST", "/admin/logout"),
    }

    if (
        caminho.startswith("/frontend/")
        or (
            (metodo, caminho) in rotas_publicas
            and not (caminho == "/agendamentos" and token)
        )
    ):
        return await call_next(request)

    if not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Autenticação administrativa necessária."}
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT s.usuario_admin_id, u.nivel, u.nome
            FROM sessao_admin s
            INNER JOIN usuario_admin u
                ON u.id = s.usuario_admin_id
            WHERE s.token_hash = %s
              AND s.expira_em > NOW()
              AND u.ativo = 1
            LIMIT 1
            """,
            (hash_sessao(token),)
        )
        sessao = cursor.fetchone()
        if not sessao:
            return JSONResponse(
                status_code=401,
                content={"detail": "Sessão administrativa inválida ou expirada."}
            )
        usuario_admin_id, nivel, nome_usuario = sessao
        request.state.usuario_admin_id = usuario_admin_id
        request.state.nivel_admin = nivel
        request.state.nome_usuario_admin = nome_usuario

        modulo = modulo_da_rota_admin(caminho)
        if caminho.startswith("/admin/usuarios") and nivel != "root":
            return JSONResponse(
                status_code=403,
                content={"detail": "Somente o administrador raiz pode gerenciar usuários."}
            )
        if modulo and nivel != "root":
            cursor.execute(
                """
                SELECT pode_visualizar, pode_editar
                FROM admin_permissao
                WHERE usuario_admin_id = %s
                  AND modulo = %s
                LIMIT 1
                """,
                (usuario_admin_id, modulo)
            )
            permissao = cursor.fetchone()
            permitido = (
                bool(permissao and (permissao[1] or permissao[0]))
                if metodo == "GET"
                else bool(permissao and permissao[1])
            )
            if not permitido:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Você não tem permissão para acessar esta área."}
                )

        if nivel == "root":
            cursor.execute("SELECT id FROM quadra ORDER BY id")
            quadras_permitidas = [int(row[0]) for row in cursor.fetchall()]
        else:
            quadras_permitidas = buscar_quadras_permitidas(
                cursor,
                usuario_admin_id
            )
        request.state.quadras_permitidas = quadras_permitidas
        parametros = parse_qs(request.scope.get("query_string", b"").decode())

        rotas_filtradas = {
            "/jogos",
            "/agendamentos",
            "/mensalidades",
            "/mensalidades/clientes",
            "/pagamentos",
            "/pagamentos/referencias",
            "/clientes",
            "/admin/quadras",
            "/relatorios"
        }
        tem_escopo_de_quadra = (
            caminho in rotas_filtradas
            or caminho.startswith((
                "/admin/resumo-reservas/",
                "/agendamentos/",
                "/mensalidades/",
                "/pagamentos/",
                "/clientes/",
                "/quadras/"
            ))
        )

        if nivel != "root" and tem_escopo_de_quadra:
            selecionada = parametros.get("quadra_id", [None])[0]
            if not selecionada and len(quadras_permitidas) == 1:
                selecionada = str(quadras_permitidas[0])
                parametros["quadra_id"] = [selecionada]
                request.scope["query_string"] = urlencode([
                    (chave, valor)
                    for chave, valores in parametros.items()
                    for valor in valores
                ]).encode()

            if selecionada:
                try:
                    quadra_id_selecionada = int(selecionada)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Quadra inválida."}
                    )
                if quadra_id_selecionada not in quadras_permitidas:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Você não tem acesso a esta quadra."}
                    )
                request.state.quadra_id_admin = quadra_id_selecionada
            elif caminho != "/admin/quadras":
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Selecione uma das quadras autorizadas."}
                )

            if metodo == "GET" and caminho.startswith((
                "/agendamentos/",
                "/mensalidades/",
                "/pagamentos/",
                "/quadras/"
            )):
                destino = resolver_quadra_recurso(
                    cursor,
                    caminho,
                    parametros,
                    {}
                )
                if destino is not None and int(destino) not in quadras_permitidas:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Você não tem acesso a esta quadra."}
                    )
            if metodo == "GET" and caminho.startswith("/clientes/"):
                partes_cliente = caminho.strip("/").split("/")
                if len(partes_cliente) > 1 and partes_cliente[1].isdigit():
                    cliente_id = int(partes_cliente[1])
                    cursor.execute(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM agendamento
                            WHERE cliente_id = %s AND quadra_id = %s
                            UNION ALL
                            SELECT 1 FROM mensalidade
                            WHERE cliente_id = %s AND quadra_id = %s
                        )
                        """,
                        (
                            cliente_id,
                            selecionada,
                            cliente_id,
                            selecionada
                        )
                    )
                    if not cursor.fetchone()[0]:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Você não tem acesso aos dados deste cliente."}
                        )

            if metodo in {"POST", "PUT", "PATCH"}:
                body_bytes = await request.body()
                request = Request(
                    request.scope,
                    receive=lambda: {
                        "type": "http.request",
                        "body": body_bytes,
                        "more_body": False
                    }
                )
                try:
                    payload = json.loads(body_bytes or b"{}")
                except (json.JSONDecodeError, TypeError):
                    payload = {}

                destino = resolver_quadra_recurso(
                    cursor,
                    caminho,
                    parametros,
                    payload
                )
                if destino is None and caminho.startswith("/clientes/"):
                    cliente_partes = caminho.strip("/").split("/")
                    if len(cliente_partes) > 1 and cliente_partes[1].isdigit():
                        cliente_id = int(cliente_partes[1])
                        cursor.execute(
                            """
                            SELECT EXISTS(
                                SELECT 1 FROM agendamento
                                WHERE cliente_id = %s AND quadra_id = %s
                                UNION ALL
                                SELECT 1 FROM mensalidade
                                WHERE cliente_id = %s AND quadra_id = %s
                            )
                            """,
                            (
                                cliente_id,
                                selecionada,
                                cliente_id,
                                selecionada
                            )
                        )
                        destino = (
                            int(selecionada)
                            if cursor.fetchone()[0]
                            else None
                        )
                if destino is None or int(destino) not in quadras_permitidas:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Você não pode alterar dados desta quadra."}
                    )
    finally:
        cursor.close()
        conexao.close()

    return await call_next(request)


app.mount(
    "/frontend",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="frontend"
)


# =========================================================
# CONEXÃO COM O BANCO
# =========================================================

def conectar_banco():
    required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Vari?veis obrigat?rias do banco n?o configuradas: "
            + ", ".join(missing)
        )

    options = {
        "host": os.environ["DB_HOST"],
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
        "connection_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        "ssl_disabled": os.getenv("DB_SSL_DISABLED", "false").strip().lower()
        in {"1", "true", "yes", "sim"},
    }
    ssl_ca = os.getenv("DB_SSL_CA")
    verify_ssl = os.getenv("DB_SSL_VERIFY_CERT", "false").strip().lower() in {
        "1", "true", "yes", "sim"
    }
    if ssl_ca:
        options["ssl_ca"] = ssl_ca
    if verify_ssl:
        options["ssl_verify_cert"] = True
        options["ssl_verify_identity"] = True
    return mysql.connector.connect(**options)


def normalizar_telefone_whatsapp(contato):
    contato_original = str(contato or "").strip()
    telefone = re.sub(r"\D", "", contato_original)

    if contato_original.startswith("+"):
        return telefone if 8 <= len(telefone) <= 15 else None
    if contato_original.startswith("00"):
        telefone = telefone[2:]
        return telefone if 8 <= len(telefone) <= 15 else None
    if telefone.startswith("55") and len(telefone) in (12, 13):
        return telefone
    if len(telefone) in (10, 11):
        return f"55{telefone}"
    if 12 <= len(telefone) <= 15:
        return telefone
    return None


def resolver_valor_mensal(valor_configurado, valor_personalizado):
    valor_padrao = float(valor_configurado or 0)
    if valor_personalizado is None and valor_padrao <= 0:
        raise HTTPException(
            status_code=400,
            detail="O valor mensal desta modalidade não está configurado."
        )
    valor = (
        valor_personalizado
        if valor_personalizado is not None
        else valor_padrao
    )
    if not math.isfinite(valor) or valor < 0:
        raise HTTPException(
            status_code=400,
            detail="Informe um valor mensal válido."
        )
    return valor


def enviar_mensagem_telegram(chat_id, mensagem):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("Telegram bot token is not configured.")
        raise HTTPException(
            status_code=503,
            detail="As notificações do Telegram não estão configuradas."
        )

    partes = []
    parte_atual = ""
    for linha in mensagem.splitlines():
        if parte_atual and len(parte_atual) + len(linha) + 1 > 3500:
            partes.append(parte_atual)
            parte_atual = ""
        parte_atual = f"{parte_atual}\n{linha}".strip()
    if parte_atual:
        partes.append(parte_atual)

    for parte in partes:
        requisicao = URLRequest(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({
                "chat_id": chat_id,
                "text": parte,
                "parse_mode": "HTML"
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urlopen(requisicao, timeout=10) as resposta:
                resultado = json.loads(resposta.read().decode("utf-8"))
        except HTTPError as erro:
            try:
                corpo_erro = json.loads(
                    erro.read().decode("utf-8")
                )
                detalhe_erro = (
                    corpo_erro.get("description")
                    if isinstance(corpo_erro, dict)
                    else None
                )
            except (OSError, UnicodeDecodeError, ValueError):
                detalhe_erro = None
            logger.error(
                "Telegram notification failed with HTTP status %s: %s",
                erro.code,
                str(detalhe_erro or "no response details")[:300]
            )
            raise HTTPException(
                status_code=502,
                detail="O Telegram não aceitou a notificação. Tente novamente."
            ) from None
        except (URLError, TimeoutError, OSError, ValueError):
            logger.error("Telegram notification could not be delivered.")
            raise HTTPException(
                status_code=502,
                detail="Não foi possível entregar a notificação pelo Telegram."
            ) from None

        if not isinstance(resultado, dict) or not resultado.get("ok"):
            detalhe_erro = (
                resultado.get("description")
                if isinstance(resultado, dict)
                else None
            )
            logger.error(
                "Telegram rejected a notification: %s",
                str(detalhe_erro or "no response details")[:300]
            )
            raise HTTPException(
                status_code=502,
                detail="O Telegram não aceitou a notificação."
            )


def obter_chat_telegram(variavel):
    chat_id = os.getenv(variavel, "").strip()
    if variavel == "TELEGRAM_ADMIN_CHAT_ID" and not chat_id:
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        logger.error("%s is not configured.", variavel)
        raise HTTPException(
            status_code=503,
            detail="Os chats de notificação do Telegram não estão configurados."
        )
    return chat_id


def enviar_notificacao_telegram_reserva(cursor, data_reserva):
    cursor.execute(
        """
        SELECT q.id, q.nome, a.horario, a.status,
               CASE
                   WHEN c.garantia_reserva = 'Obrigatório'
                   THEN COALESCE(NULLIF(a.taxa_reserva, 0), q.taxa_reserva, 0)
                   ELSE 0
               END AS taxa_reserva,
               c.nome, c.contato, c.garantia_reserva,
               COALESCE(p.valor_pago, 0) AS taxa_paga
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        INNER JOIN cliente c ON c.id = a.cliente_id
        LEFT JOIN (
            SELECT agendamento_id,
                   SUM(CASE WHEN status = 'Recebido'
                            THEN valor_pago ELSE 0 END) AS valor_pago
            FROM pagamento
            WHERE agendamento_id IS NOT NULL
            GROUP BY agendamento_id
        ) p ON p.agendamento_id = a.id
        WHERE a.data = %s
          AND a.status IN ('Pendente', 'Confirmado', 'Não atendido')
        ORDER BY q.nome, a.horario, a.id
        """,
        (data_reserva,)
    )

    linhas = [
        f"📋 <b>Fila de Reservas — "
        f"{data_reserva.strftime('%d/%m/%Y')}</b>",
    ]
    quadra_atual = None
    horario_atual = None
    registros_horario = []

    def adicionar_horario(registros):
        if not registros:
            return
        linhas.extend([
            "",
            f"<b>Horário {registros[0][2]}</b>",
            "",
        ])
        posicao = 0
        for indice, registro in enumerate(registros):
            (
                _quadra_id,
                _nome_quadra,
                _horario,
                status,
                taxa_reserva,
                nome_cliente,
                contato_cliente,
                garantia_reserva,
                taxa_paga,
            ) = registro
            if status == "Pendente":
                posicao += 1
                posicao_texto = f"{posicao} — "
            else:
                posicao_texto = ""

            obrigatoria = garantia_reserva == "Obrigatório"
            taxa_valor = float(taxa_reserva or 0)
            if not obrigatoria:
                taxa_texto = "Não"
            elif taxa_valor <= 0:
                taxa_texto = "⚠️ <b>valor não configurado</b>"
            elif float(taxa_paga or 0) >= taxa_valor:
                taxa_texto = f"💰 <b>R$ {taxa_valor:.2f}</b>".replace(".", ",")
            else:
                taxa_texto = (
                    f"💰 <b>R$ {taxa_valor:.2f} (pendente)</b>"
                    .replace(".", ",")
                )

            status_individual = {
                "Pendente": "⏳ Pendente",
                "Confirmado": "✅ Confirmado",
                "Não atendido": "❌ Não Atendido",
            }.get(status, html.escape(str(status)))
            garantia_texto = "Obrigatória" if obrigatoria else "Não obrigatória"
            telefone = normalizar_telefone_whatsapp(contato_cliente)
            link_whatsapp = (
                f'<a href="https://wa.me/{telefone}">📱 WhatsApp</a>'
                if telefone
                else "📱 WhatsApp indisponível"
            )
            linhas.extend([
                f"• <b>{posicao_texto}"
                f"{html.escape(normalizar_nome_cliente(nome_cliente))}</b>",
                f"  Taxa de Reserva: {taxa_texto} "
                f"({garantia_texto})",
                f"  Status: {status_individual}",
                f"  {link_whatsapp}",
            ])
            if indice < len(registros) - 1:
                linhas.extend(["", "──────────────", ""])

    reservas = cursor.fetchall()
    for (
        quadra_id,
        nome_quadra,
        horario,
        status,
        taxa_reserva,
        nome_cliente,
        contato_cliente,
        garantia_reserva,
        taxa_paga
    ) in reservas:
        horario_texto = str(horario)[:5]
        chave = (quadra_id, horario_texto)
        registro = (
            quadra_id,
            nome_quadra,
            horario_texto,
            status,
            taxa_reserva,
            nome_cliente,
            contato_cliente,
            garantia_reserva,
            taxa_paga,
        )
        if chave != (quadra_atual, horario_atual):
            adicionar_horario(registros_horario)
            registros_horario = []
            if quadra_id != quadra_atual:
                linhas.extend([
                    "",
                    f"🏟️ <b>{html.escape(str(nome_quadra))}</b>",
                ])
            quadra_atual, horario_atual = chave
        registros_horario.append(registro)
    adicionar_horario(registros_horario)
    if not reservas:
        linhas.extend(["", "Nenhuma solicitação ou reserva nesta data."])

    enviar_mensagem_telegram(
        obter_chat_telegram("TELEGRAM_ADMIN_CHAT_ID"),
        "\n".join(linhas)
    )


def enviar_extrato_diario_telegram(cursor, base_url):
    hoje = date.today()
    cursor.execute(
        """
        SELECT q.nome, a.horario, c.nome, 'Confirmado' AS status
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        INNER JOIN cliente c ON c.id = a.cliente_id
        WHERE a.data = %s
          AND a.status = 'Confirmado'
        ORDER BY q.nome, a.horario, a.id
        """,
        (hoje,)
    )
    jogos = cursor.fetchall()
    linhas = [
        f"📋 <b>Extrato do Dia — {hoje.strftime('%d/%m/%Y')}</b>"
    ]
    if jogos:
        quadra_atual = None
        horario_atual = None
        for nome_quadra, horario, nome_cliente, status in jogos:
            horario_texto = str(horario)[:5]
            if nome_quadra != quadra_atual:
                linhas.extend([
                    "",
                    f"🏟️ <b>{html.escape(str(nome_quadra))}</b>",
                ])
                quadra_atual = nome_quadra
                horario_atual = None
            if horario_texto != horario_atual:
                linhas.extend([
                    "",
                    f"🕒 <b>{horario_texto}</b>",
                    "",
                ])
                horario_atual = horario_texto
            linhas.extend([
                f"• {html.escape(normalizar_nome_cliente(nome_cliente))}",
                f"  ✅ {html.escape(str(status))}",
                "",
            ])
    else:
        linhas.extend(["", "Nenhum jogo confirmado para hoje."])

    url_sistema = html.escape(base_url.rstrip("/"), quote=True)
    linhas.extend([
        "",
        f'🔎 <i>Para consultar outros dias, acesse o '
        f'<a href="{url_sistema}">sistema web do Bosque Esportes</a>.</i>',
    ])

    enviar_mensagem_telegram(
        obter_chat_telegram("TELEGRAM_GROUP_CHAT_ID"),
        "\n".join(linhas)
    )


def criar_link_whatsapp_reserva(
    whatsapp_responsavel,
    nome_cliente,
    contato_cliente,
    nome_quadra,
    data_reserva,
    horario_reserva
):
    telefone_original = str(whatsapp_responsavel or "").strip()
    telefone = re.sub(r"\D", "", telefone_original)
    codigo_internacional = (
        telefone_original.startswith("+")
        or telefone_original.startswith("00")
    )
    if telefone.startswith("00"):
        telefone = telefone[2:]
        codigo_internacional = True
    if not codigo_internacional and len(telefone) in (10, 11):
        telefone = f"55{telefone}"
    if not 10 <= len(telefone) <= 15:
        return None

    mensagem = (
        "Olá! Gostaria de solicitar uma reserva no Bosque Esportes.\n"
        f"Quadra: {nome_quadra}\n"
        f"Data: {data_reserva.strftime('%d/%m/%Y')}\n"
        f"Horário: {horario_reserva.strftime('%H:%M')}\n"
        f"Nome: {normalizar_nome_cliente(nome_cliente)}\n"
        f"WhatsApp: {contato_cliente}"
    )
    return f"https://wa.me/{telefone}?{urlencode({'text': mensagem})}"


def normalizar_nome_cliente(nome):
    return " ".join(str(nome or "").split()).upper()


def normalizar_contato_cliente(contato):
    digitos = re.sub(r"\D", "", str(contato or ""))
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return digitos[2:]
    return digitos


# =========================================================
# MODELOS
# =========================================================

class NovoAgendamento(BaseModel):
    nome: str
    contato: str
    quadra_id: int
    data: str
    horario: str


class AtualizarStatus(BaseModel):
    status: str


class NovaMensalidade(BaseModel):
    nome: str
    contato: str
    quadra_id: int
    dia_semana: int
    horario: str
    data_inicio: str
    valor_mensal: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False
    )
    observacao: Optional[str] = None
    data_encerramento: Optional[str] = None


class AtualizarMensalidade(BaseModel):
    status: str
    valor_mensal: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False
    )
    observacao: Optional[str] = None
    data_encerramento: Optional[str] = None


class SolicitacaoMensalidade(BaseModel):
    nome: str
    contato: str
    quadra_id: int
    dia_semana: int
    horario: str
    data_inicio: str


class NovoPagamentoMensalidade(BaseModel):
    competencia: str
    valor: float
    data_pagamento: Optional[str] = None
    status: str = "Pago"
    forma_pagamento: Optional[str] = None
    observacao: Optional[str] = None


class NovoRecebimento(BaseModel):
    valor_recebido: float
    data_pagamento: Optional[str] = None
    metodo_pagamento: str
    observacoes: Optional[str] = None


class LoginAdmin(BaseModel):
    usuario: str
    senha: str


class NovoUsuarioAdmin(BaseModel):
    nome: str
    usuario: str
    senha: str
    permissoes: Dict[str, Dict[str, bool]]
    quadra_ids: List[int] = Field(default_factory=list)


class AtualizarUsuarioAdmin(BaseModel):
    ativo: bool
    permissoes: Dict[str, Dict[str, bool]]
    quadra_ids: List[int] = Field(default_factory=list)


class NovoPagamento(BaseModel):
    agendamento_id: Optional[int] = None
    mensalidade_id: Optional[int] = None
    competencia: Optional[str] = None
    valor_pago: float = 0
    data_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    status: str = "Pendente"
    observacao: Optional[str] = None


class AtualizarPagamento(BaseModel):
    status: str
    valor_pago: Optional[float] = None
    data_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    observacao: Optional[str] = None


class NovoCliente(BaseModel):
    nome: str
    contato: str


class AtualizarCliente(BaseModel):
    nome: Optional[str] = None
    contato: Optional[str] = None
    garantia_reserva: Optional[str] = None
    motivo_garantia: Optional[str] = None


class AtualizarQuadra(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    valor: Optional[float] = Field(default=None, ge=0)
    valor_mensal: Optional[float] = Field(default=None, ge=0)
    taxa_reserva: Optional[float] = Field(default=None, ge=0)
    medidas: Optional[str] = None
    capacidade: Optional[int] = Field(default=None, ge=0)
    descricao: Optional[str] = None
    imagem: Optional[str] = None
    ativo: Optional[int] = None
    responsavel_whatsapp: Optional[str] = None


class AtualizarConfiguracao(BaseModel):
    valor: str


CONFIGURACOES_PUBLICAS = {
    "horario_abertura_semana",
    "horario_fechamento_semana",
    "horario_abertura_domingo",
    "horario_fechamento_domingo",
    "permitir_fila",
    "limite_fila",
    "site_titulo",
    "site_subtitulo",
    "site_sobre",
    "site_sobre_titulo",
    "site_estrutura_titulo",
    "site_estrutura_subtitulo",
    "site_contato_titulo",
    "site_contato_label",
    "site_rodape",
    "site_cta",
    "mensagem_reserva"
}

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def converter_valor_mysql(valor):
    """
    Converte tipos do MySQL para tipos que o JSON entende.
    """

    if isinstance(valor, timedelta):

        total_segundos = int(
            valor.total_seconds()
        )

        horas = total_segundos // 3600

        minutos = (
            total_segundos % 3600
        ) // 60

        return f"{horas:02d}:{minutos:02d}"

    if isinstance(valor, datetime):

        return valor.isoformat()

    if isinstance(valor, date):

        return valor.isoformat()

    return valor


def linha_para_dict(cursor, linha):
    """
    Converte uma linha do banco em dicionário.
    """

    colunas = [
        descricao[0]
        for descricao in cursor.description
    ]

    resultado = {}

    for coluna, valor in zip(
        colunas,
        linha
    ):

        resultado[coluna] = (
            converter_valor_mysql(valor)
        )

    return resultado


def obter_ou_criar_cliente(
    cursor,
    nome,
    contato
):
    """
    Reutiliza o cliente existente pelo contato
    ou cria um novo.
    """

    nome = normalizar_nome_cliente(nome)
    contato = str(contato or "").strip()
    contato_normalizado = normalizar_contato_cliente(contato)

    if contato_normalizado:
        padroes_contato = [contato_normalizado]
        if len(contato_normalizado) in (10, 11):
            padroes_contato.append(f"55{contato_normalizado}")

        padroes_sql = [
            "^[^0-9]*" + "[^0-9]*".join(padrao) + "[^0-9]*$"
            for padrao in padroes_contato
        ]
        condicoes = " OR ".join(
            "contato REGEXP %s" for _ in padroes_sql
        )
        cursor.execute(
            f"""
            SELECT id, nome, contato
            FROM cliente
            WHERE {condicoes}
            ORDER BY id
            """,
            tuple(padroes_sql)
        )
        for cliente_id, nome_existente, contato_existente in cursor.fetchall():
            if (
                normalizar_contato_cliente(contato_existente)
                == contato_normalizado
                and normalizar_nome_cliente(nome_existente) == nome
            ):
                if nome_existente != nome:
                    cursor.execute(
                        "UPDATE cliente SET nome = %s WHERE id = %s",
                        (nome, cliente_id)
                    )
                return cliente_id, False

    cursor.execute(
        """
        INSERT INTO cliente
            (
                nome,
                contato,
                garantia_reserva,
                motivo_garantia
            )
        VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
        """,
        (
            nome,
            contato,
            "Dispensado",
            None
        )
    )

    return cursor.lastrowid, True


def obter_configuracao(
    cursor,
    chave
):
    """
    Busca uma configuração pelo nome.
    """

    cursor.execute(
        """
        SELECT valor
        FROM configuracao
        WHERE chave = %s
        LIMIT 1
        """,
        (chave,)
    )

    resultado = cursor.fetchone()

    if not resultado:
        return None

    return resultado[0]


# =========================================================
# PÁGINAS
# =========================================================

@app.get("/")
@app.get("/index.html", include_in_schema=False)
def pagina_inicial():

    return FileResponse(
        str(FRONTEND_DIR / "index.html")
    )


@app.get("/agendamento.html")
def pagina_agendamento():

    return FileResponse(
        str(FRONTEND_DIR / "agendamento.html")
    )


@app.get("/admin.html")
def pagina_admin():

    return FileResponse(
        str(FRONTEND_DIR / "admin.html")
    )


@app.post("/admin/login")
def login_admin(dados: LoginAdmin, request: Request):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        cursor.execute(
            """
            SELECT id, nome, usuario, senha_hash, nivel
            FROM usuario_admin
            WHERE usuario = %s
              AND ativo = 1
            LIMIT 1
            """,
            (dados.usuario.strip(),)
        )
        admin = cursor.fetchone()

        if not admin or not verificar_senha(dados.senha, admin[3]):
            raise HTTPException(
                status_code=401,
                detail="Usuário ou senha inválidos."
            )

        token = secrets.token_urlsafe(48)
        cursor.execute(
            """
            INSERT INTO sessao_admin
                (usuario_admin_id, token_hash, expira_em)
            VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
            """,
            (admin[0], hash_sessao(token), ADMIN_SESSION_HOURS)
        )
        conexao.commit()

        resposta = JSONResponse(
            content={
                "autenticado": True,
                "usuario": {
                    "nome": admin[1],
                    "usuario": admin[2],
                    "nivel": admin[4]
                },
                "permissoes": obter_permissoes_admin(
                    cursor,
                    admin[0],
                    admin[4]
                ),
                "quadra_ids": (
                    []
                    if admin[4] == "root"
                    else buscar_quadras_permitidas(cursor, admin[0])
                )
            }
        )
        resposta.set_cookie(
            ADMIN_SESSION_COOKIE,
            token,
            max_age=ADMIN_SESSION_HOURS * 60 * 60,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path="/"
        )
        return resposta
    except HTTPException:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.get("/admin/sessao")
def consultar_sessao_admin(request: Request):

    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM usuario_admin WHERE ativo = 1)"
        )
        configurado = bool(cursor.fetchone()[0])
        if not token:
            return {"autenticado": False, "configurado": configurado}

        cursor.execute(
            """
            SELECT u.id, u.nome, u.usuario, u.nivel
            FROM sessao_admin s
            INNER JOIN usuario_admin u
                ON u.id = s.usuario_admin_id
            WHERE s.token_hash = %s
              AND s.expira_em > NOW()
              AND u.ativo = 1
            LIMIT 1
            """,
            (hash_sessao(token),)
        )
        usuario = cursor.fetchone()
        if not usuario:
            return {"autenticado": False, "configurado": configurado}
        return {
            "autenticado": True,
            "configurado": configurado,
            "usuario": {
                "nome": usuario[1],
                "usuario": usuario[2],
                "nivel": usuario[3]
            },
            "permissoes": obter_permissoes_admin(
                cursor,
                usuario[0],
                usuario[3]
            ),
            "quadra_ids": (
                []
                if usuario[3] == "root"
                else buscar_quadras_permitidas(cursor, usuario[0])
            )
        }
    finally:
        cursor.close()
        conexao.close()


@app.post("/admin/logout")
def logout_admin(request: Request):

    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if token:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        try:
            cursor.execute(
                "DELETE FROM sessao_admin WHERE token_hash = %s",
                (hash_sessao(token),)
            )
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

    resposta = JSONResponse(content={"autenticado": False})
    resposta.delete_cookie(
        ADMIN_SESSION_COOKIE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/"
    )
    return resposta


@app.get("/disponibilidade")
def obter_disponibilidade(
    quadra_id: int,
    data: str
):

    try:
        data_selecionada = datetime.strptime(data, "%Y-%m-%d").date()
        if data_selecionada.isoformat() != data:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Data inválida."
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "SELECT id FROM quadra WHERE id = %s AND ativo = 1",
            (quadra_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail="Quadra não encontrada ou inativa."
            )

        cursor.execute(
            """
            SELECT data, horario, status
            FROM agendamento
            WHERE quadra_id = %s
              AND data = %s
              AND status IN ('Pendente', 'Confirmado')
            ORDER BY id
            """,
            (quadra_id, data_selecionada)
        )
        agendamentos = [
            {
                "quadra_id": quadra_id,
                "data": linha[0].isoformat(),
                "horario": converter_valor_mysql(linha[1]),
                "status": linha[2]
            }
            for linha in cursor.fetchall()
        ]

        dia_semana = (data_selecionada.weekday() + 1) % 7
        cursor.execute(
            """
            SELECT dia_semana, horario, status, data_inicio, data_encerramento
            FROM mensalidade
            WHERE quadra_id = %s
              AND dia_semana = %s
              AND status = 'Ativa'
              AND data_inicio <= %s
              AND (
                  data_encerramento IS NULL
                  OR data_encerramento >= %s
              )
            """,
            (
                quadra_id,
                dia_semana,
                data_selecionada,
                data_selecionada
            )
        )
        mensalidades = [
            {
                "quadra_id": quadra_id,
                "dia_semana": linha[0],
                "horario": converter_valor_mysql(linha[1]),
                "status": linha[2],
                "data_inicio": linha[3].isoformat(),
                "data_encerramento":
                    linha[4].isoformat() if linha[4] else None
            }
            for linha in cursor.fetchall()
        ]

        return {
            "agendamentos": agendamentos,
            "mensalidades": mensalidades
        }
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# QUADRAS
# =========================================================

@app.get("/quadras")
def listar_quadras():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                nome,
                tipo,
                valor,
                valor_mensal,
                medidas,
                capacidade,
                descricao,
                imagem,
                ativo
            FROM quadra
            WHERE ativo = 1
            ORDER BY id
            """
        )

        linhas = cursor.fetchall()

        return [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in linhas
        ]

    finally:

        cursor.close()
        conexao.close()


@app.get("/admin/quadras")
def listar_quadras_admin(
    request: Request,
    quadra_id: Optional[int] = None
):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        permitidas = getattr(
            request.state,
            "quadras_permitidas",
            []
        )
        if request.state.nivel_admin != "root" and not permitidas:
            return []
        where = ["(%s IS NULL OR id = %s)"]
        parametros = [quadra_id, quadra_id]
        if request.state.nivel_admin != "root" and quadra_id is None:
            placeholders = ", ".join(["%s"] * len(permitidas))
            where.append(f"id IN ({placeholders})")
            parametros.extend(permitidas)
        cursor.execute(
            f"""
            SELECT id, nome, tipo, valor, valor_mensal, medidas,
                   capacidade, descricao, imagem, ativo, taxa_reserva,
                   responsavel_whatsapp
            FROM quadra
            WHERE {" AND ".join(where)}
            ORDER BY id
            """,
            parametros
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


@app.get("/quadras/{quadra_id}")
def obter_quadra(
    quadra_id: int
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                nome,
                tipo,
                valor,
                valor_mensal,
                medidas,
                capacidade,
                descricao,
                imagem,
                ativo
            FROM quadra
            WHERE id = %s
            """,
            (quadra_id,)
        )

        linha = cursor.fetchone()

        if not linha:

            raise HTTPException(
                status_code=404,
                detail="Quadra não encontrada."
            )

        return linha_para_dict(
            cursor,
            linha
        )

    finally:

        cursor.close()
        conexao.close()


@app.put("/quadras/{quadra_id}")
def atualizar_quadra(
    quadra_id: int,
    dados: AtualizarQuadra
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT id
            FROM quadra
            WHERE id = %s
            """,
            (quadra_id,)
        )

        if not cursor.fetchone():

            raise HTTPException(
                status_code=404,
                detail="Quadra não encontrada."
            )

        campos = []
        valores = []

        dados_dict = dados.model_dump(
            exclude_unset=True
        )

        for campo, valor in dados_dict.items():

            campos.append(
                f"{campo} = %s"
            )

            valores.append(valor)

        if not campos:

            return {
                "mensagem":
                    "Nenhuma alteração enviada."
            }

        valores.append(
            quadra_id
        )

        sql = f"""
            UPDATE quadra
            SET {", ".join(campos)}
            WHERE id = %s
        """

        cursor.execute(
            sql,
            valores
        )

        conexao.commit()

        return {
            "mensagem":
                "Quadra atualizada com sucesso."
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# AGENDAMENTOS
# =========================================================

@app.get("/agendamentos")
def listar_agendamentos(quadra_id: Optional[int] = None):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                a.id,
                a.quadra_id,
                c.nome AS cliente,
                c.contato,
                c.garantia_reserva,
                q.nome AS quadra,
                q.tipo AS tipo_quad,
                a.data,
                a.horario,
                a.valor_hora,
                CASE
                    WHEN c.garantia_reserva = 'Obrigatório'
                    THEN COALESCE(NULLIF(a.taxa_reserva, 0), q.taxa_reserva, 0)
                    ELSE 0
                END AS taxa_reserva,
                a.valor_restante,
                a.status,
                COALESCE(p.valor_pago, 0) AS valor_pago,
                GREATEST(a.valor_hora - COALESCE(p.valor_pago, 0), 0)
                    AS saldo_pendente,
                p.pagamento_id,
                (SELECT COUNT(*) FROM agendamento ac
                 WHERE ac.cliente_id = a.cliente_id) AS total_jogos_cliente
            FROM agendamento a

            INNER JOIN cliente c
                ON c.id = a.cliente_id

            INNER JOIN quadra q
                ON q.id = a.quadra_id
            LEFT JOIN (
                SELECT agendamento_id,
                       SUM(CASE WHEN status <> 'Cancelado'
                                THEN valor_pago ELSE 0 END) AS valor_pago,
                       MAX(CASE WHEN status <> 'Cancelado' THEN id END)
                           AS pagamento_id
                FROM pagamento
                WHERE agendamento_id IS NOT NULL
                GROUP BY agendamento_id
            ) p ON p.agendamento_id = a.id

            WHERE (%s IS NULL OR a.quadra_id = %s)
            ORDER BY
                a.data,
                a.horario,
                a.id
            """,
            (quadra_id, quadra_id)
        )

        linhas = cursor.fetchall()

        agora = datetime.now()
        hoje = agora.date()
        resultado = []

        for linha in linhas:

            item = linha_para_dict(
                cursor,
                linha
            )

            data_reserva = linha[7]
            horario_reserva = linha[8]
            status = linha[12]

            horario_texto = str(horario_reserva)

            if len(horario_texto) >= 5:
                horario_texto = horario_texto[:5]

            try:
                hora, minuto = map(
                    int,
                    horario_texto.split(":")[:2]
                )

                data_hora_reserva = datetime.combine(
                    data_reserva,
                    datetime.min.time()
                ).replace(
                    hour=hora,
                    minute=minuto
                )

            except (ValueError, TypeError):

                data_hora_reserva = datetime.combine(
                    data_reserva,
                    datetime.min.time()
                )

            passou = data_hora_reserva < agora

            if passou:

                if status == "Confirmado":
                    situacao = "Concluído"
                else:
                    situacao = "Histórico"

                editavel = False

            else:

                if data_reserva == hoje:
                    situacao = "Hoje"
                else:
                    situacao = "Próximo"

                editavel = status not in [
                    "Cancelado",
                    "Não atendido"
                ]

            item["situacao"] = situacao
            item["editavel"] = editavel

            resultado.append(item)

        return resultado

    finally:

        cursor.close()
        conexao.close()


@app.get("/jogos")
def listar_jogos_do_dia(data: str, quadra_id: Optional[int] = None):
    try:
        dia = datetime.strptime(data, "%Y-%m-%d").date()
        if dia.isoformat() != data:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida.")

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT a.id AS agendamento_id, NULL AS mensalidade_id,
                   a.cliente_id, c.nome AS cliente,
                   c.contato, q.id AS quadra_id, q.nome AS quadra,
                   q.tipo AS tipo_quad, a.data, a.horario, a.status,
                   a.valor_hora AS valor,
                   CASE
                       WHEN c.garantia_reserva = 'Obrigatório'
                       THEN COALESCE(NULLIF(a.taxa_reserva, 0), q.taxa_reserva, 0)
                       ELSE 0
                   END AS taxa_reserva,
                   a.valor_restante,
                   COALESCE(p.valor_pago, 0) AS valor_pago,
                   GREATEST(a.valor_hora - COALESCE(p.valor_pago, 0), 0)
                       AS saldo_pendente,
                   p.pagamento_id,
                   (SELECT COUNT(*) FROM agendamento ac
                    WHERE ac.cliente_id = a.cliente_id
                      AND ac.status NOT IN ('Cancelado', 'Não atendido'))
                       AS total_jogos_cliente,
                   'Avulso' AS tipo_jogo,
                   q.responsavel_whatsapp
            FROM agendamento a
            INNER JOIN cliente c ON c.id = a.cliente_id
            INNER JOIN quadra q ON q.id = a.quadra_id
            LEFT JOIN (
                SELECT agendamento_id,
                       SUM(CASE WHEN status <> 'Cancelado'
                                THEN valor_pago ELSE 0 END) AS valor_pago,
                       MAX(CASE WHEN status <> 'Cancelado' THEN id END)
                           AS pagamento_id
                FROM pagamento
                WHERE agendamento_id IS NOT NULL
                GROUP BY agendamento_id
            ) p ON p.agendamento_id = a.id
            WHERE a.data = %s
              AND a.status IN ('Pendente', 'Confirmado')
              AND (%s IS NULL OR a.quadra_id = %s)

            UNION ALL

            SELECT NULL AS agendamento_id, m.id AS mensalidade_id,
                   m.cliente_id, c.nome AS cliente,
                   c.contato, q.id AS quadra_id, q.nome AS quadra,
                   q.tipo AS tipo_quad, %s AS data, m.horario,
                   'Mensalista' AS status, m.valor_mensal AS valor,
                   0 AS taxa_reserva, m.valor_mensal AS valor_restante,
                   LEAST(m.valor_mensal, COALESCE(
                       p.valor_pago, legacy.valor_pago, 0
                   )) AS valor_pago,
                   GREATEST(m.valor_mensal - COALESCE(
                       p.valor_pago, legacy.valor_pago, 0
                   ), 0) AS saldo_pendente,
                   p.pagamento_id,
                   (SELECT COUNT(*) FROM agendamento ac
                    WHERE ac.cliente_id = m.cliente_id
                      AND ac.status NOT IN ('Cancelado', 'Não atendido'))
                       AS total_jogos_cliente,
                   'Mensalista' AS tipo_jogo,
                   q.responsavel_whatsapp
            FROM mensalidade m
            INNER JOIN cliente c ON c.id = m.cliente_id
            INNER JOIN quadra q ON q.id = m.quadra_id
            LEFT JOIN (
                SELECT mensalidade_id, competencia,
                       SUM(CASE WHEN status <> 'Cancelado'
                                THEN valor_pago ELSE 0 END) AS valor_pago,
                       MAX(CASE WHEN status <> 'Cancelado' THEN id END)
                           AS pagamento_id
                FROM pagamento
                WHERE mensalidade_id IS NOT NULL
                GROUP BY mensalidade_id, competencia
            ) p ON p.mensalidade_id = m.id
               AND p.competencia = DATE_FORMAT(%s, '%Y-%m')
            LEFT JOIN (
                SELECT mensalidade_id,
                       DATE_FORMAT(competencia, '%Y-%m') AS competencia,
                       SUM(CASE WHEN status = 'Pago' THEN valor ELSE 0 END)
                           AS valor_pago
                FROM pagamento_mensalidade
                GROUP BY mensalidade_id, DATE_FORMAT(competencia, '%Y-%m')
            ) legacy ON legacy.mensalidade_id = m.id
                    AND legacy.competencia = DATE_FORMAT(%s, '%Y-%m')
            WHERE m.status = 'Ativa'
              AND m.data_inicio <= %s
              AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
              AND DAYOFWEEK(%s) - 1 = m.dia_semana
              AND (%s IS NULL OR m.quadra_id = %s)
            ORDER BY horario, quadra
            """,
            (
                dia, quadra_id, quadra_id,
                dia, dia, dia, dia, dia, dia,
                quadra_id, quadra_id
            )
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


@app.post("/agendamentos")
def criar_agendamento(
    dados: NovoAgendamento
):

    try:
        data_reserva = datetime.strptime(
            dados.data,
            "%Y-%m-%d"
        )
        horario_reserva = datetime.strptime(
            dados.horario,
            "%H:%M"
        )

        if (
            data_reserva.strftime("%Y-%m-%d") != dados.data
            or horario_reserva.strftime("%H:%M") != dados.horario
        ):
            raise ValueError

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Data ou horário inválido."
        )

    data_reserva = data_reserva.date()

    agora = datetime.now()
    hora_reserva = horario_reserva.time()
    if data_reserva < agora.date() or (
        data_reserva == agora.date()
        and hora_reserva <= agora.time()
    ):
        raise HTTPException(
            status_code=400,
            detail="Não é possível solicitar um horário que já passou."
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        # -------------------------------------------------
        # VERIFICA QUADRA
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                nome,
                tipo,
                valor,
                ativo,
                taxa_reserva,
                responsavel_whatsapp
            FROM quadra
            WHERE id = %s
            FOR UPDATE
            """,
            (dados.quadra_id,)
        )

        quadra = cursor.fetchone()

        if not quadra:

            raise HTTPException(
                status_code=404,
                detail="Quadra não encontrada."
            )

        if not quadra[4]:

            raise HTTPException(
                status_code=400,
                detail="Esta quadra está inativa."
            )

        tipo_quad = quadra[2]

        dia_config = (
            "domingo"
            if data_reserva.weekday() == 6
            else "semana"
        )
        abertura_config = obter_configuracao(
            cursor,
            f"horario_abertura_{dia_config}"
        )
        fechamento_config = obter_configuracao(
            cursor,
            f"horario_fechamento_{dia_config}"
        )

        try:
            abertura_partes = str(abertura_config).split(":")
            fechamento_partes = str(fechamento_config).split(":")
            minutos_abertura = (
                int(abertura_partes[0]) * 60 +
                int(abertura_partes[1])
            )
            minutos_fechamento = (
                int(fechamento_partes[0]) * 60 +
                int(fechamento_partes[1])
            )
            if minutos_fechamento == 0:
                minutos_fechamento = 24 * 60
        except (TypeError, ValueError, IndexError):
            minutos_abertura = 0
            minutos_fechamento = 24 * 60

        minutos_reserva = (
            hora_reserva.hour * 60 + hora_reserva.minute
        )
        if (
            minutos_reserva < minutos_abertura
            or minutos_reserva + 60 > minutos_fechamento
        ):
            raise HTTPException(
                status_code=400,
                detail="Este horário está fora do funcionamento da quadra."
            )

        valor_hora = float(
            quadra[3] or 0
        )

        # -------------------------------------------------
        # VERIFICA LOCAÇÃO MENSAL
        # -------------------------------------------------

        dia_semana = (
            data_reserva.weekday() + 1
        ) % 7

        cursor.execute(
            """
            SELECT id
            FROM mensalidade
            WHERE quadra_id = %s
              AND dia_semana = %s
              AND horario = %s
              AND status = 'Ativa'
              AND data_inicio <= %s
              AND (
                  data_encerramento IS NULL
                  OR data_encerramento >= %s
              )
            LIMIT 1
            """,
            (
                dados.quadra_id,
                dia_semana,
                dados.horario,
                dados.data,
                dados.data
            )
        )

        mensalidade = cursor.fetchone()

        if mensalidade:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Este horário possui "
                    "uma locação mensal ativa."
                )
            )

        # -------------------------------------------------
        # BLOQUEIA HORÁRIO JÁ CONFIRMADO
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM agendamento
            WHERE quadra_id = %s
              AND data = %s
              AND horario = %s
              AND status = 'Confirmado'
            LIMIT 1
            """,
            (
                dados.quadra_id,
                dados.data,
                dados.horario
            )
        )

        confirmado = cursor.fetchone()

        if confirmado:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Este horário já está confirmado "
                    "e não está disponível."
                )
            )

        # -------------------------------------------------
        # LIMITE DA FILA
        # -------------------------------------------------

        permitir_fila = obter_configuracao(
            cursor,
            "permitir_fila"
        )

        fila_ativa = str(permitir_fila).lower() in (
            "1",
            "true",
            "sim"
        )

        if fila_ativa:

            limite_fila = obter_configuracao(
                cursor,
                "limite_fila"
            )

            try:
                limite_fila = int(float(limite_fila))
            except (TypeError, ValueError):
                limite_fila = 0

        else:
            limite_fila = 1

        if limite_fila > 0:

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM agendamento
                WHERE quadra_id = %s
                  AND data = %s
                  AND horario = %s
                  AND status = 'Pendente'
                """,
                (
                    dados.quadra_id,
                    dados.data,
                    dados.horario
                )
            )

            quantidade_pendentes = cursor.fetchone()[0]

            if quantidade_pendentes >= limite_fila:

                if fila_ativa:
                    detalhe = (
                        "O limite de solicitações pendentes "
                        "para este horário foi atingido."
                    )
                else:
                    detalhe = (
                        "Este horário já possui uma solicitação pendente "
                        "e a fila está desativada."
                    )

                raise HTTPException(
                    status_code=409,
                    detail=detalhe
                )

        # -------------------------------------------------
        # CRIA / LOCALIZA CLIENTE
        # -------------------------------------------------

        nome_cliente = normalizar_nome_cliente(dados.nome)
        cliente_id, _ = obter_ou_criar_cliente(
            cursor,
            nome_cliente,
            dados.contato.strip()
        )

        # -------------------------------------------------
        # VERIFICA REGRA DE GARANTIA
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                garantia_reserva
            FROM cliente
            WHERE id = %s
            """,
            (cliente_id,)
        )

        cliente = cursor.fetchone()

        garantia_reserva = (
            cliente[0]
            if cliente
            else "Dispensado"
        )

        # -------------------------------------------------
        # CALCULA TAXA
        # -------------------------------------------------

        taxa_reserva = (
            float(quadra[5] or 0)
            if garantia_reserva == "Obrigatório"
            else 0.0
        )

        valor_restante = (
            valor_hora - taxa_reserva
        )

        if valor_restante < 0:

            valor_restante = 0.0

        # -------------------------------------------------
        # CRIA AGENDAMENTO
        #
        # Pendente NÃO bloqueia novas solicitações.
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO agendamento
                (
                    cliente_id,
                    quadra_id,
                    data,
                    horario,
                    valor_hora,
                    taxa_reserva,
                    valor_restante,
                    status
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """,
            (
                cliente_id,
                dados.quadra_id,
                dados.data,
                dados.horario,
                valor_hora,
                taxa_reserva,
                valor_restante,
                "Pendente"
            )
        )

        agendamento_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO historico_status_agendamento
                (agendamento_id, status_anterior, status_novo)
            VALUES (%s, 'Novo', 'Pendente')
            """,
            (agendamento_id,)
        )

        whatsapp_url = criar_link_whatsapp_reserva(
            whatsapp_responsavel=quadra[6],
            nome_cliente=nome_cliente,
            contato_cliente=dados.contato.strip(),
            nome_quadra=quadra[1],
            data_reserva=data_reserva,
            horario_reserva=horario_reserva
        )
        conexao.commit()

        telegram_notificado = True
        try:
            enviar_notificacao_telegram_reserva(cursor, data_reserva)
        except Exception:
            telegram_notificado = False
            logger.exception(
                "Telegram notification failed after booking %s was committed.",
                agendamento_id
            )

        return {
            "mensagem":
                "Solicitação criada com sucesso.",

            "id":
                agendamento_id,

            "telegram_notificado":
                telegram_notificado,

            "status":
                "Pendente",

            "whatsapp_url":
                whatsapp_url,

            "valor_hora":
                valor_hora,

            "taxa_reserva":
                taxa_reserva,

            "valor_restante":
                valor_restante,

            "garantia_reserva":
                garantia_reserva
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.put("/agendamentos/{agendamento_id}/status")
def atualizar_status_agendamento(
    agendamento_id: int,
    dados: AtualizarStatus,
    request: Request
):

    status_validos = [
        "Pendente",
        "Confirmado",
        "Cancelado",
        "Não atendido"
    ]

    if dados.status not in status_validos:

        raise HTTPException(
            status_code=400,
            detail="Status inválido."
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        # -------------------------------------------------
        # BUSCA O AGENDAMENTO
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                quadra_id,
                data,
                horario
            FROM agendamento
            WHERE id = %s
            """,
            (agendamento_id,)
        )

        agendamento_inicial = cursor.fetchone()

        if not agendamento_inicial:

            raise HTTPException(
                status_code=404,
                detail="Agendamento não encontrado."
            )

        quadra_id = agendamento_inicial[0]
        data_reserva = agendamento_inicial[1]
        horario = agendamento_inicial[2]

        cursor.execute(
            """
            SELECT id
            FROM quadra
            WHERE id = %s
            FOR UPDATE
            """,
            (quadra_id,)
        )

        if not cursor.fetchone():

            raise HTTPException(
                status_code=404,
                detail="Quadra não encontrada."
            )

        cursor.execute(
            """
            SELECT
                id,
                status
            FROM agendamento
            WHERE quadra_id = %s
              AND data = %s
              AND horario = %s
            ORDER BY id
            FOR UPDATE
            """,
            (
                quadra_id,
                data_reserva,
                horario
            )
        )

        agendamentos_horario = cursor.fetchall()
        agendamento = next(
            (
                item
                for item in agendamentos_horario
                if item[0] == agendamento_id
            ),
            None
        )

        if not agendamento:

            raise HTTPException(
                status_code=404,
                detail="Agendamento não encontrado."
            )

        status_atual = agendamento[1]
        cursor.execute(
            """
            SELECT taxa_reserva
            FROM agendamento
            WHERE id = %s
            """,
            (agendamento_id,)
        )
        taxa_reserva = float(cursor.fetchone()[0] or 0)

        # -------------------------------------------------
        # NÃO PERMITE ALTERAR AGENDAMENTO PASSADO
        # -------------------------------------------------

        horario_texto = str(horario)[:5]

        try:
            hora, minuto = map(
                int,
                horario_texto.split(":")[:2]
            )

            data_hora_reserva = datetime.combine(
                data_reserva,
                datetime.min.time()
            ).replace(
                hour=hora,
                minute=minuto
            )

        except (ValueError, TypeError):

            data_hora_reserva = datetime.combine(
                data_reserva,
                datetime.min.time()
            )

        if data_hora_reserva < datetime.now():

            raise HTTPException(
                status_code=409,
                detail=(
                    "Este agendamento já passou e não pode mais ser alterado."
                )
            )

        # -------------------------------------------------
        # NÃO REABRE CANCELADO / NÃO ATENDIDO
        # -------------------------------------------------

        if status_atual in ["Cancelado", "Não atendido"]:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Este agendamento não pode mais ser reaberto."
                )
            )

        # -------------------------------------------------
        # NÃO PERMITE CONFIRMAR HORÁRIO DE MENSALISTA
        # -------------------------------------------------

        if dados.status == "Confirmado":

            dia_semana = (
                data_reserva.weekday() + 1
            ) % 7

            cursor.execute(
                """
                SELECT id
                FROM mensalidade
                WHERE quadra_id = %s
                  AND dia_semana = %s
                  AND horario = %s
                  AND status = 'Ativa'
                  AND data_inicio <= %s
                LIMIT 1
                """,
                (
                    quadra_id,
                    dia_semana,
                    horario,
                    data_reserva
                )
            )

            mensalidade = cursor.fetchone()

            if mensalidade:

                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Este horário pertence "
                        "a uma mensalidade ativa."
                    )
                )

            outro_confirmado = next(
                (
                    item
                    for item in agendamentos_horario
                    if item[0] != agendamento_id
                    and item[1] == "Confirmado"
                ),
                None
            )

            if outro_confirmado:

                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Este horário já possui "
                        "outro agendamento confirmado."
                    )
                )

            cursor.execute(
                """
                SELECT COALESCE(SUM(valor_pago), 0)
                FROM pagamento
                WHERE agendamento_id = %s
                  AND status <> 'Cancelado'
                """,
                (agendamento_id,)
            )
            taxa_paga = float(cursor.fetchone()[0] or 0)
            if taxa_paga < taxa_reserva:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Registre o recebimento da taxa de reserva "
                        "antes de confirmar este agendamento."
                    )
                )

        solicitacoes_pendentes = []
        solicitacoes_reabertas = 0

        if (
            status_atual == "Confirmado" and
            dados.status != "Confirmado"
        ):

            cursor.execute(
                """
                UPDATE agendamento
                SET status = 'Pendente'
                WHERE quadra_id = %s
                  AND data = %s
                  AND horario = %s
                  AND status = 'Não atendido'
                  AND id <> %s
                """,
                (
                    quadra_id,
                    data_reserva,
                    horario,
                    agendamento_id
                )
            )

            solicitacoes_reabertas = cursor.rowcount
            for solicitacao_id in [
                item[0]
                for item in agendamentos_horario
                if item[0] != agendamento_id
                and item[1] == "Não atendido"
            ]:
                cursor.execute(
                    """
                    INSERT INTO historico_status_agendamento
                        (agendamento_id, status_anterior, status_novo)
                    VALUES (%s, 'Não atendido', 'Pendente')
                    """,
                    (solicitacao_id,)
                )

            cursor.execute(
                """
                DELETE FROM agendamento_fila_retorno
                WHERE confirmado_id = %s
                """,
                (agendamento_id,)
            )

        cursor.execute(
            """
            UPDATE agendamento
            SET status = %s
            WHERE id = %s
            """,
            (
                dados.status,
                agendamento_id
            )
        )

        if status_atual != dados.status:
            cursor.execute(
                """
                INSERT INTO historico_status_agendamento
                    (agendamento_id, status_anterior, status_novo)
                VALUES (%s, %s, %s)
                """,
                (
                    agendamento_id,
                    status_atual,
                    dados.status
                )
            )

        if dados.status == "Confirmado":

            solicitacoes_pendentes = [
                item[0]
                for item in agendamentos_horario
                if item[0] != agendamento_id
                and item[1] == "Pendente"
            ]

            for solicitacao_id in solicitacoes_pendentes:

                cursor.execute(
                    """
                    INSERT INTO historico_status_agendamento
                        (agendamento_id, status_anterior, status_novo)
                    VALUES (%s, 'Pendente', 'Não atendido')
                    """,
                    (solicitacao_id,)
                )

                cursor.execute(
                    """
                    INSERT INTO agendamento_fila_retorno
                        (agendamento_id, confirmado_id)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE
                        confirmado_id = VALUES(confirmado_id)
                    """,
                    (
                        solicitacao_id,
                        agendamento_id
                    )
                )

            if solicitacoes_pendentes:

                cursor.execute(
                    """
                    UPDATE agendamento
                    SET status = 'Não atendido'
                    WHERE quadra_id = %s
                      AND data = %s
                      AND horario = %s
                      AND status = 'Pendente'
                      AND id <> %s
                    """,
                    (
                        quadra_id,
                        data_reserva,
                        horario,
                        agendamento_id
                    )
                )

        if status_atual != dados.status:
            enviar_extrato_diario_telegram(
                cursor,
                str(request.base_url)
            )

        conexao.commit()

        return {
            "mensagem":
                "Status atualizado com sucesso.",

            "status":
                dados.status,

            "solicitacoes_atualizadas":
                len(solicitacoes_pendentes)
                if dados.status == "Confirmado"
                else solicitacoes_reabertas
                if status_atual == "Confirmado"
                else 0
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# RESUMO DE RESERVAS POR MODALIDADE
# =========================================================

@app.get("/admin/resumo-reservas")
def obter_resumo_reservas_admin(
    request: Request,
    quadra_id: Optional[int] = None
):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        filtro_quadras = "1 = 1"
        parametros_quadras = []
        if quadra_id is not None:
            if (
                request.state.nivel_admin != "root"
                and quadra_id not in request.state.quadras_permitidas
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Você não tem acesso a esta quadra."
                )
            filtro_quadras = "quadra_id = %s"
            parametros_quadras = [quadra_id]
        elif request.state.nivel_admin != "root":
            quadras_permitidas = request.state.quadras_permitidas
            if not quadras_permitidas:
                return {
                    "total": 0,
                    "avulsas": {"total": 0, "pendente": 0, "confirmado": 0,
                                "cancelado": 0, "nao_atendido": 0, "outros": 0},
                    "mensais": {"total": 0, "pendente": 0, "ativa": 0,
                                "encerrada": 0, "outros": 0}
                }
            placeholders = ", ".join(["%s"] * len(quadras_permitidas))
            filtro_quadras = f"quadra_id IN ({placeholders})"
            parametros_quadras = quadras_permitidas

        cursor.execute(
            f"""
            SELECT status, COUNT(*)
            FROM agendamento
            WHERE {filtro_quadras}
            GROUP BY status
            """,
            parametros_quadras
        )
        status_avulsas = {
            status: int(total or 0)
            for status, total in cursor.fetchall()
        }
        cursor.execute(
            f"""
            SELECT status, COUNT(*)
            FROM mensalidade
            WHERE {filtro_quadras}
            GROUP BY status
            """,
            parametros_quadras
        )
        status_mensais = {
            status: int(total or 0)
            for status, total in cursor.fetchall()
        }
        avulsas = {
            "total": sum(status_avulsas.values()),
            "pendente": status_avulsas.get("Pendente", 0),
            "confirmado": status_avulsas.get("Confirmado", 0),
            "cancelado": status_avulsas.get("Cancelado", 0),
            "nao_atendido": status_avulsas.get("Não atendido", 0),
            "outros": sum(
                total
                for status, total in status_avulsas.items()
                if status not in {
                    "Pendente", "Confirmado", "Cancelado", "Não atendido"
                }
            )
        }
        mensais = {
            "total": sum(status_mensais.values()),
            "pendente": status_mensais.get("Pendente", 0),
            "ativa": status_mensais.get("Ativa", 0),
            "encerrada": status_mensais.get("Encerrada", 0),
            "outros": sum(
                total
                for status, total in status_mensais.items()
                if status not in {"Pendente", "Ativa", "Encerrada"}
            )
        }
        return {
            "total": avulsas["total"] + mensais["total"],
            "avulsas": avulsas,
            "mensais": mensais
        }
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# MENSALIDADES
# =========================================================

@app.get("/mensalidades")
def listar_mensalidades(quadra_id: Optional[int] = None):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                m.id,
                c.id AS cliente_id,
                c.nome AS cliente,
                c.contato,
                q.id AS quadra_id,
                q.nome AS quadra,
                q.tipo AS tipo_quad,
                m.dia_semana,
                m.horario,
                m.valor_mensal,
                m.data_inicio,
                m.data_encerramento,
                m.status,
                m.observacao,
                m.criado_em

            FROM mensalidade m

            INNER JOIN cliente c
                ON c.id = m.cliente_id

            INNER JOIN quadra q
                ON q.id = m.quadra_id

            WHERE (%s IS NULL OR m.quadra_id = %s)
            ORDER BY
                m.status,
                c.nome
            """,
            (quadra_id, quadra_id)
        )

        linhas = cursor.fetchall()

        return [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in linhas
        ]

    finally:

        cursor.close()
        conexao.close()


@app.get("/mensalidades/clientes")
def listar_clientes_para_mensalidades(quadra_id: Optional[int] = None):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, nome, contato
            FROM cliente
            WHERE (%s IS NULL OR EXISTS (
                SELECT 1 FROM mensalidade m
                WHERE m.cliente_id = cliente.id
                  AND m.quadra_id = %s
            ) OR EXISTS (
                SELECT 1 FROM agendamento a
                WHERE a.cliente_id = cliente.id
                  AND a.quadra_id = %s
            ))
            ORDER BY nome
            """,
            (quadra_id, quadra_id, quadra_id)
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


@app.post("/mensalidades")
def criar_mensalidade(
    dados: NovaMensalidade
):

    if dados.dia_semana < 0 or dados.dia_semana > 6:

        raise HTTPException(
            status_code=400,
            detail="Dia da semana inválido."
        )

    try:
        data_inicio = datetime.strptime(
            dados.data_inicio,
            "%Y-%m-%d"
        ).date()
        if data_inicio.isoformat() != dados.data_inicio:
            raise ValueError
        data_encerramento = None
        if dados.data_encerramento:
            data_encerramento = datetime.strptime(
                dados.data_encerramento,
                "%Y-%m-%d"
            ).date()
            if (
                data_encerramento.isoformat() != dados.data_encerramento
                or data_encerramento < data_inicio
            ):
                raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Informe um período válido para a mensalidade."
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        # -------------------------------------------------
        # VERIFICA QUADRA
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                tipo,
                valor_mensal
            FROM quadra
            WHERE id = %s
              AND ativo = 1
            """,
            (dados.quadra_id,)
        )

        quadra = cursor.fetchone()

        if not quadra:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Quadra não encontrada "
                    "ou inativa."
                )
            )

        tipo_quad = quadra[1]

        # -------------------------------------------------
        # BUSCA VALOR MENSAL AUTOMATICAMENTE
        # -------------------------------------------------

        valor_mensal = resolver_valor_mensal(
            quadra[2],
            dados.valor_mensal
        )

        # -------------------------------------------------
        # VERIFICA CONFLITO
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM mensalidade
            WHERE quadra_id = %s
              AND dia_semana = %s
              AND horario = %s
              AND status = 'Ativa'
              AND (
                  data_encerramento IS NULL
                  OR data_encerramento >= %s
              )
              AND data_inicio <= COALESCE(%s, '9999-12-31')
            LIMIT 1
            """,
            (
                dados.quadra_id,
                dados.dia_semana,
                dados.horario,
                data_inicio,
                data_encerramento
            )
        )

        if cursor.fetchone():

            raise HTTPException(
                status_code=409,
                detail=(
                    "Já existe uma mensalidade "
                    "ativa neste horário."
                )
            )

        cursor.execute(
            """
            SELECT id
            FROM agendamento
            WHERE quadra_id = %s
              AND horario = %s
              AND status IN ('Pendente', 'Confirmado')
              AND data >= %s
              AND (%s IS NULL OR data <= %s)
              AND DAYOFWEEK(data) - 1 = %s
            ORDER BY data, id
            LIMIT 1
            """,
            (
                dados.quadra_id,
                dados.horario,
                data_inicio,
                data_encerramento,
                data_encerramento,
                dados.dia_semana
            )
        )
        reserva_conflitante = cursor.fetchone()
        if reserva_conflitante:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Não é possível criar esta mensalidade: já existe uma "
                    "solicitação ou reserva neste dia e horário "
                    f"(agendamento #{reserva_conflitante[0]})."
                )
            )

        # -------------------------------------------------
        # CLIENTE
        # -------------------------------------------------

        cliente_id, _ = obter_ou_criar_cliente(
            cursor,
            dados.nome.strip(),
            dados.contato.strip()
        )

        # -------------------------------------------------
        # CRIA MENSALIDADE
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO mensalidade
                (
                    cliente_id,
                    quadra_id,
                    dia_semana,
                    horario,
                    valor_mensal,
                    data_inicio,
                    data_encerramento,
                    observacao,
                    status
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """,
            (
                cliente_id,
                dados.quadra_id,
                dados.dia_semana,
                dados.horario,
                valor_mensal,
                data_inicio,
                data_encerramento,
                dados.observacao,
                "Ativa"
            )
        )

        mensalidade_id = cursor.lastrowid

        conexao.commit()

        return {
            "mensagem":
                "Mensalidade criada com sucesso.",

            "id":
                mensalidade_id,

            "status":
                "Ativa",

            "valor_mensal":
                valor_mensal
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.post("/solicitacoes-mensais")
def criar_solicitacao_mensalidade(dados: SolicitacaoMensalidade):
    if dados.dia_semana < 0 or dados.dia_semana > 6:
        raise HTTPException(status_code=400, detail="Dia da semana inválido.")
    try:
        data_inicio = datetime.strptime(dados.data_inicio, "%Y-%m-%d").date()
        horario = datetime.strptime(dados.horario, "%H:%M").time()
        if data_inicio.isoformat() != dados.data_inicio or data_inicio < date.today():
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Informe uma data inicial e um horário válidos.")

    if data_inicio.weekday() != (dados.dia_semana + 6) % 7:
        raise HTTPException(status_code=400, detail="O dia da semana não corresponde à data inicial.")

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, valor_mensal
            FROM quadra
            WHERE id = %s AND ativo = 1
            FOR UPDATE
            """,
            (dados.quadra_id,)
        )
        quadra = cursor.fetchone()
        if not quadra:
            raise HTTPException(status_code=404, detail="Quadra não encontrada ou inativa.")
        valor_mensal = Decimal(str(quadra[1] or 0))
        if valor_mensal <= 0:
            raise HTTPException(status_code=400, detail="O valor mensal desta quadra não está configurado.")

        cursor.execute(
            """
            SELECT id
            FROM mensalidade
            WHERE quadra_id = %s AND dia_semana = %s AND horario = %s
              AND status IN ('Ativa', 'Pendente')
              AND (data_encerramento IS NULL OR data_encerramento >= %s)
            LIMIT 1
            """,
            (dados.quadra_id, dados.dia_semana, horario, data_inicio)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="Já existe uma solicitação ou mensalidade para este dia e horário.")

        cursor.execute(
            """
            SELECT id
            FROM agendamento
            WHERE quadra_id = %s AND horario = %s
              AND status IN ('Pendente', 'Confirmado')
              AND data >= %s
              AND DAYOFWEEK(data) - 1 = %s
            ORDER BY data, id
            LIMIT 1
            """,
            (dados.quadra_id, horario, data_inicio, dados.dia_semana)
        )
        reserva = cursor.fetchone()
        if reserva:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma reserva ou solicitação neste dia e horário (agendamento #{reserva[0]})."
            )

        nome = normalizar_nome_cliente(dados.nome)
        contato = dados.contato.strip()
        if not nome or not contato:
            raise HTTPException(status_code=400, detail="Informe nome e WhatsApp.")
        cliente_id, _ = obter_ou_criar_cliente(cursor, nome, contato)
        cursor.execute(
            """
            INSERT INTO mensalidade
                (cliente_id, quadra_id, dia_semana, horario, valor_mensal,
                 data_inicio, observacao, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pendente')
            """,
            (
                cliente_id,
                dados.quadra_id,
                dados.dia_semana,
                horario,
                valor_mensal,
                data_inicio,
                "Solicitação mensal pelo site."
            )
        )
        mensalidade_id = cursor.lastrowid
        conexao.commit()
        return {
            "mensagem": "Solicitação mensal registrada; aguarda confirmação administrativa.",
            "id": mensalidade_id,
            "status": "Pendente",
            "valor_mensal": float(valor_mensal)
        }
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.put("/mensalidades/{mensalidade_id}")
def atualizar_mensalidade(
    mensalidade_id: int,
    dados: AtualizarMensalidade
):

    if (
        dados.valor_mensal is not None
        and not math.isfinite(dados.valor_mensal)
    ):
        raise HTTPException(
            status_code=400,
            detail="Informe um valor mensal válido."
        )

    status_validos = ["Pendente", "Ativa", "Encerrada"]

    if dados.status not in status_validos:

        raise HTTPException(
            status_code=400,
            detail=(
                "Status de mensalidade inválido."
            )
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT quadra_id, dia_semana, horario, data_inicio,
                   data_encerramento, status
            FROM mensalidade
            WHERE id = %s
            FOR UPDATE
            """,
            (mensalidade_id,)
        )
        mensalidade_atual = cursor.fetchone()
        if not mensalidade_atual:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Mensalidade não encontrada."
                )
            )

        if dados.status == "Ativa":
            cursor.execute(
                """
                SELECT id
                FROM mensalidade
                WHERE id <> %s
                  AND quadra_id = %s
                  AND dia_semana = %s
                  AND horario = %s
                  AND status = 'Ativa'
                  AND (data_encerramento IS NULL OR data_encerramento >= %s)
                  AND data_inicio <= COALESCE(%s, '9999-12-31')
                LIMIT 1
                """,
                (
                    mensalidade_id,
                    mensalidade_atual[0],
                    mensalidade_atual[1],
                    mensalidade_atual[2],
                    mensalidade_atual[3],
                    mensalidade_atual[4]
                )
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Já existe uma mensalidade ativa neste dia e horário.")
            cursor.execute(
                """
                SELECT id
                FROM agendamento
                WHERE quadra_id = %s AND horario = %s
                  AND status IN ('Pendente', 'Confirmado')
                  AND data >= %s
                  AND (%s IS NULL OR data <= %s)
                  AND DAYOFWEEK(data) - 1 = %s
                LIMIT 1
                """,
                (
                    mensalidade_atual[0],
                    mensalidade_atual[2],
                    mensalidade_atual[3],
                    mensalidade_atual[4],
                    mensalidade_atual[4],
                    mensalidade_atual[1]
                )
            )
            reserva_conflitante = cursor.fetchone()
            if reserva_conflitante:
                raise HTTPException(
                    status_code=409,
                    detail=f"Há um agendamento conflitante (#{reserva_conflitante[0]}) para este horário."
                )

        campos = [
            "status = %s"
        ]

        valores = [
            dados.status
        ]

        if dados.valor_mensal is not None:

            campos.append(
                "valor_mensal = %s"
            )

            valores.append(
                dados.valor_mensal
            )

        if dados.observacao is not None:

            campos.append(
                "observacao = %s"
            )

            valores.append(
                dados.observacao
            )

        if dados.data_encerramento is not None:

            campos.append(
                "data_encerramento = %s"
            )

            valores.append(
                dados.data_encerramento
            )

        valores.append(
            mensalidade_id
        )

        sql = f"""
            UPDATE mensalidade
            SET {", ".join(campos)}
            WHERE id = %s
        """

        cursor.execute(
            sql,
            valores
        )

        conexao.commit()

        return {
            "mensagem":
                "Mensalidade atualizada com sucesso."
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# PAGAMENTOS DE MENSALIDADE
# =========================================================

@app.get(
    "/mensalidades/{mensalidade_id}/pagamentos"
)
def listar_pagamentos_mensalidade(
    mensalidade_id: int
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                mensalidade_id,
                competencia,
                valor,
                data_pagamento,
                status,
                forma_pagamento,
                observacao,
                criado_em
            FROM pagamento_mensalidade
            WHERE mensalidade_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM pagamento operacional
                  WHERE operacional.mensalidade_id = pagamento_mensalidade.mensalidade_id
                    AND operacional.competencia =
                        DATE_FORMAT(pagamento_mensalidade.competencia, '%Y-%m')
                    AND operacional.status <> 'Cancelado'
              )
            ORDER BY competencia DESC
            """,
            (mensalidade_id,)
        )

        pagamentos_legados = [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT
                id,
                mensalidade_id,
                competencia,
                valor,
                data_pagamento,
                IF(status = 'Recebido', 'Pago', status) AS status,
                forma_pagamento,
                observacao,
                criado_em
            FROM pagamento
            WHERE mensalidade_id = %s
            ORDER BY competencia DESC, id DESC
            """,
            (mensalidade_id,)
        )
        pagamentos_unificados = [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]

        return pagamentos_legados + pagamentos_unificados

    finally:

        cursor.close()
        conexao.close()


@app.post(
    "/mensalidades/{mensalidade_id}/pagamentos"
)
def criar_pagamento_mensalidade(
    mensalidade_id: int,
    dados: NovoPagamentoMensalidade,
    request: Request
):

    status_validos = ["Pago", "Pendente", "Cancelado"]

    if dados.status not in status_validos:

        raise HTTPException(
            status_code=400,
            detail="Status de pagamento inválido."
        )

    if dados.status == "Pago" and not dados.forma_pagamento:
        raise HTTPException(
            status_code=400,
            detail="Informe a forma de pagamento."
        )

    if dados.valor <= 0:
        raise HTTPException(
            status_code=400,
            detail="O valor do pagamento deve ser maior que zero."
        )

    try:
        competencia = datetime.strptime(
            dados.competencia,
            "%Y-%m"
        ).strftime("%Y-%m")
        if competencia != dados.competencia:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Informe a competência no formato AAAA-MM."
        )

    formas_validas = ["PIX", "Dinheiro", "Cartão", "Outro"]
    if dados.forma_pagamento and dados.forma_pagamento not in formas_validas:
        raise HTTPException(
            status_code=400,
            detail="Forma de pagamento inválida."
        )

    data_pagamento = None
    if dados.data_pagamento:
        try:
            data_pagamento = datetime.strptime(
                dados.data_pagamento,
                "%Y-%m-%d"
            ).date()
            if data_pagamento.isoformat() != dados.data_pagamento:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Data do pagamento inválida."
            )
    elif dados.status == "Pago":
        data_pagamento = date.today()

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT id, cliente_id, valor_mensal
            FROM mensalidade
            WHERE id = %s
            FOR UPDATE
            """,
            (mensalidade_id,)
        )

        mensalidade = cursor.fetchone()
        if not mensalidade:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Mensalidade não encontrada."
                )
            )

        cursor.execute(
            """
            SELECT id
            FROM pagamento
            WHERE mensalidade_id = %s
              AND competencia = %s
              AND status <> 'Cancelado'
            LIMIT 1
            FOR UPDATE
            """,
            (mensalidade_id, competencia)
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail="Já existe um pagamento para esta competência."
            )
        cursor.execute(
            """
            SELECT id
            FROM pagamento_mensalidade
            WHERE mensalidade_id = %s
              AND DATE_FORMAT(competencia, '%Y-%m') = %s
              AND status = 'Pago'
            LIMIT 1
            FOR UPDATE
            """,
            (mensalidade_id, competencia)
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail="Já existe um registro histórico para esta competência."
            )

        valor_pago = (
            float(dados.valor)
            if dados.status == "Pago"
            else 0
        )
        cursor.execute(
            """
            INSERT INTO pagamento
                (cliente_id, mensalidade_id, competencia, tipo, valor,
                 taxa_reserva, valor_total, valor_pago, data_pagamento,
                 forma_pagamento, status, observacao)
            VALUES (%s, %s, %s, 'Mensalidade', %s, 0, %s, %s, %s, %s, %s, %s)
            """,
            (
                mensalidade[1],
                mensalidade_id,
                competencia,
                dados.valor,
                dados.valor,
                valor_pago,
                data_pagamento,
                dados.forma_pagamento,
                "Recebido" if dados.status == "Pago" else dados.status,
                dados.observacao
            )
        )
        pagamento_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO historico_status_pagamento
                (pagamento_id, status_anterior, status_novo)
            VALUES (%s, 'Novo', %s)
            """,
            (
                pagamento_id,
                "Recebido" if dados.status == "Pago" else dados.status
            )
        )
        if valor_pago > 0:
            cursor.execute(
                """
                INSERT INTO pagamento_recebimento
                    (pagamento_id, valor_recebido, data_hora_recebimento,
                     usuario_recebedor_id, nome_usuario, metodo_pagamento,
                     observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    pagamento_id,
                    valor_pago,
                    datetime.combine(data_pagamento or date.today(), datetime.now().time()),
                    request.state.usuario_admin_id,
                    request.state.nome_usuario_admin,
                    dados.forma_pagamento,
                    dados.observacao
                )
            )

        conexao.commit()

        return {
            "mensagem":
                "Pagamento registrado com sucesso.",

            "id":
                pagamento_id
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.get("/pagamentos")
def listar_pagamentos(quadra_id: Optional[int] = None):

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT
                p.id,
                p.tipo,
                p.cliente_id,
                c.nome AS cliente,
                p.agendamento_id,
                p.mensalidade_id,
                p.competencia,
                q.id AS quadra_id,
                q.nome AS quadra,
                p.valor,
                p.taxa_reserva,
                p.valor_total,
                p.valor_pago,
                p.data_pagamento,
                p.forma_pagamento,
                p.status,
                p.observacao,
                p.criado_em,
                'Sistema' AS origem
            FROM pagamento p
            INNER JOIN cliente c
                ON c.id = p.cliente_id
            LEFT JOIN agendamento a
                ON a.id = p.agendamento_id
            LEFT JOIN mensalidade m
                ON m.id = p.mensalidade_id
            LEFT JOIN quadra q
                ON q.id = COALESCE(a.quadra_id, m.quadra_id)
            WHERE (%s IS NULL OR q.id = %s)
            ORDER BY p.criado_em DESC, p.id DESC
            """,
            (quadra_id, quadra_id)
        )
        resultado = [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT
                CONCAT('mensalidade-legada-', p.id) AS id,
                'Mensalidade' AS tipo,
                m.cliente_id,
                c.nome AS cliente,
                NULL AS agendamento_id,
                p.mensalidade_id,
                DATE_FORMAT(
                    COALESCE(p.data_pagamento, p.criado_em),
                    '%Y-%m'
                ) AS competencia,
                q.id AS quadra_id,
                q.nome AS quadra,
                p.valor,
                0 AS taxa_reserva,
                p.valor AS valor_total,
                IF(p.status = 'Pago', p.valor, 0) AS valor_pago,
                p.data_pagamento,
                p.forma_pagamento,
                IF(p.status = 'Pago', 'Recebido', p.status) AS status,
                p.observacao,
                p.criado_em,
                'Mensalidade (histórico)' AS origem
            FROM pagamento_mensalidade p
            INNER JOIN mensalidade m
                ON m.id = p.mensalidade_id
            INNER JOIN cliente c
                ON c.id = m.cliente_id
            INNER JOIN quadra q
                ON q.id = m.quadra_id
            WHERE (%s IS NULL OR q.id = %s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM pagamento operacional
                  WHERE operacional.mensalidade_id = p.mensalidade_id
                    AND operacional.competencia =
                        DATE_FORMAT(p.competencia, '%Y-%m')
                    AND operacional.status <> 'Cancelado'
              )
            ORDER BY p.criado_em DESC, p.id DESC
            """,
            (quadra_id, quadra_id)
        )
        resultado.extend(
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        )
        resultado.sort(
            key=lambda item: (
                item.get("criado_em") or "",
                str(item.get("id"))
            ),
            reverse=True
        )
        return resultado
    finally:
        cursor.close()
        conexao.close()


@app.get("/pagamentos/referencias")
def listar_referencias_pagamento(quadra_id: Optional[int] = None):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT a.id, c.nome AS cliente, q.nome AS quadra,
                   a.data, a.horario, a.status, a.taxa_reserva
            FROM agendamento a
            INNER JOIN cliente c ON c.id = a.cliente_id
            INNER JOIN quadra q ON q.id = a.quadra_id
            WHERE a.status IN ('Pendente', 'Confirmado')
              AND (%s IS NULL OR q.id = %s)
            ORDER BY a.data DESC, a.id DESC
            """,
            (quadra_id, quadra_id)
        )
        agendamentos = [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT m.id, c.nome AS cliente, q.nome AS quadra,
                   q.tipo AS tipo_quad, m.dia_semana, m.horario,
                   m.valor_mensal, m.status
            FROM mensalidade m
            INNER JOIN cliente c ON c.id = m.cliente_id
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE m.status = 'Ativa'
              AND (%s IS NULL OR q.id = %s)
            ORDER BY c.nome
            """,
            (quadra_id, quadra_id)
        )
        mensalidades = [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
        return {
            "agendamentos": agendamentos,
            "mensalidades": mensalidades
        }
    finally:
        cursor.close()
        conexao.close()


@app.post("/pagamentos")
def criar_pagamento(dados: NovoPagamento, request: Request):

    if (dados.agendamento_id is None) == (dados.mensalidade_id is None):
        raise HTTPException(
            status_code=400,
            detail="Informe uma reserva ou uma mensalidade para relacionar o pagamento."
        )

    status_validos = ["Pendente", "Recebido", "Cancelado"]
    formas_validas = ["PIX", "Dinheiro", "Cartão", "Outro"]
    if dados.status not in status_validos:
        raise HTTPException(status_code=400, detail="Status de pagamento inválido.")
    if dados.forma_pagamento and dados.forma_pagamento not in formas_validas:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")
    if not math.isfinite(dados.valor_pago) or dados.valor_pago < 0:
        raise HTTPException(status_code=400, detail="O valor recebido não pode ser negativo.")
    competencia = None
    if dados.mensalidade_id:
        try:
            competencia = datetime.strptime(
                dados.competencia or "",
                "%Y-%m"
            ).strftime("%Y-%m")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Informe a competência da mensalidade no formato AAAA-MM."
            )
    elif dados.competencia:
        raise HTTPException(
            status_code=400,
            detail="Competência só deve ser informada para mensalidades."
        )
    if dados.status == "Recebido" and dados.valor_pago <= 0:
        raise HTTPException(
            status_code=400,
            detail="Informe um valor recebido."
        )
    if dados.valor_pago > 0 and not dados.forma_pagamento:
        raise HTTPException(
            status_code=400,
            detail="Informe a forma de pagamento do valor recebido."
        )

    data_pagamento = None
    if dados.data_pagamento:
        try:
            data_pagamento = datetime.strptime(
                dados.data_pagamento,
                "%Y-%m-%d"
            ).date()
            if data_pagamento.isoformat() != dados.data_pagamento:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Data do pagamento inválida.")
    elif dados.valor_pago > 0:
        data_pagamento = date.today()

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        tipo = "Reserva" if dados.agendamento_id else "Mensalidade"
        cliente_id = None
        valor = 0.0
        taxa_reserva = 0.0
        valor_total = 0.0

        if dados.agendamento_id:
            cursor.execute(
                """
                SELECT cliente_id, valor_hora, taxa_reserva,
                       valor_restante, status, data
                FROM agendamento
                WHERE id = %s
                FOR UPDATE
                """,
                (dados.agendamento_id,)
            )
            reserva = cursor.fetchone()
            if not reserva:
                raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
            if reserva[4] == "Cancelado":
                raise HTTPException(status_code=409, detail="Não é possível registrar pagamento para uma reserva cancelada.")

            cursor.execute(
                """
                SELECT id
                FROM pagamento
                WHERE agendamento_id = %s
                  AND status <> 'Cancelado'
                LIMIT 1
                FOR UPDATE
                """,
                (dados.agendamento_id,)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="Esta reserva já possui um pagamento ativo."
                )

            cliente_id = reserva[0]
            taxa_reserva = float(reserva[2] or 0)
            valor = float(reserva[3] or 0)
            valor_total = valor + taxa_reserva

            cursor.execute(
                """
                SELECT COALESCE(SUM(valor_pago), 0)
                FROM pagamento
                WHERE agendamento_id = %s
                  AND status = 'Recebido'
                """,
                (dados.agendamento_id,)
            )
            total_ja_pago = float(cursor.fetchone()[0] or 0)
            if total_ja_pago + dados.valor_pago > valor_total:
                raise HTTPException(
                    status_code=409,
                    detail="O valor informado excede o saldo desta reserva."
                )
        else:
            cursor.execute(
                """
                SELECT cliente_id, valor_mensal
                FROM mensalidade
                WHERE id = %s
                FOR UPDATE
                """,
                (dados.mensalidade_id,)
            )
            mensalidade = cursor.fetchone()
            if not mensalidade:
                raise HTTPException(status_code=404, detail="Mensalidade não encontrada.")
            cliente_id = mensalidade[0]
            valor = float(mensalidade[1])
            valor_total = valor
            cursor.execute(
                """
                SELECT id
                FROM pagamento
                WHERE mensalidade_id = %s
                  AND competencia = %s
                  AND status <> 'Cancelado'
                LIMIT 1
                FOR UPDATE
                """,
                (dados.mensalidade_id, competencia)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="Esta competência já possui um pagamento ativo."
                )
            cursor.execute(
                """
                SELECT id
                FROM pagamento_mensalidade
                WHERE mensalidade_id = %s
                  AND DATE_FORMAT(competencia, '%Y-%m') = %s
                  AND status = 'Pago'
                LIMIT 1
                FOR UPDATE
                """,
                (dados.mensalidade_id, competencia)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="Já existe um registro histórico para esta competência."
                )

            cursor.execute(
                """
                SELECT COALESCE(SUM(valor_pago), 0)
                FROM pagamento
                WHERE mensalidade_id = %s
                  AND competencia = %s
                  AND status = 'Recebido'
                """,
                (dados.mensalidade_id, competencia)
            )
            total_ja_pago = float(cursor.fetchone()[0] or 0)
            if total_ja_pago + dados.valor_pago > valor_total:
                raise HTTPException(
                    status_code=409,
                    detail="O valor informado excede o valor da competência mensal."
                )

        status_final = (
            "Recebido"
            if dados.status != "Cancelado"
            and dados.valor_pago > 0
            and dados.valor_pago >= valor_total
            else "Pendente" if dados.status == "Recebido" else dados.status
        )

        cursor.execute(
            """
            INSERT INTO pagamento
                (cliente_id, agendamento_id, mensalidade_id, competencia, tipo,
                 valor, taxa_reserva, valor_total, valor_pago,
                 data_pagamento, forma_pagamento, status, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cliente_id,
                dados.agendamento_id,
                dados.mensalidade_id,
                competencia,
                tipo,
                valor,
                taxa_reserva,
                valor_total,
                dados.valor_pago,
                data_pagamento,
                dados.forma_pagamento,
                status_final,
                dados.observacao
            )
        )
        pagamento_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO historico_status_pagamento
                (pagamento_id, status_anterior, status_novo)
            VALUES (%s, 'Novo', %s)
            """,
            (pagamento_id, status_final)
        )
        if dados.valor_pago > 0:
            cursor.execute(
                """
                INSERT INTO pagamento_recebimento
                    (pagamento_id, valor_recebido, data_hora_recebimento,
                     usuario_recebedor_id, nome_usuario, metodo_pagamento,
                     observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    pagamento_id,
                    dados.valor_pago,
                    datetime.combine(data_pagamento or date.today(), datetime.now().time()),
                    request.state.usuario_admin_id,
                    request.state.nome_usuario_admin,
                    dados.forma_pagamento,
                    dados.observacao
                )
            )
        if (
            dados.agendamento_id
            and status_final == "Recebido"
            and taxa_reserva > 0
            and dados.valor_pago >= taxa_reserva
        ):
            enviar_extrato_diario_telegram(
                cursor,
                str(request.base_url)
            )
        conexao.commit()
        return {
            "mensagem": "Pagamento registrado com sucesso.",
            "id": pagamento_id,
            "valor": valor,
            "taxa_reserva": taxa_reserva,
            "valor_total": valor_total,
            "valor_pago": dados.valor_pago,
            "status": status_final
        }
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.get("/pagamentos/recebimentos")
def listar_recebimentos(quadra_id: Optional[int] = None):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT r.id, r.pagamento_id, r.valor_recebido,
                   r.data_hora_recebimento, r.usuario_recebedor_id,
                   r.nome_usuario, r.metodo_pagamento, r.observacoes,
                   p.tipo, p.competencia, c.nome AS cliente,
                   q.nome AS quadra, p.valor_total
            FROM pagamento_recebimento r
            INNER JOIN pagamento p ON p.id = r.pagamento_id
            INNER JOIN cliente c ON c.id = p.cliente_id
            LEFT JOIN agendamento a ON a.id = p.agendamento_id
            LEFT JOIN mensalidade m ON m.id = p.mensalidade_id
            LEFT JOIN quadra q ON q.id = COALESCE(a.quadra_id, m.quadra_id)
            WHERE (%s IS NULL OR q.id = %s)
            ORDER BY r.data_hora_recebimento DESC, r.id DESC
            """,
            (quadra_id, quadra_id)
        )
        return [linha_para_dict(cursor, linha) for linha in cursor.fetchall()]
    finally:
        cursor.close()
        conexao.close()


@app.post("/pagamentos/{pagamento_id}/recebimentos")
def registrar_recebimento(
    pagamento_id: int,
    dados: NovoRecebimento,
    request: Request
):
    formas_validas = {"PIX", "Dinheiro", "Cartão", "Outro"}
    if dados.metodo_pagamento not in formas_validas:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")
    try:
        valor_recebido = Decimal(str(dados.valor_recebido)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor recebido inválido.")
    if not valor_recebido.is_finite() or valor_recebido <= 0:
        raise HTTPException(status_code=400, detail="O valor recebido deve ser maior que zero.")
    data_pagamento = date.today()
    if dados.data_pagamento:
        try:
            data_pagamento = datetime.strptime(dados.data_pagamento, "%Y-%m-%d").date()
            if data_pagamento.isoformat() != dados.data_pagamento:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Data do recebimento inválida.")

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT status, valor_total, valor_pago, taxa_reserva,
                   agendamento_id
            FROM pagamento
            WHERE id = %s
            FOR UPDATE
            """,
            (pagamento_id,)
        )
        pagamento = cursor.fetchone()
        if not pagamento:
            raise HTTPException(status_code=404, detail="Pagamento não encontrado.")
        if pagamento[0] == "Cancelado":
            raise HTTPException(status_code=409, detail="Não é possível receber valores para um pagamento cancelado.")
        saldo = Decimal(str(pagamento[1] or 0)) - Decimal(str(pagamento[2] or 0))
        if valor_recebido > saldo:
            raise HTTPException(
                status_code=409,
                detail=f"O recebimento excede o saldo de R$ {max(saldo, Decimal('0')):.2f}."
            )

        total_atualizado = Decimal(str(pagamento[2] or 0)) + valor_recebido
        status_novo = "Recebido" if total_atualizado >= Decimal(str(pagamento[1])) else "Pendente"
        data_hora = datetime.combine(data_pagamento, datetime.now().time())
        cursor.execute(
            """
            INSERT INTO pagamento_recebimento
                (pagamento_id, valor_recebido, data_hora_recebimento,
                 usuario_recebedor_id, nome_usuario, metodo_pagamento,
                 observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pagamento_id,
                valor_recebido,
                data_hora,
                request.state.usuario_admin_id,
                request.state.nome_usuario_admin,
                dados.metodo_pagamento,
                dados.observacoes
            )
        )
        cursor.execute(
            """
            UPDATE pagamento
            SET valor_pago = %s, status = %s, data_pagamento = %s,
                forma_pagamento = %s,
                observacao = COALESCE(%s, observacao)
            WHERE id = %s
            """,
            (
                total_atualizado,
                status_novo,
                data_pagamento,
                dados.metodo_pagamento,
                dados.observacoes,
                pagamento_id
            )
        )
        if pagamento[0] != status_novo:
            cursor.execute(
                """
                INSERT INTO historico_status_pagamento
                    (pagamento_id, status_anterior, status_novo)
                VALUES (%s, %s, %s)
                """,
                (pagamento_id, pagamento[0], status_novo)
            )
        if (
            pagamento[4] is not None
            and status_novo == "Recebido"
            and Decimal(str(pagamento[3] or 0)) > 0
        ):
            enviar_extrato_diario_telegram(cursor, str(request.base_url))
        conexao.commit()
        return {
            "mensagem": "Recebimento registrado.",
            "pagamento_id": pagamento_id,
            "valor_recebido": float(valor_recebido),
            "total_recebido": float(total_atualizado),
            "saldo_pendente": float(max(Decimal(str(pagamento[1])) - total_atualizado, Decimal("0"))),
            "status": status_novo
        }
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.put("/pagamentos/{pagamento_id}")
def atualizar_pagamento(
    pagamento_id: int,
    dados: AtualizarPagamento,
    request: Request
):

    status_validos = ["Pendente", "Recebido", "Cancelado"]
    formas_validas = ["PIX", "Dinheiro", "Cartão", "Outro"]
    if dados.status not in status_validos:
        raise HTTPException(status_code=400, detail="Status de pagamento inválido.")
    if dados.forma_pagamento and dados.forma_pagamento not in formas_validas:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida.")

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT status, valor_total, taxa_reserva, agendamento_id,
                   mensalidade_id, valor_pago, competencia
            FROM pagamento
            WHERE id = %s
            FOR UPDATE
            """,
            (pagamento_id,)
        )
        pagamento = cursor.fetchone()
        if not pagamento:
            raise HTTPException(status_code=404, detail="Pagamento não encontrado.")

        status_anterior = pagamento[0]
        if dados.valor_pago is not None:
            if not math.isfinite(dados.valor_pago):
                raise HTTPException(status_code=400, detail="Valor recebido inválido.")
            if Decimal(str(dados.valor_pago)).quantize(
                Decimal("0.01")
            ) != Decimal(str(pagamento[5] or 0)).quantize(Decimal("0.01")):
                raise HTTPException(
                    status_code=409,
                    detail="Os valores recebidos não podem ser sobrescritos. Registre cada parcela como um novo recebimento."
                )
        valor_pago = (
            dados.valor_pago
            if dados.valor_pago is not None
            else float(pagamento[5])
        )
        if valor_pago < 0 or valor_pago > float(pagamento[1]):
            raise HTTPException(status_code=400, detail="Valor recebido fora dos limites do pagamento.")
        if dados.status == "Recebido":
            if valor_pago <= 0:
                raise HTTPException(status_code=400, detail="Informe o valor recebido.")
            if valor_pago < float(pagamento[1]):
                raise HTTPException(
                    status_code=409,
                    detail="O pagamento só pode ser marcado como recebido quando o saldo estiver zerado."
                )
            if pagamento[3] is not None:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(valor_pago), 0)
                    FROM pagamento
                    WHERE agendamento_id = %s
                      AND id <> %s
                      AND status = 'Recebido'
                    """,
                    (pagamento[3], pagamento_id)
                )
                total_ja_recebido = float(cursor.fetchone()[0] or 0)
                if total_ja_recebido + valor_pago > float(pagamento[1]):
                    raise HTTPException(
                        status_code=409,
                        detail="O valor recebido excede o total da reserva."
                    )
                if total_ja_recebido + valor_pago < float(pagamento[2]):
                    raise HTTPException(
                        status_code=409,
                        detail="O recebimento não cobre a taxa de reserva."
                    )
            elif pagamento[4] is not None and pagamento[6]:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(valor_pago), 0)
                    FROM pagamento
                    WHERE mensalidade_id = %s
                      AND competencia = %s
                      AND id <> %s
                      AND status = 'Recebido'
                    """,
                    (pagamento[4], pagamento[6], pagamento_id)
                )
                total_ja_recebido = float(cursor.fetchone()[0] or 0)
                if total_ja_recebido + valor_pago > float(pagamento[1]):
                    raise HTTPException(
                        status_code=409,
                        detail="O valor recebido excede o total da competência mensal."
                    )
            if dados.data_pagamento is None and status_anterior != "Recebido":
                data_pagamento = date.today()
            elif dados.data_pagamento:
                data_pagamento = datetime.strptime(
                    dados.data_pagamento,
                    "%Y-%m-%d"
                ).date()
                if data_pagamento.isoformat() != dados.data_pagamento:
                    raise ValueError
            else:
                data_pagamento = None
            if dados.forma_pagamento is None and status_anterior != "Recebido":
                raise HTTPException(status_code=400, detail="Informe a forma de pagamento.")
        else:
            if dados.data_pagamento:
                data_pagamento = datetime.strptime(
                    dados.data_pagamento,
                    "%Y-%m-%d"
                ).date()
                if data_pagamento.isoformat() != dados.data_pagamento:
                    raise ValueError
            else:
                data_pagamento = None

        cursor.execute(
            """
            UPDATE pagamento
            SET status = %s,
                valor_pago = %s,
                data_pagamento = COALESCE(%s, data_pagamento),
                forma_pagamento = COALESCE(%s, forma_pagamento),
                observacao = COALESCE(%s, observacao)
            WHERE id = %s
            """,
            (
                dados.status,
                valor_pago,
                data_pagamento,
                dados.forma_pagamento,
                dados.observacao,
                pagamento_id
            )
        )
        if status_anterior != dados.status:
            cursor.execute(
                """
                INSERT INTO historico_status_pagamento
                    (pagamento_id, status_anterior, status_novo)
                VALUES (%s, %s, %s)
                """,
                (pagamento_id, status_anterior, dados.status)
            )
        taxa_ja_recebida = (
            status_anterior == "Recebido"
            and float(pagamento[5] or 0) >= float(pagamento[2] or 0)
        )
        taxa_agora_recebida = (
            pagamento[3] is not None
            and dados.status == "Recebido"
            and float(pagamento[2] or 0) > 0
            and valor_pago >= float(pagamento[2] or 0)
        )
        pagamento_reserva_alterado = (
            pagamento[3] is not None
            and status_anterior != dados.status
        )
        if (
            pagamento_reserva_alterado
            or (taxa_agora_recebida and not taxa_ja_recebida)
        ):
            cursor.execute(
                "SELECT data FROM agendamento WHERE id = %s",
                (pagamento[3],)
            )
            reserva = cursor.fetchone()
            if reserva:
                enviar_extrato_diario_telegram(
                    cursor,
                    str(request.base_url)
                )
        conexao.commit()
        return {"mensagem": "Pagamento atualizado com sucesso.", "status": dados.status}
    except HTTPException:
        conexao.rollback()
        raise
    except ValueError:
        conexao.rollback()
        raise HTTPException(status_code=400, detail="Data do pagamento inválida.")
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.get("/pagamentos/{pagamento_id}/recebimentos")
def historico_recebimentos(pagamento_id: int):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, pagamento_id, valor_recebido, data_hora_recebimento,
                   usuario_recebedor_id, nome_usuario, metodo_pagamento,
                   observacoes
            FROM pagamento_recebimento
            WHERE pagamento_id = %s
            ORDER BY data_hora_recebimento, id
            """,
            (pagamento_id,)
        )
        return [linha_para_dict(cursor, linha) for linha in cursor.fetchall()]
    finally:
        cursor.close()
        conexao.close()


@app.get("/pagamentos/{pagamento_id}/historico")
def historico_pagamento(pagamento_id: int):

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, pagamento_id, status_anterior, status_novo, alterado_em
            FROM historico_status_pagamento
            WHERE pagamento_id = %s
            ORDER BY alterado_em, id
            """,
            (pagamento_id,)
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


# =========================================================
# CLIENTES
# =========================================================

@app.get("/clientes")
def listar_clientes(quadra_id: Optional[int] = None):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT
                c.id,
                c.nome,
                c.contato,
                c.garantia_reserva,
                c.motivo_garantia,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM mensalidade m
                    WHERE m.cliente_id = c.id
                      AND (%s IS NULL OR m.quadra_id = %s)
                      AND m.status = 'Ativa'
                      AND m.data_inicio <= CURDATE()
                      AND (
                          m.data_encerramento IS NULL
                          OR m.data_encerramento >= CURDATE()
                      )
                ) THEN 1 ELSE 0 END AS mensalista,

                COUNT(a.id) AS total_agendamentos,

                COALESCE(
                    SUM(
                        CASE
                            WHEN a.status = 'Confirmado'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_confirmados

            FROM cliente c

            LEFT JOIN agendamento a
                ON a.cliente_id = c.id
               AND (%s IS NULL OR a.quadra_id = %s)

            GROUP BY
                c.id,
                c.nome,
                c.contato,
                c.garantia_reserva,
                c.motivo_garantia

            HAVING (
                %s IS NULL
                OR COUNT(a.id) > 0
                OR EXISTS (
                    SELECT 1 FROM mensalidade m
                    WHERE m.cliente_id = c.id
                      AND m.quadra_id = %s
                )
            )
            ORDER BY
                c.nome
            """,
            (
                quadra_id,
                quadra_id,
                quadra_id,
                quadra_id,
                quadra_id,
                quadra_id
            )
        )

        linhas = cursor.fetchall()

        return [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in linhas
        ]

    finally:

        cursor.close()
        conexao.close()


@app.post("/clientes")
def criar_cliente(
    dados: NovoCliente
):

    nome = normalizar_nome_cliente(dados.nome)
    contato = dados.contato.strip()

    if not nome:

        raise HTTPException(
            status_code=400,
            detail="Nome do cliente é obrigatório."
        )

    if not contato:

        raise HTTPException(
            status_code=400,
            detail="Contato do cliente é obrigatório."
        )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cliente_id, novo = obter_ou_criar_cliente(
            cursor,
            nome,
            contato
        )

        conexao.commit()

        return {
            "mensagem":
                "Cliente criado com sucesso."
                if novo
                else "Cliente já cadastrado.",

            "id":
                cliente_id,

            "novo":
                novo
        }

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.put("/clientes/{cliente_id}")
def atualizar_cliente(
    cliente_id: int,
    dados: AtualizarCliente
):

    garantias_validas = [
        "Dispensado",
        "Obrigatório"
    ]

    if (
        dados.garantia_reserva is not None
        and dados.garantia_reserva
        not in garantias_validas
    ):

        raise HTTPException(
            status_code=400,
            detail="Garantia de reserva inválida."
        )

    if dados.contato is not None:
        contato = dados.contato.strip()
        if not contato or len(contato) > 20:
            raise HTTPException(
                status_code=400,
                detail="Informe um contato válido com até 20 caracteres."
            )

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            """
            SELECT id
            FROM cliente
            WHERE id = %s
            """,
            (cliente_id,)
        )

        if not cursor.fetchone():

            raise HTTPException(
                status_code=404,
                detail="Cliente não encontrado."
            )

        campos = []
        valores = []

        dados_dict = dados.model_dump(
            exclude_unset=True
        )
        if dados.nome is not None:
            dados_dict["nome"] = normalizar_nome_cliente(dados.nome)
        if dados.contato is not None:
            dados_dict["contato"] = dados.contato.strip()

        for campo, valor in dados_dict.items():

            campos.append(
                f"{campo} = %s"
            )

            valores.append(valor)

        if not campos:

            return {
                "mensagem":
                    "Nenhuma alteração enviada."
            }

        valores.append(
            cliente_id
        )

        sql = f"""
            UPDATE cliente
            SET {", ".join(campos)}
            WHERE id = %s
        """

        cursor.execute(
            sql,
            valores
        )

        conexao.commit()

        return {
            "mensagem":
                "Cliente atualizado com sucesso."
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.get("/clientes/{cliente_id}")
def obter_cliente(
    cliente_id: int,
    quadra_id: Optional[int] = None
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        # -------------------------------------------------
        # DADOS DO CLIENTE
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                nome,
                contato,
                garantia_reserva,
                motivo_garantia
            FROM cliente
            WHERE id = %s
            """,
            (cliente_id,)
        )

        cliente = cursor.fetchone()

        if not cliente:

            raise HTTPException(
                status_code=404,
                detail="Cliente não encontrado."
            )

        dados_cliente = linha_para_dict(
            cursor,
            cliente
        )

        # -------------------------------------------------
        # AGENDAMENTOS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                a.id,
                q.nome AS quadra,
                a.data,
                a.horario,
                a.valor_hora,
                a.taxa_reserva,
                a.valor_restante,
                a.status
            FROM agendamento a

            INNER JOIN quadra q
                ON q.id = a.quadra_id

            WHERE a.cliente_id = %s
              AND (%s IS NULL OR a.quadra_id = %s)

            ORDER BY
                a.data DESC,
                a.horario DESC
            """,
            (cliente_id, quadra_id, quadra_id)
        )

        agendamentos = [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in cursor.fetchall()
        ]

        # -------------------------------------------------
        # MENSALIDADES
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                m.id,
                q.nome AS quadra,
                m.dia_semana,
                m.horario,
                m.valor_mensal,
                m.data_inicio,
                m.data_encerramento,
                m.status
            FROM mensalidade m

            INNER JOIN quadra q
                ON q.id = m.quadra_id

            WHERE m.cliente_id = %s
              AND (%s IS NULL OR m.quadra_id = %s)

            ORDER BY
                m.data_inicio DESC
            """,
            (cliente_id, quadra_id, quadra_id)
        )

        mensalidades = [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in cursor.fetchall()
        ]

        return {
            "cliente":
                dados_cliente,

            "agendamentos":
                agendamentos,

            "mensalidades":
                mensalidades
        }

    finally:

        cursor.close()
        conexao.close()


# =========================================================
# CONFIGURAÇÕES
# =========================================================

@app.get("/configuracoes")
def listar_configuracoes():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:

        chaves_publicas = sorted(CONFIGURACOES_PUBLICAS)
        placeholders = ", ".join(["%s"] * len(chaves_publicas))
        cursor.execute(
            f"""
            SELECT id, chave, valor, descricao, tipo, editavel
            FROM configuracao
            WHERE chave IN ({placeholders})
            ORDER BY id
            """,
            chaves_publicas
        )

        linhas = cursor.fetchall()

        return [
            linha_para_dict(
                cursor,
                linha
            )
            for linha in linhas
        ]

    finally:

        cursor.close()
        conexao.close()


@app.get("/admin/configuracoes")
def listar_configuracoes_admin():

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            """
            SELECT id, chave, valor, descricao, tipo, editavel
            FROM configuracao
            ORDER BY id
            """
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


@app.put("/configuracoes/{chave}")
def atualizar_configuracao(
    chave: str,
    dados: AtualizarConfiguracao
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        valor_configurado = dados.valor.strip()
        if chave.startswith(("taxa_reserva_", "mensalidade_")):
            raise HTTPException(
                status_code=400,
                detail="Valores de quadra e taxas devem ser alterados no cadastro da quadra."
            )
        if chave == "limite_fila":
            try:
                limite_fila = int(valor_configurado)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="O limite da fila deve ser um número inteiro."
                )
            if limite_fila < 0:
                raise HTTPException(
                    status_code=400,
                    detail="O limite da fila não pode ser negativo."
                )
            valor_configurado = str(limite_fila)
        elif chave in {
            "horario_abertura_semana",
            "horario_fechamento_semana",
            "horario_abertura_domingo",
            "horario_fechamento_domingo"
        }:
            encerramento = chave.startswith("horario_fechamento")
            horario_meia_noite = encerramento and valor_configurado == "24:00"
            try:
                parsed_time = datetime.strptime(valor_configurado, "%H:%M")
                horario_valido = (
                    parsed_time.strftime("%H:%M") == valor_configurado
                )
            except ValueError:
                horario_valido = False
            if not horario_valido and not horario_meia_noite:
                raise HTTPException(
                    status_code=400,
                    detail="Informe o horário no formato HH:MM."
                )
        elif chave == "permitir_fila":
            if valor_configurado.lower() not in {"0", "1", "true", "false", "sim", "não", "nao"}:
                raise HTTPException(
                    status_code=400,
                    detail="Valor inválido para a configuração de fila."
                )
            valor_configurado = (
                "1"
                if valor_configurado.lower() in {"1", "true", "sim"}
                else "0"
            )

        cursor.execute(
            """
            SELECT
                id,
                editavel
            FROM configuracao
            WHERE chave = %s
            """,
            (chave,)
        )

        configuracao = cursor.fetchone()

        if not configuracao:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Configuração não encontrada."
                )
            )

        if not configuracao[1]:

            raise HTTPException(
                status_code=403,
                detail=(
                    "Esta configuração "
                    "não pode ser editada."
                )
            )

        cursor.execute(
            """
            UPDATE configuracao
            SET valor = %s
            WHERE chave = %s
            """,
            (
                valor_configurado,
                chave
            )
        )

        conexao.commit()

        return {
            "mensagem":
                "Configuração atualizada com sucesso."
        }

    except HTTPException:

        conexao.rollback()
        raise

    except Exception as erro:

        conexao.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )

    finally:

        cursor.close()
        conexao.close()


@app.get("/relatorios")
def obter_relatorios(
    inicio: str,
    fim: str,
    quadra_id: Optional[int] = None,
    tipo_quad: Optional[str] = None,
    inativo_dias: int = 30
):

    try:
        data_inicio = datetime.strptime(inicio, "%Y-%m-%d").date()
        data_fim = datetime.strptime(fim, "%Y-%m-%d").date()
        if data_inicio.isoformat() != inicio or data_fim.isoformat() != fim:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Período inválido.")

    if data_fim < data_inicio:
        raise HTTPException(status_code=400, detail="A data final deve ser posterior à inicial.")
    if (data_fim - data_inicio).days > 366:
        raise HTTPException(status_code=400, detail="O período máximo do relatório é de 366 dias.")
    if inativo_dias < 1 or inativo_dias > 365:
        raise HTTPException(status_code=400, detail="O período de inatividade deve estar entre 1 e 365 dias.")

    filtros = ["a.data BETWEEN %s AND %s"]
    parametros = [data_inicio, data_fim]
    if quadra_id is not None:
        filtros.append("a.quadra_id = %s")
        parametros.append(quadra_id)
    if tipo_quad:
        filtros.append("q.tipo = %s")
        parametros.append(tipo_quad)
    where_reservas = " AND ".join(filtros)

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(a.status = 'Confirmado') AS confirmadas,
                SUM(a.status = 'Pendente') AS pendentes,
                SUM(a.status = 'Cancelado') AS canceladas,
                SUM(a.status = 'Não atendido') AS nao_atendidas,
                SUM(a.status NOT IN (
                    'Confirmado', 'Pendente', 'Cancelado', 'Não atendido'
                )) AS outros,
                COUNT(DISTINCT a.cliente_id) AS clientes
            FROM agendamento a
            INNER JOIN quadra q ON q.id = a.quadra_id
            WHERE {where_reservas}
            """,
            parametros
        )
        row = cursor.fetchone()
        resumo = {
            "reservas": int(row[0] or 0),
            "confirmadas": int(row[1] or 0),
            "pendentes": int(row[2] or 0),
            "canceladas": int(row[3] or 0),
            "nao_atendidas": int(row[4] or 0),
            "outros": int(row[5] or 0),
            "clientes": int(row[6] or 0)
        }

        filtros_mensalidades = [
            "m.data_inicio <= %s",
            "(m.data_encerramento IS NULL OR m.data_encerramento >= %s)"
        ]
        parametros_mensalidades = [data_fim, data_inicio]
        if quadra_id is not None:
            filtros_mensalidades.append("m.quadra_id = %s")
            parametros_mensalidades.append(quadra_id)
        if tipo_quad:
            filtros_mensalidades.append("q.tipo = %s")
            parametros_mensalidades.append(tipo_quad)
        cursor.execute(
            f"""
            SELECT m.status, m.dia_semana, m.data_inicio, m.data_encerramento
            FROM mensalidade m
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE {" AND ".join(filtros_mensalidades)}
            """,
            parametros_mensalidades
        )
        mensalidades_no_periodo = cursor.fetchall()
        status_mensais = {
            "Pendente": 0,
            "Ativa": 0,
            "Encerrada": 0,
            "outros": 0
        }
        ocorrencias_mensais = {
            "Pendente": 0,
            "Ativa": 0,
            "Encerrada": 0,
            "outros": 0
        }
        for status, dia_semana, inicio_mensalidade, fim_mensalidade in mensalidades_no_periodo:
            chave_status = status if status in status_mensais else "outros"
            status_mensais[chave_status] += 1
            inicio_ocorrencia = max(data_inicio, inicio_mensalidade)
            fim_ocorrencia = min(data_fim, fim_mensalidade or data_fim)
            for offset in range((fim_ocorrencia - inicio_ocorrencia).days + 1):
                dia = inicio_ocorrencia + timedelta(days=offset)
                if (dia.weekday() + 1) % 7 == int(dia_semana):
                    ocorrencias_mensais[chave_status] += 1

        modalidades = {
            "avulsas": {
                "total": resumo["reservas"],
                "pendente": resumo["pendentes"],
                "confirmado": resumo["confirmadas"],
                "cancelado": resumo["canceladas"],
                "nao_atendido": resumo["nao_atendidas"],
                "outros": resumo["outros"]
            },
            "mensais": {
                "total": len(mensalidades_no_periodo),
                "status": status_mensais,
                "ocorrencias": ocorrencias_mensais
            }
        }

        dias_periodo = (data_fim - data_inicio).days + 1
        if data_inicio.toordinal() > dias_periodo:
            fim_periodo_anterior = data_inicio - timedelta(days=1)
            inicio_periodo_anterior = fim_periodo_anterior - timedelta(
                days=dias_periodo - 1
            )
            parametros_periodo_anterior = [
                inicio_periodo_anterior,
                fim_periodo_anterior
            ] + parametros[2:]
            cursor.execute(
                f"""
                SELECT
                    COUNT(*),
                    SUM(a.status = 'Confirmado')
                FROM agendamento a
                INNER JOIN quadra q ON q.id = a.quadra_id
                WHERE {where_reservas}
                """,
                parametros_periodo_anterior
            )
            row_anterior = cursor.fetchone()
        else:
            row_anterior = (0, 0)
        comparacao_periodos = {
            "atual": {
                "reservas": resumo["reservas"],
                "confirmadas": resumo["confirmadas"]
            },
            "anterior": {
                "reservas": int(row_anterior[0] or 0),
                "confirmadas": int(row_anterior[1] or 0)
            }
        }

        cursor.execute(
            f"""
            SELECT DATE_FORMAT(a.data, '%Y-%m-%d') AS dia,
                   COUNT(*) AS total,
                   SUM(a.status = 'Confirmado') AS confirmadas,
                   SUM(a.status = 'Pendente') AS pendentes,
                   SUM(a.status = 'Cancelado') AS canceladas,
                   SUM(a.status = 'Não atendido') AS nao_atendidas
            FROM agendamento a
            INNER JOIN quadra q ON q.id = a.quadra_id
            WHERE {where_reservas}
            GROUP BY a.data
            ORDER BY a.data
            """,
            parametros
        )
        reservas_periodo = [
            {
                "dia": linha[0],
                "total": int(linha[1] or 0),
                "confirmadas": int(linha[2] or 0),
                "pendentes": int(linha[3] or 0),
                "canceladas": int(linha[4] or 0),
                "nao_atendidas": int(linha[5] or 0)
            }
            for linha in cursor.fetchall()
        ]
        reservas_periodo = completar_serie_diaria_reservas(
            data_inicio,
            data_fim,
            reservas_periodo
        )

        cursor.execute(
            """
            SELECT q.id, q.nome, q.tipo, COUNT(a.id) AS confirmadas
            FROM quadra q
            LEFT JOIN agendamento a
                ON a.quadra_id = q.id
               AND a.data BETWEEN %s AND %s
               AND a.status = 'Confirmado'
            WHERE q.ativo = 1
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            GROUP BY q.id, q.nome, q.tipo
            ORDER BY q.nome
            """,
            (
                data_inicio,
                data_fim,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        uso_quadras = [
            {
                "quadra_id": linha[0],
                "quadra": linha[1],
                "tipo": linha[2],
                "confirmadas": int(linha[3] or 0)
            }
            for linha in cursor.fetchall()
        ]

        dias = (data_fim - data_inicio).days + 1
        domingo_abertura = obter_configuracao(
            cursor,
            "horario_abertura_domingo"
        )
        domingo_fechamento = obter_configuracao(
            cursor,
            "horario_fechamento_domingo"
        )
        semana_abertura = obter_configuracao(
            cursor,
            "horario_abertura_semana"
        )
        semana_fechamento = obter_configuracao(
            cursor,
            "horario_fechamento_semana"
        )

        def minutos_config(valor, padrao):
            try:
                partes = str(valor).split(":")
                return int(partes[0]) * 60 + int(partes[1])
            except (ValueError, TypeError, IndexError):
                return padrao

        minutos_abertos = 0
        for offset in range(dias):
            dia = data_inicio + timedelta(days=offset)
            if dia.weekday() == 6:
                abertura = minutos_config(domingo_abertura, 7 * 60)
                fechamento = minutos_config(domingo_fechamento, 17 * 60)
            else:
                abertura = minutos_config(semana_abertura, 8 * 60)
                fechamento = minutos_config(semana_fechamento, 24 * 60)
                if fechamento == 0:
                    fechamento = 24 * 60
            minutos_abertos += max(0, fechamento - abertura)

        filtro_quadras = ["ativo = 1"]
        parametros_quadras = []
        if quadra_id is not None:
            filtro_quadras.append("id = %s")
            parametros_quadras.append(quadra_id)
        if tipo_quad:
            filtro_quadras.append("tipo = %s")
            parametros_quadras.append(tipo_quad)
        cursor.execute(
            "SELECT COUNT(*) FROM quadra WHERE " + " AND ".join(filtro_quadras),
            parametros_quadras
        )
        quantidade_quadras = int(cursor.fetchone()[0] or 0)
        capacidade_horas = (
            minutos_abertos * quantidade_quadras / 60
        )

        cursor.execute(
            f"""
            SELECT COALESCE(SUM(a.valor_hora), 0),
                   COALESCE(SUM(a.taxa_reserva), 0)
            FROM agendamento a
            INNER JOIN quadra q ON q.id = a.quadra_id
            WHERE {where_reservas}
              AND a.status = 'Confirmado'
            """,
            parametros
        )
        faturamento_reservas, taxas_reservas = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE WHEN p.status <> 'Cancelado'
                         THEN p.valor_pago ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN p.status <> 'Cancelado'
                              AND p.tipo = 'Reserva'
                         THEN LEAST(p.valor_pago, p.taxa_reserva)
                         ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN p.status <> 'Cancelado'
                         THEN GREATEST(p.valor_total - p.valor_pago, 0)
                         ELSE 0 END
                ), 0),
                SUM(
                    p.status <> 'Cancelado'
                    AND p.valor_pago < p.valor_total
                )
            FROM pagamento p
            LEFT JOIN agendamento a ON a.id = p.agendamento_id
            LEFT JOIN mensalidade m ON m.id = p.mensalidade_id
            LEFT JOIN quadra q ON q.id = COALESCE(a.quadra_id, m.quadra_id)
            WHERE COALESCE(p.data_pagamento, DATE(p.criado_em))
                  BETWEEN %s AND %s
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            """,
            (
                data_inicio,
                data_fim,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        recebidos = cursor.fetchone()
        faturamento_pagamentos = float(recebidos[0] or 0)
        taxas_pagamentos = float(recebidos[1] or 0)

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE WHEN p.status = 'Pago' THEN p.valor ELSE 0 END
                ), 0),
                SUM(p.status = 'Pago'),
                SUM(p.status = 'Pendente'),
                COALESCE(SUM(
                    CASE WHEN p.status = 'Pendente' THEN p.valor ELSE 0 END
                ), 0)
            FROM pagamento_mensalidade p
            INNER JOIN mensalidade m ON m.id = p.mensalidade_id
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE COALESCE(p.data_pagamento, DATE(p.criado_em))
                  BETWEEN %s AND %s
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            """,
            (
                data_inicio,
                data_fim,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        legado_valores = cursor.fetchone()
        faturamento_pagamentos += float(legado_valores[0] or 0)
        pagamentos_pendentes = int(recebidos[3] or 0) + int(legado_valores[2] or 0)
        valor_pendente = float(recebidos[2] or 0) + float(legado_valores[3] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM mensalidade m
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE m.status = 'Ativa'
              AND m.data_inicio <= %s
              AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            """,
            (
                data_fim,
                data_inicio,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        mensalistas_ativos = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            f"""
            SELECT DATE_FORMAT(COALESCE(p.data_pagamento, DATE(p.criado_em)), '%Y-%m-%d'),
                   COALESCE(SUM(p.valor_pago), 0),
                   COALESCE(SUM(
                       CASE WHEN p.tipo = 'Reserva'
                            THEN LEAST(p.valor_pago, p.taxa_reserva)
                            ELSE 0 END
                   ), 0)
            FROM pagamento p
            LEFT JOIN agendamento a ON a.id = p.agendamento_id
            LEFT JOIN mensalidade m ON m.id = p.mensalidade_id
            LEFT JOIN quadra q ON q.id = COALESCE(a.quadra_id, m.quadra_id)
            WHERE p.status <> 'Cancelado'
              AND p.valor_pago > 0
              AND COALESCE(p.data_pagamento, DATE(p.criado_em))
                  BETWEEN %s AND %s
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            GROUP BY 1
            ORDER BY 1
            """,
            (
                data_inicio,
                data_fim,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        pagamentos_periodo = [
            {
                "dia": linha[0],
                "recebido": float(linha[1] or 0),
                "taxas": float(linha[2] or 0)
            }
            for linha in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT DATE_FORMAT(
                       COALESCE(p.data_pagamento, DATE(p.criado_em)),
                       '%Y-%m-%d'
                   ),
                   COALESCE(SUM(p.valor), 0)
            FROM pagamento_mensalidade p
            INNER JOIN mensalidade m ON m.id = p.mensalidade_id
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE p.status = 'Pago'
              AND COALESCE(p.data_pagamento, DATE(p.criado_em))
                  BETWEEN %s AND %s
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM pagamento operacional
                  WHERE operacional.mensalidade_id = p.mensalidade_id
                    AND operacional.competencia =
                        DATE_FORMAT(p.competencia, '%Y-%m')
                    AND operacional.status <> 'Cancelado'
              )
            GROUP BY 1
            ORDER BY 1
            """,
            (
                data_inicio,
                data_fim,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        valores_legados_por_dia = {
            linha[0]: float(linha[1] or 0)
            for linha in cursor.fetchall()
        }
        pagamentos_por_dia = {
            item["dia"]: item for item in pagamentos_periodo
        }
        for dia, valor in valores_legados_por_dia.items():
            pagamentos_por_dia.setdefault(
                dia,
                {"dia": dia, "recebido": 0.0, "taxas": 0.0}
            )
            pagamentos_por_dia[dia]["recebido"] += valor
        pagamentos_periodo = sorted(
            pagamentos_por_dia.values(),
            key=lambda item: item["dia"]
        )

        cursor.execute(
            """
            SELECT m.quadra_id, m.dia_semana, m.data_inicio,
                   m.data_encerramento
            FROM mensalidade m
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE m.status = 'Ativa'
              AND m.data_inicio <= %s
              AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
              AND (%s IS NULL OR q.id = %s)
              AND (%s IS NULL OR q.tipo = %s)
            """,
            (
                data_fim,
                data_inicio,
                quadra_id,
                quadra_id,
                tipo_quad,
                tipo_quad
            )
        )
        mensalidades_periodo = cursor.fetchall()
        horas_mensalistas_por_quadra = {}
        for quadra_mensalista, dia_semana, inicio_mensalidade, fim_mensalidade in mensalidades_periodo:
            inicio_ocorrencia = max(data_inicio, inicio_mensalidade)
            fim_ocorrencia = min(data_fim, fim_mensalidade or data_fim)
            ocorrencias = 0
            for offset in range((fim_ocorrencia - inicio_ocorrencia).days + 1):
                dia = inicio_ocorrencia + timedelta(days=offset)
                if (dia.weekday() + 1) % 7 == int(dia_semana):
                    ocorrencias += 1
            horas_mensalistas_por_quadra[quadra_mensalista] = (
                horas_mensalistas_por_quadra.get(quadra_mensalista, 0)
                + ocorrencias
            )

        for quadra_uso in uso_quadras:
            quadra_uso["mensalistas"] = horas_mensalistas_por_quadra.get(
                quadra_uso["quadra_id"],
                0
            )
            quadra_uso["horas_ocupadas"] = (
                quadra_uso["confirmadas"] + quadra_uso["mensalistas"]
            )

        horas_confirmadas = (
            resumo["confirmadas"]
            + sum(horas_mensalistas_por_quadra.values())
        )
        resumo.update({
            "utilizacao_percentual": round(
                horas_confirmadas / capacidade_horas * 100,
                2
            ) if capacidade_horas else 0,
            "horas_disponiveis": round(capacidade_horas, 2),
            "horas_confirmadas": horas_confirmadas,
            "faturamento_reservas": float(faturamento_reservas or 0),
            "faturamento_pagamentos": faturamento_pagamentos,
            "taxas_reservas": float(taxas_reservas or 0),
            "taxas_recebidas": taxas_pagamentos,
            "mensalistas_ativos": mensalistas_ativos,
            "pagamentos_pendentes": pagamentos_pendentes,
            "valor_pendente": valor_pendente
        })

        resultado = {
            "inicio": data_inicio.isoformat(),
            "fim": data_fim.isoformat(),
            "resumo": resumo,
            "modalidades": modalidades,
            "reservas_por_periodo": reservas_periodo,
            "utilizacao_quadras": uso_quadras,
            "pagamentos_por_periodo": pagamentos_periodo,
            "comparacao_periodos": comparacao_periodos
        }
        resultado.update(
            construir_dashboard_avancado(
                cursor,
                data_inicio,
                data_fim,
                quadra_id,
                tipo_quad,
                resumo,
                inativo_dias
            )
        )
        return resultado
    finally:
        cursor.close()
        conexao.close()


def calcular_indice_cancelamento(solicitacoes, cancelamentos):
    if not solicitacoes:
        return 0
    return round(float(cancelamentos) / float(solicitacoes) * 100, 2)


def calcular_media_solicitacoes(solicitacoes, ocorrencias):
    if not ocorrencias:
        return 0
    return round(float(solicitacoes) / float(ocorrencias), 2)


def completar_serie_diaria_reservas(data_inicio, data_fim, registros):
    registros_por_data = {
        str(item["dia"]): item
        for item in registros
    }
    serie = []
    for offset in range((data_fim - data_inicio).days + 1):
        dia = (data_inicio + timedelta(days=offset)).isoformat()
        serie.append(
            registros_por_data.get(
                dia,
                {
                    "dia": dia,
                    "total": 0,
                    "confirmadas": 0,
                    "pendentes": 0,
                    "canceladas": 0,
                    "nao_atendidas": 0
                }
            )
        )
    return serie


def construir_dashboard_avancado(
    cursor,
    data_inicio,
    data_fim,
    quadra_id,
    tipo_quad,
    resumo,
    inativo_dias
):
    filtros_quadras = ["1 = 1"]
    parametros_quadras = []
    if quadra_id is not None:
        filtros_quadras.append("q.id = %s")
        parametros_quadras.append(quadra_id)
    if tipo_quad:
        filtros_quadras.append("q.tipo = %s")
        parametros_quadras.append(tipo_quad)
    where_quadras = " AND ".join(filtros_quadras)

    nomes_dias = [
        "Segunda", "Terça", "Quarta", "Quinta",
        "Sexta", "Sábado", "Domingo"
    ]
    cursor.execute(
        f"""
        SELECT WEEKDAY(a.data),
               COUNT(*),
               SUM(a.status = 'Confirmado'),
               SUM(a.status = 'Pendente'),
               SUM(a.status = 'Cancelado'),
               SUM(a.status = 'Não atendido'),
               COALESCE(SUM(
                   CASE WHEN a.status = 'Confirmado'
                        THEN a.valor_hora + a.taxa_reserva ELSE 0 END
               ), 0)
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY WEEKDAY(a.data)
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    weekdays_rows = {
        int(row[0]): row[1:]
        for row in cursor.fetchall()
    }
    dias_por_semana = [0] * 7
    for offset in range((data_fim - data_inicio).days + 1):
        dias_por_semana[(data_inicio + timedelta(days=offset)).weekday()] += 1
    demanda_dia_semana = [
        {
            "dia": nomes_dias[index],
            "solicitacoes": int(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[0] or 0),
            "confirmadas": int(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[1] or 0),
            "pendentes": int(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[2] or 0),
            "canceladas": int(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[3] or 0),
            "nao_atendidas": int(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[4] or 0),
            "faturado": float(weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[5] or 0),
            "ocorrencias_periodo": dias_por_semana[index],
            "media_solicitacoes": calcular_media_solicitacoes(
                weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[0] or 0,
                dias_por_semana[index]
            ),
            "percentual_cancelamentos": calcular_indice_cancelamento(
                weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[0] or 0,
                weekdays_rows.get(index, (0, 0, 0, 0, 0, 0))[3] or 0
            )
        }
        for index in range(7)
    ]

    cursor.execute(
        f"""
        SELECT HOUR(a.horario),
               COUNT(*),
               SUM(a.status = 'Confirmado'),
               SUM(a.status = 'Pendente'),
               SUM(a.status = 'Cancelado'),
               SUM(a.status = 'Não atendido')
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY HOUR(a.horario)
        ORDER BY HOUR(a.horario)
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    demanda_horario = {
        f"{int(row[0]):02d}:00": {
            "solicitacoes": int(row[1] or 0),
            "confirmadas": int(row[2] or 0),
            "pendentes": int(row[3] or 0),
            "canceladas": int(row[4] or 0),
            "nao_atendidas": int(row[5] or 0)
        }
        for row in cursor.fetchall()
    }

    cursor.execute(
        f"""
        SELECT q.id, q.nome, q.tipo,
               COUNT(a.id),
               SUM(a.status = 'Confirmado'),
               SUM(a.status = 'Pendente'),
               SUM(a.status = 'Cancelado'),
               SUM(a.status = 'Não atendido'),
               COALESCE(SUM(
                   CASE WHEN a.status = 'Confirmado'
                        THEN a.valor_hora + a.taxa_reserva ELSE 0 END
               ), 0)
        FROM quadra q
        LEFT JOIN agendamento a
          ON a.quadra_id = q.id
         AND a.data BETWEEN %s AND %s
        WHERE {where_quadras}
        GROUP BY q.id, q.nome, q.tipo
        ORDER BY q.nome
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    demanda_quadras = [
        {
            "quadra_id": int(row[0]),
            "quadra": row[1],
            "tipo": row[2],
            "solicitacoes": int(row[3] or 0),
            "confirmadas": int(row[4] or 0),
            "pendentes": int(row[5] or 0),
            "canceladas": int(row[6] or 0),
            "nao_atendidas": int(row[7] or 0),
            "faturado": float(row[8] or 0),
            "percentual_cancelamentos": calcular_indice_cancelamento(
                row[3] or 0,
                row[6] or 0
            )
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        f"""
        SELECT q.id, q.nome, q.tipo, HOUR(a.horario), COUNT(*),
               SUM(a.status = 'Confirmado')
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY q.id, q.nome, q.tipo, HOUR(a.horario)
        ORDER BY q.nome, HOUR(a.horario)
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    heatmap_values = {}
    for court_id, court_name, court_type, slot, requests, confirmed in cursor.fetchall():
        hour = f"{int(slot):02d}:00"
        heatmap_values[(int(court_id), hour)] = int(requests or 0)

    cursor.execute(
        f"""
        SELECT q.id, q.nome, q.tipo, q.ativo
        FROM quadra q
        WHERE {where_quadras}
        ORDER BY q.nome
        """,
        parametros_quadras
    )
    court_rows = cursor.fetchall()
    courts = [
        {
            "quadra_id": int(row[0]),
            "quadra": row[1],
            "tipo": row[2]
        }
        for row in court_rows
    ]
    active_court_ids = {
        int(row[0])
        for row in court_rows
        if row[3]
    }

    cursor.execute(
        """
        SELECT chave, valor
        FROM configuracao
        WHERE chave IN (
            'horario_abertura_semana',
            'horario_fechamento_semana',
            'horario_abertura_domingo',
            'horario_fechamento_domingo'
        )
        """
    )
    hours_config = dict(cursor.fetchall())

    def minute_of_day(value, fallback):
        try:
            hours, minutes = map(int, str(value).split(":")[:2])
            return hours * 60 + minutes
        except (ValueError, TypeError, IndexError):
            return fallback

    def operating_slots(day):
        prefix = "domingo" if day.weekday() == 6 else "semana"
        opening = hours_config.get(f"horario_abertura_{prefix}", "07:00")
        closing = hours_config.get(f"horario_fechamento_{prefix}", "00:00")
        open_minutes = minute_of_day(
            opening,
            7 * 60 if prefix == "domingo" else 8 * 60
        )
        close_minutes = minute_of_day(
            closing,
            17 * 60 if prefix == "domingo" else 24 * 60
        )
        if close_minutes == 0:
            close_minutes = 24 * 60
        first_slot = ((open_minutes + 59) // 60) * 60
        last_slot = ((close_minutes - 60) // 60) * 60
        return max(0, (last_slot - first_slot) // 60 + 1)

    all_slots = set(demanda_horario)
    for offset in range((data_fim - data_inicio).days + 1):
        day = data_inicio + timedelta(days=offset)
        prefix = "domingo" if day.weekday() == 6 else "semana"
        opening = minute_of_day(
            hours_config.get(
                f"horario_abertura_{prefix}",
                "07:00" if prefix == "domingo" else "08:00"
            ),
            7 * 60 if prefix == "domingo" else 8 * 60
        )
        closing = minute_of_day(
            hours_config.get(
                f"horario_fechamento_{prefix}",
                "17:00" if prefix == "domingo" else "00:00"
            ),
            17 * 60 if prefix == "domingo" else 24 * 60
        )
        if closing == 0:
            closing = 24 * 60
        first_slot = ((opening + 59) // 60) * 60
        last_slot = ((closing - 60) // 60) * 60
        if last_slot >= first_slot:
            all_slots.update(
                f"{minute // 60:02d}:00"
                for minute in range(first_slot, last_slot + 1, 60)
            )

    for slot in sorted(all_slots):
        demanda_horario.setdefault(
            slot,
            {
                "solicitacoes": 0,
                "confirmadas": 0,
                "pendentes": 0,
                "canceladas": 0,
                "nao_atendidas": 0
            }
        )
    horarios_ordenados = sorted(demanda_horario)
    heatmap = [
        {
            "quadra_id": court["quadra_id"],
            "quadra": court["quadra"],
            "tipo": court["tipo"],
            "valores": [
                heatmap_values.get((court["quadra_id"], hour), 0)
                for hour in horarios_ordenados
            ]
        }
        for court in courts
    ]
    horarios_ranked = [
        {"horario": hour, **values}
        for hour, values in demanda_horario.items()
    ]
    horarios_com_solicitacoes = [
        item for item in horarios_ranked if item["solicitacoes"] > 0
    ]
    horarios_mais = sorted(
        horarios_com_solicitacoes,
        key=lambda item: (-item["solicitacoes"], item["horario"])
    )[:10]
    horarios_menos = sorted(
        horarios_com_solicitacoes,
        key=lambda item: (item["solicitacoes"], item["horario"])
    )[:10]

    period_days = (data_fim - data_inicio).days + 1
    cursor.execute(
        f"""
        SELECT q.id, a.data, a.status
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND a.status = 'Confirmado'
          AND {where_quadras}
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    confirmed_per_court = {}
    confirmed_by_court_day = {}
    confirmed_by_court_month = {}
    for court_id, day, status in cursor.fetchall():
        court_id = int(court_id)
        confirmed_per_court[court_id] = confirmed_per_court.get(court_id, 0) + 1
        month_key = day.strftime("%Y-%m")
        court_day_key = (court_id, day)
        court_month_key = (court_id, month_key)
        confirmed_by_court_day[court_day_key] = (
            confirmed_by_court_day.get(court_day_key, 0) + 1
        )
        confirmed_by_court_month[court_month_key] = (
            confirmed_by_court_month.get(court_month_key, 0) + 1
        )

    cursor.execute(
        f"""
        SELECT m.quadra_id, m.dia_semana, m.data_inicio,
               m.data_encerramento, m.status
        FROM mensalidade m
        INNER JOIN quadra q ON q.id = m.quadra_id
        WHERE m.data_inicio <= %s
          AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
          AND {where_quadras}
        """,
        [data_fim, data_inicio] + parametros_quadras
    )
    recurring_occupancy = {}
    recurring_by_court_day = {}
    recurring_by_court_month = {}
    for court_id, weekday, member_start, member_end, member_status in cursor.fetchall():
        start = max(data_inicio, member_start)
        end = min(data_fim, member_end or data_fim)
        if member_status != "Ativa" and member_end is None:
            continue
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if (day.weekday() + 1) % 7 != int(weekday):
                continue
            court_id = int(court_id)
            recurring_occupancy[court_id] = recurring_occupancy.get(court_id, 0) + 1
            court_day_key = (court_id, day)
            recurring_by_court_day[court_day_key] = (
                recurring_by_court_day.get(court_day_key, 0) + 1
            )
            key = day.strftime("%Y-%m")
            court_month_key = (court_id, key)
            recurring_by_court_month[court_month_key] = (
                recurring_by_court_month.get(court_month_key, 0) + 1
            )

    days_total_open_hours = sum(
        operating_slots(data_inicio + timedelta(days=offset))
        for offset in range(period_days)
    )
    total_available = days_total_open_hours * len(active_court_ids)
    total_occupied = sum(
        confirmed_per_court.get(court_id, 0)
        + recurring_occupancy.get(court_id, 0)
        for court_id in active_court_ids
    )
    utilization_by_court = []
    for court in courts:
        if court["quadra_id"] not in active_court_ids:
            continue
        court_id = court["quadra_id"]
        occupied = confirmed_per_court.get(court_id, 0) + recurring_occupancy.get(court_id, 0)
        available = days_total_open_hours
        utilization_by_court.append({
            **court,
            "horas_ocupadas": occupied,
            "horas_disponiveis": available,
            "utilizacao_percentual": round(occupied / available * 100, 2) if available else 0
        })
    utilization_by_day = []
    for offset in range(period_days):
        day = data_inicio + timedelta(days=offset)
        available = operating_slots(day) * len(active_court_ids)
        occupied = sum(
            confirmed_by_court_day.get((court_id, day), 0)
            + recurring_by_court_day.get((court_id, day), 0)
            for court_id in active_court_ids
        )
        utilization_by_day.append({
            "dia": day.isoformat(),
            "horas_ocupadas": occupied,
            "horas_disponiveis": available,
            "utilizacao_percentual": round(occupied / available * 100, 2) if available else 0
        })
    month_keys = []
    cursor_month = date(data_inicio.year, data_inicio.month, 1)
    last_month = date(data_fim.year, data_fim.month, 1)
    while cursor_month <= last_month:
        month_keys.append(cursor_month.strftime("%Y-%m"))
        cursor_month = date(
            cursor_month.year + (cursor_month.month == 12),
            1 if cursor_month.month == 12 else cursor_month.month + 1,
            1
        )
    utilization_by_month = []
    for month_key in month_keys:
        month_start = date.fromisoformat(month_key + "-01")
        _, month_end_day = calendar.monthrange(month_start.year, month_start.month)
        month_end = date(month_start.year, month_start.month, month_end_day)
        period_start = max(data_inicio, month_start)
        period_end = min(data_fim, month_end)
        month_open_hours = sum(
            operating_slots(period_start + timedelta(days=offset))
            for offset in range((period_end - period_start).days + 1)
        ) * len(active_court_ids)
        occupied = sum(
            confirmed_by_court_month.get((court_id, month_key), 0)
            + recurring_by_court_month.get((court_id, month_key), 0)
            for court_id in active_court_ids
        )
        utilization_by_month.append({
            "mes": month_key,
            "horas_ocupadas": occupied,
            "horas_disponiveis": month_open_hours,
            "utilizacao_percentual": round(occupied / month_open_hours * 100, 2) if month_open_hours else 0
        })

    cursor.execute(
        f"""
        SELECT a.cliente_id, c.nome, COUNT(*),
               COALESCE(SUM(a.valor_hora + a.taxa_reserva), 0), MAX(a.data)
        FROM agendamento a
        INNER JOIN cliente c ON c.id = a.cliente_id
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND a.status = 'Confirmado'
          AND {where_quadras}
        GROUP BY a.cliente_id, c.nome
        ORDER BY COUNT(*) DESC, SUM(a.valor_hora) DESC, c.nome
        LIMIT 10
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    top_clients = [
        {
            "cliente_id": int(row[0]),
            "cliente": row[1],
            "jogos": int(row[2] or 0),
            "valor_gerado": float(row[3] or 0),
            "ultimo_jogo": row[4].isoformat() if row[4] else None
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        f"""
        SELECT a.cliente_id, c.nome, q.nome,
               COUNT(*), COALESCE(SUM(a.valor_hora + a.taxa_reserva), 0)
        FROM agendamento a
        INNER JOIN cliente c ON c.id = a.cliente_id
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND a.status = 'Confirmado'
          AND {where_quadras}
        GROUP BY a.cliente_id, c.nome, q.id, q.nome
        ORDER BY a.cliente_id
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    monthly_client_acc = {}
    for client_id, client_name, court_name, games_count, generated in cursor.fetchall():
        item = monthly_client_acc.setdefault(
            int(client_id),
            {
                "cliente_id": int(client_id),
                "cliente": client_name,
                "jogos": 0,
                "valor_gerado": 0.0,
                "quadras": {}
            }
        )
        item["jogos"] += int(games_count or 0)
        item["valor_gerado"] += float(generated or 0)
        item["quadras"][court_name] = item["quadras"].get(court_name, 0) + int(games_count or 0)
    top_clients_month = sorted(
        (
            {
                **item,
                "quadra_mais_utilizada": sorted(
                    item["quadras"].items(),
                    key=lambda pair: (-pair[1], pair[0])
                )[0][0],
            }
            for item in monthly_client_acc.values()
        ),
        key=lambda item: (-item["jogos"], -item["valor_gerado"], item["cliente"])
    )[:10]
    for item in top_clients_month:
        del item["quadras"]

    cursor.execute(
        f"""
        SELECT m.id, m.cliente_id, c.nome, m.valor_mensal,
               m.dia_semana, m.horario, m.data_inicio,
               m.data_encerramento, m.status
        FROM mensalidade m
        INNER JOIN cliente c ON c.id = m.cliente_id
        INNER JOIN quadra q ON q.id = m.quadra_id
        WHERE m.data_inicio <= %s
          AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
          AND {where_quadras}
        """,
        [data_fim, data_inicio] + parametros_quadras
    )
    memberships = cursor.fetchall()
    members_top = []
    memberships_new = 0
    memberships_abandoned = 0
    active_at_start = 0
    active_at_end = 0
    membership_history = {}
    for row in memberships:
        membership_id, client_id, name, monthly_value, weekday, slot, member_start, member_end, member_status = row
        if data_inicio <= member_start <= data_fim:
            memberships_new += 1
        active_on_start = (
            member_start <= data_inicio
            and (member_end is None or member_end >= data_inicio)
            and (member_status == "Ativa" or member_end is not None)
        )
        active_on_end = (
            member_start <= data_fim
            and (member_end is None or member_end >= data_fim)
            and member_status == "Ativa"
        )
        if active_on_start:
            active_at_start += 1
        if active_on_end:
            active_at_end += 1
        abandoned = (
            member_status == "Encerrada"
            or (member_end is not None and data_inicio <= member_end <= data_fim)
        )
        if abandoned:
            memberships_abandoned += 1
            abandon_month = (
                member_end.strftime("%Y-%m")
                if member_end
                else data_fim.strftime("%Y-%m")
            )
            membership_history[abandon_month] = membership_history.get(abandon_month, 0) + 1
        start = max(data_inicio, member_start)
        end = min(data_fim, member_end or data_fim)
        count = 0
        last_played = None
        if end >= start:
            for offset in range((end - start).days + 1):
                day = start + timedelta(days=offset)
                if (day.weekday() + 1) % 7 == int(weekday):
                    count += 1
                    last_played = day
        if count:
            members_top.append({
                "mensalidade_id": int(membership_id),
                "cliente": name,
                "jogos": count,
                "valor_mensal": float(monthly_value or 0),
                "ultimo_jogo": last_played.isoformat() if last_played else None,
                "status": member_status
            })
    members_top.sort(key=lambda item: (-item["jogos"], -item["valor_mensal"], item["cliente"]))
    members_top = members_top[:10]

    cursor.execute(
        f"""
        SELECT MIN(a.data),
               COUNT(*),
               SUM(a.status = 'Confirmado'),
               SUM(a.status = 'Cancelado'),
               SUM(a.status = 'Não atendido'),
               COALESCE(SUM(
                   CASE WHEN a.status = 'Confirmado'
                        THEN a.valor_hora + a.taxa_reserva ELSE 0 END
               ), 0)
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY YEAR(a.data), MONTH(a.data)
        ORDER BY YEAR(a.data), MONTH(a.data)
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    demand_month = [
        {
            "mes": row[0].strftime("%Y-%m"),
            "solicitacoes": int(row[1] or 0),
            "confirmadas": int(row[2] or 0),
            "canceladas": int(row[3] or 0),
            "nao_atendidas": int(row[4] or 0),
            "faturado": float(row[5] or 0)
        }
        for row in cursor.fetchall()
    ]
    meses_com_dados = [item for item in demand_month if item["solicitacoes"] > 0]
    maior_demanda = max(meses_com_dados, key=lambda item: item["solicitacoes"]) if meses_com_dados else None
    menor_demanda = min(meses_com_dados, key=lambda item: item["solicitacoes"]) if meses_com_dados else None

    cursor.execute(
        f"""
        SELECT a.data, COUNT(*)
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.status = 'Cancelado'
          AND a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY a.data
        ORDER BY a.data
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    cancelations_by_date = [
        {"dia": row[0].isoformat(), "cancelamentos": int(row[1] or 0)}
        for row in cursor.fetchall()
    ]
    cursor.execute(
        f"""
        SELECT c.id, c.nome, COUNT(*)
        FROM agendamento a
        INNER JOIN cliente c ON c.id = a.cliente_id
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.status = 'Cancelado'
          AND a.data BETWEEN %s AND %s
          AND {where_quadras}
        GROUP BY c.id, c.nome
        ORDER BY COUNT(*) DESC, c.nome
        LIMIT 10
        """,
        [data_inicio, data_fim] + parametros_quadras
    )
    cancelations_by_client = [
        {"cliente_id": int(row[0]), "cliente": row[1], "cancelamentos": int(row[2] or 0)}
        for row in cursor.fetchall()
    ]

    today = date.today()
    end_today = today
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=6)
    next_month = today + timedelta(days=29)

    cursor.execute(
        f"""
        SELECT
            SUM(a.status = 'Confirmado' AND a.data = %s),
            SUM(a.status = 'Confirmado' AND a.data = %s),
            SUM(a.status = 'Confirmado' AND a.data BETWEEN %s AND %s),
            SUM(a.status = 'Confirmado' AND a.data BETWEEN %s AND %s),
            SUM(a.status = 'Pendente' AND a.data >= %s)
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.data >= %s
          AND {where_quadras}
        """,
        [
            today,
            tomorrow,
            today,
            next_week,
            today,
            next_month,
            today,
            today
        ] + parametros_quadras
    )
    future_row = cursor.fetchone()
    future_counts = {
        "hoje": int(future_row[0] or 0),
        "amanha": int(future_row[1] or 0),
        "proximos_7_dias": int(future_row[2] or 0),
        "proximos_30_dias": int(future_row[3] or 0),
        "pendentes_futuros": int(future_row[4] or 0)
    }
    cursor.execute(
        f"""
        SELECT m.dia_semana, m.data_inicio, m.data_encerramento
        FROM mensalidade m
        INNER JOIN quadra q ON q.id = m.quadra_id
        WHERE m.status = 'Ativa'
          AND m.data_inicio <= %s
          AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
          AND {where_quadras}
        """,
        [next_month, today] + parametros_quadras
    )
    future_memberships = cursor.fetchall()
    for key, start_day, end_day in (
        ("hoje", today, end_today),
        ("amanha", tomorrow, tomorrow),
        ("proximos_7_dias", today, next_week),
        ("proximos_30_dias", today, next_month)
    ):
        recurring_count = 0
        for weekday, member_start, member_end in future_memberships:
            first = max(start_day, member_start)
            last = min(end_day, member_end or end_day)
            if last < first:
                continue
            for offset in range((last - first).days + 1):
                if ((first + timedelta(days=offset)).weekday() + 1) % 7 == int(weekday):
                    recurring_count += 1
        future_counts[key] += recurring_count
    inactive_cutoff = today - timedelta(days=inativo_dias)
    cursor.execute(
        f"""
        SELECT a.cliente_id, c.nome, c.contato, MAX(a.data)
        FROM cliente c
        INNER JOIN agendamento a ON a.cliente_id = c.id
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE a.status = 'Confirmado'
          AND a.data <= %s
          AND {where_quadras}
        GROUP BY a.cliente_id, c.nome, c.contato
        HAVING MAX(a.data) < %s
        ORDER BY MAX(a.data), c.nome
        LIMIT 100
        """,
        [inactive_cutoff] + parametros_quadras + [inactive_cutoff]
    )
    clientes_inativos_30 = [
        {
            "cliente_id": int(row[0]),
            "cliente": row[1],
            "contato": row[2],
            "ultimo_jogo": row[3].isoformat()
        }
        for row in cursor.fetchall()
    ]

    receivables = []
    cursor.execute(
        f"""
        SELECT a.id, c.nome, q.nome, a.data, a.horario,
               a.valor_hora + a.taxa_reserva,
               COALESCE(p.valor_pago, 0)
        FROM agendamento a
        INNER JOIN cliente c ON c.id = a.cliente_id
        INNER JOIN quadra q ON q.id = a.quadra_id
        LEFT JOIN (
            SELECT agendamento_id,
                   SUM(CASE WHEN status <> 'Cancelado' THEN valor_pago ELSE 0 END) valor_pago
            FROM pagamento
            WHERE agendamento_id IS NOT NULL
            GROUP BY agendamento_id
        ) p ON p.agendamento_id = a.id
        WHERE a.status = 'Confirmado'
          AND {where_quadras}
        ORDER BY a.data, a.horario
        """,
        parametros_quadras
    )
    for booking_id, client, court_name, due, slot, total, paid in cursor.fetchall():
        balance = max(float(total or 0) - float(paid or 0), 0)
        if balance:
            receivables.append({
                "referencia": f"Reserva #{booking_id}",
                "cliente": client,
                "quadra": court_name,
                "vencimento": due.isoformat(),
                "valor": balance
            })

    competence = today.strftime("%Y-%m")
    cursor.execute(
        f"""
        SELECT m.id, c.nome, q.nome, m.valor_mensal,
               COALESCE(p.valor_pago, 0) + COALESCE(legacy.valor_pago, 0)
        FROM mensalidade m
        INNER JOIN cliente c ON c.id = m.cliente_id
        INNER JOIN quadra q ON q.id = m.quadra_id
        LEFT JOIN (
            SELECT mensalidade_id, competencia,
                   SUM(CASE WHEN status <> 'Cancelado' THEN valor_pago ELSE 0 END)
                       AS valor_pago
            FROM pagamento
            WHERE competencia = %s
              AND mensalidade_id IS NOT NULL
            GROUP BY mensalidade_id, competencia
        ) p ON p.mensalidade_id = m.id
           AND p.competencia = %s
        LEFT JOIN (
            SELECT pm.mensalidade_id,
                   SUM(CASE WHEN pm.status = 'Pago' THEN pm.valor ELSE 0 END)
                       AS valor_pago
            FROM pagamento_mensalidade pm
            WHERE DATE_FORMAT(pm.competencia, '%Y-%m') = %s
              AND NOT EXISTS (
                  SELECT 1 FROM pagamento operacional
                  WHERE operacional.mensalidade_id = pm.mensalidade_id
                    AND operacional.competencia =
                        DATE_FORMAT(pm.competencia, '%Y-%m')
                    AND operacional.status <> 'Cancelado'
              )
            GROUP BY pm.mensalidade_id
        ) legacy ON legacy.mensalidade_id = m.id
        WHERE m.data_inicio <= %s
          AND (m.data_encerramento IS NULL OR m.data_encerramento >= %s)
          AND m.status = 'Ativa'
          AND {where_quadras}
        """,
        [
            competence,
            competence,
            competence,
            today,
            today
        ] + parametros_quadras
    )
    for membership_id, client, court_name, monthly_value, paid in cursor.fetchall():
        paid = float(paid or 0)
        balance = max(float(monthly_value or 0) - paid, 0)
        if balance:
            receivables.append({
                "referencia": f"Mensalidade #{membership_id} ({competence})",
                "cliente": client,
                "quadra": court_name,
                "vencimento": f"{competence}-01",
                "valor": balance
            })
    receivable_total = sum(item["valor"] for item in receivables)
    receivable_today = sum(
        item["valor"] for item in receivables
        if item["vencimento"] == today.isoformat()
    )
    receivable_week = sum(
        item["valor"] for item in receivables
        if today <= date.fromisoformat(item["vencimento"]) <= today + timedelta(days=6)
    )
    current_month = today.strftime("%Y-%m")
    receivable_month = sum(
        item["valor"] for item in receivables
        if item["vencimento"].startswith(current_month)
    )

    summary_extra = {
        "taxa_conversao_percentual": round(
            resumo["confirmadas"] / resumo["reservas"] * 100, 2
        ) if resumo["reservas"] else 0,
        "jogos_futuros": future_counts["proximos_30_dias"],
        "mensalistas_ativos_inicio": active_at_start,
        "mensalistas_ativos_fim": active_at_end,
        "novos_mensalistas": memberships_new,
        "mensalistas_cancelados": memberships_abandoned,
        "taxa_abandono_percentual": round(
            memberships_abandoned / active_at_start * 100, 2
        ) if active_at_start else 0,
        "valor_a_receber_hoje": round(receivable_today, 2),
        "valor_a_receber_7_dias": round(receivable_week, 2),
        "valor_a_receber_mes": round(receivable_month, 2),
        "total_a_receber": round(receivable_total, 2),
        "horas_disponiveis_periodo": total_available,
        "horas_ocupadas_periodo": total_occupied,
        "utilizacao_periodo_percentual": round(
            total_occupied / total_available * 100, 2
        ) if total_available else 0,
        "cancelamentos_percentual": round(
            resumo["canceladas"] / resumo["reservas"] * 100, 2
        ) if resumo["reservas"] else 0,
        "faturamento_periodo": round(sum(
            item["faturado"] for item in demanda_quadras
        ), 2),
        "recebido_periodo": round(
            float(resumo.get("faturamento_pagamentos") or 0),
            2
        ),
        "a_receber_periodo": round(receivable_total, 2)
    }

    first_day_month = today.replace(day=1)
    cursor.execute(
        f"""
        SELECT
            COALESCE(SUM(
                CASE WHEN a.data = %s AND a.status = 'Confirmado'
                     THEN a.valor_hora + a.taxa_reserva ELSE 0 END
            ), 0),
            COALESCE(SUM(
                CASE WHEN a.data BETWEEN %s AND %s
                           AND a.status = 'Confirmado'
                     THEN a.valor_hora + a.taxa_reserva ELSE 0 END
            ), 0)
        FROM agendamento a
        INNER JOIN quadra q ON q.id = a.quadra_id
        WHERE {where_quadras}
        """,
        [today, first_day_month, today] + parametros_quadras
    )
    generated_today, generated_month = cursor.fetchone()

    def received_between(start_day, end_day):
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(p.valor_pago), 0)
            FROM pagamento p
            LEFT JOIN agendamento a ON a.id = p.agendamento_id
            LEFT JOIN mensalidade m ON m.id = p.mensalidade_id
            LEFT JOIN quadra q ON q.id = COALESCE(a.quadra_id, m.quadra_id)
            WHERE p.status <> 'Cancelado'
              AND p.data_pagamento BETWEEN %s AND %s
              AND {where_quadras}
            """,
            [start_day, end_day] + parametros_quadras
        )
        unified = float(cursor.fetchone()[0] or 0)
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(p.valor), 0)
            FROM pagamento_mensalidade p
            INNER JOIN mensalidade m ON m.id = p.mensalidade_id
            INNER JOIN quadra q ON q.id = m.quadra_id
            WHERE p.status = 'Pago'
              AND p.data_pagamento BETWEEN %s AND %s
              AND {where_quadras}
              AND NOT EXISTS (
                  SELECT 1 FROM pagamento operacional
                  WHERE operacional.mensalidade_id = p.mensalidade_id
                    AND operacional.competencia =
                        DATE_FORMAT(p.competencia, '%Y-%m')
                    AND operacional.status <> 'Cancelado'
              )
            """,
            [start_day, end_day] + parametros_quadras
        )
        return unified + float(cursor.fetchone()[0] or 0)

    generated_day_received = received_between(today, today)
    generated_month_received = received_between(first_day_month, today)
    summary_extra.update({
        "faturamento_dia": float(generated_today or 0),
        "faturamento_mes": float(generated_month or 0),
        "recebido_dia": round(generated_day_received, 2),
        "recebido_mes": round(generated_month_received, 2),
        "faturamento_periodo": round(sum(
            item["faturado"] for item in demanda_quadras
        ), 2)
    })
    demand_cancel_by_weekday = [
        {
            "dia": item["dia"],
            "solicitacoes": item["solicitacoes"],
            "cancelamentos": item["canceladas"],
            "percentual_cancelamentos": item["percentual_cancelamentos"]
        }
        for item in demanda_dia_semana
        if item["solicitacoes"] > 0
    ]
    demand_cancel_by_weekday.sort(
        key=lambda item: (
            -item["percentual_cancelamentos"],
            -item["cancelamentos"],
            item["dia"]
        )
    )
    cancel_by_hour = [
        {
            "horario": hour,
            "solicitacoes": values["solicitacoes"],
            "cancelamentos": values["canceladas"],
            "percentual_cancelamentos": calcular_indice_cancelamento(
                values["solicitacoes"],
                values["canceladas"]
            )
        }
        for hour, values in demanda_horario.items()
        if values["solicitacoes"] > 0
    ]
    cancel_by_hour.sort(
        key=lambda item: (
            -item["percentual_cancelamentos"],
            -item["cancelamentos"],
            item["horario"]
        )
    )
    cancel_by_court = [
        {
            "quadra": item["quadra"],
            "solicitacoes": item["solicitacoes"],
            "cancelamentos": item["canceladas"],
            "percentual_cancelamentos": item["percentual_cancelamentos"]
        }
        for item in sorted(
            demanda_quadras,
            key=lambda item: (
                -item["percentual_cancelamentos"],
                -item["canceladas"],
                item["quadra"]
            )
        )
        if item["solicitacoes"] > 0
    ]
    summary_extra["taxa_conversao_percentual"] = summary_extra["taxa_conversao_percentual"]
    summary_extra["mensalistas_abandono_historico"] = sum(membership_history.values())

    return {
        "resumo": {**resumo, **summary_extra},
        "funil": [
            {
                "status": "Solicitações",
                "quantidade": resumo["reservas"],
                "percentual": 100
            },
            *[
                {
                    "status": label,
                    "quantidade": resumo[key],
                    "percentual": round(resumo[key] / resumo["reservas"] * 100, 2)
                    if resumo["reservas"] else 0
                }
                for key, label in (
                    ("confirmadas", "Confirmadas"),
                    ("pendentes", "Pendentes"),
                    ("nao_atendidas", "Não atendidas"),
                    ("canceladas", "Canceladas")
                )
            ]
        ],
        "demanda_dia_semana": demanda_dia_semana,
        "demanda_horario": horarios_ranked,
        "horarios_mais_requisitados": horarios_mais,
        "horarios_menos_requisitados": horarios_menos,
        "demanda_quadras": demanda_quadras,
        "mapa_calor": {
            "horarios": horarios_ordenados,
            "quadras": heatmap
        },
        "utilizacao_periodo": {
            "total": {
                "horas_ocupadas": total_occupied,
                "horas_disponiveis": total_available,
                "percentual": summary_extra["utilizacao_periodo_percentual"]
            },
            "por_quadra": utilization_by_court,
            "por_dia": utilization_by_day,
            "por_mes": utilization_by_month
        },
        "cancelamentos": {
            "total": resumo["canceladas"],
            "percentual": summary_extra["cancelamentos_percentual"],
            "por_dia_semana": demand_cancel_by_weekday,
            "por_horario": cancel_by_hour,
            "por_quadra": cancel_by_court,
            "por_cliente": cancelations_by_client,
            "evolucao": cancelations_by_date
        },
        "clientes_top": top_clients,
        "clientes_top_mes": top_clients_month,
        "mensalistas": {
            "ativos_inicio": active_at_start,
            "ativos_fim": active_at_end,
            "novos": memberships_new,
            "cancelados": memberships_abandoned,
            "abandono_percentual": summary_extra["taxa_abandono_percentual"],
            "abandono_por_mes": [
                {"mes": month, "cancelados": count}
                for month, count in sorted(membership_history.items())
            ],
            "ranking": members_top
        },
        "demanda_mensal": {
            "meses": demand_month,
            "maior_demanda": maior_demanda,
            "menor_demanda": menor_demanda
        },
        "jogos_futuros": future_counts,
        "contas_a_receber": {
            "hoje": round(receivable_today, 2),
            "proximos_7_dias": round(receivable_week, 2),
            "mes": round(receivable_month, 2),
            "total": round(receivable_total, 2),
            "lancamentos": receivables[:200]
        },
        "clientes_inativos": {
            "periodo_dias": inativo_dias,
            "clientes": clientes_inativos_30
        }
    }


# =========================================================
# USUÁRIOS ADMIN
# =========================================================

@app.get("/admin/usuarios")
def listar_usuarios_admin():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                nome,
                usuario,
                nivel,
                ativo,
                criado_em
            FROM usuario_admin
            ORDER BY nome
            """
        )

        usuarios = cursor.fetchall()
        resultado = []
        for usuario in usuarios:
            permissoes = obter_permissoes_admin(
                cursor,
                usuario[0],
                usuario[3]
            )
            resultado.append({
                "id": usuario[0],
                "nome": usuario[1],
                "usuario": usuario[2],
                "nivel": usuario[3],
                "ativo": bool(usuario[4]),
                "criado_em": converter_valor_mysql(usuario[5]),
                "permissoes": permissoes
                ,
                "quadra_ids": buscar_quadras_permitidas(
                    cursor,
                    usuario[0]
                )
            })
        return resultado

    finally:

        cursor.close()
        conexao.close()


def validar_permissoes_usuario(permissoes):
    modulos_desconhecidos = set(permissoes) - MODULOS_ADMIN
    if modulos_desconhecidos:
        raise HTTPException(
            status_code=400,
            detail="A solicitação contém permissões de módulo inválidas."
        )

    resultado = {}
    for modulo in MODULOS_ADMIN:
        configuracao = permissoes.get(modulo, {})
        visualizar = bool(configuracao.get("visualizar", False))
        editar = bool(configuracao.get("editar", False))
        resultado[modulo] = {
            "visualizar": visualizar or editar,
            "editar": editar
        }
    if not any(permissao["visualizar"] for permissao in resultado.values()):
        raise HTTPException(
            status_code=400,
            detail="Conceda acesso a pelo menos um módulo para criar um usuário ativo."
        )
    return resultado


def validar_quadra_ids(cursor, quadra_ids):
    ids = sorted(set(quadra_ids))
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="Selecione ao menos uma quadra para o usuário."
        )
    placeholders = ", ".join(["%s"] * len(ids))
    cursor.execute(
        f"SELECT id FROM quadra WHERE id IN ({placeholders})",
        ids
    )
    encontrados = {int(row[0]) for row in cursor.fetchall()}
    if encontrados != set(ids):
        raise HTTPException(
            status_code=400,
            detail="A seleção contém uma quadra inexistente."
        )
    return ids


@app.get("/admin/escopo-quadras")
def listar_quadras_do_escopo(request: Request):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        permitidas = getattr(request.state, "quadras_permitidas", [])
        if not permitidas:
            return []
        placeholders = ", ".join(["%s"] * len(permitidas))
        cursor.execute(
            f"SELECT id, nome, tipo FROM quadra WHERE id IN ({placeholders}) ORDER BY nome",
            permitidas
        )
        return [
            linha_para_dict(cursor, linha)
            for linha in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conexao.close()


@app.post("/admin/usuarios")
def criar_usuario_admin(dados: NovoUsuarioAdmin):

    nome = dados.nome.strip()
    usuario = dados.usuario.strip()
    if not nome or not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", usuario):
        raise HTTPException(
            status_code=400,
            detail="Informe um nome e um usuário com 3 a 50 letras, números, ponto, hífen ou sublinhado."
        )
    if len(dados.senha) < 12:
        raise HTTPException(
            status_code=400,
            detail="A senha deve ter pelo menos 12 caracteres."
        )
    permissoes = validar_permissoes_usuario(dados.permissoes)

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        quadra_ids = validar_quadra_ids(cursor, dados.quadra_ids)
        cursor.execute(
            """
            INSERT INTO usuario_admin
                (nome, usuario, senha_hash, nivel, ativo)
            VALUES (%s, %s, %s, 'admin', 1)
            """,
            (nome, usuario, gerar_hash_senha(dados.senha))
        )
        usuario_id = cursor.lastrowid
        cursor.executemany(
            """
            INSERT INTO admin_permissao
                (usuario_admin_id, modulo, pode_visualizar, pode_editar)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    usuario_id,
                    modulo,
                    permissao["visualizar"],
                    permissao["editar"]
                )
                for modulo, permissao in permissoes.items()
            ]
        )
        cursor.executemany(
            """
            INSERT INTO admin_quadra_permissao (usuario_admin_id, quadra_id)
            VALUES (%s, %s)
            """,
            [(usuario_id, quadra_id) for quadra_id in quadra_ids]
        )
        conexao.commit()
        return {"mensagem": "Usuário administrativo criado.", "id": usuario_id}
    except mysql.connector.IntegrityError:
        conexao.rollback()
        raise HTTPException(
            status_code=409,
            detail="Este nome de usuário já está em uso."
        )
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()


@app.put("/admin/usuarios/{usuario_admin_id}")
def atualizar_usuario_admin(
    usuario_admin_id: int,
    dados: AtualizarUsuarioAdmin,
    request: Request
):

    if usuario_admin_id == request.state.usuario_admin_id:
        raise HTTPException(
            status_code=400,
            detail="Não é permitido alterar a própria conta raiz por esta tela."
        )
    permissoes = validar_permissoes_usuario(dados.permissoes)

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        quadra_ids = validar_quadra_ids(cursor, dados.quadra_ids)
        cursor.execute(
            """
            SELECT nivel
            FROM usuario_admin
            WHERE id = %s
            FOR UPDATE
            """,
            (usuario_admin_id,)
        )
        usuario = cursor.fetchone()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        if usuario[0] == "root":
            raise HTTPException(
                status_code=403,
                detail="A conta raiz não pode ser alterada por esta tela."
            )

        cursor.execute(
            "UPDATE usuario_admin SET ativo = %s WHERE id = %s",
            (dados.ativo, usuario_admin_id)
        )
        cursor.execute(
            "DELETE FROM admin_permissao WHERE usuario_admin_id = %s",
            (usuario_admin_id,)
        )
        cursor.execute(
            "DELETE FROM admin_quadra_permissao WHERE usuario_admin_id = %s",
            (usuario_admin_id,)
        )
        cursor.executemany(
            """
            INSERT INTO admin_permissao
                (usuario_admin_id, modulo, pode_visualizar, pode_editar)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    usuario_admin_id,
                    modulo,
                    permissao["visualizar"],
                    permissao["editar"]
                )
                for modulo, permissao in permissoes.items()
            ]
        )
        cursor.executemany(
            """
            INSERT INTO admin_quadra_permissao (usuario_admin_id, quadra_id)
            VALUES (%s, %s)
            """,
            [
                (usuario_admin_id, quadra_id)
                for quadra_id in quadra_ids
            ]
        )
        if not dados.ativo:
            cursor.execute(
                "DELETE FROM sessao_admin WHERE usuario_admin_id = %s",
                (usuario_admin_id,)
            )
        conexao.commit()
        return {"mensagem": "Permissões do usuário atualizadas."}
    except HTTPException:
        conexao.rollback()
        raise
    except Exception as erro:
        conexao.rollback()
        raise HTTPException(status_code=500, detail=str(erro))
    finally:
        cursor.close()
        conexao.close()

# =========================================================
# TESTE DA API
# =========================================================

@app.get("/api/status")
def status_api():

    return {
        "sistema":
            "Bosque Esportes",

        "status":
            "online"
    }


@app.get("/api/ready")
def readiness_api():
    conexao = None
    cursor = None
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return {"sistema": "Bosque Esportes", "status": "ready"}
    except (RuntimeError, ValueError, mysql.connector.Error):
        logger.exception("Readiness check failed.")
        return JSONResponse(
            status_code=503,
            content={"sistema": "Bosque Esportes", "status": "not_ready"}
        )
    finally:
        if cursor is not None:
            cursor.close()
        if conexao is not None:
            conexao.close()