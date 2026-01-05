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


# Catálogo de subsídios (placeholder - deve ser carregado externamente)
CATALOGO_SUBSIDIOS = {}


def carregar_catalogo_subsidios(catalogo_dict: dict):
    """
    Carrega o catálogo de subsídios.
    Args:
        catalogo_dict: Dicionário com subsídios indexados por ID.
    """
    global CATALOGO_SUBSIDIOS
    CATALOGO_SUBSIDIOS = catalogo_dict


def obter_info_subsidio(id_subsidio: str) -> dict:
    """
    Obtém as informações de um subsídio do catálogo.
    Args:
        id_subsidio: ID do subsídio.
    Returns:
        dict: Informações do subsídio ou dict vazio.
    """
    return CATALOGO_SUBSIDIOS.get(str(id_subsidio), {})


def calcular_data_inicio_relativa(periodo_info: str, data_oficio: str) -> str:
    """
    Calcula a data de início quando o LLM retorna um período relativo.
    
    Args:
        periodo_info: Informação do período (ex: ULTIMOS_5_ANOS, DDMMAAAA)
        data_oficio: Data do ofício no formato DDMMAAAA
    
    Returns:
        str: Data calculada no formato DDMMAAAA
    """
    if not periodo_info or periodo_info == "NAO_ENCONTRADO_NO_TEXTO":
        return "NAO_ENCONTRADO_NO_TEXTO"
    
    # Se já é uma data no formato DDMMAAAA, retorna como está
    if re.match(r"^\d{8}$", periodo_info):
        return periodo_info
    
    # Tenta parsear a data do ofício
    try:
        if data_oficio and data_oficio != "NAO_ENCONTRADO_NO_TEXTO":
            data_ref = datetime.strptime(data_oficio, "%d%m%Y")
        else:
            logger.warning("Data do ofício não disponível para cálculo relativo")
            return "NAO_ENCONTRADO_NO_TEXTO"
    except ValueError as e:
        logger.error(f"Erro ao parsear data do ofício '{data_oficio}': {e}")
        return "NAO_ENCONTRADO_NO_TEXTO"
    
    periodo_info_upper = periodo_info.upper()
    
    # Padrão: ULTIMOS_N_ANOS
    match_anos = re.match(r"ULTIMOS?_?(\d+)_?ANOS?", periodo_info_upper)
    if match_anos:
        anos = int(match_anos.group(1))
        data_inicio = data_ref - relativedelta(years=anos)
        return data_inicio.strftime("%d%m%Y")
    
    # Padrão: ULTIMOS_N_MESES
    match_meses = re.match(r"ULTIMOS?_?(\d+)_?MES(?:ES)?", periodo_info_upper)
    if match_meses:
        meses = int(match_meses.group(1))
        data_inicio = data_ref - relativedelta(months=meses)
        return data_inicio.strftime("%d%m%Y")
    
    # Padrão: ULTIMOS_N_DIAS
    match_dias = re.match(r"ULTIMOS?_?(\d+)_?DIAS?", periodo_info_upper)
    if match_dias:
        dias = int(match_dias.group(1))
        data_inicio = data_ref - timedelta(days=dias)
        return data_inicio.strftime("%d%m%Y")
    
    # Padrão: DESDE_ABERTURA
    if "DESDE_ABERTURA" in periodo_info_upper or "DESDE_INICIO" in periodo_info_upper:
        return "DESDE_ABERTURA"
    
    logger.warning(f"Padrão de período não reconhecido: {periodo_info}")
    return periodo_info


def resolver_data_fim(periodo_fim: str, data_oficio: str) -> str:
    """
    Resolve a data de fim, substituindo DATA_OFICIO pela data real.
    """
    if periodo_fim == "DATA_OFICIO":
        if data_oficio and data_oficio != "NAO_ENCONTRADO_NO_TEXTO":
            return data_oficio
        else:
            return "NAO_ENCONTRADO_NO_TEXTO"
    return periodo_fim


def gerar_chave_envolvido(nome: str, documento: str) -> str:
    """
    Gera uma chave única para identificação do envolvido: NOME|DOCUMENTO
    """
    nome_limpo = (nome or "").strip().upper()
    doc_limpo = re.sub(r'[^\d]', '', documento or "")
    
    if nome_limpo and doc_limpo:
        return f"{nome_limpo}|{doc_limpo}"
    elif nome_limpo:
        return f"{nome_limpo}|SEM_DOCUMENTO"
    elif doc_limpo:
        return f"SEM_NOME|{doc_limpo}"
    else:
        return "ENVOLVIDO_NAO_IDENTIFICADO"


