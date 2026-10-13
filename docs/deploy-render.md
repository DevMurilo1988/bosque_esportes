# Deploy de teste no Render

O projeto está preparado para o fluxo **Render para teste → validação do seu
avô → escolha da hospedagem definitiva**. O `render.yaml` define um Web Service
Python gratuito em Virginia e usa `/api/ready` como health check.

## Banco de dados

O sistema usa **MySQL** (`mysql-connector-python`). O Render oferece Postgres
gerenciado, que não é compatível com esta aplicação sem uma migração do banco e
do código. Não crie um Render Postgres para este deploy.

Use um serviço MySQL gerenciado externo que aceite conexões TLS da aplicação.
Para o Aiven, copie host, porta, nome do banco, usuário e senha da tela de
informações de conexão do serviço MySQL; não use `localhost`. A aplicação usa
`mysql-connector-python` e lê esses dados de `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER` e `DB_PASSWORD`. `DB_SSL_DISABLED=false` mantém TLS habilitado;
`DB_SSL_VERIFY_CERT=true` valida o certificado do servidor e a identidade do
host. Configure `DB_SSL_CA` com o caminho do certificado CA baixado no Aiven
(por exemplo, o caminho do Secret File criado no Render). Não desabilite a
validação TLS em produção.
Não exponha o MySQL do seu computador nem use o usuário `root` do banco na
aplicação. Crie um banco e um usuário próprios, com apenas as permissões
necessárias para o schema do Bosque Esportes. As tabelas devem ser criadas uma
vez com um usuário administrativo do banco; o usuário configurado no Render
precisa apenas de `SELECT`, `INSERT`, `UPDATE` e `DELETE` nas tabelas do sistema.

## Preparação

1. Faça backup do MySQL local antes de exportar qualquer tabela.
2. Crie o banco MySQL externo e seu usuário restrito. Anote host, porta, nome do
   banco, usuário e senha em um gerenciador seguro; não os coloque no GitHub.
3. Crie o schema do serviço externo usando `backend/schema.mysql.sql`. Para um
   banco já existente, aplique também
   `backend/migrations/20261013_pagamento_recebimentos_incrementais.sql`
   depois das migrações financeiras já utilizadas; faça backup antes de
   executar alterações no banco.
4. Transfira para o banco externo os dados que devem permanecer disponíveis,
   como as quadras, configurações, clientes mantidos e usuário administrativo.
   Use uma exportação de dados do MySQL Workbench ou ferramenta equivalente.
   **Não importe `sessao_admin`**: sessões locais são temporárias.
5. Confira no destino as quatro quadras, configurações e a conta root. Como
   alternativa, crie o primeiro root usando `backend/create_admin.py` com
   `DB_*` apontando para o banco externo.
6. Crie um repositório GitHub privado para o projeto e envie os arquivos do
   projeto. O `.gitignore` exclui `.env`, ambientes virtuais, caches e arquivos
   de transferência. Não envie dumps nem arquivos com credenciais.
7. No Render, crie um Blueprint a partir do repositório. O `render.yaml` pede as
   variáveis marcadas `sync: false`; preencha `DB_HOST`, `DB_NAME`, `DB_USER` e
   `DB_PASSWORD` com as credenciais do MySQL externo.
8. Confirme no painel do Render que `COOKIE_SECURE=true`,
   `DB_SSL_DISABLED=false` e `DB_SSL_VERIFY_CERT=true`. Para o Aiven, configure
   o certificado CA como Secret File e informe o caminho absoluto em `DB_SSL_CA`.
9. Aguarde o deploy ficar healthy e abra a URL `onrender.com`. `/api/ready`
   deve retornar `{"sistema":"Bosque Esportes","status":"ready"}`. Faça login,
   envie uma solicitação de teste e confira os dados diretamente no banco.
10. Antes de convidar o usuário de teste, combine que o plano gratuito pode
    suspender o serviço após 15 minutos sem acessos, causando demora na primeira
    abertura. Não use dados pessoais reais até revisar backups, privacidade e
    plano do banco externo.

O comando de inicialização do `render.yaml` já escuta em `0.0.0.0` e utiliza
`$PORT`, atribuído pelo Render. O `requirements.txt` contém FastAPI, Uvicorn,
Pydantic (instalado como dependência do FastAPI), `mysql-connector-python` e
`python-dotenv`; SQLAlchemy, PyMySQL e `requests` não são necessários porque o
código usa o conector MySQL e `urllib` diretamente.

## Solicitações pelo WhatsApp

Depois de salvar uma solicitação como **Pendente**, o site abre uma conversa
`wa.me` com o WhatsApp definido no cadastro da quadra e preenche uma mensagem
com nome e contato do cliente, quadra, data e horário. O cliente precisa tocar
em **Enviar** no WhatsApp; o site não envia a mensagem por conta própria. O
responsável continua o atendimento pelo WhatsApp Business e confirma a reserva
no painel administrativo.

Cadastre o telefone do responsável em cada quadra, incluindo DDD. Números
brasileiros com 10 ou 11 dígitos recebem o código `55` automaticamente. O
telefone será usado como destinatário do link; sem um número válido, o pedido
continua registrado e o site avisa que o WhatsApp do responsável não está
configurado. Nenhum token ou configuração da API da Meta é necessário.

## Notificações administrativas pelo Telegram

O Telegram usa um bot compartilhado, mas envia dois fluxos para chats distintos:
as novas solicitações e filas vão somente para o chat privado da administração;
o grupo geral recebe apenas o extrato atualizado quando há uma mudança de
status de reserva/pagamento ou o recebimento da taxa de garantia. O extrato
lista apenas reservas confirmadas e mensalidades ativas da data, nunca
solicitações pendentes. Em datas futuras, a mensagem inclui um link para o
sistema web.

1. Crie um bot com o `@BotFather` e guarde o token em um gerenciador seguro.
2. Inicie uma conversa privada com o bot e envie `/start`. Obtenha esse chat ID
   para `TELEGRAM_ADMIN_CHAT_ID`.
3. Adicione o bot ao grupo geral, permita que ele envie mensagens e obtenha o
   chat ID do grupo para `TELEGRAM_GROUP_CHAT_ID` (normalmente um número
   negativo). Não use o chat privado da administração como grupo.
4. Configure `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` e
   `TELEGRAM_GROUP_CHAT_ID` no `.env` local e como variáveis secretas do Render.
   A configuração antiga `TELEGRAM_CHAT_ID` continua aceita como fallback para
   o chat privado, mas prefira a variável nova.
5. Reinicie/reimplante o serviço e teste uma solicitação e uma mudança de
   status. Uma solicitação é salva mesmo se o Telegram estiver indisponível;
   nesse caso, o backend registra a falha nos logs e a tela informa que a
   notificação precisa ser verificada. Se o Telegram não aceitar um extrato do
   grupo, a alteração correspondente é revertida para manter o painel
   sincronizado.

Não publique o token, não o inclua em repositórios e evite compartilhar URLs
que contenham o token do bot.

## Limites e segurança

- O filesystem do Render é efêmero. Imagens enviadas localmente ao servidor não
  persistem em redeploy; use URLs estáveis ou armazenamento de objetos.
- Guarde as credenciais apenas nas variáveis do Render e no `.env` local
  ignorado pelo Git.
- Para um ambiente real, use banco com backup gerenciado e revise o plano,
  TLS, política de retenção e acessos do provedor.
- O serviço web gratuito do Render serve para validação, não para operação
  contínua: pode suspender por inatividade e não oferece a mesma disponibilidade
  de um plano pago.
