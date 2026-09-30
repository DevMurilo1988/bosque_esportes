# Bosque Esportes

Aplicação web de agendamento e administração do Bosque Esportes. A API e o
frontend estático são servidos pela mesma aplicação FastAPI; os dados ficam em
um banco MySQL externo.

## Rodar localmente

1. Instale Python 3.13.
2. Crie e ative um ambiente virtual.
3. Instale as dependências:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copie `.env.example` para `.env` e configure o acesso ao MySQL local.
5. Inicie o servidor:

   ```powershell
   uvicorn backend.main:app --reload
   ```

6. Abra `http://127.0.0.1:8000/`. A verificação `/api/ready` confirma também
   que o banco de dados está acessível.

## Deploy de teste no Render

O arquivo `render.yaml` configura um Web Service Python gratuito para teste.
Siga [`docs/deploy-render.md`](docs/deploy-render.md) para preparar um MySQL
externo, importar o schema e os dados necessários, conectar o repositório e
configurar as variáveis secretas do serviço.

Não use o plano gratuito como hospedagem definitiva: o serviço pode suspender
após inatividade. O filesystem do serviço não é armazenamento persistente.

## Estrutura

- `backend/`: API FastAPI, provisionamento do primeiro administrador, script de
  demonstração e migrações MySQL.
- `frontend/`: páginas, estilos, JavaScript e imagens.
- `docs/`: documentação de estrutura e implantação.