def normalizar_dados_envolvidos(lista_subs: list) -> list:
    """
    Normaliza a lista de envolvidos, garantindo estrutura consistente.
    Adiciona chave única para cada envolvido.
    """
    if not lista_subs:
        return [{
            "chave_envolvido": "ENVOLVIDO_NAO_IDENTIFICADO",
            "nome": "",
            "numero_documento_envolvido": "",
            "tipo_documento": "",
            "subsidios": {}
        }]
    
    envolvidos_normalizados = []
    chaves_vistas = set()
    
    for envolvido in lista_subs:
        nome = envolvido.get("nome", "")
        documento = envolvido.get("numero_documento_envolvido", "")
        
        chave = gerar_chave_envolvido(nome, documento)
        
        # Evita duplicatas por chave
        if chave in chaves_vistas:
            contador = 1
            chave_original = chave
            while chave in chaves_vistas:
                chave = f"{chave_original}_{contador}"
                contador += 1
        
        chaves_vistas.add(chave)
        
        envolvido_normalizado = {
            "chave_envolvido": chave,
            "nome": nome,
            "numero_documento_envolvido": documento,
            "tipo_documento": envolvido.get("tipo_documento", ""),
            "subsidios": envolvido.get("subsidios", {})
        }
        envolvidos_normalizados.append(envolvido_normalizado)
    
    return envolvidos_normalizados


def montar_prompt_periodo_quebra(texto_oficio: str, envolvido: dict, id_subsidio: str, 
                                  dados_subsidio: dict, info_sub: dict, contexto: str = "") -> str:
    """
    Monta o prompt para extração do período de quebra de um subsídio específico.
    
    Args:
        texto_oficio: Texto completo do ofício
        envolvido: Dados do envolvido atual
        id_subsidio: ID do subsídio sendo analisado
        dados_subsidio: Dados do subsídio (classificação já realizada)
        info_sub: Informações do catálogo para este subsídio
        contexto: Contexto adicional
    """
    nome = envolvido.get("nome", "Não identificado")
    cpf_cnpj = envolvido.get("numero_documento_envolvido", "Não identificado")
    chave_envolvido = envolvido.get("chave_envolvido", "N/A")
    
    # Formata info do subsídio do catálogo
    info_sub_str = ""
    if info_sub:
        partes = []
        if info_sub.get("id"):
            partes.append(f"ID: {info_sub['id']}")
        if info_sub.get("nome"):
            partes.append(f"Nome: {info_sub['nome']}")
        if info_sub.get("descricao"):
            partes.append(f"Descrição: {info_sub['descricao']}")
        exemplos = info_sub.get("exemplos", [])
        if exemplos:
            if isinstance(exemplos, list):
                partes.append(f"Exemplos: {', '.join(exemplos)}")
            else:
                partes.append(f"Exemplos: {exemplos}")
        info_sub_str = "\n".join(partes)
    else:
        info_sub_str = "Informações do subsídio não disponíveis no catálogo."
    
    # Classificação já realizada
    classif_str = json.dumps(dados_subsidio, ensure_ascii=False, indent=2) if dados_subsidio else "{}"
    
    prompt = f"""Você é um especialista em análise de ofícios judiciais de quebra de sigilo bancário.

## TAREFA
Extraia o PERÍODO DE QUEBRA DE SIGILO para:
- Envolvido: {nome} (Documento: {cpf_cnpj})
- Subsídio: ID {id_subsidio}

## INFORMAÇÕES DO SUBSÍDIO (CATÁLOGO)
{info_sub_str}

## CLASSIFICAÇÃO JÁ REALIZADA
{classif_str}

## IDENTIFICAÇÃO DO ENVOLVIDO
- Chave: {chave_envolvido}
- Nome: {nome}
- CPF/CNPJ: {cpf_cnpj}

## TEXTO DO OFÍCIO
{texto_oficio}

{f"## CONTEXTO" + chr(10) + contexto if contexto else ""}

## INSTRUÇÕES
1. Localize o trecho que menciona o período de quebra para este subsídio.
2. O período pode estar expresso como:
   - Datas explícitas: "de 01/01/2020 a 31/12/2023"
   - Períodos relativos: "últimos 5 anos", "últimos 3 meses"
   - Referências à data do ofício: "até a presente data"
   - Desde abertura: "desde a abertura da conta"

## FORMATO DE RESPOSTA (JSON)
{{
    "periodo_quebra_inicio": "<DDMMAAAA ou ULTIMOS_N_ANOS ou ULTIMOS_N_MESES ou ULTIMOS_N_DIAS ou DESDE_ABERTURA ou NAO_ENCONTRADO_NO_TEXTO>",
    "periodo_quebra_fim": "<DDMMAAAA ou DATA_OFICIO ou NAO_ENCONTRADO_NO_TEXTO>",
    "periodo_quebra_texto_original": "<trecho exato do texto ou null>"
}}

## REGRAS
- periodo_quebra_inicio: DDMMAAAA, ULTIMOS_5_ANOS, ULTIMOS_3_MESES, ULTIMOS_30_DIAS, DESDE_ABERTURA ou NAO_ENCONTRADO_NO_TEXTO
- periodo_quebra_fim: DDMMAAAA, DATA_OFICIO ou NAO_ENCONTRADO_NO_TEXTO
- NÃO INVENTE datas
- Responda SOMENTE com o JSON"""

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
                model="gpt-4o",
                temperature=0.1,
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
                periodo_inicio in ["NAO_ENCONTRADO_NO_TEXTO", "DESDE_ABERTURA"]
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

    def buscar_data_oficio(self, row: pd.Series) -> str:
        """
        Busca a data do ofício na linha atual do DataFrame e retorna no formato DDMMAAAA.
        """
        try:
            if "data_oficio" in row and pd.notna(row["data_oficio"]):
                data_oficio = row["data_oficio"]
                data_formatada = pd.to_datetime(data_oficio).strftime("%d%m%Y")
                return data_formatada
            else:
                logger.warning("Data do ofício não encontrada na linha.")
                return "NAO_ENCONTRADO_NO_TEXTO"
        except Exception as e:
            logger.error(f"Erro ao buscar data do ofício na linha: {e}")
            return "NAO_ENCONTRADO_NO_TEXTO"


