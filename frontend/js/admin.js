// =========================================================
// BOSQUE ESPORTES - ADMIN
// =========================================================


// =========================================================
// VARIÁVEIS
// =========================================================

let agendamentos = [];
let mensalistas = [];
let clientes = [];
let quadras = [];
let configuracoes = [];
let permissoesAdmin = {};
let usuarioAdminAtual = null;
const fetchOriginal = window.fetch.bind(window);

window.fetch = (input, options) => {
    if (!usuarioAdminAtual || usuarioAdminAtual.nivel === 'root') {
        return fetchOriginal(input, options);
    }
    const url = new URL(
        typeof input === 'string' ? input : input.url,
        window.location.href
    );
    const aplicaEscopo = [
        '/agendamentos',
        '/mensalidades',
        '/pagamentos',
        '/clientes',
        '/jogos',
        '/relatorios',
        '/quadras/'
    ].some(prefixo => url.pathname === prefixo || url.pathname.startsWith(`${prefixo}/`));
    if (aplicaEscopo) {
        const escopo = document.getElementById('admin-court-scope-select');
        if (escopo && escopo.value) url.searchParams.set('quadra_id', escopo.value);
    }
    return fetchOriginal(url.toString(), options);
};

const modulosAdmin = {
    agendamentos: 'Agendamentos',
    mensalistas: 'Mensalistas',
    pagamentos: 'Pagamentos',
    relatorios: 'Relatórios',
    clientes: 'Clientes',
    quadras: 'Quadras',
    configuracoes: 'Configurações'
};


// Valores mensais padrão antigos; o valor atual é configurado por quadra.

const configuracoesLegadas = [
    'mensalidade_salao',
    'mensalidade_sintetico',
    'mensalidade_areia',
    'taxa_reserva_salao',
    'taxa_reserva_sintetico',
    'taxa_reserva_areia'
];


// =========================================================
// INICIALIZAÇÃO
// =========================================================

document.addEventListener('DOMContentLoaded', () => {

    const app = document.getElementById('admin-app');
    const login = document.getElementById('admin-login');
    const loginForm = document.getElementById('admin-login-form');
    const loginError = document.getElementById('admin-login-erro');
    const logoutButton = document.getElementById('admin-logout');

    function mostrarLogin(configurado) {
        app.hidden = true;
        login.hidden = false;
        loginError.textContent = configurado
            ? ''
            : 'Nenhum administrador cadastrado. Execute .\\.venv\\Scripts\\python.exe backend\\create_admin.py no terminal.';
        loginForm.querySelector('button[type="submit"]').disabled =
            !configurado;
    }

    function inicializarPainel(sessao) {
        usuarioAdminAtual = sessao.usuario;
        permissoesAdmin = sessao.permissoes || {};
        login.hidden = true;
        app.hidden = false;
        configurarEscopoQuadra();
        configurarMenu();
        configurarAgendamentos();
        configurarMensalistas();
        configurarClientes();
        configurarQuadras();
        configurarConfiguracoes();
        configurarRelatorios();
        configurarPagamentos();
        aplicarPermissoesPainel();
        if (usuarioAdminAtual.nivel === 'root') {
            configurarUsuariosAdmin();
        }
        const primeiraSecao = document.querySelector(
            '.menu-btn:not([hidden])'
        );
        if (primeiraSecao) primeiraSecao.click();
    }

    async function consultarSessao() {
        try {
            const resposta = await fetch('/admin/sessao');
            const sessao = await resposta.json();
            if (sessao.autenticado) {
                inicializarPainel(sessao);
            } else {
                mostrarLogin(sessao.configurado);
            }
        } catch (erro) {
            console.error(erro);
            mostrarLogin(true);
            loginError.textContent =
                'Não foi possível conectar ao serviço de autenticação.';
        }
    }

    loginForm.addEventListener('submit', async event => {
        event.preventDefault();
        loginError.textContent = '';
        const button = loginForm.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
            const resposta = await fetch('/admin/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    usuario: document.getElementById('admin-usuario').value,
                    senha: document.getElementById('admin-senha').value
                })
            });
            const resultado = await resposta.json();
            if (!resposta.ok) {
                throw new Error(resultado.detail || 'Falha ao entrar.');
            }
            loginForm.reset();
            inicializarPainel(resultado);
        } catch (erro) {
            loginError.textContent = erro.message;
        } finally {
            button.disabled = false;
        }
    });

    async function configurarEscopoQuadra() {
        const container = document.getElementById('admin-court-scope');
        const select = document.getElementById('admin-court-scope-select');
        if (!container || !select || !usuarioAdminAtual ||
            usuarioAdminAtual.nivel === 'root') return;
        try {
            const resposta = await fetchOriginal('/admin/escopo-quadras');
            const lista = await resposta.json();
            if (!resposta.ok) throw new Error(lista.detail || 'Não foi possível carregar as quadras autorizadas.');
            select.innerHTML = lista.map(item =>
                `<option value="${Number(item.id)}">${escaparHTML(item.nome)}</option>`
            ).join('');
            container.hidden = lista.length <= 1;
            if (lista.length) select.value = String(lista[0].id);
            select.addEventListener('change', () => {
                const filtroJogos = document.getElementById('jogos-dia-quadra');
                if (filtroJogos && [...filtroJogos.options].some(
                    option => option.value === select.value
                )) {
                    filtroJogos.value = select.value;
                }
                const secaoAtiva = document.querySelector('.menu-btn.active:not([hidden])');
                if (secaoAtiva) secaoAtiva.click();
            });
            const secaoAtiva = document.querySelector('.menu-btn.active:not([hidden])');
            if (secaoAtiva) secaoAtiva.click();
        } catch (erro) {
            console.error(erro);
        }
    }

    logoutButton.addEventListener('click', async () => {
        try {
            await fetch('/admin/logout', {method: 'POST'});
        } finally {
            usuarioAdminAtual = null;
            permissoesAdmin = {};
            mostrarLogin(true);
        }
    });

    consultarSessao();

});


// =========================================================
// MENU
// =========================================================

function configurarMenu() {

    const botoes =
        document.querySelectorAll('.menu-btn');

    botoes.forEach(botao => {

        botao.addEventListener('click', () => {

            const secao =
                botao.dataset.section;

            botoes.forEach(item => {
                item.classList.remove('active');
            });

            botao.classList.add('active');

            document
                .querySelectorAll('.admin-section')
                .forEach(section => {
                    section.classList.remove('active');
                });

            const sectionSelecionada =
                document.getElementById(
                    `section-${secao}`
                );

            if (sectionSelecionada) {
                sectionSelecionada.classList.add('active');
            }


            if (secao === 'agendamentos') {
                carregarAgendamentos();
                document.getElementById('btn-atualizar-jogos-dia')?.click();
            }

            if (secao === 'mensalistas') {
                carregarMensalistas();
                carregarClientesParaMensalista();
                carregarQuadrasParaMensalista();
            }

            if (secao === 'clientes') {
                carregarClientes();
            }

            if (secao === 'quadras') {
                carregarQuadras();
            }

            if (secao === 'configuracoes') {
                carregarConfiguracoes();
            }

            if (secao === 'pagamentos') {
                carregarReferenciasPagamento();
                carregarPagamentos();
            }

            if (secao === 'usuarios') {
                carregarUsuariosAdmin();
            }

            if (secao === 'relatorios') {
                carregarRelatorios();
            }

        });

    });

}


function temPermissaoAdmin(modulo, editar = false) {
    if (usuarioAdminAtual && usuarioAdminAtual.nivel === 'root') return true;
    const permissao = permissoesAdmin[modulo];
    return Boolean(permissao && (editar ? permissao.editar : permissao.visualizar));
}


function aplicarPermissoesPainel() {
    document.querySelectorAll('.menu-btn').forEach(botao => {
        const modulo = botao.dataset.section;
        const permitido = modulo === 'usuarios'
            ? usuarioAdminAtual.nivel === 'root'
            : temPermissaoAdmin(modulo);
        botao.hidden = !permitido;
    });

    document.querySelectorAll('.admin-section').forEach(secao => {
        const modulo = secao.id.replace('section-', '');
        const permitido = modulo === 'usuarios'
            ? usuarioAdminAtual.nivel === 'root'
            : temPermissaoAdmin(modulo);
        secao.hidden = !permitido;
        secao.classList.toggle(
            'admin-readonly',
            permitido && modulo !== 'usuarios' && !temPermissaoAdmin(modulo, true)
        );
        if (!permitido) secao.classList.remove('active');
    });

    const resumo = document.querySelector('.admin-container > .resumo');
    if (resumo) resumo.hidden = !temPermissaoAdmin('agendamentos');
}


function configurarUsuariosAdmin() {
    const formulario = document.getElementById('form-novo-usuario');
    const btnAtualizar = document.getElementById('btn-atualizar-usuarios');
    if (!formulario || !btnAtualizar) return;

    if (formulario.dataset.configurado !== 'true') {
        renderizarPermissoesUsuario('novo-admin-permissoes', 'novo', {});
        formulario.addEventListener('submit', criarUsuarioAdmin);
        btnAtualizar.addEventListener('click', async () => {
            await carregarQuadrasPermissao();
            await carregarUsuariosAdmin();
        });
        formulario.dataset.configurado = 'true';
    }
    carregarQuadrasPermissao().then(carregarUsuariosAdmin);
}

async function carregarQuadrasPermissao() {
    try {
        const resposta = await fetch('/admin/quadras');
        const resultado = await resposta.json();
        if (!resposta.ok) {
            throw new Error(resultado.detail || 'Não foi possível carregar as quadras.');
        }
        quadras = resultado;
        renderizarQuadrasPermissao('novo-admin-quadras', []);
    } catch (erro) {
        const mensagem = document.getElementById('mensagem-novo-usuario');
        if (mensagem) mensagem.textContent = erro.message;
    }
}

function renderizarQuadrasPermissao(containerId, selecionadas) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const ids = new Set((selecionadas || []).map(Number));
    container.innerHTML = quadras.map(quadra => `
        <label>
            <input type="checkbox" data-quadra-id="${Number(quadra.id)}"
                ${ids.has(Number(quadra.id)) ? 'checked' : ''}>
            ${escaparHTML(quadra.nome)} · ${escaparHTML(quadra.tipo)}
        </label>
    `).join('') || '<p>Nenhuma quadra disponível.</p>';
}

function lerQuadrasPermissao(container) {
    return [...container.querySelectorAll('[data-quadra-id]:checked')]
        .map(campo => Number(campo.dataset.quadraId));
}


function renderizarPermissoesUsuario(containerId, prefixo, permissoes) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = Object.entries(modulosAdmin).map(([modulo, titulo]) => {
        const acesso = permissoes[modulo] || {};
        const podeVer = Boolean(acesso.visualizar || acesso.editar);
        const podeEditar = Boolean(acesso.editar);
        return `
            <fieldset class="admin-permission-card">
                <legend>${escaparHTML(titulo)}</legend>
                <label>
                    <input type="checkbox" data-permission="${modulo}" data-level="visualizar"
                        ${podeVer ? 'checked' : ''}>
                    Visualizar
                </label>
                <label>
                    <input type="checkbox" data-permission="${modulo}" data-level="editar"
                        ${podeEditar ? 'checked' : ''}>
                    Editar
                </label>
            </fieldset>
        `;
    }).join('');

    container.querySelectorAll('[data-level="editar"]').forEach(campo => {
        campo.addEventListener('change', () => {
            if (campo.checked) {
                container.querySelector(
                    `[data-permission="${campo.dataset.permission}"][data-level="visualizar"]`
                ).checked = true;
            }
        });
    });
    container.dataset.prefix = prefixo;
}


function lerPermissoesUsuario(container) {
    return Object.fromEntries(
        Object.keys(modulosAdmin).map(modulo => {
            const ver = container.querySelector(
                `[data-permission="${modulo}"][data-level="visualizar"]`
            );
            const editar = container.querySelector(
                `[data-permission="${modulo}"][data-level="editar"]`
            );
            return [modulo, {
                visualizar: Boolean(ver && ver.checked),
                editar: Boolean(editar && editar.checked)
            }];
        })
    );
}


