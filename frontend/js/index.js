document.addEventListener('DOMContentLoaded', () => {

    // ==================================================
    // BUSCAR QUADRAS DO BANCO
    // ==================================================

    Promise.all([
        fetch('/quadras').then(response => {
            if (!response.ok) throw new Error('Não foi possível carregar as quadras.');
            return response.json();
        }),
        fetch('/configuracoes').then(response => {
            if (!response.ok) throw new Error('Não foi possível carregar o conteúdo da página inicial.');
            return response.json();
        })
    ]).then(([quadras, configuracoes]) => {
        ['salao', 'sintetico', 'areia'].forEach(tipo => {
            const daModalidade = quadras.filter(item =>
                Number(item.ativo) === 1 && normalizarTipo(item.tipo) === tipo
            );
            atualizarPrecoCard(daModalidade, tipo);
            atualizarInformacoesQuadra(daModalidade, tipo);
        });
        aplicarConfiguracoes(configuracoes);
    }).catch(error => console.error('Erro ao carregar a página inicial:', error));


    // ==================================================
    // FUNÇÃO: ATUALIZAR PREÇO
    // ==================================================

    function atualizarPrecoCard(quadras, tipo) {

        const elemento =
            document.querySelector(`.biome-${tipo} .price`);


        if (!elemento) {
            return;
        }


        // Normalize the modality labels so configured prices always match
        // whether the database stores the label or the internal value.
        if (quadras.length === 0) {
            elemento.textContent = 'Valores sob consulta';
            return;
        }


        // Remove valores inválidos
        const precos =
            quadras
                .map(quadra => Number(quadra.valor))
                .filter(valor => !isNaN(valor) && valor > 0);


        if (precos.length === 0) {
            elemento.textContent = 'Valores sob consulta';
            return;
        }


        // Encontra o menor preço
        const menorPreco =
            Math.min(...precos);


        // Formata para moeda brasileira
        const precoFormatado =
            menorPreco.toLocaleString(
                'pt-BR',
                {
                    style: 'currency',
                    currency: 'BRL'
                }
            );


        const valoresMensais = quadras
            .map(quadra => Number(quadra.valor_mensal))
            .filter(valor => Number.isFinite(valor) && valor > 0);
        const mensal = valoresMensais.length
            ? ` · mensal a partir de ${Math.min(...valoresMensais).toLocaleString('pt-BR', {
                style: 'currency',
                currency: 'BRL'
            })}`
            : '';
        elemento.textContent = `A partir de ${precoFormatado}/h${mensal}`;

    }

    function normalizarTipo(valor) {
        return String(valor || '')
            .toLocaleLowerCase('pt-BR')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function atualizarInformacoesQuadra(quadrasDaModalidade, tipo) {
        const card = document.querySelector(`.biome-${tipo}`);
        if (!card) return;
        let background = card.querySelector('.biome-card-bg');
        if (!background) {
            background = document.createElement('div');
            background.className = 'biome-card-bg';
            card.insertBefore(background, card.firstChild);
        }
        if (!quadrasDaModalidade.length) return;
        const quadra = quadrasDaModalidade[0];
        const badge = document.querySelector(`[data-home-badge="${tipo}"]`);
        const descricao = document.querySelector(`[data-home-description="${tipo}"]`);
        const medidas = quadra.medidas ? ` · ${quadra.medidas}` : '';
        if (badge) {
            badge.textContent = `${quadra.nome}${quadrasDaModalidade.length > 1
                ? ` + ${quadrasDaModalidade.length - 1}`
                : ''}${medidas}`;
        }
        if (descricao && quadra.descricao) descricao.textContent = quadra.descricao;
        if (card && quadra.imagem && /^\/frontend\/(?!\/)[A-Za-z0-9/_.,-]+$/.test(quadra.imagem)) {
            background.style.backgroundImage = `url("${quadra.imagem}")`;
        }
    }

    function aplicarConfiguracoes(lista) {
        const porChave = Object.fromEntries(
            lista.map(item => [item.chave, item.valor])
        );
        const h1 = document.getElementById('home-title');
        if (porChave.site_titulo && h1) {
            const destaque = h1.querySelector('span');
            const partes = porChave.site_titulo.trim().split(/(?<=\.)\s+/);
            if (destaque && partes.length > 1) {
                destaque.textContent = partes.pop();
                h1.firstChild.nodeValue = `${partes.join(' ')} `;
            } else {
                h1.textContent = porChave.site_titulo;
            }
        }
        const vinculos = [
            ['site_subtitulo', 'home-subtitle'],
            ['site_sobre', 'home-about-copy'],
            ['site_sobre_titulo', 'home-about-title'],
            ['site_estrutura_titulo', 'home-structure-title'],
            ['site_estrutura_subtitulo', 'home-structure-copy'],
            ['site_contato_titulo', 'home-contact-title'],
            ['site_rodape', 'home-footer-copy']
        ];
        vinculos.forEach(([chave, id]) => {
            const elemento = document.getElementById(id);
            if (elemento && porChave[chave]) elemento.textContent = porChave[chave];
        });
        const cta = document.getElementById('home-cta');
        if (cta && porChave.site_cta) cta.textContent = porChave.site_cta;
        const contatoLabel = document.getElementById('home-contact-label');
        if (contatoLabel && porChave.site_contato_label) {
            contatoLabel.textContent = porChave.site_contato_label;
        }
    }


    // ==================================================
    // FUNÇÃO: ATUALIZAR IMAGEM
    // ==================================================

    function atualizarImagemCard(
        tipo,
        caminhoImagem
    ) {

        const card =
            document.querySelector(
                `.biome-${tipo}`
            );


        if (!card) {
            return;
        }


        // Verifica se o card já possui
        // uma área específica para background.

        let background =
            card.querySelector('.biome-card-bg');


        // Se não existir, cria.
        if (!background) {

            background =
                document.createElement('div');

            background.classList.add(
                'biome-card-bg'
            );

            card.insertBefore(
                background,
                card.firstChild
            );

        }


        background.style.backgroundImage =
            `url('${caminhoImagem}')`;

    }

});