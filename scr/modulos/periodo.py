import logging
import concurrent.futures
import json
import re
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Configuração do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



def montar_prompt_periodo_quebra(texto_oficio: str, envolvido: dict, id_subsidio: str, 
                                  dados_subsidio: dict, info_sub: Dict[str, any], contexto: str) -> str:
    """
    Monta o prompt para extração do período de quebra de um subsídio específico.
    
    Args:
        texto_oficio: Texto completo do ofício
        envolvido: Dados do envolvido atual
        id_subsidio: ID do subsídio sendo analisado
        dados_subsidio: Dados do subsídio (classificação já realizada)
        info_sub: Informações do catálogo para este subsídio (JSON string)
        contexto: Contexto adicional
    """
    nome = envolvido.get("nome","")
    cpf_cnpj = envolvido.get("numero_documento_envolvido", "")
    chave_envolvido = envolvido.get("chave_envolvido", "N/A")
    trecho = dados_subsidio.get("trecho", "")
    prompt = f"""

        ## PERSONA
        Você é especialista em análise de ofícios judiciais e deve interpretar o texto OCR para identificar período de quebra de subsídio solicitado.

        ## OBJETIVO
        Encontrar o período de quebra de sigilo bancário solicitado no TEXTO DO OFÍCIO considerando o ENVOLVIDO e SUBSÍDIO.

        ## CONTEXTO DE OFÍCIOS E QUEBRA DE SIGILO
        Contexto sobre conteúdo de um ofício judicial para ajudar na interpretação e reasoning:
        {contexto}

        ## Descrição do conteúdo de SUBSÍDIO IDENTIFICADO que será fornecido:
        - ID_SUBSIDIO: nome do subsídio que será analisado;
        - Trecho: recorte do TEXTO DO OFÍCIO que foi utilizado anteriormente para encontrar a solicitação do subsídio.

        ## Descrição do conteúdo de ENVOLVIDO que será fornecido:
        - Nome: Nome do envolvido encontrado no texto;
        - Documento: Número do documento (pode ser CPF ou CNPJ) do envolvido encontrado no texto;

        ### REGRAS PARA ENVOLVIDO:
        - Se **Nome** estiver como NÃO IDENTIFICADO, considere para a análise no texto o **Documento**;
        - Se **Documento** estiver como NÃO IDENTIFICADO, considere para a análise no texto o **Nome**;
        - Se **Nome E Documento** estiver como NÃO IDENTIFICADO, faça uma análise geral.

        ## Descrição do TEXTO DO OFÍCIO que será fornecido:
        - Texto completo contendo informações de ofício judicial que deve ser analisado para encontrar o período de quebra.
        - Pode conter um ou mais subsídios além do SUBSÍDIO_IDENTIFICADO no TEXTO DO OFÍCIO. **A interpretação deve ser feita apenas para o SUBSÍDIO_IDENTIFICADO**.
        - Pode conter um ou mais indivíduos além do ENVOLVIDO no TEXTO DO OFÍCIO. **A interpretação deve ser feita apenas para o ENVOLVIDO**.

        ## Regras sobre o PERÍODO DE QUEBRA:
        - É composto de uma período_quebra_inicio (data inicial da solicitação de quebra de sigilo) E periodo_quebra_fim (data final da solicitação de quetbra);
        - Pode vir em diversos formatos, como por exemplo:
        - DD/MM/YYYY;
        - DD-MM-YYYY;
        - DDMMYYYY;
        - "Últimos cinco anos";
        - "entre dezembro e janeiro de 2024".
        - Caso apareça um período de quebra similar/relativo ao exemplo "últimos cinco anos", considere:
        - Se houver TEXTO DO OFÍCIO data de criação do ofício, considere ela como periodo_quebra_fim e faça o cálculo do período_quebra_inicio;
        - Se **NÃO** houver TEXTO DO OFÍCIO data de criação do ofício, considere como periodo_quebra_fim a resposta "DATA_OFICIO".
        - Se a solicitação for feita apenas para um dia específico, considere o periodo_quebra_inicio e periodo_quebra_fim iguais.

        ## INFORMAÇÕES SOBRE O SUBSÍDIO
        Considere a descrição e termos de exemplo para apoiar na análise e interpretação do subsídio:
        {info_sub}

        ## INSTRUÇÕES
        1. Leia e interprete o TEXTO DO OFÍCIO:
        {texto_oficio}
        2. Para o ID_SUBSIDIO: {id_subsidio} | Trecho: {trecho}, responda:
        2.1 Foi solicitado um período de quebra de sigilo bancário específico para ele?
            2.1.1 Se sim, considere ele como o período de quebra;
            2.1.2 Se não, há um período de quebra geral para a solicitação?
        3. Para o ENVOLVIDO de nome {nome} e documento {cpf_cnpj}, responda:
        3.1 Foi solicitado um período de quebra de sigilo bancário específico para ele?
            3.1.1 Se sim, é o mesmo período encontrado para o o SUBSÍDIO_IDENTIFICADO?
            3.1.2 Caso tenha um período de quebra geral para o envolvido, é o mesmo período de quebra encontrado para o o SUBSÍDIO_IDENTIFICADO?
        4. Caso a data "periodo_quebra_inicio" não for encontrada, retorne no campo "periodo_quebra_inicio": "NAO_ENCONTRADO_NO_TEXTO";
        5. Caso a data "periodo_quebra_fim" não for encontrada, retorne no campo "periodo_quebra_fim": "NAO_ENCONTRADO_NO_TEXTO";
        6. Todas as REGRAS foram consideradas durante a análise?
        7. Faça um reasoning e revise a resposta final.
        8. Adicione o trecho que comprova a quebra de sigilo solicitada no campo "periodo_quebra_texto_original".
        9. Retorne o JSON com a resposta no seguinte formato:
        {{
            "periodo_quebra_inicio": "DDMMYYYY",
            "periodo_quebra_fim": "DDMMYYYY",
            "periodo_quebra_texto_original": "Solicito a quebra de sigilo bancário dos últimos 10 anos"
        }}

        # Monta o prompt final
        """
    return prompt