async function carregarUsuariosAdmin() {
    const lista = document.getElementById('lista-usuarios-admin');
    const mensagem = document.getElementById('mensagem-usuarios-admin');
    try {
        const resposta = await fetch('/admin/usuarios');
        const usuarios = await resposta.json();
        if (!resposta.ok) {
            throw new Error(usuarios.detail || 'Não foi possível carregar os usuários.');
        }
        mensagem.hidden = usuarios.length > 0;
        lista.innerHTML = usuarios.map(usuario => {
            const raiz = usuario.nivel === 'root';
            return `
                <article class="admin-user-card" data-admin-user="${usuario.id}">
                    <div class="admin-user-card-heading">
                        <div>
                            <strong>${escaparHTML(usuario.nome)}</strong>
                            <span>@${escaparHTML(usuario.usuario)} · ${raiz ? 'Raiz' : 'Administrador'}</span>
                        </div>
                        <label class="admin-user-active">
                            <input type="checkbox" data-user-active ${usuario.ativo ? 'checked' : ''}
                                ${raiz ? 'disabled' : ''}>
                            Ativo
                        </label>
                    </div>
                    <div class="admin-permission-grid">
                        ${Object.entries(modulosAdmin).map(([modulo, titulo]) => {
                            const acesso = usuario.permissoes[modulo] || {};
                            return `
                                <fieldset class="admin-permission-card">
                                    <legend>${escaparHTML(titulo)}</legend>
                                    <label><input type="checkbox" data-permission="${modulo}" data-level="visualizar"
                                        ${acesso.visualizar ? 'checked' : ''} ${raiz ? 'disabled' : ''}> Visualizar</label>
                                    <label><input type="checkbox" data-permission="${modulo}" data-level="editar"
                                        ${acesso.editar ? 'checked' : ''} ${raiz ? 'disabled' : ''}> Editar</label>
                                </fieldset>
                            `;
                        }).join('')}
                    </div>
                    <fieldset class="admin-permission-courts">
                        <legend>Quadras permitidas</legend>
                        <div class="admin-permission-grid" data-user-courts></div>
                    </fieldset>
                    ${raiz
                        ? '<p class="admin-root-note">A conta raiz tem acesso total e não pode ser alterada nesta tela.</p>'
                        : `<button type="button" class="btn-destaque" data-save-user="${usuario.id}">Salvar acessos</button>`}
                </article>
            `;
        }).join('');

        lista.querySelectorAll('[data-admin-user]').forEach(card => {
            const usuario = usuarios.find(item =>
                Number(item.id) === Number(card.dataset.adminUser)
            );
            const container = card.querySelector('[data-user-courts]');
            container.innerHTML = quadras.map(quadra => `
                <label>
                    <input type="checkbox" data-quadra-id="${Number(quadra.id)}"
                        ${(usuario.quadra_ids || []).map(Number).includes(Number(quadra.id)) ? 'checked' : ''}
                        ${usuario.nivel === 'root' ? 'disabled' : ''}>
                    ${escaparHTML(quadra.nome)} · ${escaparHTML(quadra.tipo)}
                </label>
            `).join('');
        });

        lista.querySelectorAll('[data-save-user]').forEach(botao => {
            botao.addEventListener('click', salvarPermissoesUsuario);
        });
    } catch (erro) {
        mensagem.hidden = false;
        mensagem.textContent = erro.message;
    }
}


async function criarUsuarioAdmin(event) {
    event.preventDefault();
    const mensagem = document.getElementById('mensagem-novo-usuario');
    const formulario = event.currentTarget;
    const permissaoContainer = document.getElementById('novo-admin-permissoes');
    const dados = {
        nome: document.getElementById('novo-admin-nome').value.trim(),
        usuario: document.getElementById('novo-admin-usuario').value.trim(),
        senha: document.getElementById('novo-admin-senha').value,
        permissoes: lerPermissoesUsuario(permissaoContainer),
        quadra_ids: lerQuadrasPermissao(
            document.getElementById('novo-admin-quadras')
        )
    };
    try {
        const resposta = await fetch('/admin/usuarios', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(dados)
        });
        const resultado = await resposta.json();
        if (!resposta.ok) throw new Error(resultado.detail || 'Não foi possível criar o usuário.');
        formulario.reset();
        renderizarPermissoesUsuario('novo-admin-permissoes', 'novo', {});
        mensagem.textContent = 'Usuário criado com sucesso.';
        await carregarUsuariosAdmin();
    } catch (erro) {
        mensagem.textContent = erro.message;
    }
}


async function salvarPermissoesUsuario(event) {
    const botao = event.currentTarget;
    const card = botao.closest('[data-admin-user]');
    const id = card.dataset.adminUser;
    const ativo = card.querySelector('[data-user-active]').checked;
    try {
        const resposta = await fetch(`/admin/usuarios/${encodeURIComponent(id)}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                ativo,
                permissoes: lerPermissoesUsuario(card),
                quadra_ids: lerQuadrasPermissao(
                    card.querySelector('[data-user-courts]')
                )
            })
        });
        const resultado = await resposta.json();
        if (!resposta.ok) throw new Error(resultado.detail || 'Não foi possível salvar os acessos.');
        await carregarUsuariosAdmin();
    } catch (erro) {
        alert(erro.message);
    }
}


// =========================================================
// PAGAMENTOS
// =========================================================

function configurarPagamentos() {

    const tipo = document.getElementById('pagamento-tipo');
    const reserva = document.getElementById('pagamento-reserva');
    const mensalidade = document.getElementById('pagamento-mensalidade');
    const atualizar = document.getElementById('btn-atualizar-pagamentos');
    const salvar = document.getElementById('btn-salvar-pagamento');

    tipo.addEventListener('change', atualizarFormularioPagamento);
    reserva.addEventListener('change', preencherValorPagamento);
    mensalidade.addEventListener('change', preencherValorPagamento);
    document.getElementById('fechar-historico-pagamento')
        .addEventListener('click', () =>
            document.getElementById('pagamento-historico-dialog').close()
        );
    atualizar.addEventListener('click', () => {
        carregarReferenciasPagamento();
        carregarPagamentos();
    });
    salvar.addEventListener('click', salvarPagamento);

    atualizarFormularioPagamento();
    document.getElementById('pagamento-competencia').value =
        dataLocalISO(new Date()).slice(0, 7);

}

function atualizarFormularioPagamento() {

    const mensalidadeSelecionada =
        document.getElementById('pagamento-tipo').value === 'Mensalidade';

    document.getElementById('pagamento-reserva-field').hidden =
        mensalidadeSelecionada;
    document.getElementById('pagamento-mensalidade-field').hidden =
        !mensalidadeSelecionada;
    document.getElementById('pagamento-competencia-field').hidden =
        !mensalidadeSelecionada;

    preencherSelectsPagamento();
    preencherValorPagamento();

}

function preencherSelectsPagamento() {

    const reservaSelect =
        document.getElementById('pagamento-reserva');
    const mensalidadeSelect =
        document.getElementById('pagamento-mensalidade');

    if (reservaSelect) {
        const atual = reservaSelect.value;
        reservaSelect.innerHTML =
            '<option value="">Selecione uma reserva</option>';
        agendamentos
            .filter(item =>
                ['Pendente', 'Confirmado'].includes(item.status)
            )
            .forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent =
                    `#${item.id} · ${item.cliente} · ${item.quadra} · ` +
                    `${formatarData(item.data)} ${formatarHorario(item.horario)} · ` +
                    `Taxa ${formatarMoeda(item.taxa_reserva || 0)}`;
                reservaSelect.appendChild(option);
            });
        reservaSelect.value = atual;
    }

    if (mensalidadeSelect) {
        const atual = mensalidadeSelect.value;
        mensalidadeSelect.innerHTML =
            '<option value="">Selecione uma mensalidade</option>';
        mensalistas.forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent =
                    `${item.cliente} · ${item.quadra} · ` +
                    `${nomeDiaSemana(item.dia_semana)} ${formatarHorario(item.horario)} · ` +
                    `${formatarMoeda(item.valor_mensal)}/mês · ${item.status}`;
                mensalidadeSelect.appendChild(option);
            });
        mensalidadeSelect.value = atual;
    }

}

function preencherValorPagamento() {

    const ehMensalidade =
        document.getElementById('pagamento-tipo').value === 'Mensalidade';
    const select = document.getElementById(
        ehMensalidade ? 'pagamento-mensalidade' : 'pagamento-reserva'
    );
    const registro = ehMensalidade
        ? mensalistas.find(item => Number(item.id) === Number(select.value))
        : agendamentos.find(item => Number(item.id) === Number(select.value));

    document.getElementById('pagamento-valor').value =
        registro
            ? Number(ehMensalidade ? registro.valor_mensal : registro.taxa_reserva || 0)
            : 0;

}


async function carregarReferenciasPagamento() {
    try {
        const resposta = await fetch('/pagamentos/referencias');
        const dados = await resposta.json();
        if (!resposta.ok) {
            throw new Error(dados.detail || 'Erro ao carregar referências dos pagamentos.');
        }
        agendamentos = dados.agendamentos;
        mensalistas = dados.mensalidades;
        preencherSelectsPagamento();
        preencherValorPagamento();
    } catch (erro) {
        console.error(erro);
        alert(erro.message);
    }
}


async function carregarPagamentos() {

    try {
        const response = await fetch('/pagamentos');
        const resultado = await response.json();
        if (!response.ok) {
            throw new Error(resultado.detail || 'Erro ao carregar pagamentos.');
        }
        renderizarPagamentos(resultado);
    } catch (erro) {
        console.error(erro);
        mostrarErroTabela('lista-pagamentos', 'Erro ao carregar pagamentos.');
    }

}

function renderizarPagamentos(pagamentos) {

    const tbody = document.getElementById('lista-pagamentos');
    const empty = document.getElementById('mensagem-pagamentos');
    tbody.innerHTML = '';
    empty.style.display = pagamentos.length ? 'none' : 'block';

    pagamentos.forEach(item => {
        const linha = document.createElement('tr');
        const legado = String(item.id).startsWith('mensalidade-legada-');
        const id = escaparAtributo(item.id);
        linha.innerHTML = `
            <td>${formatarData(item.data_pagamento || item.criado_em)}</td>
            <td>${escaparHTML(item.cliente || '')}</td>
            <td>${escaparHTML(item.tipo)} · ${escaparHTML(item.quadra || '-')}</td>
            <td>${escaparHTML(item.competencia || '-')}</td>
            <td>${formatarMoeda(item.valor)}</td>
            <td>${formatarMoeda(item.taxa_reserva)}</td>
            <td>${formatarMoeda(item.valor_total)}</td>
            <td>${formatarMoeda(item.valor_pago)}</td>
            <td>${escaparHTML(item.forma_pagamento || '-')}</td>
            <td>${escaparHTML(item.status)}</td>
            <td>
                ${
                    legado
                        ? 'Histórico antigo'
                        : `<select class="payment-status" data-id="${id}">
                            ${['Pendente', 'Recebido', 'Cancelado'].map(status =>
                                `<option value="${status}" ${item.status === status ? 'selected' : ''}>${status}</option>`
                            ).join('')}
                           </select>
                           <button type="button" class="payment-history"
                               data-id="${id}">Histórico</button>`
                }
            </td>
        `;
        tbody.appendChild(linha);
    });

    tbody.querySelectorAll('.payment-status').forEach(select => {
        select.addEventListener('change', atualizarStatusPagamento);
    });
    tbody.querySelectorAll('.payment-history').forEach(button => {
        button.addEventListener('click', () =>
            carregarHistoricoPagamento(button.dataset.id)
        );
    });

}

async function carregarHistoricoPagamento(id) {

    const dialog = document.getElementById('pagamento-historico-dialog');
    const conteudo = document.getElementById('pagamento-historico-conteudo');
    conteudo.textContent = 'Carregando histórico...';
    dialog.showModal();

    try {
        const response = await fetch(
            `/pagamentos/${encodeURIComponent(id)}/historico`
        );
        const historico = await response.json();
        if (!response.ok) {
            throw new Error(historico.detail || 'Erro ao carregar histórico.');
        }
        conteudo.innerHTML = historico.length
            ? `<ol>${historico.map(item => `
                <li>
                    <strong>${escaparHTML(item.status_anterior)}</strong>
                    → ${escaparHTML(item.status_novo)}
                    <small>${escaparHTML(item.alterado_em)}</small>
                </li>
              `).join('')}</ol>`
            : '<p>Nenhuma alteração de status registrada.</p>';
    } catch (erro) {
        conteudo.textContent = erro.message;
    }

}

async function salvarPagamento() {

    const ehMensalidade =
        document.getElementById('pagamento-tipo').value === 'Mensalidade';
    const referencia = document.getElementById(
        ehMensalidade ? 'pagamento-mensalidade' : 'pagamento-reserva'
    ).value;
    if (!referencia) {
        alert(ehMensalidade
            ? 'Selecione uma mensalidade.'
            : 'Selecione uma reserva.');
        return;
    }

    const status = document.getElementById('pagamento-status').value;
    const valorPago = Number(document.getElementById('pagamento-valor').value);
    const pagamento = {
        [ehMensalidade ? 'mensalidade_id' : 'agendamento_id']:
            Number(referencia),
        competencia: ehMensalidade
            ? document.getElementById('pagamento-competencia').value
            : null,
        valor_pago: status === 'Recebido' ? valorPago : 0,
        data_pagamento:
            document.getElementById('pagamento-data').value || null,
        forma_pagamento:
            document.getElementById('pagamento-forma').value || null,
        status,
        observacao:
            document.getElementById('pagamento-observacao').value.trim() || null
    };

    try {
        const response = await fetch('/pagamentos', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(pagamento)
        });
        const resultado = await response.json();
        if (!response.ok) {
            throw new Error(resultado.detail || 'Erro ao registrar pagamento.');
        }
        alert('Pagamento registrado com sucesso.');
        document.getElementById('pagamento-observacao').value = '';
        await carregarPagamentos();
    } catch (erro) {
        console.error(erro);
        alert(erro.message);
    }

}

