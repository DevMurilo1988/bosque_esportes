from getpass import getpass
import os
import re

import mysql.connector

from main import conectar_banco, gerar_hash_senha


def main():
    nome = os.environ.get("BOSQUE_ADMIN_NOME")
    usuario = os.environ.get("BOSQUE_ADMIN_USUARIO")
    senha = os.environ.get("BOSQUE_ADMIN_SENHA")
    confirmar = os.environ.get("BOSQUE_ADMIN_SENHA_CONFIRMACAO")

    nome = (nome if nome is not None else input("Nome do administrador: ")).strip()
    usuario = (
        usuario
        if usuario is not None
        else input("Usuário de acesso: ")
    ).strip()
    senha = senha if senha is not None else getpass(
        "Senha (mínimo 12 caracteres): "
    )
    confirmar = confirmar if confirmar is not None else getpass(
        "Confirme a senha: "
    )

    if not nome or not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", usuario):
        raise SystemExit(
            "Nome obrigatório. Usuário: 3–50 letras, números, ponto, hífen ou sublinhado."
        )

    if len(senha) < 12 or senha != confirmar:
        raise SystemExit("A senha deve ter 12 caracteres ou mais e as confirmações devem coincidir.")

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM usuario_admin")
        if cursor.fetchone()[0]:
            raise SystemExit(
                "A conta raiz inicial já foi criada. Cadastre novos usuários pela tela de administração."
            )

        cursor.execute(
            """
            INSERT INTO usuario_admin
                (nome, usuario, senha_hash, nivel, ativo)
            VALUES (%s, %s, %s, 'root', 1)
            """,
            (nome, usuario, gerar_hash_senha(senha))
        )
        conexao.commit()
        print(f"Administrador '{usuario}' criado.")
    except mysql.connector.IntegrityError:
        conexao.rollback()
        raise SystemExit("Esse usuário já existe.")
    finally:
        cursor.close()
        conexao.close()


if __name__ == "__main__":
    main()