class PeriodExtractorLLM:
    def __init__(self, client):
        """
        Inicializa a classe PeriodExtractorLLM com um cliente LLM.
        Args:
            client: Cliente LLM configurado.
        """
        self.client = client

    def extract_period_from_text(self, prompt: str) -> dict[str, str]:
        """
        Utiliza o LLM para interpretar o texto e extrair o período de quebra de sigilo.

        Args:
            prompt (str): Prompt formatado para a LLM.

        Returns:
            dict[str, str]: Resultado com os períodos de quebra extraídos.
        """
        try:
            # Envia o prompt para o modelo LLM
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="gpt-5",
                response_format={"type": "json_object"}
            )

            # Processa a resposta do LLM
            period = json.loads(response.choices[0].message.content)

            # Valida se as datas estão no formato esperado
            periodo_inicio = period.get("periodo_quebra_inicio", "NAO_ENCONTRADO_NO_TEXTO")
            periodo_fim = period.get("periodo_quebra_fim", "NAO_ENCONTRADO_NO_TEXTO")
            
            # Valida formato do inicio (data, período relativo ou não encontrado)
            inicio_valido = (
                re.match(r"^\d{8}$", periodo_inicio) or
                re.match(r"^ULTIMOS?_?\d+_?(ANOS?|MES(ES)?|DIAS?)$", periodo_inicio.upper()) or
                periodo_inicio in ["NAO_ENCONTRADO_NO_TEXTO"]
            )
            
            # Valida formato do fim
            fim_valido = (
                re.match(r"^\d{8}$", periodo_fim) or
                periodo_fim in ["NAO_ENCONTRADO_NO_TEXTO", "DATA_OFICIO"]
            )
            
            if inicio_valido and fim_valido:
                return {
                    "periodo_quebra_inicio": periodo_inicio,
                    "periodo_quebra_fim": periodo_fim,
                    "periodo_quebra_texto_original": period.get("periodo_quebra_texto_original"),
                }
            else:
                logger.warning("Resposta inválida do LLM ou formato inesperado.")
        except Exception as e:
            logger.error(f"Erro ao processar resposta do LLM: {e}")

        # Retorna "NAO ENCONTRADO NO TEXTO" em caso de erro ou resposta inválida
        return {
            "periodo_quebra_inicio": "NAO_ENCONTRADO_NO_TEXTO",
            "periodo_quebra_fim": "NAO_ENCONTRADO_NO_TEXTO",
            "periodo_quebra_texto_original": None,
        }