async function atualizarStatusPagamento(event) {

    const select = event.target;
    const id = select.dataset.id;
    const pagamento = {
        status: select.value
    };
    if (pagamento.status === 'Recebido') {
        const valorAtual = prompt('Informe o valor recebido:');
        if (valorAtual === null) {
            await carregarPagamentos();
            return;
        }
        pagamento.valor_pago = Number(valorAtual);
        pagamento.forma_pagamento =
            prompt('Forma de pagamento (PIX, Dinheiro, Cartão ou Outro):');
        pagamento.data_pagamento = dataLocalISO(new Date());
    }

    try {
        const response = await fetch(`/pagamentos/${encodeURIComponent(id)}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(pagamento)
        });
        const resultado = await response.json();
        if (!response.ok) {
            throw new Error(resultado.detail || 'Erro ao atualizar pagamento.');
        }
        await carregarPagamentos();
    } catch (erro) {
        console.error(erro);
        alert(erro.message);
        await carregarPagamentos();
    }

}


// =========================================================
// RELATÓRIOS E GRÁFICOS
// =========================================================

function configurarRelatorios() {

    const hoje = new Date();
    const inicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
    document.getElementById('relatorio-inicio').value =
        dataLocalISO(inicio);
    document.getElementById('relatorio-fim').value =
        dataLocalISO(hoje);
    document.getElementById('relatorio-periodo').value = 'month';

    document.getElementById('btn-atualizar-relatorios')
        .addEventListener('click', carregarRelatorios);

    document.getElementById('relatorio-periodo')
        .addEventListener('change', aplicarPeriodoRelatorio);
    document.getElementById('relatorio-inativo-dias')
        .addEventListener('change', event => {
            const custom = document.getElementById('relatorio-inativo-custom');
            custom.hidden = event.target.value !== 'custom';
            if (event.target.value !== 'custom') carregarRelatorios();
        });
    document.getElementById('relatorio-inativo-custom')
        .addEventListener('change', carregarRelatorios);
    ['relatorio-inicio', 'relatorio-fim'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            document.getElementById('relatorio-periodo').value = 'custom';
        });
    });
    document.querySelectorAll('[data-report-tab]').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('[data-report-tab]').forEach(tab =>
                tab.classList.toggle('active', tab === button)
            );
            document.querySelectorAll('[data-report-pane]').forEach(pane => {
                const active = pane.dataset.reportPane === button.dataset.reportTab;
                pane.hidden = !active;
                pane.classList.toggle('active', active);
            });
        });
    });
    preencherFiltroRelatorio();

}

function aplicarPeriodoRelatorio(event) {
    const choice = event.currentTarget.value;
    if (choice === 'custom') return;
    const today = new Date();
    let start;
    let end = new Date(today);
    if (choice === 'today') {
        start = new Date(today);
    } else if (choice === '7days') {
        start = new Date(today);
        start.setDate(today.getDate() - 6);
    } else if (choice === '30days') {
        start = new Date(today);
        start.setDate(today.getDate() - 29);
    } else if (choice === 'month') {
        start = new Date(today.getFullYear(), today.getMonth(), 1);
    } else if (choice === 'previous-month') {
        start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        end = new Date(today.getFullYear(), today.getMonth(), 0);
    }
    document.getElementById('relatorio-inicio').value = dataLocalISO(start);
    document.getElementById('relatorio-fim').value = dataLocalISO(end);
}

function dataLocalISO(data) {
    return [
        data.getFullYear(),
        String(data.getMonth() + 1).padStart(2, '0'),
        String(data.getDate()).padStart(2, '0')
    ].join('-');
}

async function preencherFiltroRelatorio() {

    try {
        const response = await fetch('/admin/escopo-quadras');
        const lista = await response.json();
        if (!response.ok) {
            throw new Error('Não foi possível carregar as quadras do relatório.');
        }
        const select = document.getElementById('relatorio-quadra');
        lista.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.nome;
            select.appendChild(option);
        });
    } catch (erro) {
        console.error(erro);
    }

}

async function carregarRelatorios() {

    const params = new URLSearchParams({
        inicio: document.getElementById('relatorio-inicio').value,
        fim: document.getElementById('relatorio-fim').value
    });
    const quadra = document.getElementById('relatorio-quadra').value;
    const tipo = document.getElementById('relatorio-tipo').value;
    if (quadra) params.set('quadra_id', quadra);
    if (tipo) params.set('tipo_quad', tipo);
    const inatividade = document.getElementById('relatorio-inativo-dias').value;
    const customInatividade = document.getElementById('relatorio-inativo-custom').value;
    params.set(
        'inativo_dias',
        inatividade === 'custom' ? customInatividade : inatividade
    );

    try {
        const response = await fetch(`/relatorios?${params}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'Erro ao consultar relatórios.');
        }
        renderizarResumoRelatorio(data.resumo);
        renderizarGraficoBarras(
            'grafico-reservas',
            data.reservas_por_periodo,
            [['total', 'Solicitações', '#45b7d1']],
            false,
            'dia',
            'line',
            [
                ['confirmadas', 'Confirmadas'],
                ['pendentes', 'Pendentes'],
                ['canceladas', 'Canceladas'],
                ['nao_atendidas', 'Não atendidas']
            ]
        );
        renderizarGraficoBarras(
            'grafico-pagamentos',
            data.pagamentos_por_periodo,
            [['recebido', 'Recebido', '#38c172']],
            true,
            'dia',
            'line',
            [['taxas', 'Taxas']]
        );
        renderizarGraficoBarras(
            'grafico-comparacao',
            [
                {
                    periodo: 'Atual',
                    reservas: data.comparacao_periodos.atual.reservas,
                    confirmadas: data.comparacao_periodos.atual.confirmadas
                },
                {
                    periodo: 'Anterior',
                    reservas: data.comparacao_periodos.anterior.reservas,
                    confirmadas: data.comparacao_periodos.anterior.confirmadas
                }
            ],
            [
                ['reservas', 'Solicitações', '#45b7d1'],
                ['confirmadas', 'Confirmadas', '#38c172']
            ],
            false,
            'periodo',
            'vertical'
        );
        renderizarDashboardDetalhado(data);
    } catch (erro) {
        console.error(erro);
        document.getElementById('relatorio-resumo').textContent =
            erro.message;
    }

}

function renderizarResumoRelatorio(resumo) {

    const campos = [
        ['Solicitações', resumo.reservas],
        ['Confirmadas', resumo.confirmadas],
        ['Pendentes', resumo.pendentes],
        ['Não atendidas', resumo.nao_atendidas],
        ['Canceladas', resumo.canceladas],
        ['Jogos futuros · 30 dias', resumo.jogos_futuros],
        ['Conversão', `${resumo.taxa_conversao_percentual}%`],
        ['Utilização', `${resumo.utilizacao_periodo_percentual}%`],
        ['Faturado no período', formatarMoeda(resumo.faturamento_periodo)],
        ['Recebido no período', formatarMoeda(resumo.recebido_periodo)],
        ['A receber', formatarMoeda(resumo.total_a_receber)],
        ['Mensalistas ativos', resumo.mensalistas_ativos]
    ];
    document.getElementById('relatorio-resumo').innerHTML =
        campos.map(([label, valor]) => `
            <div class="resumo-card">
                <span>${escaparHTML(label)}</span>
                <strong>${escaparHTML(valor)}</strong>
            </div>
        `).join('');

}

function renderizarDashboardDetalhado(data) {
    const summary = data.resumo;
    renderizarGraficoDonut('relatorio-funil', data.funil);

    renderizarTarjetas('relatorio-futuros', [
        ['Hoje', data.jogos_futuros.hoje],
        ['Amanhã', data.jogos_futuros.amanha],
        ['Próximos 7 dias', data.jogos_futuros.proximos_7_dias],
        ['Próximos 30 dias', data.jogos_futuros.proximos_30_dias],
        ['Pendentes futuros', data.jogos_futuros.pendentes_futuros]
    ]);

    renderizarGraficoBarras(
        'grafico-demanda-semana',
        data.demanda_dia_semana,
        [
            ['solicitacoes', 'Solicitações', '#45b7d1']
        ],
        false,
        'dia',
        'vertical'
    );
    renderizarGraficoBarras(
        'grafico-demanda-horario',
        data.demanda_horario,
        [
            ['pendentes', 'Pendentes', '#f0b429'],
            ['confirmadas', 'Confirmadas', '#38c172'],
            ['canceladas', 'Canceladas', '#e55353'],
            ['nao_atendidas', 'Não atendidas', '#858b94']
        ],
        false,
        'horario',
        'stacked-horizontal',
        [['solicitacoes', 'Solicitações']]
    );
    renderizarTablaReporte('horarios-mais', [
        ['Horário', item => escaparHTML(item.horario)],
        ['Solicitações', item => item.solicitacoes]
    ], data.horarios_mais_requisitados, 'Sem solicitações no período.');
    renderizarTablaReporte('horarios-menos', [
        ['Horário', item => escaparHTML(item.horario)],
        ['Solicitações', item => item.solicitacoes]
    ], data.horarios_menos_requisitados, 'Sem horários disponíveis no período.');
    renderizarGraficoBarras(
        'grafico-demanda-quadras',
        data.demanda_quadras,
        [
            ['pendentes', 'Pendentes', '#f0b429'],
            ['confirmadas', 'Confirmadas', '#38c172'],
            ['canceladas', 'Canceladas', '#e55353'],
            ['nao_atendidas', 'Não atendidas', '#858b94']
        ],
        false,
        'quadra',
        'stacked-horizontal',
        [['solicitacoes', 'Solicitações']]
    );
    renderizarGraficoBarras(
        'grafico-utilizacao',
        data.utilizacao_periodo.por_quadra,
        [['utilizacao_percentual', 'Utilização', '#38c172']],
        false,
        'quadra',
        'horizontal'
    );
    renderizarMapaCalor(data.mapa_calor);
    renderizarGraficoBarras(
        'grafico-cancelamentos',
        data.cancelamentos.evolucao,
        [['cancelamentos', 'Cancelamentos', '#e55353']],
        false,
        'dia',
        'line'
    );
    renderizarGraficoBarras(
        'grafico-cancel-semana',
        data.cancelamentos.por_dia_semana,
        [['cancelamentos', 'Cancelamentos', '#e55353']],
        false,
        'dia',
        'vertical'
    );
    renderizarTablaReporte('relatorio-cancel-horario', [
        ['Horário', item => escaparHTML(item.horario)],
        ['Cancelamentos', item => item.cancelamentos]
    ], data.cancelamentos.por_horario);
    renderizarTablaReporte('relatorio-cancel-quadra', [
        ['Quadra', item => escaparHTML(item.quadra)],
        ['Cancelamentos', item => item.cancelamentos]
    ], data.cancelamentos.por_quadra);
    renderizarTablaReporte('relatorio-cancel-cliente', [
        ['Cliente', item => escaparHTML(item.cliente)],
        ['Cancelamentos', item => item.cancelamentos]
    ], data.cancelamentos.por_cliente);
    renderizarTablaReporte('relatorio-utilizacao-dia', [
        ['Dia', item => escaparHTML(formatarData(item.dia))],
        ['Ocupadas / disponíveis', item => `${item.horas_ocupadas} / ${item.horas_disponiveis}`],
        ['Utilização', item => `${item.utilizacao_percentual}%`]
    ], data.utilizacao_periodo.por_dia);
    renderizarTablaReporte('relatorio-utilizacao-mes', [
        ['Mês', item => escaparHTML(item.mes)],
        ['Ocupadas / disponíveis', item => `${item.horas_ocupadas} / ${item.horas_disponiveis}`],
        ['Utilização', item => `${item.utilizacao_percentual}%`]
    ], data.utilizacao_periodo.por_mes);
    renderizarTarjetas('relatorio-extremos-mensais', [
        ['Maior demanda', data.demanda_mensal.maior_demanda
            ? `${data.demanda_mensal.maior_demanda.mes} · ${data.demanda_mensal.maior_demanda.solicitacoes} solicitações`
            : 'Sem dados'],
        ['Menor demanda', data.demanda_mensal.menor_demanda
            ? `${data.demanda_mensal.menor_demanda.mes} · ${data.demanda_mensal.menor_demanda.solicitacoes} solicitações`
            : 'Sem dados'],
        ['Cancelamentos no período', `${data.cancelamentos.total} · ${data.cancelamentos.percentual}%`]
    ]);
    renderizarTarjetas('relatorio-financeiro-resumo', [
        ['Faturado hoje', formatarMoeda(summary.faturamento_dia)],
        ['Faturado no mês', formatarMoeda(summary.faturamento_mes)],
        ['Faturado no período', formatarMoeda(summary.faturamento_periodo)],
        ['Recebido hoje', formatarMoeda(summary.recebido_dia)],
        ['Recebido no mês', formatarMoeda(summary.recebido_mes)],
        ['Recebido no período', formatarMoeda(summary.recebido_periodo)],
        ['A receber hoje', formatarMoeda(data.contas_a_receber.hoje)],
        ['A receber em 7 dias', formatarMoeda(data.contas_a_receber.proximos_7_dias)],
        ['A receber no mês', formatarMoeda(data.contas_a_receber.mes)],
        ['Total a receber', formatarMoeda(data.contas_a_receber.total)]
    ]);
    renderizarGraficoBarras(
        'grafico-financeiro-quadras',
        data.demanda_quadras,
        [['faturado', 'Faturado', '#38c172']],
        true,
        'quadra',
        'horizontal'
    );
    renderizarGraficoBarras(
        'grafico-financeiro-semana',
        data.demanda_dia_semana,
        [['faturado', 'Faturado', '#38c172']],
        true,
        'dia',
        'vertical'
    );
    renderizarGraficoBarras(
        'grafico-financeiro-mes',
        data.demanda_mensal.meses,
        [['faturado', 'Faturado', '#38c172']],
        true,
        'mes',
        'line'
    );
    renderizarTablaReporte('relatorio-contas-receber', [
        ['Vencimento', item => escaparHTML(formatarData(item.vencimento))],
        ['Referência', item => escaparHTML(item.referencia)],
        ['Cliente', item => escaparHTML(item.cliente)],
        ['Quadra', item => escaparHTML(item.quadra)],
        ['Saldo', item => formatarMoeda(item.valor)]
    ], data.contas_a_receber.lancamentos, 'Nenhum valor a receber no momento.');
    renderizarTablaReporte('relatorio-clientes-top', [
        ['Posição', (_, index) => index + 1],
        ['Cliente', item => escaparHTML(item.cliente)],
        ['Jogos', item => item.jogos],
        ['Valor gerado', item => formatarMoeda(item.valor_gerado)],
        ['Último jogo', item => escaparHTML(formatarData(item.ultimo_jogo))]
    ], data.clientes_top);
    renderizarTablaReporte('relatorio-clientes-mes', [
        ['Posição', (_, index) => index + 1],
        ['Cliente', item => escaparHTML(item.cliente)],
        ['Jogos', item => item.jogos],
        ['Valor gerado', item => formatarMoeda(item.valor_gerado)],
        ['Quadra mais utilizada', item => escaparHTML(item.quadra_mais_utilizada)]
    ], data.clientes_top_mes);
    renderizarTablaReporte('relatorio-clientes-inativos', [
        ['Cliente', item => escaparHTML(item.cliente)],
        ['Contato', item => escaparHTML(item.contato)],
        ['Último jogo', item => escaparHTML(formatarData(item.ultimo_jogo))]
    ], data.clientes_inativos.clientes, `Nenhum cliente sem jogo confirmado nos últimos ${data.clientes_inativos.periodo_dias} dias.`);
    renderizarTarjetas('relatorio-mensalistas-resumo', [
        ['Ativos no início', data.mensalistas.ativos_inicio],
        ['Novos no período', data.mensalistas.novos],
        ['Ativos no fim', data.mensalistas.ativos_fim],
        ['Abandonos', data.mensalistas.cancelados],
        ['Taxa de abandono', `${data.mensalistas.abandono_percentual}%`]
    ]);
    renderizarTablaReporte('relatorio-mensalistas-top', [
        ['Mensalista', item => escaparHTML(item.cliente)],
        ['Jogos no período', item => item.jogos],
        ['Valor mensal', item => formatarMoeda(item.valor_mensal)],
        ['Último jogo', item => escaparHTML(formatarData(item.ultimo_jogo))],
        ['Status', item => escaparHTML(item.status)]
    ], data.mensalistas.ranking);
    renderizarGraficoBarras(
        'grafico-abandono-mensalistas',
        data.mensalistas.abandono_por_mes,
        [['cancelados', 'Mensalistas encerrados', '#e55353']],
        false,
        'mes',
        'line'
    );
}