########## Funções de Processamento ##########


def processar_subsidio_individual(args: tuple) -> tuple:
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
        periodo_inicio = resultado_quebra.get("periodo_quebra_inicio", "NAO_ENCONTRADO_NO_TEXTO")
        periodo_fim = resultado_quebra.get("periodo_quebra_fim", "NAO_ENCONTRADO_NO_TEXTO")
        
        # Resolve data fim se for DATA_OFICIO
        periodo_fim_resolvido = resolver_data_fim(periodo_fim, data_oficio)
        
        # Calcula data início se for período relativo
        data_referencia = periodo_fim_resolvido if periodo_fim_resolvido != "NAO_ENCONTRADO_NO_TEXTO" else data_oficio
        periodo_inicio_calculado = calcular_data_inicio_relativa(periodo_inicio, data_referencia)
        
        resultado_final = {
            "periodo_quebra_inicio": periodo_inicio_calculado,
            "periodo_quebra_fim": periodo_fim_resolvido,
            "periodo_quebra_texto_original": resultado_quebra.get("periodo_quebra_texto_original"),
        }
        
        logger.info(f"Concluído: Envolvido={chave_envolvido}, Subsídio={id_subsidio}, "
                   f"Período={periodo_inicio_calculado} a {periodo_fim_resolvido}")
        
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
    """
    texto_base = row.get("texto_limpo", "")
    lista_subs = row.get("listaSubs", [{}])  # Lista de subsídios
    contexto = row.get("contexto", "")
    
    # Busca data do ofício
    data_oficio = "NAO_ENCONTRADO_NO_TEXTO"
    if "data_oficio" in row and pd.notna(row.get("data_oficio")):
        try:
            data_oficio = pd.to_datetime(row["data_oficio"]).strftime("%d%m%Y")
        except:
            pass

    # Normaliza os dados dos envolvidos (adiciona chave NOME|DOCUMENTO)
    envolvidos_normalizados = normalizar_dados_envolvidos(lista_subs)

    # Prepara lista de tarefas (envolvido x subsídio)
    tarefas = []
    
    for envolvido in envolvidos_normalizados:
        nome = envolvido.get("nome", "")
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
            # Obtém informações do catálogo para este subsídio (info_sub)
            info_sub = obter_info_subsidio(id_subsidio)
            
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
            resultados = list(executor.map(processar_subsidio_individual, tarefas))
        
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
                    dados_subsidio["periodo_quebra_inicio"] = resultado.get(
                        "periodo_quebra_inicio", "NAO_ENCONTRADO_NO_TEXTO"
                    )
                    dados_subsidio["periodo_quebra_fim"] = resultado.get(
                        "periodo_quebra_fim", "NAO_ENCONTRADO_NO_TEXTO"
                    )
                    dados_subsidio["periodo_quebra_texto_original"] = resultado.get(
                        "periodo_quebra_texto_original", None
                    )

    # Atualiza a listaSubs no retorno
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


# Exemplo de uso:
# from openai import OpenAI
# client = OpenAI()
# 
# # Carregar catálogo de subsídios
# carregar_catalogo_subsidios({"1": {"id": "1", "nome": "Extrato", "descricao": "...", "exemplos": [...]}})
# 
# # Processar dados
# dados_processados = processa_todos_com_logger(dados, client)
# print(dados_processados)
