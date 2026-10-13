document.addEventListener('DOMContentLoaded', () => {

    // ==================================================
    // PARÂMETROS DA URL
    // ==================================================

    const urlParams = new URLSearchParams(
        window.location.search
    );

    const tipo = urlParams.get('tipo');


    // ==================================================
    // ELEMENTOS DA PÁGINA
    // ==================================================

    const selectQuadra =
        document.getElementById('select-quadra');

    const inputDate =
        document.getElementById('input-date');

    const containerHorarios =
        document.getElementById('container-horarios');

    const elementoNomeQuadra =
        document.getElementById('display-nome-quadra');

    const elementoHorario =
        document.getElementById('display-horario');

    const elementoNomeVisual =
        document.getElementById('visual-nome-quadra');

    const elementoPreco =
        document.getElementById('display-preco');

    const elementoPrecoMensal =
        document.getElementById('display-preco-mensal');

    const elementoTituloQuadra =
        document.getElementById('display-titulo-quadra');

    const elementoTipoQuadra =
        document.getElementById('display-tipo-quadra');

    const elementoMedidasQuadra =
        document.getElementById('display-medidas-quadra');

    const elementoDescricaoQuadra =
        document.getElementById('display-descricao-quadra');

    const elementoStatus =
        document.getElementById('tag-status');

    const cartaoQuadra =
        document.getElementById('spatial-card');

    const imagemQuadra =
        document.getElementById('display-imagem-quadra');

    const inputNome =
        document.getElementById('input-nome');

    const inputWhatsapp =
        document.getElementById('input-whatsapp');

    const btnAvancar =
        document.getElementById('btn-avancar');


    // ==================================================
    // VARIÁVEIS
    // ==================================================

    let quadraSelecionada = null;
    let horarioSelecionado = null;
    let quadrasDoTipo = [];
    let configuracoes = {};
    let mensalidades = [];
    let agendamentos = [];
    let atualizandoAgendamentos = false;


    // ==================================================
    // DATA MÍNIMA = HOJE
    // ==================================================

    const agora = new Date();
    const hoje = [
        agora.getFullYear(),
        String(agora.getMonth() + 1).padStart(2, '0'),
        String(agora.getDate()).padStart(2, '0')
    ].join('-');

    inputDate.min = hoje;


    // ==================================================
    // INICIALIZAÇÃO
    // ==================================================

    carregarConfiguracoes();
    carregarQuadras();

    window.addEventListener(
        'focus',
        atualizarDisponibilidade
    );

    document.addEventListener(
        'visibilitychange',
        () => {
            if (!document.hidden) {
                atualizarDisponibilidade();
            }
        }
    );

    window.setInterval(
        () => {
            if (!document.hidden) {
                atualizarDisponibilidade();
            }
        },
        10000
    );


    function atualizarDisponibilidade() {

        if (!quadraSelecionada || !inputDate.value) {
            return;
        }

        carregarAgendamentos();

    }


    // ==================================================
    // CONFIGURAÇÕES
    // ==================================================

    function carregarConfiguracoes() {

        fetch('/configuracoes')

            .then(response => {

                if (!response.ok) {
                    throw new Error(
                        'Não foi possível carregar as configurações.'
                    );
                }

                return response.json();

            })

            .then(dados => {

                configuracoes = {};

                dados.forEach(configuracao => {

                    configuracoes[
                        configuracao.chave
                    ] = configuracao.valor;

                });

                if (inputDate.value) {
                    carregarHorarios();
                }

            })

            .catch(error => {

                console.error(
                    'Erro ao carregar configurações:',
                    error
                );

            });

    }


    // ==================================================
    // MENSALIDADES
    // ==================================================

    function carregarMensalidades() {

        carregarAgendamentos();

    }


    // ==================================================
    // AGENDAMENTOS
    // ==================================================

    function carregarAgendamentos() {

        if (
            atualizandoAgendamentos ||
            !quadraSelecionada ||
            !inputDate.value
        ) {
            return;
        }

        atualizandoAgendamentos = true;

        fetch(
            `/disponibilidade?quadra_id=${encodeURIComponent(quadraSelecionada.id)}` +
            `&data=${encodeURIComponent(inputDate.value)}`
        )

            .then(response => {

                if (!response.ok) {
                    throw new Error(
                        'Não foi possível carregar os agendamentos.'
                    );
                }

                return response.json();

            })

            .then(dados => {

                agendamentos = dados.agendamentos;
                mensalidades = dados.mensalidades;

                if (
                    quadraSelecionada &&
                    inputDate.value
                ) {
                    carregarHorarios();
                }

            })

            .catch(error => {

                console.error(
                    'Erro ao carregar agendamentos:',
                    error
                );

            })

            .finally(() => {

                atualizandoAgendamentos = false;

            });

    }


    // ==================================================
    // QUADRAS
    // ==================================================

    function carregarQuadras() {

        fetch('/quadras')

            .then(response => {

                if (!response.ok) {
                    throw new Error(
                        'Não foi possível carregar as quadras.'
                    );
                }

                return response.json();

            })

            .then(quadras => {

                quadrasDoTipo = quadras.filter(
                    quadra =>
                        quadra.tipo === tipo &&
                        (
                            quadra.ativo === undefined ||
                            Number(quadra.ativo) === 1 ||
                            quadra.ativo === true
                        )
                );


                if (quadrasDoTipo.length === 0) {

                    console.log(
                        'Nenhuma quadra encontrada para o tipo:',
                        tipo
                    );

                    containerHorarios.innerHTML =
                        '<p class="schedule-empty">Não há quadras disponíveis para esta modalidade no momento.</p>';

                    return;
                }


                // ==================================================
                // PREENCHER SELECT
                // ==================================================

                quadrasDoTipo.forEach(quadra => {

                    const option =
                        document.createElement('option');

                    option.value = quadra.id;

                    option.textContent =
                        quadra.nome;

                    selectQuadra.appendChild(option);

                });


                // ==================================================
                // EVENTO: SELECIONAR QUADRA
                // ==================================================

                selectQuadra.addEventListener(
                    'change',
                    () => {

                        const idSelecionado =
                            Number(selectQuadra.value);


                        quadraSelecionada =
                            quadrasDoTipo.find(
                                quadra =>
                                    Number(quadra.id) ===
                                    idSelecionado
                            );


                        horarioSelecionado = null;

                        containerHorarios.innerHTML = '';


                        if (!quadraSelecionada) {

                            limparResumoQuadra();
                            atualizarInstrucaoHorarios();

                            return;
                        }


                        atualizarResumoQuadra();


                        if (inputDate.value) {
                            atualizarDisponibilidade();
                        }

                    }
                );


                // ==================================================
                // EVENTO: SELECIONAR DATA
                // ==================================================

                inputDate.addEventListener(
                    'change',
                    () => {

                        horarioSelecionado = null;
                        atualizarDisponibilidade();
                        atualizarStatusReserva();

                    }
                );


                // ==================================================
                // EVENTO: SOLICITAR RESERVA
                // ==================================================

                btnAvancar.addEventListener(
                    'click',
                    solicitarReserva
                );

            })

            .catch(error => {

                console.error(
                    'Erro ao buscar quadras:',
                    error
                );

                alert(
                    'Não foi possível carregar as quadras.'
                );

            });

    }


    // ==================================================
    // ATUALIZAR RESUMO DA QUADRA
    // ==================================================

    function atualizarResumoQuadra() {

        if (!quadraSelecionada) {
            return;
        }

        elementoNomeQuadra.textContent =
            quadraSelecionada.nome;

        elementoNomeVisual.textContent =
            quadraSelecionada.nome;

        elementoTituloQuadra.textContent =
            quadraSelecionada.nome;

        const tipos = {
            salao: 'Salão',
            sintetico: 'Campo sintético',
            areia: 'Quadra de areia'
        };

        elementoTipoQuadra.textContent =
            tipos[quadraSelecionada.tipo] ||
            quadraSelecionada.tipo ||
            'Quadra esportiva';

        elementoMedidasQuadra.textContent =
            quadraSelecionada.medidas ||
            'Informações não cadastradas';

        elementoDescricaoQuadra.textContent =
            quadraSelecionada.descricao ||
            'Um espaço preparado para você aproveitar o jogo com conforto e segurança.';

        cartaoQuadra.dataset.tipo =
            quadraSelecionada.tipo || '';

        imagemQuadra.hidden = true;
        imagemQuadra.removeAttribute('src');

        if (quadraSelecionada.imagem) {
            try {
                const urlImagem = new URL(
                    quadraSelecionada.imagem,
                    window.location.origin
                );
                if (urlImagem.origin === window.location.origin) {
                    imagemQuadra.onload = () => {
                        imagemQuadra.hidden = false;
                    };
                    imagemQuadra.onerror = () => {
                        imagemQuadra.hidden = true;
                    };
                    imagemQuadra.src = urlImagem.href;
                }
            } catch (erro) {
                console.error('Caminho de imagem inválido para a quadra.', erro);
            }
        }

        const valorHora =
            Number(
                quadraSelecionada.valor || 0
            );

        const valorMensal =
            Number(quadraSelecionada.valor_mensal);

        elementoPreco.textContent =
            Number.isFinite(valorHora) && valorHora > 0
                ? formatarMoeda(valorHora)
                : 'Consulte';

        elementoPrecoMensal.textContent =
            Number.isFinite(valorMensal) && valorMensal > 0
                ? formatarMoeda(valorMensal)
                : 'Consulte';

        atualizarStatusReserva();

    }

    function limparResumoQuadra() {

        elementoNomeQuadra.textContent = '—';
        elementoHorario.textContent = '—';
        elementoNomeVisual.textContent = 'Escolha sua quadra';
        elementoTituloQuadra.textContent = 'Conheça nosso espaço';
        elementoTipoQuadra.textContent = 'Modalidade';
        elementoMedidasQuadra.textContent =
            'Informações após selecionar a quadra';
        elementoDescricaoQuadra.textContent =
            'Selecione uma quadra ao lado para conferir os detalhes, os valores e os horários disponíveis.';
        elementoPreco.textContent = '—';
        elementoPrecoMensal.textContent = '—';
        cartaoQuadra.dataset.tipo = '';
        imagemQuadra.hidden = true;
        imagemQuadra.removeAttribute('src');

        atualizarStatusReserva();

    }

    function atualizarStatusReserva() {

        if (!quadraSelecionada) {
            elementoStatus.textContent = 'Selecione uma quadra';
        } else if (!inputDate.value) {
            elementoStatus.textContent = 'Selecione uma data';
        } else if (horarioSelecionado) {
            elementoStatus.textContent = 'Horário escolhido';
        } else {
            elementoStatus.textContent = 'Escolha um horário';
        }

    }

    function atualizarInstrucaoHorarios() {

        const mensagem =
            !quadraSelecionada
                ? 'Escolha uma quadra e uma data para ver os horários.'
                : 'Escolha uma data para ver os horários disponíveis.';

        containerHorarios.innerHTML =
            `<p class="schedule-empty">${mensagem}</p>`;

    }

    function formatarMoeda(valor) {

        return valor.toLocaleString(
            'pt-BR',
            {
                style: 'currency',
                currency: 'BRL'
            }
        );

    }


    // ==================================================
    // SOLICITAR RESERVA
    // ==================================================

    function solicitarReserva() {

        if (!quadraSelecionada) {

            alert(
                'Selecione uma quadra.'
            );

            return;
        }


        if (!inputDate.value) {

            alert(
                'Selecione uma data.'
            );

            return;
        }


        if (!horarioSelecionado) {

            alert(
                'Selecione um horário.'
            );

            return;
        }


        if (!inputNome.value.trim()) {

            alert(
                'Digite seu nome.'
            );

            inputNome.focus();

            return;
        }


        if (!inputWhatsapp.value.trim()) {

            alert(
                'Digite seu WhatsApp.'
            );

            inputWhatsapp.focus();

            return;
        }


        // ==================================================
        // CONFERE NOVAMENTE A DISPONIBILIDADE
        // ==================================================

        const conflitoMensal =
            existeMensalistaNoHorario(
                quadraSelecionada.id,
                inputDate.value,
                horarioSelecionado
            );


        if (conflitoMensal) {

            alert(
                'Este horário está reservado para um mensalista.'
            );

            carregarHorarios();

            return;
        }


        const confirmados =
            contarConfirmados(
                quadraSelecionada.id,
                inputDate.value,
                horarioSelecionado
            );


        if (confirmados > 0) {

            alert(
                'Este horário já foi confirmado.'
            );

            carregarHorarios();

            return;
        }


        const dados = {

            nome: inputNome.value.trim(),

            contato: inputWhatsapp.value.trim(),

            quadra_id: quadraSelecionada.id,

            data: inputDate.value,

            horario: horarioSelecionado

        };


        btnAvancar.disabled = true;

        btnAvancar.textContent =
            'ENVIANDO...';

        const janelaWhatsapp =
            window.open('about:blank', '_blank');

        if (janelaWhatsapp) {
            janelaWhatsapp.opener = null;
        }

        fetch('/agendamentos', {

            method: 'POST',

            headers: {
                'Content-Type': 'application/json'
            },

            body: JSON.stringify(dados)

        })

        .then(async response => {

            const resultado =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    resultado.detail ||
                    'Erro ao enviar reserva.'
                );

            }


            return resultado;

        })

        .then(resultado => {
            const avisoTelegram =
                resultado.telegram_notificado === false
                    ? '\n\nAtenção: a solicitação foi salva, mas a notificação ' +
                      'administrativa pelo Telegram falhou. Avise a administração.'
                    : '';

            if (resultado.whatsapp_url) {
                if (janelaWhatsapp) {
                    janelaWhatsapp.location.href =
                        resultado.whatsapp_url;
                } else {
                    window.location.assign(resultado.whatsapp_url);
                }
                alert(
                    'Solicitação registrada como Pendente.\n\n' +
                    'O WhatsApp abrirá com a mensagem preenchida. ' +
                    'Toque em Enviar para avisar o responsável.' +
                    avisoTelegram
                );
            } else {
                if (janelaWhatsapp) {
                    janelaWhatsapp.close();
                }
                alert(
                    'Solicitação registrada como Pendente, mas esta quadra ' +
                    'ainda não tem um WhatsApp de responsável configurado.' +
                    avisoTelegram
                );
            }


            limparFormulario();

            carregarAgendamentos();

        })

        .catch(error => {
            if (janelaWhatsapp) {
                janelaWhatsapp.close();
            }

            console.error(
                'Erro ao solicitar reserva:',
                error
            );


            alert(
                error.message ||
                'Não foi possível enviar a solicitação.'
            );

        })

        .finally(() => {

            btnAvancar.disabled = false;

            btnAvancar.textContent =
                'Solicitar Reserva';

        });

    }


    // ==================================================
    // LIMPAR FORMULÁRIO
    // ==================================================

    function limparFormulario() {

        horarioSelecionado = null;

        quadraSelecionada = null;


        selectQuadra.value = '';

        inputDate.value = '';

        inputNome.value = '';

        inputWhatsapp.value = '';


        containerHorarios.innerHTML = '';


        elementoNomeQuadra.textContent =
            '—';

        limparResumoQuadra();
        atualizarInstrucaoHorarios();

    }


    // ==================================================
    // CARREGAR HORÁRIOS
    // ==================================================

    function carregarHorarios() {

        const horarioAnterior = horarioSelecionado;

        containerHorarios.innerHTML = '';

        horarioSelecionado = null;
        elementoHorario.textContent = '—';


        if (
            !quadraSelecionada ||
            !inputDate.value
        ) {

            atualizarInstrucaoHorarios();
            atualizarStatusReserva();
            return;

        }


        // ==================================================
        // DATA
        // ==================================================

        const [
            ano,
            mes,
            dia
        ] = inputDate.value.split('-');


        const dataSelecionada =
            new Date(
                Number(ano),
                Number(mes) - 1,
                Number(dia)
            );


        const diaSemana =
            dataSelecionada.getDay();


        // ==================================================
        // HORÁRIO DE FUNCIONAMENTO
        // ==================================================

        let minutosAbertura;
        let minutosFechamento;


        if (diaSemana === 0) {

            minutosAbertura =
                obterMinutosConfiguracao(
                    'horario_abertura_domingo',
                    7 * 60
                );

            minutosFechamento =
                obterMinutosConfiguracao(
                    'horario_fechamento_domingo',
                    17 * 60
                );
            if (minutosFechamento === 0) minutosFechamento = 24 * 60;

        } else {

            minutosAbertura =
                obterMinutosConfiguracao(
                    'horario_abertura_semana',
                    8 * 60
                );

            minutosFechamento =
                obterMinutosConfiguracao(
                    'horario_fechamento_semana',
                    23 * 60
                );
            if (minutosFechamento === 0) minutosFechamento = 24 * 60;

        }


        // ==================================================
        // SEGURANÇA
        // ==================================================

        if (
            !Number.isFinite(minutosAbertura) ||
            !Number.isFinite(minutosFechamento) ||
            minutosAbertura >= minutosFechamento
        ) {

            console.error(
                'Horários de funcionamento inválidos:',
                {
                    minutosAbertura,
                    minutosFechamento,
                    configuracoes
                }
            );

            containerHorarios.innerHTML =
                '<p>Horário de funcionamento inválido.</p>';

            return;
        }


        // ==================================================
        // CRIA HORÁRIOS
        // ==================================================

        let botaoSelecionado = null;


        const primeiroHorario =
            Math.ceil(minutosAbertura / 60) * 60;
        const ultimoHorario =
            Math.floor((minutosFechamento - 60) / 60) * 60;

        for (
            let minutosHorario = primeiroHorario;
            minutosHorario <= ultimoHorario;
            minutosHorario += 60
        ) {

            const hora = minutosHorario / 60;

            const horario =
                document.createElement('button');


            horario.type = 'button';

            horario.classList.add('slot');


            const textoHorario =
                `${hora
                    .toString()
                    .padStart(2, '0')}:00`;


            horario.textContent =
                textoHorario;


            // ==================================================
            // MENSALISTA
            // ==================================================

            const horarioMensalista =
                existeMensalistaNoHorario(
                    quadraSelecionada.id,
                    inputDate.value,
                    textoHorario
                );


            // ==================================================
            // CONFIRMADO
            // ==================================================

            const confirmado =
                existeConfirmado(
                    quadraSelecionada.id,
                    inputDate.value,
                    textoHorario
                );


            // ==================================================
            // LIMITE DA FILA
            // ==================================================

            const quantidadePendentes =
                contarPendentes(
                    quadraSelecionada.id,
                    inputDate.value,
                    textoHorario
                );


            const limiteFila =
                obterLimiteFila();


            const filaAtiva =
                obterConfiguracaoBoolean(
                    'permitir_fila',
                    true
                );


            const filaCheia =
                filaAtiva
                    ? limiteFila > 0 &&
                      quantidadePendentes >= limiteFila
                    : quantidadePendentes >= 1;


            const horarioOcupado =
                horarioMensalista ||
                confirmado ||
                filaCheia;


            // ==================================================
            // ESTADO DO BOTÃO
            // ==================================================

            if (horarioOcupado) {

                horario.classList.add(
                    'disabled'
                );

                horario.disabled = true;


                if (horarioMensalista) {

                    horario.title =
                        'Horário reservado para mensalista';

                } else if (confirmado) {

                    horario.title =
                        'Horário já confirmado';

                } else if (filaCheia) {

                    horario.title =
                        filaAtiva
                            ? 'Limite de reservas pendentes atingido'
                            : 'Já existe uma solicitação pendente e a fila está desativada';

                }

            } else if (
                textoHorario === horarioAnterior
            ) {

                horarioSelecionado = textoHorario;
                elementoHorario.textContent = textoHorario;
                horario.classList.add('active');
                botaoSelecionado = horario;

            }


            containerHorarios.appendChild(
                horario
            );


            // ==================================================
            // EVENTO
            // ==================================================

            horario.addEventListener(
                'click',
                () => {

                    if (horarioOcupado) {
                        return;
                    }


                    horarioSelecionado =
                        textoHorario;
                    elementoHorario.textContent =
                        textoHorario;
                    atualizarStatusReserva();


                    if (botaoSelecionado) {

                        botaoSelecionado
                            .classList
                            .remove('active');

                    }


                    horario.classList.add(
                        'active'
                    );


                    botaoSelecionado =
                        horario;

                }
            );

        }

        if (containerHorarios.childElementCount === 0) {
            containerHorarios.innerHTML =
                '<p class="schedule-empty">Não há horários de uma hora dentro do funcionamento configurado.</p>';
        }

        atualizarStatusReserva();

    }


    // ==================================================
    // VERIFICAR MENSALISTA
    // ==================================================

    function existeMensalistaNoHorario(
        quadraId,
        data,
        horario
    ) {

        const [
            ano,
            mes,
            dia
        ] = data.split('-');


        const dataSelecionada =
            new Date(
                Number(ano),
                Number(mes) - 1,
                Number(dia)
            );


        const diaSemana =
            dataSelecionada.getDay();


        return mensalidades.some(
            mensalidade => {

                // ------------------------------------------
                // MESMA QUADRA
                // ------------------------------------------

                if (
                    Number(mensalidade.quadra_id) !==
                    Number(quadraId)
                ) {
                    return false;
                }


                // ------------------------------------------
                // MENSALIDADE ATIVA
                // ------------------------------------------

                if (
                    mensalidade.status !==
                    'Ativa'
                ) {
                    return false;
                }


                // ------------------------------------------
                // MESMO DIA DA SEMANA
                // ------------------------------------------

                if (
                    Number(mensalidade.dia_semana) !==
                    Number(diaSemana)
                ) {
                    return false;
                }


                // ------------------------------------------
                // MESMO HORÁRIO
                // ------------------------------------------

                if (
                    normalizarHorario(
                        mensalidade.horario
                    ) !== horario
                ) {
                    return false;
                }


                // ------------------------------------------
                // DATA DE INÍCIO
                // ------------------------------------------

                if (
                    mensalidade.data_inicio &&
                    data < mensalidade.data_inicio
                ) {
                    return false;
                }


                // ------------------------------------------
                // DATA DE ENCERRAMENTO
                // ------------------------------------------

                if (
                    mensalidade.data_encerramento &&
                    data > mensalidade.data_encerramento
                ) {
                    return false;
                }


                // ------------------------------------------
                // É MENSALISTA PARA ESTE HORÁRIO
                // ------------------------------------------

                return true;

            }
        );

    }


    // ==================================================
    // CONFIRMADOS
    // ==================================================

    function existeConfirmado(
        quadraId,
        data,
        horario
    ) {

        return agendamentos.some(
            agendamento => {

                return (
                    Number(agendamento.quadra_id) ===
                    Number(quadraId)
                    &&
                    agendamento.data ===
                    data
                    &&
                    normalizarHorario(
                        agendamento.horario
                    ) === horario
                    &&
                    agendamento.status ===
                    'Confirmado'
                );

            }
        );

    }


    // ==================================================
    // CONTAR CONFIRMADOS
    // ==================================================

    function contarConfirmados(
        quadraId,
        data,
        horario
    ) {

        return agendamentos.filter(
            agendamento => {

                return (
                    Number(agendamento.quadra_id) ===
                    Number(quadraId)
                    &&
                    agendamento.data ===
                    data
                    &&
                    normalizarHorario(
                        agendamento.horario
                    ) === horario
                    &&
                    agendamento.status ===
                    'Confirmado'
                );

            }
        ).length;

    }


    // ==================================================
    // CONTAR PENDENTES
    // ==================================================

    function contarPendentes(
        quadraId,
        data,
        horario
    ) {

        return agendamentos.filter(
            agendamento => {

                return (
                    Number(agendamento.quadra_id) ===
                    Number(quadraId)
                    &&
                    agendamento.data ===
                    data
                    &&
                    normalizarHorario(
                        agendamento.horario
                    ) === horario
                    &&
                    agendamento.status ===
                    'Pendente'
                );

            }
        ).length;

    }


    // ==================================================
    // LIMITE DA FILA
    // ==================================================

    function obterLimiteFila() {

        const valor =
            Number(
                configuracoes.limite_fila
            );


        if (
            Number.isFinite(valor) &&
            valor > 0
        ) {

            return valor;

        }


        return 0;

    }


    // ==================================================
    // CONFIGURAÇÃO BOOLEAN
    // ==================================================

    function obterConfiguracaoBoolean(
        chave,
        valorPadrao
    ) {

        if (
            configuracoes[chave] ===
            undefined
        ) {

            return valorPadrao;

        }


        const valor =
            configuracoes[chave];


        return (
            valor === true ||
            valor === 1 ||
            valor === '1' ||
            valor === 'true'
        );

    }


    // ==================================================
    // HORA DA CONFIGURAÇÃO
    // ==================================================

    function obterMinutosConfiguracao(
        chave,
        valorPadrao
    ) {

        const valor =
            configuracoes[chave];


        if (
            valor === undefined ||
            valor === null ||
            valor === ''
        ) {

            return valorPadrao;

        }


        const texto =
            String(valor).trim();


        // ------------------------------------------
        // ACEITA:
        // 08:00
        // 08:30
        // 23:00
        // 24:00
        // ------------------------------------------

        const partes =
            texto.split(':');


        const hora =
            Number(partes[0]);
        const minuto =
            Number(partes[1]);


        if (
            !Number.isInteger(hora) ||
            !Number.isInteger(minuto) ||
            hora < 0 ||
            hora > 24 ||
            minuto < 0 ||
            minuto > 59 ||
            (hora === 24 && minuto !== 0)
        ) {

            console.warn(
                `Configuração "${chave}" inválida:`,
                valor
            );

            return valorPadrao;

        }


        return hora * 60 + minuto;

    }


    // ==================================================
    // NORMALIZAR HORÁRIO
    // ==================================================

    function normalizarHorario(
        horario
    ) {

        if (!horario) {
            return '';
        }


        const texto =
            String(horario);


        return texto.substring(
            0,
            5
        );

    }

});