function renderizarTarjetas(containerId, items) {
    const container = document.getElementById(containerId);
    container.innerHTML = items.map(([label, value]) => `
        <div class="report-mini-kpi">
            <span>${escaparHTML(label)}</span>
            <strong>${escaparHTML(value)}</strong>
        </div>
    `).join('');
}

function renderizarTablaReporte(containerId, columns, rows, emptyText) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!rows || !rows.length) {
        container.innerHTML = `<p class="report-empty">${escaparHTML(emptyText || 'Sem dados para o período selecionado.')}</p>`;
        return;
    }
    container.innerHTML = `
        <div class="report-table-scroll">
            <table class="report-table">
                <thead><tr>${columns.map(([label]) => `<th>${escaparHTML(label)}</th>`).join('')}</tr></thead>
                <tbody>${rows.map((row, index) => `
                    <tr>${columns.map(([, render]) => `<td>${render(row, index)}</td>`).join('')}</tr>
                `).join('')}</tbody>
            </table>
        </div>
    `;
}

function renderizarMapaCalor(mapa) {
    const container = document.getElementById('relatorio-mapa-calor');
    const maximo = Math.max(1, ...mapa.quadras.flatMap(row => row.valores));
    if (!mapa.quadras.length || !mapa.horarios.length) {
        container.innerHTML = '<p class="report-empty">Sem quadras ou horários disponíveis.</p>';
        return;
    }
    container.innerHTML = `
        <div class="report-table-scroll">
            <table class="report-heatmap">
                <thead><tr><th>Quadra / horário</th>${mapa.horarios.map(hour => `<th>${escaparHTML(hour)}</th>`).join('')}</tr></thead>
                <tbody>${mapa.quadras.map(court => `
                    <tr><th>${escaparHTML(court.quadra)}</th>${court.valores.map(value => {
                        const intensidade = Number(value) / maximo;
                        const estilo = Number(value)
                            ? ` style="background:rgba(56,193,114,${(0.16 + intensidade * 0.72).toFixed(2)})"`
                            : '';
                        return `<td title="${Number(value)} solicitações"${estilo}>${Number(value)}</td>`;
                    }).join('')}</tr>
                `).join('')}</tbody>
            </table>
        </div>
    `;
}

function renderizarGraficoDonut(containerId, funil) {
    const container = document.getElementById(containerId);
    const total = Number(funil[0]?.quantidade || 0);
    const cores = {
        Confirmadas: '#38c172',
        Pendentes: '#f0b429',
        Canceladas: '#e55353',
        'Não atendidas': '#858b94'
    };
    const partes = funil.slice(1);
    let acumulado = 0;
    const gradientes = partes.map(item => {
        const percentual = total ? Number(item.quantidade || 0) / total * 100 : 0;
        const inicio = acumulado;
        acumulado += percentual;
        return `${cores[item.status] || '#45b7d1'} ${inicio}% ${acumulado}%`;
    });
    const legenda = partes.map(item => `
        <li>
            <span><i style="background:${cores[item.status] || '#45b7d1'}"></i>
                ${escaparHTML(item.status)}</span>
            <strong>${Number(item.quantidade).toLocaleString('pt-BR')}
                <small>${Number(item.percentual).toLocaleString('pt-BR')}%</small>
            </strong>
        </li>
    `).join('');

    container.innerHTML = total
        ? `
            <div class="report-donut-layout">
                <div class="report-donut" role="img"
                    aria-label="${total} solicitações distribuídas por status"
                    style="--report-donut:conic-gradient(${gradientes.join(',')})">
                    <div><strong>${total.toLocaleString('pt-BR')}</strong><span>solicitações</span></div>
                </div>
                <ul class="report-donut-legend">${legenda}</ul>
            </div>
        `
        : '<p class="report-empty">Sem solicitações no período selecionado.</p>';
}

function renderizarGraficoBarras(
    id,
    registros,
    series,
    moeda,
    labelKey = 'dia',
    tipo = 'vertical',
    tooltipKeys = []
) {
    const container = document.getElementById(id);
    if (!container) return;
    if (!registros?.length) {
        container.innerHTML =
            '<p class="report-empty">Sem dados para o período selecionado.</p>';
        return;
    }
    const largura = 900;
    const margemDireita = 24;
    const margemInferior = 46;
    const margemTopo = 18;
    const margemEsquerda = ['horizontal', 'stacked-horizontal'].includes(tipo)
        ? 164
        : moeda ? 88 : 54;
    const plotWidth = largura - margemEsquerda - margemDireita;
    const formatoValor = valor => moeda
        ? formatarMoeda(valor)
        : Number(valor).toLocaleString('pt-BR');
    const rotuloData = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value))
        ? formatarData(value).slice(0, 5)
        : String(value ?? '');
    const nomeCompleto = item => String(item[labelKey] ?? '');
    const textoTooltip = (item, seriesLabel, value) => {
        const detalhes = tooltipKeys.map(([key, label]) =>
            `${label}: ${formatoValor(item[key] || 0)}`
        );
        return [
            nomeCompleto(item),
            `${seriesLabel}: ${formatoValor(value)}`,
            ...detalhes
        ].join(' · ');
    };
    const legend = series.map(([, label, color]) =>
        `<span><i style="background:${color}"></i>${escaparHTML(label)}</span>`
    ).join('');
    let svg;

    if (tipo === 'line') {
        const altura = 286;
        const plotHeight = altura - margemTopo - margemInferior;
        const maximo = Math.max(1, ...registros.flatMap(item =>
            series.map(([key]) => Number(item[key] || 0))
        ));
        const xAt = index => margemEsquerda +
            (registros.length === 1 ? plotWidth / 2 : index * plotWidth / (registros.length - 1));
        const yAt = value => margemTopo + plotHeight - Number(value || 0) / maximo * plotHeight;
        const grid = Array.from({ length: 5 }, (_, index) => {
            const value = maximo * (4 - index) / 4;
            const y = margemTopo + plotHeight * index / 4;
            return `
                <line x1="${margemEsquerda}" y1="${y}" x2="${largura - margemDireita}"
                    y2="${y}" class="report-chart-gridline" />
                <text x="${margemEsquerda - 10}" y="${y + 4}" text-anchor="end"
                    class="report-chart-axis">${escaparHTML(formatoValor(value))}</text>
            `;
        }).join('');
        const step = Math.max(1, Math.ceil(registros.length / 8));
        const labels = registros.map((item, index) => {
            if (index % step !== 0 && index !== registros.length - 1) return '';
            return `<text x="${xAt(index)}" y="${altura - 13}" text-anchor="middle"
                class="report-chart-axis">${escaparHTML(rotuloData(item[labelKey]))}</text>`;
        }).join('');
        const lines = series.map(([key, label, color]) => {
            const points = registros.map((item, index) =>
                `${xAt(index).toFixed(1)},${yAt(item[key]).toFixed(1)}`
            ).join(' ');
            const pointRadius = registros.length > 30 ? 5 : 3.2;
            const dots = registros.map((item, index) => `
                <circle cx="${xAt(index).toFixed(1)}" cy="${yAt(item[key]).toFixed(1)}"
                    r="${pointRadius}" fill="${color}" class="report-chart-point">
                    <title>${escaparHTML(textoTooltip(item, label, item[key]))}</title>
                </circle>
            `).join('');
            return `<polyline points="${points}" fill="none" stroke="${color}"
                stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />${dots}`;
        }).join('');
        svg = `
            <svg viewBox="0 0 ${largura} ${altura}" role="img"
                aria-label="Gráfico de linhas: ${escaparAtributo(id)}">
                ${grid}${lines}${labels}
            </svg>`;
    } else if (tipo === 'horizontal' || tipo === 'stacked-horizontal') {
        const rowHeight = tipo === 'stacked-horizontal' ? 32 : 38;
        const altura = Math.max(118, margemTopo + registros.length * rowHeight + margemInferior);
        const barsHeight = altura - margemTopo - margemInferior;
        const totais = registros.map(item => tipo === 'stacked-horizontal'
            ? series.reduce((total, [key]) => total + Number(item[key] || 0), 0)
            : Math.max(...series.map(([key]) => Number(item[key] || 0)))
        );
        const maximo = Math.max(1, ...totais);
        const grid = Array.from({ length: 5 }, (_, index) => {
            const value = maximo * index / 4;
            const x = margemEsquerda + plotWidth * index / 4;
            return `
                <line x1="${x}" y1="${margemTopo}" x2="${x}" y2="${altura - margemInferior}"
                    class="report-chart-gridline" />
                <text x="${x}" y="${altura - 14}" text-anchor="middle"
                    class="report-chart-axis">${escaparHTML(formatoValor(value))}</text>
            `;
        }).join('');
        const bars = registros.map((item, index) => {
            const centerY = margemTopo + rowHeight * index + rowHeight / 2;
            const fullName = nomeCompleto(item);
            const visibleName = fullName.length > 22 ? `${fullName.slice(0, 21)}…` : fullName;
            let offset = 0;
            const segments = series.map(([key, label, color]) => {
                const value = Number(item[key] || 0);
                const width = value / maximo * plotWidth;
                const x = margemEsquerda + offset;
                offset += width;
                return width <= 0 ? '' : `
                    <rect x="${x}" y="${centerY - 9}" width="${width}" height="18"
                        rx="3" fill="${color}">
                        <title>${escaparHTML(textoTooltip(item, label, value))}</title>
                    </rect>`;
            }).join('');
            return `
                <text x="${margemEsquerda - 12}" y="${centerY + 4}" text-anchor="end"
                    class="report-chart-category">
                    <title>${escaparHTML(fullName)}</title>${escaparHTML(visibleName)}
                </text>
                ${segments}
            `;
        }).join('');
        svg = `
            <svg viewBox="0 0 ${largura} ${altura}" role="img"
                aria-label="Gráfico de barras horizontais: ${escaparAtributo(id)}">
                ${grid}${bars}
            </svg>`;
    } else {
        const altura = 286;
        const plotHeight = altura - margemTopo - margemInferior;
        const maximo = Math.max(1, ...registros.flatMap(item =>
            tipo === 'stacked-vertical'
                ? [series.reduce((total, [key]) => total + Number(item[key] || 0), 0)]
                : series.map(([key]) => Number(item[key] || 0))
        ));
        const groupWidth = plotWidth / registros.length;
        const groupPadding = Math.min(14, groupWidth * 0.16);
        const barWidth = Math.max(2, Math.min(32,
            (groupWidth - groupPadding * 2) / (tipo === 'stacked-vertical' ? 1 : series.length)
        ));
        const yAt = value => margemTopo + plotHeight - Number(value || 0) / maximo * plotHeight;
        const grid = Array.from({ length: 5 }, (_, index) => {
            const value = maximo * (4 - index) / 4;
            const y = margemTopo + plotHeight * index / 4;
            return `
                <line x1="${margemEsquerda}" y1="${y}" x2="${largura - margemDireita}"
                    y2="${y}" class="report-chart-gridline" />
                <text x="${margemEsquerda - 10}" y="${y + 4}" text-anchor="end"
                    class="report-chart-axis">${escaparHTML(formatoValor(value))}</text>
            `;
        }).join('');
        const bars = registros.map((item, index) => {
            const groupCenter = margemEsquerda + groupWidth * (index + 0.5);
            const fullName = nomeCompleto(item);
            let offset = 0;
            const rects = series.map(([key, label, color], seriesIndex) => {
                const value = Number(item[key] || 0);
                const height = Math.max(0, plotHeight * value / maximo);
                let x;
                let y;
                if (tipo === 'stacked-vertical') {
                    x = groupCenter - barWidth / 2;
                    y = yAt(offset + value);
                    offset += value;
                } else {
                    const totalWidth = series.length * barWidth;
                    x = groupCenter - totalWidth / 2 + seriesIndex * barWidth;
                    y = yAt(value);
                }
                return height <= 0 ? '' : `
                    <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}"
                        width="${Math.max(1, barWidth - 3).toFixed(1)}"
                        height="${height.toFixed(1)}" rx="3" fill="${color}">
                        <title>${escaparHTML(textoTooltip(item, label, value))}</title>
                    </rect>`;
            }).join('');
            const label = tipo === 'vertical' ? rotuloData(fullName) :
                (fullName.length > 12 ? `${fullName.slice(0, 11)}…` : fullName);
            return `
                ${rects}
                <text x="${groupCenter}" y="${altura - 14}" text-anchor="middle"
                    class="report-chart-axis">
                    <title>${escaparHTML(fullName)}</title>${escaparHTML(label)}
                </text>
            `;
        }).join('');
        svg = `
            <svg viewBox="0 0 ${largura} ${altura}" role="img"
                aria-label="Gráfico de barras: ${escaparAtributo(id)}">
                ${grid}${bars}
            </svg>`;
    }

    container.innerHTML = `
        ${series.length > 1 ? `<div class="report-legend">${legend}</div>` : ''}
        <div class="report-chart${registros.length > 10 || tipo.includes('horizontal')
            ? ' report-chart-dense'
            : ''}">${svg}</div>`;
}