########## Funções de Processamento ##########


def processar_subsidio_quebra(args: tuple) -> tuple:
    """
    Processa um subsídio individual de um envolvido.
    Função para execução paralela.
    
    Args:
        args: Tupla com (client, texto_oficio, envolvido, id_subsidio, dados_subsidio, 
              info_sub, contexto, data_oficio)
    
    Returns:
        tuple: (chave_envolvido, id_subsidio, resultado_periodo)
    """
    (client, texto_oficio, envolvido, id_subsidio, dados_subsidio, 
     info_sub, contexto, data_oficio) = args
    
    chave_envolvido = envolvido.get("chave_envolvido", "N/A")
    
    logger.info(f"Processando: Envolvido={chave_envolvido}, Subsídio={id_subsidio}")
    
    try:
        # Monta o prompt específico para este envolvido+subsídio
        prompt = montar_prompt_periodo_quebra(
            texto_oficio=texto_oficio,
            envolvido=envolvido,
            id_subsidio=id_subsidio,
            dados_subsidio=dados_subsidio,
            info_sub=info_sub,
            contexto=contexto
        )
        
        # Extrai o período
        period_extractor_llm = PeriodExtractorLLM(client)
        resultado_quebra = period_extractor_llm.extract_period_from_text(prompt)
        
        # Resolve datas relativas
        periodo_fim = resultado_quebra.get("periodo_quebra_fim", "NAO_ENCONTRADO_NO_TEXTO")
        
        # Resolve data fim se for DATA_OFICIO
        if periodo_fim == "DATA_OFICIO":
            resultado_quebra["periodo_quebra_fim"] = data_oficio
        
        resultado_final = {
            "periodo_quebra_inicio": resultado_quebra.get("periodo_quebra_inicio", "NAO_ENCONTRADO_NO_TEXTO"),
            "periodo_quebra_fim": periodo_fim,
            "periodo_quebra_texto_original": resultado_quebra.get("periodo_quebra_texto_original"),
        }
        
        logger.info(f"Concluído: Envolvido={chave_envolvido}, Subsídio={id_subsidio}")
        
        return (chave_envolvido, id_subsidio, resultado_final)
        
    except Exception as e:
        logger.error(f"Erro ao processar Envolvido={chave_envolvido}, Subsídio={id_subsidio}: {e}")
        return (chave_envolvido, id_subsidio, {
            "periodo_quebra_inicio": "NAO_ENCONTRADO_NO_TEXTO",
            "periodo_quebra_fim": "NAO_ENCONTRADO_NO_TEXTO",
            "periodo_quebra_texto_original": None,
        })


