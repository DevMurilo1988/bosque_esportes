Regras de negócio e implantação

Status:	      Significado:
Pendente	  Cliente solicitou e está aguardando sua vez/contato
Confirmado	  Cliente aceitou e pagou a taxa de reserva
Cancelado	  Cliente desistiu antes da confirmação
Não Atendido  Cliente estava na fila, mas perdeu a oportunidade porque outra pessoa foi confirmada

FILA DE RESERVAS
    - Solicitações pendentes ocupam vagas da fila, conforme o limite configurado.
    - Com a fila desativada, somente uma solicitação pendente é permitida por quadra, data e horário.
    - Ao confirmar uma solicitação, as demais pendentes do mesmo horário passam para "Não atendido".
    - Se a confirmação for desfeita ou cancelada, as solicitações movidas automaticamente voltam para "Pendente".
    - A tabela agendamento_fila_retorno registra quais solicitações foram movidas automaticamente para permitir essa restauração.
    - Bancos existentes devem aplicar backend/migrations/20260929_agendamento_fila_retorno.sql uma vez.

PERMISSÕES POR QUADRA E CONTEÚDO DO SITE
    - backend/migrations/20260930_court_operations.sql adiciona o WhatsApp do responsável na quadra, cria a relação admin_quadra_permissao e insere configurações editáveis da página inicial e da mensagem de atendimento.
    - A migração é aditiva e pode ser reaplicada: não remove nem atualiza dados existentes. Em banco já migrado, a coluna de responsável é preservada.
    - admin_quadra_permissao é uma relação muitos-para-muitos entre administradores e quadras. Mantém o escopo de acesso fora da tabela de usuários e permite conceder várias quadras a cada operador sem duplicar usuários ou dados de quadra.
    - `/admin/escopo-quadras` retorna apenas quadras autorizadas para o seletor do painel; `/admin/quadras` é a consulta detalhada usada para administrar seus dados.
    - `/jogos?data=AAAA-MM-DD&quadra_id=ID` combina reservas avulsas e ocorrências de mensalistas para a gestão do dia. O painel permite conferir saldos, abrir o atendimento pelo WhatsApp e registrar recebimentos externos.
    - `backend/seed_demo_data.py --month AAAA-MM --replace-operational-data` substitui reservas, mensalidades, pagamentos e históricos por uma massa de demonstração. Preserva quadras, configurações, administradores e clientes não identificados pelo prefixo `DEMO`; a opção explícita de substituição é obrigatória.

PAGAMENTOS E MIGRAÇÕES
    - Pagamentos operacionais ficam relacionados à reserva ou mensalidade e mantêm histórico de status.
    - Para mensalidades recorrentes, cada pagamento informa a competência no formato AAAA-MM; pagamentos da mesma competência respeitam o valor mensal cadastrado.
    - Em bancos existentes, aplicar em ordem: backend/migrations/20260929_operational_finance_auth.sql, backend/migrations/20260929_pagamento_valor_pago.sql, backend/migrations/20260929_pagamento_competencia.sql e backend/migrations/20260929_admin_permissoes.sql. A primeira migração não cria `valor_pago`; a seguinte adiciona essa coluna.
    - A criação do primeiro administrador é feita localmente com backend/create_admin.py. A senha não deve ser armazenada no frontend.
    - Aplicar backend/migrations/20260929_admin_permissoes.sql para ativar permissões administrativas independentes por módulo. A conta inicial criada por backend/create_admin.py recebe nível `root`; apenas ela pode criar contas administrativas e definir acessos. Usuários comuns têm permissões de visualização e edição controladas por módulo.
    - O endpoint público `/configuracoes` retorna apenas horários de funcionamento e regras da fila. A lista integral, incluindo taxas e dados administrativos, exige sessão em `/admin/configuracoes`.
    - Pagamentos de mensalidade novos também são registrados na tabela operacional `pagamento`; `pagamento_mensalidade` é mantida para preservar o histórico legado.
    - Para bancos já existentes, aplicar também backend/migrations/20260930_court_operations.sql. A tabela de permissões por quadra é independente das permissões de módulo em admin_permissao.




########################################################################################################################################

ESTRUTURA E IMPLANTAÇÃO
    - `backend/main.py` reúne a API FastAPI e serve as páginas estáticas de `frontend/`; não há build separado do frontend.
    - `backend/schema.mysql.sql` é uma referência de schema sem dados para uma instalação MySQL nova. Atualize-a junto com mudanças estruturais e preserve as migrações aditivas para bancos existentes.
    - `backend/migrations/` contém as migrações incrementais para atualizar bancos existentes.
    - `requirements.txt` lista as dependências Python diretas; `render.yaml` configura o serviço de teste no Render; `docs/deploy-render.md` descreve a preparação do banco e publicação.
    - Credenciais locais ficam em `.env`, ignorado pelo Git. Configure o banco e cookies seguros por variáveis de ambiente no host. Nunca publique `.env`, exportações com dados, nem sessões administrativas.
    - `.venv/`, `__pycache__/` e arquivos temporários não fazem parte do deploy; o `.gitignore` da raiz os exclui.