// =========================================================
// AGENDAMENTOS
// =========================================================

function configurarAgendamentos() {

    criarFiltroSituacao();
    configurarJogosDia();

    const btnAtualizar =
        document.getElementById(
            'btn-atualizar'
        );

    const btnLimpar =
        document.getElementById(
            'btn-limpar-filtros'
        );

    const filtroData =
        document.getElementById(
            'filtro-data'
        );

    const filtroQuadra =
        document.getElementById(
            'filtro-quadra'
        );

    const filtroStatus =
        document.getElementById(
            'filtro-status'
        );

    const filtroSituacao =
        document.getElementById(
            'filtro-situacao'
        );


    if (btnAtualizar) {

        btnAtualizar.addEventListener(
            'click',
            carregarAgendamentos
        );

    }

    function configurarJogosDia() {
        const data = document.getElementById('jogos-dia-data');
        const quadra = document.getElementById('jogos-dia-quadra');
        const atualizar = document.getElementById('btn-atualizar-jogos-dia');
        const dialog = document.getElementById('jogo-pagamento-dialog');
        const form = document.getElementById('jogo-pagamento-form');
        const fechar = document.getElementById('fechar-jogo-pagamento');
        if (!data || !quadra || !atualizar || !form || !dialog) return;

        data.value = dataLocalISO(new Date());
        data.addEventListener('change', carregarJogosDia);
        quadra.addEventListener('change', () => {
            const escopo = document.getElementById('admin-court-scope-select');
            if (usuarioAdminAtual && usuarioAdminAtual.nivel !== 'root' &&
                escopo && escopo.value !== quadra.value) {
                escopo.value = quadra.value;
                escopo.dispatchEvent(new Event('change'));
                return;
            }
            carregarJogosDia();
        });
        atualizar.addEventListener('click', carregarJogosDia);
        fechar.addEventListener('click', () => dialog.close());
        form.addEventListener('submit', salvarPagamentoJogo);

        carregarQuadrasAdminDia();
    }

    async function carregarQuadrasAdminDia() {
        const select = document.getElementById('jogos-dia-quadra');
        try {
            const [resposta, respostaConfiguracoes] = await Promise.all([
                fetch('/admin/escopo-quadras'),
                fetch('/configuracoes')
            ]);
            const dados = await resposta.json();
            if (!resposta.ok) throw new Error(dados.detail || 'Não foi possível carregar quadras.');
            if (respostaConfiguracoes.ok) {
                configuracoes = await respostaConfiguracoes.json();
            }
            const escopoRestrito =
                usuarioAdminAtual && usuarioAdminAtual.nivel !== 'root';
            select.innerHTML = escopoRestrito
                ? ''
                : '<option value="">Todas</option>';
            dados.forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent = item.nome;
                select.appendChild(option);
            });
            if (escopoRestrito && dados.length) {
                select.value = String(dados[0].id);
            }
            await carregarJogosDia();
        } catch (erro) {
            mostrarMensagemJogosDia(erro.message);
        }
    }

    function mostrarMensagemJogosDia(texto) {
        const mensagem = document.getElementById('mensagem-jogos-dia');
        mensagem.textContent = texto;
        mensagem.style.display = 'block';
    }

    async function carregarJogosDia() {
        const data = document.getElementById('jogos-dia-data').value;
        if (!data) return;
        const tbody = document.getElementById('lista-jogos-dia');
        const mensagem = document.getElementById('mensagem-jogos-dia');
        const resumo = document.getElementById('jogos-dia-resumo');
        const params = new URLSearchParams({data});
        const quadraId = document.getElementById('jogos-dia-quadra').value;
        if (quadraId) params.set('quadra_id', quadraId);
        tbody.innerHTML = '';
        mensagem.textContent = 'Carregando jogos...';
        mensagem.style.display = 'block';
        try {
            const resposta = await fetch(`/jogos?${params}`);
            const jogos = await resposta.json();
            if (!resposta.ok) throw new Error(jogos.detail || 'Não foi possível carregar os jogos.');
            resumo.textContent = `${jogos.length} ${jogos.length === 1 ? 'jogo' : 'jogos'} em ${formatarData(data)}`;
            mensagem.style.display = jogos.length ? 'none' : 'block';
            mensagem.textContent = 'Nenhum jogo encontrado para esta data.';
            tbody.innerHTML = jogos.map(jogo => {
                const pago = Number(jogo.valor_pago || 0);
                const total = Number(jogo.valor || 0);
                const saldo = Number(jogo.saldo_pendente || 0);
                const celular = normalizarWhatsapp(jogo.contato);
                const responsavel = normalizarWhatsapp(jogo.responsavel_whatsapp);
                const mensagemCliente = mensagemAtendimentoJogo(jogo);
                const clienteLink = celular
                    ? `<a target="_blank" rel="noopener noreferrer" href="https://wa.me/${celular}?text=${encodeURIComponent(mensagemCliente)}">Cliente</a>`
                    : 'Contato indisponível';
                const responsavelLink = responsavel
                    ? `<a target="_blank" rel="noopener noreferrer" href="https://wa.me/${responsavel}?text=${encodeURIComponent(mensagemCliente)}">Responsável</a>`
                    : '';
                const ref = jogo.agendamento_id
                    ? `data-agendamento="${Number(jogo.agendamento_id)}"`
                    : `data-mensalidade="${Number(jogo.mensalidade_id)}"`;
                return `
                    <tr>
                        <td>${escaparHTML(formatarHorario(jogo.horario))}</td>
                        <td>${escaparHTML(jogo.cliente)}<br><small>${escaparHTML(jogo.contato || '')}</small></td>
                        <td>${escaparHTML(jogo.quadra)}</td>
                        <td>${escaparHTML(jogo.tipo_jogo)}</td>
                        <td>${escaparHTML(jogo.status)}</td>
                        <td>${formatarMoeda(pago)} / ${formatarMoeda(total)}</td>
                        <td>${formatarMoeda(saldo)}</td>
                        <td>${Number(jogo.total_jogos_cliente || 0)}</td>
                        <td class="day-game-actions">
                            ${clienteLink} ${responsavelLink}
                            <button type="button" data-receber-jogo ${ref}
                                data-valor="${total}" data-pago="${pago}"
                                data-pagamento="${Number(jogo.pagamento_id || 0)}"
                                data-cliente="${escaparAtributo(jogo.cliente)}"
                                data-quadra="${escaparAtributo(jogo.quadra)}"
                                data-data="${escaparAtributo(data)}"
                                data-horario="${escaparAtributo(jogo.horario)}">
                                Recebimento
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
            tbody.querySelectorAll('[data-receber-jogo]').forEach(button => {
                button.addEventListener('click', abrirPagamentoJogo);
            });
        } catch (erro) {
            resumo.textContent = 'Não foi possível carregar os jogos.';
            mostrarMensagemJogosDia(erro.message);
        }
    }

    function normalizarWhatsapp(contato) {
        const digitos = String(contato || '').replace(/\D/g, '');
        if (!digitos) return '';
        if (digitos.startsWith('55') || ![10, 11].includes(digitos.length)) {
            return digitos;
        }
        return `55${digitos}`;
    }

    function mensagemAtendimentoJogo(jogo) {
        const padrao = configuracoes.find(item => item.chave === 'mensagem_reserva')?.valor
            || 'Olá {nome}! Recebemos sua solicitação para {quadra} em {data} às {horario}.';
        const valores = {
            nome: jogo.cliente,
            quadra: jogo.quadra,
            data: formatarData(jogo.data),
            horario: formatarHorario(jogo.horario)
        };
        return padrao.replace(/\{(nome|quadra|data|horario)\}/g, (_, chave) => valores[chave] || '');
    }

    function abrirPagamentoJogo(event) {
        const botao = event.currentTarget;
        const form = document.getElementById('jogo-pagamento-form');
        form.dataset.pagamento = botao.dataset.pagamento;
        form.dataset.agendamento = botao.dataset.agendamento || '';
        form.dataset.mensalidade = botao.dataset.mensalidade || '';
        form.dataset.valorTotal = botao.dataset.valor;
        document.getElementById('jogo-pagamento-resumo').textContent =
            `${botao.dataset.cliente} · ${botao.dataset.quadra} · ${formatarData(botao.dataset.data)} ${formatarHorario(botao.dataset.horario)}`;
        document.getElementById('jogo-pagamento-total').value = botao.dataset.pago;
        document.getElementById('jogo-pagamento-total').max = botao.dataset.valor;
        document.getElementById('jogo-pagamento-data').value = dataLocalISO(new Date());
        document.getElementById('jogo-pagamento-dialog').showModal();
    }

    async function salvarPagamentoJogo(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const valorTotal = Number(form.dataset.valorTotal);
        const valorPago = Number(document.getElementById('jogo-pagamento-total').value);
        const forma = document.getElementById('jogo-pagamento-forma').value;
        const data = document.getElementById('jogo-pagamento-data').value;
        if (!Number.isFinite(valorPago) || valorPago <= 0 || valorPago > valorTotal) {
            alert('Informe o total acumulado recebido, maior que zero e até o total do jogo.');
            return;
        }
        if (!forma || !data) {
            alert('Informe a forma e a data do recebimento.');
            return;
        }
        let pagamentoId = Number(form.dataset.pagamento);
        const mensalidadeId = Number(form.dataset.mensalidade);
        try {
            if (!pagamentoId) {
                const payload = {
                    agendamento_id: Number(form.dataset.agendamento) || null,
                    mensalidade_id: mensalidadeId || null,
                    competencia: mensalidadeId ? data.slice(0, 7) : null,
                    status: 'Pendente',
                    valor_pago: 0
                };
                const criado = await fetch('/pagamentos', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const resultadoCriacao = await criado.json();
                if (!criado.ok) throw new Error(resultadoCriacao.detail || 'Não foi possível criar o registro de pagamento.');
                pagamentoId = Number(resultadoCriacao.id);
            }
            const status = valorPago >= valorTotal ? 'Recebido' : 'Pendente';
            const resposta = await fetch(`/pagamentos/${pagamentoId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    status,
                    valor_pago: valorPago,
                    forma_pagamento: forma,
                    data_pagamento: data
                })
            });
            const resultado = await resposta.json();
            if (!resposta.ok) throw new Error(resultado.detail || 'Não foi possível atualizar o recebimento.');
            document.getElementById('jogo-pagamento-dialog').close();
            await carregarJogosDia();
            await carregarPagamentos();
        } catch (erro) {
            alert(erro.message);
        }
    }


    if (btnLimpar) {

        btnLimpar.addEventListener(
            'click',
            () => {

                if (filtroData) {
                    filtroData.value = '';
                }

                if (filtroQuadra) {
                    filtroQuadra.value = '';
                }

                if (filtroStatus) {
                    filtroStatus.value = '';
                }

                if (filtroSituacao) {
                    filtroSituacao.value = '';
                }

                renderizarAgendamentos();

            }
        );

    }


    if (filtroData) {

        filtroData.addEventListener(
            'change',
            renderizarAgendamentos
        );

    }


    if (filtroQuadra) {

        filtroQuadra.addEventListener(
            'change',
            renderizarAgendamentos
        );

    }


    if (filtroStatus) {

        filtroStatus.addEventListener(
            'change',
            renderizarAgendamentos
        );

    }


    if (filtroSituacao) {

        filtroSituacao.addEventListener(
            'change',
            renderizarAgendamentos
        );

    }

}


