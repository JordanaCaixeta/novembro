# Objetivo Geral

    O problema que você precisa resolver
    Você está construindo uma solução multiagentes, usando smolagents, capaz de analisar textos OCR(já extraídos) de ofícios jurídicos de quebra de sigilo, que são altamente variados, ruidosos e inconsistentes.
    O objetivo é extrair de forma precisa e sem alucinação:
        1.	Quem é a pessoa (ou pessoas) cuja quebra de sigilo está sendo solicitada.
        2.	PConsiderar apenas solicitações para instituição financeira (ou se não estiver explícito, assumir que é para a instituição financeira) (BACENdeve ser considerado).
        3.	Quais tipos de subsídios (documentos/arquivos/etc.) estão sendo solicitados no texto.
        4.	Datas/períodos da quebra de sigilo para cada tipo de subsídio.
        5.	O sistema deve operar sobre um catálogo grande de subsídios, cada um contendo:
            o	Nome
            o	Descrição
            o	Exemplos
________________________________________
# 1. Requisitos técnicos levantados
    1.1. Framework
        •	Você quer usar smolagents, que permite criar agentes + ferramentas modulares em Python.
    1.2. OCR muito diverso
        •	Formatação diferente, ruído, hifenização, páginas quebradas, rodapés, cabeçalhos.
        •	Requer pré-processamento robusto e segmentação inteligente.
    1.3. Lista grande de subsídios
        •	Muitos itens → LLM sozinho começa a alucinar.
        •	Solução proposta:
            o	Heurística de palavras-chave + embeddings primeiro.
            o	LLM para confirmação.
            o	Forçar JSON e validar schema.
    1.4 Preocupação com redução de alucinação
        Estratégias definidas:
        •	Dividir a tarefa em múltiplos agentes especializados.
        •	Prompting estrito + saída JSON + validação.
        •	Logging para auditoria.
_______________________________________________________
# 2. Arquitetura multi-agente pontos principais
    2.1 Limpa e normaliza texto OCR, corrige hifenização, remove rodapé, cria parágrafos.
    2.2	Identifica o trecho do texto referente à instituição financeira.Se não houver instituição explícita → assume banco.
    2.3	Extrai nomes, CPFs, CNPJs e contexto de quem é alvo da quebra de sigilo.
    2.4	Recebe o trecho da instituição financeira. Compara com catálogo grande de subsídios. Usa heurística + embeddings + LLM robusto.
    2.5	Extrai datas relacionadas ao pedido de sigilo. Usa regex + heurística + LLM.
    2.6 Orquestrador que coordena todos, registra logs, executa pipelines paralelos, valida e consolida o resultado.
________________________________________

# 3. CONSIDERAÇÕES ESPECÍFICAS SOBRE O BANCO X
    O pipeline é para o Banco X, e os ofícios chegam de várias formas:
    •	Às vezes o pedido é explicitamente para o Banco X(ou lista de nomes relacionados ao banco X).
    •	Às vezes é para instituição financeira genérica → o Banco X deve ser considerado como alvo.
    •	Às vezes há pedidos múltiplos no mesmo documento, por exemplo:
    o	Quebra de sigilo bancário → Banco X
    o	Quebra de sigilo fiscal → Receita Federal
    o	Quebra de sigilo telefônico → Operadora
    o	Quebra junto ao BACEN
    •	Às vezes o ofício NÃO menciona nenhuma instituição → neste caso, considerar que a quebra é para instituição financeira, portanto inclui Banco X.
    O pipeline deve conseguir:
    •	Descartar trechos relacionados a outras instituições (Receita, Polícia, BACEN, operadoras).
    •	Isolar o trecho destinado a instituições financeiras (mesmo que não cite o Banco X pelo nome).
    •	Tratar de forma correta quando houver múltiplos destinatários, sem misturar pedidos alheios com os do Banco X.
________________________________________
# 4.  Dificuldades do OCR e Natureza do Ofício
    O ofício pode conter qualquer combinação dos seguintes trechos, e SEM PADRÃO:
        1.	Header/Rodapé gerado pelo OCR
            o	Ex.:"<<PAGE_12>>", "<<OCR_TEXT>>", "Scanned by …", “Página 1/5”, “___”.
        2.	Header/Rodapé jurídico do documento
            o	Ex.: "PODER JUDICIÁRIO DO ESTADO X", "FÓRUM CRIMINAL", "COMARCA Y".
        3.	Identificação do documento
            o	Número do processo
            o	Autoridade judiciária
            o	Data de emissão
            o	Natureza do procedimento
        4.	Descrição do caso
            o	Contexto da investigação, crime, situação processual.
        5.	Fundamentação jurídica da quebra
            o	Artigos de lei
            o	Justificativas
            o	Precedentes
        6.	Solicitação de quebra de sigilo (trecho mais importante para nós)
            o	Produtos, serviços, contas, cartões, extratos, transações…
            o	Datas e períodos
            o	Restrição a instituição específica
            o	Às vezes dividido em blocos: “Oficie-se ao Banco X”; “Oficie-se ao BACEN”; etc.
        7.	Informações dos investigados
            o	Nome(s)
            o	CPF(s)
            o	Endereço (às vezes)
            o	Filiação
            o	Outras informações sensíveis
        8.	Prazos
            o	Ex.: “Prazo de 10 dias para cumprimento”.
            O pipeline precisa:
                •	Isolar automaticamente a parte do documento que importa (a “solicitação bancária”),
                mesmo sem padronização.
                •	Ignorar tudo que não for relevante, como:
                    o	Header/rodapé OCR
                    o	Cabeçalho institucional
                    o	Fundamentação jurídica longa
                    o	Justificativas
                    o	Pedidos para outras instituições
# 5.  Validação CCS após extração
    Tool que faz integração via API com banco de dados CCS:
    Após extrair:
    •	Nome
    •	CPF
    Você chama a tool:
    get_ccs_relations(cpf)
    Essa tool retorna:
    •	Contas vinculadas
    •	Relacionamentos financeiros
    •	Se o CPF realmente aparece no CCS
    O pipeline deve integrar essa tool no fluxo.