def processar_envolvidos_com_logger(row, client):
    """
    Processa todos os envolvidos como isolados e adiciona logs para acompanhamento.
    Atualiza diretamente a listaSubs com os períodos de quebra extraídos.
    Executa chamadas paralelas para cada envolvido e cada subsídio.
    
    Retorna lista_subs com a mesma estrutura, adicionando periodo_quebra_inicio,
    periodo_quebra_fim e periodo_quebra_texto_original em cada subsídio.
    """
    texto_base = row.get("texto_limpo", "")
    lista_subs = row.get("listaSubs", [{}])  # Lista de envolvidos com subsídios
    contexto = pd.read_json(f"caminho_arquiv")

    catalogo_df = pd.read_json(f"caminho_arquiv")
    catalogo = catalogo_df.get("ID_SUBSIDIO", {})

    dataoficio = row.get("data_oficio")
    data_oficio = pd.to_datetime(dataoficio).strftime("%d%m%Y")

    # Normaliza os dados dos envolvidos (adiciona chave NOME|DOCUMENTO)
    envolvidos_normalizados = normalizar_dados_envolvidos(lista_subs)

    # Prepara lista de tarefas (envolvido x subsídio)
    tarefas = []
    
    for envolvido in envolvidos_normalizados:
        # Suporta tanto "nome" quanto "nome_envolvido"
        nome = envolvido.get("nome_envolvido", envolvido.get("nome", ""))
        cpf_cnpj = envolvido.get("numero_documento_envolvido", "")
        chave_envolvido = envolvido.get("chave_envolvido", "")
        subsidios = envolvido.get("subsidios", {})

        logger.info(f"Preparando envolvido: Nome={nome}, CPF/CNPJ={cpf_cnpj}, Chave={chave_envolvido}")

        # Mesmo sem subsídios, o envolvido foi normalizado
        if not subsidios:
            logger.warning(f"Envolvido {chave_envolvido} sem subsídios para processar")
            continue
        
        # Cria uma tarefa para cada subsídio do envolvido
        for id_subsidio, dados_subsidio in subsidios.items():
            info = catalogo.get(id_subsidio, {})
            info_sub = {"id":id_subsidio, **info}
            print(f"entrada catálogo:{info_sub}")
            
            tarefa = (
                client,
                texto_base,
                envolvido,
                id_subsidio,
                dados_subsidio,
                info_sub,
                contexto,
                data_oficio
            )
            tarefas.append(tarefa)
    
    logger.info(f"Total de tarefas a processar: {len(tarefas)}")
    
    # Processa em paralelo (cada envolvido+subsídio)
    resultados_por_envolvido = {}
    
    if tarefas:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            resultados = list(executor.map(processar_subsidio_quebra, tarefas))
        
       # Organiza resultados por envolvido
        for chave_envolvido, id_subsidio, resultado in resultados:
            if chave_envolvido not in resultados_por_envolvido:
                resultados_por_envolvido[chave_envolvido] = {}
            resultados_por_envolvido[chave_envolvido][id_subsidio] = resultado

    # Atualiza os subsídios com os períodos de quebra extraídos
    for envolvido in envolvidos_normalizados:
        chave = envolvido.get("chave_envolvido")
        subsidios = envolvido.get("subsidios", {})
        
        if chave in resultados_por_envolvido:
            for id_subsidio, dados_subsidio in subsidios.items():
                if id_subsidio in resultados_por_envolvido[chave]:
                    resultado = resultados_por_envolvido[chave][id_subsidio]
                    # Adiciona os campos de período diretamente no subsídio
                    dados_subsidio["periodo_quebra_inicio"] = resultado.get(
                        "periodo_quebra_inicio", "NAO_ENCONTRADO_NO_TEXTO"
                    )
                    dados_subsidio["periodo_quebra_fim"] = resultado.get(
                        "periodo_quebra_fim", "NAO_ENCONTRADO_NO_TEXTO"
                    )
                    dados_subsidio["periodo_quebra_texto_original"] = resultado.get(
                        "periodo_quebra_texto_original", None
                    )

    # Atualiza a listaSubs no retorno (mantém estrutura original + campos de período)
    row["listaSubs"] = envolvidos_normalizados
    return row


def processa_todos_com_logger(df_temp, client):
    """
    Processa os dados em paralelo com logs e atualiza a listaSubs.
    """
    rows = df_temp.to_dict(orient="records")
    
    logger.info(f"Iniciando processamento de {len(rows)} documentos")
    
    def processar_row(row):
        return processar_envolvidos_com_logger(row, client)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=250) as executor:
        resultados = list(executor.map(processar_row, rows))
    
    logger.info(f"Processamento concluído para {len(resultados)} documentos")
    
    return pd.DataFrame(resultados)




# # Processar dados
dados_processados = processa_todos_com_logger(dados, client)
print(dados_processados)