// =========================================================
// CRIAR FILTRO DE SITUAÇÃO
// =========================================================

function criarFiltroSituacao() {

    const filtroStatus =
        document.getElementById(
            'filtro-status'
        );

    if (!filtroStatus) {
        return;
    }

    if (
        document.getElementById(
            'filtro-situacao'
        )
    ) {
        return;
    }


    const filtro =
        document.createElement('div');

    filtro.className = 'filtro';

    filtro.innerHTML = `
        <label for="filtro-situacao">
            Situação
        </label>

        <select id="filtro-situacao">

            <option value="">
                Todas
            </option>

            <option value="Hoje">
                Hoje
            </option>

            <option value="Próximo">
                Próximos
            </option>

            <option value="Concluído">
                Concluídos
            </option>

            <option value="Histórico">
                Histórico
            </option>

        </select>
    `;


    const filtros =
        filtroStatus.closest('.filtros');

    if (filtros) {
        filtros.appendChild(filtro);
    }

}


// =========================================================
// CARREGAR AGENDAMENTOS
// =========================================================

async function carregarAgendamentos() {

    try {

        const resposta =
            await fetch('/agendamentos');

        if (!resposta.ok) {
            throw new Error(
                'Erro ao carregar agendamentos.'
            );
        }

        agendamentos =
            await resposta.json();

        preencherSelectsPagamento();
        preencherFiltroQuadras();
        renderizarAgendamentos();
        atualizarResumo();

    } catch (erro) {

        console.error(erro);

        mostrarErroTabela(
            'lista-agendamentos',
            'Erro ao carregar os agendamentos.'
        );

    }

}


// =========================================================
// RENDERIZAR AGENDAMENTOS
// =========================================================

function renderizarAgendamentos() {

    const tbody =
        document.getElementById(
            'lista-agendamentos'
        );

    const mensagem =
        document.getElementById(
            'mensagem-vazia'
        );


    if (!tbody) {
        return;
    }


    const filtroData =
        document.getElementById(
            'filtro-data'
        )?.value || '';


    const filtroQuadra =
        document.getElementById(
            'filtro-quadra'
        )?.value || '';


    const filtroStatus =
        document.getElementById(
            'filtro-status'
        )?.value || '';


    const filtroSituacao =
        document.getElementById(
            'filtro-situacao'
        )?.value || '';


    const filtrados =
        agendamentos.filter(agendamento => {

            if (
                filtroData &&
                agendamento.data !== filtroData
            ) {
                return false;
            }


            if (
                filtroQuadra &&
                String(agendamento.quadra) !==
                filtroQuadra
            ) {
                return false;
            }


            if (
                filtroStatus &&
                agendamento.status !==
                filtroStatus
            ) {
                return false;
            }


            if (
                filtroSituacao &&
                agendamento.situacao !==
                filtroSituacao
            ) {
                return false;
            }


            return true;

        });


    tbody.innerHTML = '';


    if (filtrados.length === 0) {

        if (mensagem) {
            mensagem.style.display = 'block';
        }

        const quantidade =
            document.getElementById(
                'quantidade-resultados'
            );

        if (quantidade) {
            quantidade.textContent =
                '0 registros';
        }

        return;
    }


    if (mensagem) {
        mensagem.style.display = 'none';
    }


    const quantidade =
        document.getElementById(
            'quantidade-resultados'
        );

    if (quantidade) {

        quantidade.textContent =
            `${filtrados.length} registro(s)`;

    }


    // Ordena por data e horário.

    filtrados.sort((a, b) => {

        const dataA =
            `${a.data} ${a.horario}`;

        const dataB =
            `${b.data} ${b.horario}`;

        return dataA.localeCompare(dataB);

    });


    filtrados.forEach(agendamento => {

        const tr =
            document.createElement('tr');


        const contato =
            String(
                agendamento.contato || ''
            ).replace(/\D/g, '');


        const whatsapp =
            contato
                ? `https://wa.me/55${contato}`
                : '#';


        const garantia =
            agendamento.garantia_reserva ||
            'Dispensado';


        const statusEditavel =
            agendamento.editavel === true;


        let controleStatus;


        // -------------------------------------------------
        // STATUS EDITÁVEL
        // -------------------------------------------------

        if (statusEditavel) {

            controleStatus = `
                <select
                    class="status-select ${classeStatus(
                        agendamento.status
                    )}"
                    data-id="${agendamento.id}"
                >

                    <option
                        value="Pendente"
                        ${
                            agendamento.status ===
                            'Pendente'
                                ? 'selected'
                                : ''
                        }
                    >
                        Pendente
                    </option>


                    <option
                        value="Confirmado"
                        ${
                            agendamento.status ===
                            'Confirmado'
                                ? 'selected'
                                : ''
                        }
                    >
                        Confirmado
                    </option>


                    <option
                        value="Cancelado"
                        ${
                            agendamento.status ===
                            'Cancelado'
                                ? 'selected'
                                : ''
                        }
                    >
                        Cancelado
                    </option>


                    <option
                        value="Não atendido"
                        ${
                            agendamento.status ===
                            'Não atendido'
                                ? 'selected'
                                : ''
                        }
                    >
                        Não atendido
                    </option>

                </select>
            `;

        }


        // -------------------------------------------------
        // STATUS BLOQUEADO
        // -------------------------------------------------

        else {

            controleStatus = `
                <span
                    class="status-select ${classeStatus(
                        agendamento.status
                    )}"
                    style="
                        display:inline-block;
                        padding:7px 10px;
                        cursor:not-allowed;
                        opacity:.75;
                    "
                    title="Este agendamento não pode mais ser alterado."
                >
                    ${escaparHTML(
                        agendamento.status
                    )}
                </span>
            `;

        }


        // -------------------------------------------------
        // LINHA
        // -------------------------------------------------

        tr.innerHTML = `

            <td>
                ${agendamento.id}
            </td>


            <td>

                <strong>
                    ${escaparHTML(
                        agendamento.cliente
                    )}
                </strong>

                <br>

                <small>
                    Garantia:
                    ${escaparHTML(garantia)}
                </small>

            </td>


            <td>

                ${
                    contato
                        ? `
                            <a
                                href="${whatsapp}"
                                target="_blank"
                                rel="noopener noreferrer"
                                class="whatsapp-link"
                            >
                                ${escaparHTML(
                                    agendamento.contato
                                )}
                            </a>
                        `
                        : '-'
                }

            </td>


            <td>
                ${escaparHTML(
                    agendamento.quadra
                )}
            </td>


            <td>
                ${formatarData(
                    agendamento.data
                )}
            </td>


            <td>
                ${formatarHorario(
                    agendamento.horario
                )}
            </td>


            <td>
                ${formatarMoeda(agendamento.valor_hora)}
            </td>


            <td>
                ${formatarMoeda(agendamento.taxa_reserva)}
            </td>


            <td>
                ${controleStatus}
            </td>

        `;


        tbody.appendChild(tr);

    });


    // -----------------------------------------------------
    // EVENTOS DOS SELECTS
    // -----------------------------------------------------

    document
        .querySelectorAll(
            '.status-select[data-id]'
        )
        .forEach(select => {

            select.addEventListener(
                'change',
                atualizarStatusAgendamento
            );

        });

}


// =========================================================
// ATUALIZAR STATUS
// =========================================================

async function atualizarStatusAgendamento(event) {

    const select =
        event.target;

    const id =
        select.dataset.id;

    const novoStatus =
        select.value;


    try {

        const resposta =
            await fetch(
                `/agendamentos/${id}/status`,
                {
                    method: 'PUT',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify({
                            status:
                                novoStatus
                        })
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao atualizar status.'
            );

        }


        await carregarAgendamentos();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

        await carregarAgendamentos();

    }

}


// =========================================================
// RESUMO
// =========================================================

function atualizarResumo() {

    const total =
        agendamentos.length;


    const pendentes =
        agendamentos.filter(
            item =>
                item.status === 'Pendente'
        ).length;


    const confirmados =
        agendamentos.filter(
            item =>
                item.status === 'Confirmado'
        ).length;


    const cancelados =
        agendamentos.filter(
            item =>
                item.status === 'Cancelado'
        ).length;


    const elementoTotal =
        document.getElementById(
            'total-agendamentos'
        );


    const elementoPendentes =
        document.getElementById(
            'total-pendentes'
        );


    const elementoConfirmados =
        document.getElementById(
            'total-confirmados'
        );


    const elementoCancelados =
        document.getElementById(
            'total-cancelados'
        );


    if (elementoTotal) {
        elementoTotal.textContent =
            total;
    }


    if (elementoPendentes) {
        elementoPendentes.textContent =
            pendentes;
    }


    if (elementoConfirmados) {
        elementoConfirmados.textContent =
            confirmados;
    }


    if (elementoCancelados) {
        elementoCancelados.textContent =
            cancelados;
    }

}


// =========================================================
// FILTRO DE QUADRAS
// =========================================================

function preencherFiltroQuadras() {

    const select =
        document.getElementById(
            'filtro-quadra'
        );


    if (!select) {
        return;
    }


    const valorAtual =
        select.value;


    const nomes =
        [
            ...new Set(
                agendamentos
                    .map(item => item.quadra)
                    .filter(Boolean)
            )
        ];


    select.innerHTML =
        '<option value="">Todas</option>';


    nomes.forEach(nome => {

        const option =
            document.createElement(
                'option'
            );


        option.value =
            nome;


        option.textContent =
            nome;


        select.appendChild(option);

    });


    select.value =
        valorAtual;

}


// =========================================================
// MENSALISTAS
// =========================================================

function configurarMensalistas() {

    const btnNovo =
        document.getElementById(
            'btn-novo-mensalista'
        );


    const btnFechar =
        document.getElementById(
            'btn-fechar-formulario'
        );


    const btnCancelar =
        document.getElementById(
            'btn-cancelar-mensalista'
        );


    const btnSalvar =
        document.getElementById(
            'btn-salvar-mensalista'
        );


    const selectQuadra =
        document.getElementById(
            'mensalista-quadra'
        );


    if (btnNovo) {

        btnNovo.addEventListener(
            'click',
            abrirFormularioMensalista
        );

    }


    if (btnFechar) {

        btnFechar.addEventListener(
            'click',
            fecharFormularioMensalista
        );

    }


    if (btnCancelar) {

        btnCancelar.addEventListener(
            'click',
            fecharFormularioMensalista
        );

    }


    if (btnSalvar) {

        btnSalvar.addEventListener(
            'click',
            salvarMensalista
        );

    }


    if (selectQuadra) {

        selectQuadra.addEventListener(
            'change',
            mostrarValorMensalQuadra
        );

    }


    const btnAtualizar =
        document.getElementById(
            'btn-atualizar-mensalistas'
        );


    if (btnAtualizar) {

        btnAtualizar.addEventListener(
            'click',
            () => {

                carregarMensalistas();
                carregarClientesParaMensalista();
                carregarQuadrasParaMensalista();

            }
        );

    }

}


// =========================================================
// CARREGAR MENSALISTAS
// =========================================================

async function carregarMensalistas() {

    try {

        const resposta =
            await fetch('/mensalidades');


        if (!resposta.ok) {

            throw new Error(
                'Erro ao carregar mensalistas.'
            );

        }


        mensalistas =
            await resposta.json();

        preencherSelectsPagamento();
        renderizarMensalistas();

    } catch (erro) {

        console.error(erro);

        mostrarErroTabela(
            'lista-mensalistas',
            'Erro ao carregar mensalistas.'
        );

    }

}


// =========================================================
// RENDERIZAR MENSALISTAS
// =========================================================

function renderizarMensalistas() {

    const tbody =
        document.getElementById(
            'lista-mensalistas'
        );


    const mensagem =
        document.getElementById(
            'mensagem-mensalistas'
        );


    if (!tbody) {
        return;
    }


    tbody.innerHTML = '';


    if (mensalistas.length === 0) {

        if (mensagem) {
            mensagem.style.display =
                'block';
        }

        return;

    }


    if (mensagem) {
        mensagem.style.display =
            'none';
    }


    mensalistas.forEach(item => {

        const tr =
            document.createElement('tr');


        tr.innerHTML = `

            <td>
                ${escaparHTML(
                    item.cliente
                )}
            </td>


            <td>
                ${escaparHTML(
                    item.quadra
                )}
            </td>


            <td>
                ${nomeDiaSemana(
                    item.dia_semana
                )}
            </td>


            <td>
                ${formatarHorario(
                    item.horario
                )}
            </td>


            <td>
                ${formatarMoeda(
                    item.valor_mensal
                )}
            </td>


            <td>
                ${formatarData(
                    item.data_inicio
                )}
            </td>


            <td>

                <span class="${
                    item.status === 'Ativa'
                        ? 'mensalidade-ativa'
                        : 'mensalidade-encerrada'
                }">

                    ${escaparHTML(
                        item.status
                    )}

                </span>

            </td>


            <td>

                ${
                    item.status === 'Ativa'
                        ? `
                            <button
                                class="btn-encerrar"
                                onclick="encerrarMensalidade(${item.id})"
                            >
                                Encerrar
                            </button>
                        `
                        : '-'
                }

            </td>

        `;


        tbody.appendChild(tr);

    });

}


