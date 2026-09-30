# Deploy de teste no Render

O projeto está preparado para o fluxo **Render para teste → validação do seu
avô → escolha da hospedagem definitiva**. O `render.yaml` define um Web Service
Python gratuito em Virginia e usa `/api/ready` como health check.

## Banco de dados

O sistema usa **MySQL** (`mysql-connector-python`). O Render oferece Postgres
gerenciado, que não é compatível com esta aplicação sem uma migração do banco e
do código. Não crie um Render Postgres para este deploy.

Use um serviço MySQL gerenciado externo que aceite conexões TLS da aplicação.
Não exponha o MySQL do seu computador nem use o usuário `root` do banco na
aplicação. Crie um banco e um usuário próprios, com apenas as permissões
necessárias para o schema do Bosque Esportes. As tabelas devem ser criadas uma
vez com um usuário administrativo do banco; o usuário configurado no Render
precisa apenas de `SELECT`, `INSERT`, `UPDATE` e `DELETE` nas tabelas do sistema.

## Preparação

1. Faça backup do MySQL local antes de exportar qualquer tabela.
2. Crie o banco MySQL externo e seu usuário restrito. Anote host, porta, nome do
   banco, usuário e senha em um gerenciador seguro; não os coloque no GitHub.
3. Crie o schema do serviço externo usando `backend/schema.mysql.sql`.
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
8. Confirme no painel do Render que `COOKIE_SECURE=true` e que a conexão TLS
   exigida pelo provedor está habilitada. Se o provedor entregar um certificado
   CA, configure-o como Secret File e indique seu caminho em `DB_SSL_CA`;
   habilite `DB_SSL_VERIFY_CERT=true`.
9. Aguarde o deploy ficar healthy e abra a URL `onrender.com`. `/api/ready`
   deve retornar `{"sistema":"Bosque Esportes","status":"ready"}`. Faça login,
   envie uma solicitação de teste e confira os dados diretamente no banco.
10. Antes de convidar o usuário de teste, combine que o plano gratuito pode
    suspender o serviço após 15 minutos sem acessos, causando demora na primeira
    abertura. Não use dados pessoais reais até revisar backups, privacidade e
    plano do banco externo.

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