// =========================================================
// CLIENTES PARA MENSALISTA
// =========================================================

async function carregarClientesParaMensalista() {

    try {

        const resposta =
            await fetch('/mensalidades/clientes');


        if (!resposta.ok) {

            throw new Error(
                'Erro ao carregar clientes.'
            );

        }


        clientes =
            await resposta.json();


        const select =
            document.getElementById(
                'mensalista-cliente'
            );


        if (!select) {
            return;
        }


        select.innerHTML =
            '<option value="">Selecione um cliente</option>';


        clientes.forEach(cliente => {

            const option =
                document.createElement(
                    'option'
                );


            option.value =
                cliente.id;


            option.textContent =
                `${cliente.nome} - ${cliente.contato}`;


            select.appendChild(option);

        });

    } catch (erro) {

        console.error(erro);

    }

}


// =========================================================
// QUADRAS PARA MENSALISTA
// =========================================================

async function carregarQuadrasParaMensalista() {

    try {

        if (quadras.length === 0) {

            const resposta =
                await fetch('/admin/escopo-quadras');


            if (!resposta.ok) {

                throw new Error(
                    'Erro ao carregar quadras.'
                );

            }


            quadras =
                await resposta.json();

        }


        preencherSelectQuadrasMensalista();

    } catch (erro) {

        console.error(erro);

    }

}


// =========================================================
// SELECT DE QUADRAS
// =========================================================

function preencherSelectQuadrasMensalista() {

    const select =
        document.getElementById(
            'mensalista-quadra'
        );


    if (!select) {
        return;
    }


    select.innerHTML =
        '<option value="">Selecione uma quadra</option>';


    quadras
        .filter(
            quadra =>
                Number(quadra.ativo) === 1
        )
        .forEach(quadra => {

            const option =
                document.createElement(
                    'option'
                );


            option.value =
                quadra.id;


            option.textContent =
                quadra.nome;


            select.appendChild(option);

        });

}


// =========================================================
// VALOR MENSAL DA QUADRA
// =========================================================

function mostrarValorMensalQuadra() {

    const select =
        document.getElementById(
            'mensalista-quadra'
        );


    const campoValor =
        document.getElementById(
            'mensalista-valor'
        );


    if (!select || !campoValor) {
        return;
    }


    const quadraId =
        Number(select.value);


    const quadra =
        quadras.find(
            item =>
                Number(item.id) ===
                quadraId
        );


    if (!quadra) {

        campoValor.value =
            'Selecione uma quadra';

        return;

    }


    if (
        quadra.valor_mensal === null ||
        quadra.valor_mensal === undefined ||
        Number(quadra.valor_mensal) <= 0
    ) {

        campoValor.value =
            'Não configurado';

        return;

    }


    campoValor.value =
        formatarMoeda(
            quadra.valor_mensal
        );

}


// =========================================================
// FORMULÁRIO MENSALISTA
// =========================================================

function abrirFormularioMensalista() {

    const formulario =
        document.getElementById(
            'form-mensalista'
        );


    if (!formulario) {

        console.error(
            'Formulário #form-mensalista não encontrado.'
        );

        return;

    }


    formulario.classList.add(
        'aberto'
    );


    carregarClientesParaMensalista();
    carregarQuadrasParaMensalista();

}


function fecharFormularioMensalista() {

    const formulario =
        document.getElementById(
            'form-mensalista'
        );


    if (!formulario) {
        return;
    }


    formulario.classList.remove(
        'aberto'
    );


    limparFormularioMensalista();

}


function limparFormularioMensalista() {

    const cliente =
        document.getElementById(
            'mensalista-cliente'
        );


    const quadra =
        document.getElementById(
            'mensalista-quadra'
        );


    const dia =
        document.getElementById(
            'mensalista-dia'
        );


    const horario =
        document.getElementById(
            'mensalista-horario'
        );


    const valor =
        document.getElementById(
            'mensalista-valor'
        );


    const inicio =
        document.getElementById(
            'mensalista-inicio'
        );


    const observacao =
        document.getElementById(
            'mensalista-observacao'
        );


    if (cliente) {
        cliente.value = '';
    }


    if (quadra) {
        quadra.value = '';
    }


    if (dia) {
        dia.value = '';
    }


    if (horario) {
        horario.value = '';
    }


    if (valor) {
        valor.value =
            'Selecione uma quadra';
    }


    if (inicio) {
        inicio.value = '';
    }


    if (observacao) {
        observacao.value = '';
    }

}


// =========================================================
// SALVAR MENSALISTA
// =========================================================

async function salvarMensalista() {

    const clienteId =
        Number(
            document.getElementById(
                'mensalista-cliente'
            ).value
        );


    const quadraId =
        Number(
            document.getElementById(
                'mensalista-quadra'
            ).value
        );


    const diaSemana =
        Number(
            document.getElementById(
                'mensalista-dia'
            ).value
        );


    const horario =
        document.getElementById(
            'mensalista-horario'
        ).value;


    const dataInicio =
        document.getElementById(
            'mensalista-inicio'
        ).value;


    const observacao =
        document.getElementById(
            'mensalista-observacao'
        ).value;


    if (!clienteId) {

        alert(
            'Selecione um cliente.'
        );

        return;

    }


    if (!quadraId) {

        alert(
            'Selecione uma quadra.'
        );

        return;

    }


    if (
        !Number.isInteger(diaSemana) ||
        diaSemana < 0 ||
        diaSemana > 6
    ) {

        alert(
            'Selecione o dia da semana.'
        );

        return;

    }


    if (!horario) {

        alert(
            'Informe o horário.'
        );

        return;

    }


    if (!dataInicio) {

        alert(
            'Informe a data de início.'
        );

        return;

    }


    const quadra =
        quadras.find(
            item =>
                Number(item.id) ===
                quadraId
        );


    if (
        !quadra ||
        quadra.valor_mensal === null ||
        quadra.valor_mensal === undefined ||
        Number(quadra.valor_mensal) <= 0
    ) {

        alert(
            'Configure o valor mensal desta quadra antes de criar o mensalista.'
        );

        return;

    }


    const cliente =
        clientes.find(
            item =>
                Number(item.id) ===
                clienteId
        );


    if (!cliente) {

        alert(
            'Cliente não encontrado.'
        );

        return;

    }


    const dados = {

        nome:
            cliente.nome,

        contato:
            cliente.contato,

        quadra_id:
            quadraId,

        dia_semana:
            diaSemana,

        horario:
            horario,

        data_inicio:
            dataInicio,

        observacao:
            observacao || null

    };


    try {

        const resposta =
            await fetch(
                '/mensalidades',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(dados)
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao criar mensalista.'
            );

        }


        alert(
            `Mensalista criado com sucesso!

Valor mensal: ${formatarMoeda(
    resultado.valor_mensal
)}`
        );


        fecharFormularioMensalista();

        await carregarMensalistas();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// ENCERRAR MENSALIDADE
// =========================================================

async function encerrarMensalidade(id) {

    const confirmar =
        confirm(
            'Deseja realmente encerrar esta mensalidade?'
        );


    if (!confirmar) {
        return;
    }


    const hoje =
        new Date()
            .toISOString()
            .split('T')[0];


    try {

        const resposta =
            await fetch(
                `/mensalidades/${id}`,
                {
                    method: 'PUT',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify({
                            status:
                                'Encerrada',

                            data_encerramento:
                                hoje
                        })
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao encerrar mensalidade.'
            );

        }


        await carregarMensalistas();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// CLIENTES
// =========================================================

function configurarClientes() {

    const btnAtualizar =
        document.getElementById(
            'btn-atualizar-clientes'
        );


    if (btnAtualizar) {

        btnAtualizar.addEventListener(
            'click',
            carregarClientes
        );

    }

}


// =========================================================
// CARREGAR CLIENTES
// =========================================================

async function carregarClientes() {

    try {

        const resposta =
            await fetch('/clientes');


        if (!resposta.ok) {

            throw new Error(
                'Erro ao carregar clientes.'
            );

        }


        clientes =
            await resposta.json();


        renderizarClientes();

    } catch (erro) {

        console.error(erro);

        mostrarErroTabela(
            'lista-clientes',
            'Erro ao carregar clientes.'
        );

    }

}


// =========================================================
// RENDERIZAR CLIENTES
// =========================================================

function renderizarClientes() {

    const tbody =
        document.getElementById(
            'lista-clientes'
        );


    const mensagem =
        document.getElementById(
            'mensagem-clientes'
        );


    if (!tbody) {
        return;
    }


    tbody.innerHTML = '';


    if (clientes.length === 0) {

        if (mensagem) {
            mensagem.style.display =
                'block';
        }

        return;

    }


    if (mensagem) {
        mensagem.style.display =
            'none';
    }


    clientes.forEach(cliente => {

        const tr =
            document.createElement('tr');


        const garantia =
            cliente.garantia_reserva ||
            'Dispensado';


        const motivo =
            cliente.motivo_garantia ||
            '';


        tr.innerHTML = `

            <td>
                ${cliente.id}
            </td>


            <td>
                ${escaparHTML(
                    cliente.nome
                )}
            </td>


            <td>
                <input
                    type="tel"
                    id="contato-cliente-${cliente.id}"
                    value="${escaparAtributo(cliente.contato || '')}"
                    maxlength="20"
                    aria-label="Contato de ${escaparAtributo(cliente.nome)}"
                >
            </td>

            <td>
                ${Number(cliente.mensalista) === 1 ? 'Ativo' : 'Não'}
            </td>


            <td>

                <select
                    class="status-select garantia-select"
                    id="garantia-${cliente.id}"
                >

                    <option
                        value="Dispensado"
                        ${
                            garantia ===
                            'Dispensado'
                                ? 'selected'
                                : ''
                        }
                    >
                        Dispensado
                    </option>


                    <option
                        value="Obrigatório"
                        ${
                            garantia ===
                            'Obrigatório'
                                ? 'selected'
                                : ''
                        }
                    >
                        Obrigatório
                    </option>

                </select>

            </td>


            <td>

                <input
                    type="text"
                    id="motivo-garantia-${cliente.id}"
                    value="${escaparAtributo(
                        motivo
                    )}"
                    placeholder="Motivo"
                    style="
                        min-width:180px;
                        height:36px;
                        background:#101216;
                        border:1px solid #343942;
                        border-radius:7px;
                        color:#fff;
                        padding:0 10px;
                    "
                >

            </td>


            <td>

                <button
                    class="btn-destaque"
                    onclick="salvarGarantiaCliente(${cliente.id})"
                >
                    Salvar
                </button>


                <button
                    onclick="verHistoricoCliente(${cliente.id})"
                >
                    Histórico
                </button>

            </td>

        `;


        tbody.appendChild(tr);

    });

}


// =========================================================
// SALVAR GARANTIA
// =========================================================

async function salvarGarantiaCliente(id) {

    const contato =
        document.getElementById(
            `contato-cliente-${id}`
        ).value.trim();

    const garantia =
        document.getElementById(
            `garantia-${id}`
        ).value;


    const motivo =
        document.getElementById(
            `motivo-garantia-${id}`
        ).value.trim();

    if (!contato) {
        alert('O contato do cliente é obrigatório.');
        return;
    }


    try {

        const resposta =
            await fetch(
                `/clientes/${id}`,
                {
                    method: 'PUT',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify({
                            contato,
                            garantia_reserva:
                                garantia,

                            motivo_garantia:
                                motivo || null
                        })
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao atualizar garantia do cliente.'
            );

        }


        alert(
            'Configuração de garantia atualizada!'
        );


        await carregarClientes();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// HISTÓRICO CLIENTE
// =========================================================

async function verHistoricoCliente(id) {

    try {

        const resposta =
            await fetch(
                `/clientes/${id}`
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao carregar histórico.'
            );

        }


        let mensagem =
            'CLIENTE\n\n';


        mensagem +=
            `Nome: ${resultado.cliente.nome}\n`;


        mensagem +=
            `Contato: ${resultado.cliente.contato}\n`;


        mensagem +=
            `Garantia: ${resultado.cliente.garantia_reserva}\n`;


        if (
            resultado.cliente.motivo_garantia
        ) {

            mensagem +=
                `Motivo: ${resultado.cliente.motivo_garantia}\n`;

        }


        mensagem +=
            `\nAgendamentos: ${resultado.agendamentos.length}\n`;


        mensagem +=
            `Mensalidades: ${resultado.mensalidades.length}`;


        alert(mensagem);

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// QUADRAS
// =========================================================

function configurarQuadras() {

    const btnAtualizar =
        document.getElementById(
            'btn-atualizar-quadras'
        );


    if (btnAtualizar) {

        btnAtualizar.addEventListener(
            'click',
            carregarQuadras
        );

    }

}


// =========================================================
// CARREGAR QUADRAS
// =========================================================

async function carregarQuadras() {

    try {

        const resposta =
            await fetch('/admin/quadras');


        if (!resposta.ok) {

            throw new Error(
                'Erro ao carregar quadras.'
            );

        }


        quadras =
            await resposta.json();


        renderizarQuadras();

        preencherSelectQuadrasMensalista();

    } catch (erro) {

        console.error(erro);

        alert(
            'Erro ao carregar quadras.'
        );

    }

}


// =========================================================
// RENDERIZAR QUADRAS
// =========================================================

function renderizarQuadras() {

    const container =
        document.getElementById(
            'lista-quadras'
        );


    if (!container) {
        return;
    }


    container.innerHTML = '';


    if (quadras.length === 0) {

        container.innerHTML = `

            <div
                class="mensagem-vazia"
                style="display:block;"
            >
                Nenhuma quadra encontrada.
            </div>

        `;

        return;

    }


    quadras.forEach(quadra => {

        const card =
            document.createElement('div');


        card.className =
            'quadra-card';


        card.innerHTML = `

            <h3>
                ${escaparHTML(
                    quadra.nome
                )}
            </h3>


            <label>
                Nome da quadra
            </label>

            <input
                type="text"
                id="quadra-nome-${quadra.id}"
                value="${escaparAtributo(
                    quadra.nome || ''
                )}"
            >


            <label>
                Tipo
            </label>

            <select
                id="quadra-tipo-${quadra.id}"
            >

                <option
                    value="sintetico"
                    ${
                        quadra.tipo ===
                        'sintetico'
                            ? 'selected'
                            : ''
                    }
                >
                    Sintético
                </option>


                <option
                    value="salao"
                    ${
                        quadra.tipo ===
                        'salao'
                            ? 'selected'
                            : ''
                    }
                >
                    Salão
                </option>


                <option
                    value="areia"
                    ${
                        quadra.tipo ===
                        'areia'
                            ? 'selected'
                            : ''
                    }
                >
                    Areia
                </option>

            </select>


            <label>
                Valor por hora
            </label>

            <input
                type="number"
                id="quadra-valor-${quadra.id}"
                value="${quadra.valor ?? ''}"
                step="0.01"
                min="0"
                placeholder="0,00"
            >


            <label>
                Valor mensal
            </label>

            <input
                type="number"
                id="quadra-valor-mensal-${quadra.id}"
                value="${quadra.valor_mensal ?? ''}"
                step="0.01"
                min="0"
                placeholder="0,00"
            >


            <label>
                Taxa de reserva
            </label>

            <input
                type="number"
                id="quadra-taxa-${quadra.id}"
                value="${quadra.taxa_reserva ?? 0}"
                step="0.01"
                min="0"
                placeholder="0,00"
            >

            <label>
                WhatsApp responsável
            </label>

            <input
                type="tel"
                id="quadra-responsavel-${quadra.id}"
                value="${escaparAtributo(
                    quadra.responsavel_whatsapp || ''
                )}"
                placeholder="Ex.: 5541999999999"
            >


            <label>
                Capacidade
            </label>

            <input
                type="number"
                id="quadra-capacidade-${quadra.id}"
                value="${quadra.capacidade ?? ''}"
                min="0"
            >


            <label>
                Medidas
            </label>

            <input
                type="text"
                id="quadra-medidas-${quadra.id}"
                value="${escaparAtributo(
                    quadra.medidas || ''
                )}"
                placeholder="Ex.: 40m x 20m"
            >


            <label>
                Descrição
            </label>

            <textarea
                id="quadra-descricao-${quadra.id}"
            >${escaparHTML(
                quadra.descricao || ''
            )}</textarea>


            <label>
                Imagem
            </label>

            <input
                type="text"
                id="quadra-imagem-${quadra.id}"
                value="${escaparAtributo(
                    quadra.imagem || ''
                )}"
                placeholder="Caminho da imagem"
            >


            <label>

                <input
                    type="checkbox"
                    id="quadra-ativo-${quadra.id}"
                    ${
                        Number(quadra.ativo) === 1
                            ? 'checked'
                            : ''
                    }
                >

                Quadra ativa

            </label>


            <button
                class="btn-destaque"
                onclick="salvarQuadra(${quadra.id})"
            >
                Salvar alterações
            </button>

        `;


        container.appendChild(card);

    });

}


// =========================================================
// SALVAR QUADRA
// =========================================================

async function salvarQuadra(id) {

    const nome =
        document.getElementById(
            `quadra-nome-${id}`
        ).value.trim();


    const tipo =
        document.getElementById(
            `quadra-tipo-${id}`
        ).value;


    const valor =
        Number(
            document.getElementById(
                `quadra-valor-${id}`
            ).value
        );


    const valorMensalTexto =
        document.getElementById(
            `quadra-valor-mensal-${id}`
        ).value;


    const taxaTexto =
        document.getElementById(
            `quadra-taxa-${id}`
        ).value;


    const capacidadeTexto =
        document.getElementById(
            `quadra-capacidade-${id}`
        ).value;


    const medidas =
        document.getElementById(
            `quadra-medidas-${id}`
        ).value.trim();


    const descricao =
        document.getElementById(
            `quadra-descricao-${id}`
        ).value.trim();


    const imagem =
        document.getElementById(
            `quadra-imagem-${id}`
        ).value.trim();

    const responsavelWhatsapp =
        document.getElementById(
            `quadra-responsavel-${id}`
        ).value.trim();


    const ativo =
        document.getElementById(
            `quadra-ativo-${id}`
        ).checked
            ? 1
            : 0;


    if (!nome) {

        alert(
            'O nome da quadra é obrigatório.'
        );

        return;

    }


    if (
        Number.isNaN(valor) ||
        valor < 0
    ) {

        alert(
            'Informe um valor por hora válido.'
        );

        return;

    }


    let valorMensal = null;


    if (valorMensalTexto !== '') {

        valorMensal =
            Number(valorMensalTexto);


        if (
            Number.isNaN(valorMensal) ||
            valorMensal < 0
        ) {

            alert(
                'Informe um valor mensal válido.'
            );

            return;

        }

    }


    let taxaReserva = 0;


    if (taxaTexto !== '') {

        taxaReserva =
            Number(taxaTexto);


        if (
            Number.isNaN(taxaReserva) ||
            taxaReserva < 0
        ) {

            alert(
                'Informe uma taxa de reserva válida.'
            );

            return;

        }

    }


    let capacidade = null;


    if (capacidadeTexto !== '') {

        capacidade =
            Number(capacidadeTexto);


        if (
            Number.isNaN(capacidade) ||
            capacidade < 0
        ) {

            alert(
                'Informe uma capacidade válida.'
            );

            return;

        }

    }


    const dados = {

        nome,
        tipo,
        valor,
        valor_mensal:
            valorMensal,
        taxa_reserva:
            taxaReserva,
        medidas:
            medidas || null,
        capacidade,
        descricao:
            descricao || null,
        imagem:
            imagem || null,
        responsavel_whatsapp:
            responsavelWhatsapp || null,
        ativo

    };


    try {

        const resposta =
            await fetch(
                `/quadras/${id}`,
                {
                    method: 'PUT',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(dados)
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao atualizar quadra.'
            );

        }


        alert(
            'Quadra atualizada com sucesso!'
        );


        await carregarQuadras();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// CONFIGURAÇÕES GERAIS
// =========================================================

function configurarConfiguracoes() {

    const btnAtualizar =
        document.getElementById(
            'btn-atualizar-configuracoes'
        );


    if (btnAtualizar) {

        btnAtualizar.addEventListener(
            'click',
            carregarConfiguracoes
        );

    }

}


// =========================================================
// CARREGAR CONFIGURAÇÕES
// =========================================================

async function carregarConfiguracoes() {

    try {

        const resposta =
            await fetch('/admin/configuracoes');


        if (!resposta.ok) {

            throw new Error(
                'Erro ao carregar configurações.'
            );

        }


        configuracoes =
            await resposta.json();


        renderizarConfiguracoes();

    } catch (erro) {

        console.error(erro);

        alert(
            'Erro ao carregar configurações.'
        );

    }

}


// =========================================================
// RENDERIZAR CONFIGURAÇÕES
// =========================================================

function renderizarConfiguracoes() {

    const container =
        document.getElementById(
            'lista-configuracoes'
        );


    if (!container) {
        return;
    }


    container.innerHTML = '';


    const configuracoesAtuais =
        configuracoes.filter(config => {

            return !configuracoesLegadas.includes(
                config.chave
            );

        });


    if (
        configuracoesAtuais.length === 0
    ) {

        container.innerHTML = `

            <div
                class="mensagem-vazia"
                style="display:block;"
            >
                Nenhuma configuração geral cadastrada.
            </div>

        `;

        return;

    }


    configuracoesAtuais.forEach(config => {

        const card =
            document.createElement('div');


        card.className =
            'config-card';


        card.innerHTML = `

            <label>

                ${escaparHTML(
                    config.descricao ||
                    config.chave
                )}

            </label>


            <p>

                Chave:

                ${escaparHTML(
                    config.chave
                )}

            </p>


            <input
                type="text"
                id="config-${escaparAtributo(
                    config.chave
                )}"
                value="${escaparAtributo(
                    config.valor || ''
                )}"
                ${
                    Number(config.editavel) !== 1
                        ? 'disabled'
                        : ''
                }
            >


            ${
                Number(config.editavel) === 1
                    ? `

                        <button
                            class="btn-destaque"
                            onclick="salvarConfiguracao(
                                '${escaparJS(config.chave)}'
                            )"
                        >
                            Salvar
                        </button>

                    `
                    : `

                        <small>
                            Configuração protegida
                        </small>

                    `
            }

        `;


        container.appendChild(card);

    });

}


// =========================================================
// SALVAR CONFIGURAÇÃO
// =========================================================

async function salvarConfiguracao(chave) {

    const campo =
        document.getElementById(
            `config-${chave}`
        );


    if (!campo) {
        return;
    }


    try {

        const resposta =
            await fetch(
                `/configuracoes/${encodeURIComponent(chave)}`,
                {
                    method: 'PUT',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify({
                            valor:
                                campo.value
                        })
                }
            );


        const resultado =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                resultado.detail ||
                'Erro ao salvar configuração.'
            );

        }


        alert(
            'Configuração salva com sucesso!'
        );


        await carregarConfiguracoes();

    } catch (erro) {

        console.error(erro);

        alert(
            erro.message
        );

    }

}


// =========================================================
// FUNÇÕES UTILITÁRIAS
// =========================================================

function formatarMoeda(valor) {

    const numero =
        Number(valor);


    if (Number.isNaN(numero)) {
        return 'R$ 0,00';
    }


    return numero.toLocaleString(
        'pt-BR',
        {
            style: 'currency',
            currency: 'BRL'
        }
    );

}


// =========================================================
// FORMATAR DATA
// =========================================================

function formatarData(data) {

    if (!data) {
        return '-';
    }


    const partes =
        String(data).substring(0, 10).split('-');


    if (partes.length !== 3) {
        return data;
    }


    return `${partes[2]}/${partes[1]}/${partes[0]}`;

}


// =========================================================
// FORMATAR HORÁRIO
// =========================================================

function formatarHorario(horario) {

    if (!horario) {
        return '-';
    }


    return String(horario)
        .substring(0, 5);

}


// =========================================================
// DIA DA SEMANA
// =========================================================

function nomeDiaSemana(dia) {

    const dias = [

        'Domingo',
        'Segunda-feira',
        'Terça-feira',
        'Quarta-feira',
        'Quinta-feira',
        'Sexta-feira',
        'Sábado'

    ];


    return dias[dia] || '-';

}


// =========================================================
// CLASSE STATUS
// =========================================================

function classeStatus(status) {

    const mapa = {

        'Pendente':
            'status-pendente',

        'Confirmado':
            'status-confirmado',

        'Cancelado':
            'status-cancelado',

        'Não atendido':
            'status-nao-atendido'

    };


    return mapa[status] || '';

}


// =========================================================
// CLASSE SITUAÇÃO
// =========================================================

function classeSituacao(situacao) {

    const mapa = {

        'Hoje':
            'hoje',

        'Próximo':
            'proximo',

        'Concluído':
            'concluido',

        'Histórico':
            'historico'

    };


    return mapa[situacao] || 'indefinido';

}


// =========================================================
// ESCAPAR HTML
// =========================================================

function escaparHTML(valor) {

    return String(valor ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');

}


// =========================================================
// ESCAPAR ATRIBUTO
// =========================================================

function escaparAtributo(valor) {

    return escaparHTML(valor);

}


// =========================================================
// ESCAPAR JAVASCRIPT
// =========================================================

function escaparJS(valor) {

    return String(valor ?? '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");

}


// =========================================================
// MOSTRAR ERRO NA TABELA
// =========================================================

function mostrarErroTabela(
    idTabela,
    mensagem
) {

    const tbody =
        document.getElementById(
            idTabela
        );


    if (!tbody) {
        return;
    }


    tbody.innerHTML = `

        <tr>

            <td
                colspan="10"
                style="
                    text-align:center;
                    padding:30px;
                    color:#e55353;
                "
            >

                ${escaparHTML(mensagem)}

            </td>

        </tr>

    `;

}