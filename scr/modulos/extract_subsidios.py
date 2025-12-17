# 6. ETAPA DE VALIDAÇÃO


import re
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel
from smolagents import tool
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scr.modulos.datas_management import extract_period_from_text

## 6.1 AGENTE VALIDAÇÃO MAS TF-IDF

class SubsidyMatch(BaseModel):
    subsidio_id: str
    nome_subsidio: str
    texto_original: str  # Como apareceu no ofício
    similarity_score: float
    periodo: Optional[dict] = None  # {"inicio": "01/01/2023", "fim": "31/12/2023"} -> quero tirar do código essa parte
    carta_circular: Optional[str] = None  # Carta Circular associada -> quero tirar do código essa parte
    llm_validated: bool = False  # Se passou por validação LLM -> quero tirar do código essa parte
    llm_confidence: Optional[float] = None  # Confidence do LLM (0-1)
    texto_evidencia: Optional[str] = None  # Frase exata onde foi encontrado
    justificativa_match: Optional[str] = None  # Por que o LLM achou que é esse subsídio
    sugestao_exemplo: Optional[str] = None  # Texto para adicionar aos exemplos do catálogo
    
class SubsidiesExtraction(BaseModel):
    subsidios_solicitados: List[SubsidyMatch]
    total_subsidios: int
    subsidios_nao_identificados: List[str]

class LLMSubsidyValidation(BaseModel):
    """Validação de um subsídio individual pelo LLM"""
    subsidio_id: str
    e_valido: bool  # Se o match faz sentido
    confidence: float  # 0.0 a 1.0
    texto_evidencia: Optional[str] = None  # Frase exata do ofício onde foi encontrado
    justificativa: Optional[str] = None  # Por que o LLM considera que é esse subsídio
    sugestao_exemplo: Optional[str] = None  # Como adicionar aos exemplos do catálogo

class LLMSubsidioNovo(BaseModel):
    """Subsídio novo identificado pelo LLM que não estava no catálogo"""
    texto_solicitacao: str  # O que foi solicitado
    texto_evidencia: str  # Onde aparece no ofício
    catalogo_id_sugerido: Optional[str] = None  # Se o LLM achar que é variante de algum existente
    e_subsidio_novo: bool = True  # Se é realmente novo ou variante
    justificativa: str  # Por que o LLM acha que é novo/variante

class LLMValidationResult(BaseModel):
    """Resultado completo da validação LLM"""
    validacoes: List[LLMSubsidyValidation]  # Validação dos matches TF-IDF
    subsidios_novos: List[LLMSubsidioNovo]  # Subsídios não capturados pelo TF-IDF
    todos_subsidios_capturados: bool  # Se o LLM acredita que pegou tudo
    confidence_geral: float  # Confidence geral da extração (0-1)
    observacoes: Optional[str] = None  # Observações gerais do LLM

def validate_subsidies_with_llm(
    texto_oficio: str,
    tfidf_matches: List[SubsidyMatch],
    unmatched_fragments: List[str],
    classificacao_llm: dict[str, dict[str, any]],
    catalogo_completo: pd.DataFrame
) -> LLMValidationResult:
    """
    Valida os matches do TF-IDF usando LLM e identifica subsídios faltantes

    Implementação REAL com smolagents LiteLLMModel

    Args:
        texto_oficio: Texto completo do ofício
        tfidf_matches: Matches identificados pelo TF-IDF
        unmatched_fragments: Fragmentos não identificados pelo TF-IDF
        classificacao_llm: resultado JSON do classificador (prévio) com as flag_presenca
        catalogo_completo: DataFrame com catálogo de subsídios

    Returns:
        LLMValidationResult com validações e subsídios novos identificados
    """

    import logging
    import json
    import os
    logger = logging.getLogger(__name__)

    from smolagents import LiteLLMModel


    # Processando o json para gerar o texto formatado
    catalogo_text = load_catalog(catalog_path)

    # Prepara matches do TF-IDF
    matches_text = "\n".join([
        f"Match {i+1}: {m.nome_subsidio} (ID: {m.subsidio_id}, Score: {m.similarity_score:.2f})\n"
        f"  Texto encontrado: \"{m.texto_original}\""
        for i, m in enumerate(tfidf_matches)
    ]) if tfidf_matches else "Nenhum match identificado pelo TF-IDF"

    # Prepara fragmentos não identificados
    fragments_text = "\n".join([
        f"- {frag}" for frag in unmatched_fragments
    ]) if unmatched_fragments else "Nenhum fragmento não identificado"
    
    response = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f"""
                ## PERSONA
                    Você é um especialista em análise de ofícios judiciais de quebra de sigilo bancário.
                
                ## OBJETIVO
                    Sua tarefa é validar a extração de subsídios (tipos de documentos solicitados) de um ofício.

                ## OFÍCIO COMPLETO:
                ```
                {texto_oficio}
                ```
                
                ## SUBSÍDIOS JÁ IDENTIFICADOS PELO SISTEMA (TF-IDF):
                {matches_text}
                
                ## FRAGMENTOS NÃO IDENTIFICADOS:
                {fragments_text}
                
                ## CATÁLOGO DE SUBSÍDIOS DISPONÍVEIS (primeiros 50):
                {catalogo_text}

                ## CLASSIFICAÇÃO POR LLM PARA CADA UM DOS IDS DOS SUBSÍDIOS
                {classificacao_llm}
                 ---

                ## SUAS TAREFAS:
                
                ### 1. VALIDAR MATCHES DO TF-IDF
                Para cada match identificado, responda:
                    - Há termos similares ou contexto indicando solicitação?
                    - Ele realmente faz sentido no contexto do ofício?
                    - Qual é a frase EXATA do ofício onde o subsídio foi mencionado?
                    - A sua localização no texto é depois de termos de solicitação (como por exemplo DETERMINO|SOLICITO|REQUEIRO|OFICIE-SE, ou sinônimos), caso o ofício apresente esses termos? 
                    - Por que você considera que esse match está correto (ou incorreto)?
                    - Ele foi identificado pela *CLASSIFICAÇÃO POR LLM*?
                    - Como essa solicitação poderia ser adicionada aos exemplos do catálogo? (texto curto e genérico)
                
                ### 2. IDENTIFICAR SUBSÍDIOS FALTANTES
                    - Há algum subsídio solicitado no ofício que NÃO está na lista de matches?
                    - Se sim, analise o 'trecho_identificado' com a frase exata onde ele aparece e a 'justificativa_agente'
                    - A *CLASSIFICAÇÃO POR LLM* está correta?
                    - Esse subsídio existe no catálogo ou é totalmente novo?
                
                ### 3. MAPEAR FRAGMENTOS NÃO IDENTIFICADOS
                    - Os fragmentos não identificados correspondem a algum subsídio do catálogo?
                    - Se sim, qual?
                ### 4. CONFERIR SE SUBSÍDIOS PRESENTES NÃO ESTÃO INCLUSOS NA ORIGEM DESTINO 
                    - O trecho o qual o subsídio foi solicitado é um complemento de ORIGEM DESTINO? 
                    - Se sim, analise se ele é apenas uma descrição do conteúdo que pode estar presente dentro de ORIGEM DESTINO ou de fato um subsídio que está sendo a mais de forma mais específica.
                    
                
                ---

                ## FORMATO DE RESPOSTA (JSON):
                
                Retorne APENAS um objeto JSON válido no seguinte formato:
                
                {{
                  "validacoes": [
                    {{
                      "subsidio_id": "1",
                      "e_valido": true,
                      "confidence": 0.95,
                      "texto_evidencia": "Solicito extratos de conta corrente",
                      "justificativa": "O ofício solicita explicitamente extratos de conta corrente, match correto",
                      "sugestao_exemplo": "extratos de conta corrente;movimentações bancárias"
                    }}
                  ],
                  "subsidios_novos": [
                    {{
                      "texto_solicitacao": "informações sobre cartões corporativos",
                      "texto_evidencia": "Determino o fornecimento de informações sobre cartões corporativos",
                      "catalogo_id_sugerido": "3",
                      "e_subsidio_novo": false,
                      "justificativa": "Corresponde ao subsídio 'Cartão de Crédito' (ID 3) mas com wording diferente"
                    }}
                  ],
                  "todos_subsidios_capturados": false,
                  "confidence_geral": 0.85,
                  "observacoes": "O ofício solicita 5 subsídios, mas o TF-IDF capturou apenas 3. Identifiquei 2 faltantes."
                }}
                
                ## INSTRUÇÕES IMPORTANTES:
                1. Rejeite matches que não fazem sentido
                2. No caso de incerteza, considere o texto **OFÍCIO COMPLETO** para apoiar nas respostas
                3. Extraia a frase EXATA do ofício (não parafraseie)
                4. A sugestão de exemplo deve ser curta e genérica para o catálogo
                5. Se um fragmento não identificado é variante de um subsídio existente, mapeie para o catalogo_id
                6. Confidence deve refletir sua certeza (0.0 = incerto, 1.0 = absoluto)
                7. Retorne APENAS o JSON, sem texto adicional
                """
            }
        ],
        model="gpt-5"
    )
    result_dict = json.loads(response.choices[0].message.content)
    return result_dict

class SubsidyMatcher:
    def __init__(self, catalog_df: pd.DataFrame):
        """
        catalog_df deve ter colunas: 
        - ID_SUBSIDIO
        - nome
        - Termos  
        - exemplos (lista de strings de como é pedido)
        """
        self.catalog = catalog_df
        
        # Prepara corpus para TF-IDF
        corpus = []
        self.id_mapping = []
        
        for idx, row in catalog_df.iterrows():
            # Combina nome, descrição e exemplos
            text_representation = f"{row['nome']} {row['descricao']}"
            if isinstance(row['exemplos'], list):
                text_representation += " " + " ".join(row['exemplos'])
            corpus.append(text_representation)
            self.id_mapping.append(row['subsidio_id'])
        
        # Cria vetorizador TF-IDF
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(3, 5),
            lowercase=True
        )
        self.catalog_vectors = self.vectorizer.fit_transform(corpus)
    
    def find_matches(self, requested_text: str, threshold: float = 0.3) -> List[SubsidyMatch]:
        """
        Encontra subsídios correspondentes no catálogo
        """
        # Vetoriza o texto solicitado
        request_vector = self.vectorizer.transform([requested_text])
        
        # Calcula similaridades
        similarities = cosine_similarity(request_vector, self.catalog_vectors)[0]
        
        # Encontra melhores matches
        matches = []
        for idx, score in enumerate(similarities):
            if score >= threshold:
                matches.append({
                    'subsidio_id': self.id_mapping[idx],
                    'nome_subsidio': self.catalog.iloc[idx]['nome'],
                    'similarity_score': float(score)
                })
        
        return sorted(matches, key=lambda x: x['similarity_score'], reverse=True)

@tool
def extract_and_match_subsidies(text: str, catalog_path: str) -> SubsidiesExtraction:
    """
    Extrai todos os subsídios solicitados e faz matching com catálogo
    Args:
        text(str): O texto do ofício judicial contendo as solicitações de subsídios.
        catalog_path (str): O caminho para o arquivo CSV contendo o catálogo de subsídios. 
    Returns:
        SubsidiesExtraction: Um objeto contendo os subsídios identificados, o total de subsídios e os fragmentos não identificados.
    """
    catalog_df = pd.read_json(catalog_path)
    matcher = SubsidyMatcher(catalog_df)
    
    # Padrões para encontrar blocos de solicitação
    request_patterns = [
        r'(?:DETERMINO|SOLICITO|REQUEIRO|OFICIE-SE)(.+?)(?:\n\n|$)',
        r'(?:forneça|disponibilize|informe|apresente)(.+?)(?:\.|;|\n)',
        r'(?:extratos?|saldos?|movimenta[çã][õo]es?)(.+?)(?:\.|;|\n)'
    ]
    
    all_matches = []
    unmatched = []
    
    for pattern in request_patterns:
        requests = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        
        for request in requests:
            # Quebra em itens individuais se houver lista
            items = re.split(r'[;,]|\n-|\n\d+\.', request)
            
            for item in items:
                if len(item.strip()) > 10:  # Ignora fragmentos muito curtos
                    matches = matcher.find_matches(item.strip())
                    
                    if matches:
                        best_match = matches[0]
                        
                        all_matches.append(SubsidyMatch(
                            subsidio_id=best_match['subsidio_id'],
                            nome_subsidio=best_match['nome_subsidio'],
                            texto_original=item.strip(),
                            similarity_score=best_match['similarity_score'],
                        ))
                    else:
                        unmatched.append(item.strip())
    
    return SubsidiesExtraction(
        subsidios_solicitados=all_matches,
        total_subsidios=len(all_matches),
        subsidios_nao_identificados=unmatched
    )

@tool
def extract_and_match_subsidies_hybrid(
    text: str,
    catalog_path: str,
    use_llm_validation: bool = True
) -> SubsidiesExtraction:
    """
    Extrai subsídios usando TF-IDF + Validação LLM

    Arquitetura em 3 fases:
    1. TF-IDF com threshold baixo (recall alto)
    2. Validação LLM para confirmar matches e encontrar faltantes
    3. Consolidação final com evidências textuais

    Args:
        text: Texto do ofício
        catalog_path: Path para catálogo CSV
        use_llm_validation: Se True, usa LLM. Se False, apenas TF-IDF (modo rápido)
        classificacao_llm: entrada do JSON com classificação flag presença

    Returns:
        SubsidiesExtraction com validações LLM incluídas
    """

    import logging
    logger = logging.getLogger(__name__)

    catalog_df = load_catalog(catalog_path)
    matcher = SubsidyMatcher(catalog_df)

    logger.info("FASE 1: Extração TF-IDF")

    request_patterns = [
        r'(?:DETERMINO|SOLICITO|REQUEIRO|OFICIE-SE)(.+?)(?:\n\n|$)',
        r'(?:forneça|disponibilize|informe|apresente)(.+?)(?:\.|;|\n)',
        r'(?:extratos?|saldos?|movimenta[çã][õo]es?)(.+?)(?:\.|;|\n)'
    ]

    all_matches = []
    unmatched_fragments = []

    for pattern in request_patterns:
        requests = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)

        for request in requests:
            items = re.split(r'[;,]|\n-|\n\d+\.', request)

            for item in items:
                if len(item.strip()) > 10:
                    # Threshold BAIXO (0.50) para pegar mais matches
                    matches = matcher.find_matches(item.strip(), threshold=0.20)

                    if matches:
                        best_match = matches[0]

                        all_matches.append(SubsidyMatch(
                            subsidio_id=best_match['subsidio_id'],
                            nome_subsidio=best_match['nome_subsidio'],
                            texto_original=item.strip(),
                            similarity_score=best_match['similarity_score'],
                            llm_validated=False  # Ainda não validado
                        ))
                    else:
                        unmatched_fragments.append(item.strip())

    logger.info(f"TF-IDF encontrou {len(all_matches)} matches, {len(unmatched_fragments)} não identificados")

    # Se não usa LLM, retorna só TF-IDF
    if not use_llm_validation:
        logger.info("Modo rápido: retornando apenas TF-IDF sem validação LLM")
        return SubsidiesExtraction(
            subsidios_solicitados=all_matches,
            total_subsidios=len(all_matches),
            subsidios_nao_identificados=unmatched_fragments
        )

    # FASE 2: Validação LLM
    logger.info("FASE 2: Validação LLM de todos os matches")

    llm_validation = validate_subsidies_with_llm(
        texto_oficio=text,
        tfidf_matches=all_matches,
        unmatched_fragments=unmatched_fragments,
        classificacao_llm=classificacao_llm,
        catalogo_completo=catalog_df
    )
    # garante que os 'subsidios_novos' está presente no dicionario
        llm_validation_dict['subsidios_novos'] = []

    # converte o dicionário retornado em uma instancia de LLMValidationResult

    # FASE 3: Consolidação - aplica validações LLM aos matches
    logger.info("FASE 3: Consolidando resultados TF-IDF + LLM")

    final_matches = []

    # Atualiza matches existentes com validações LLM
    for match in all_matches:
        # Busca validação correspondente
        validacao = next(
            (v for v in llm_validation.validacoes if v.subsidio_id == match.subsidio_id),
            None
        )

        if validacao and validacao.e_valido:
            # Match confirmado pelo LLM - adiciona evidências
            match.llm_validated = True
            match.llm_confidence = validacao.confidence
            match.texto_evidencia = validacao.texto_evidencia
            match.justificativa_match = validacao.justificativa
            match.sugestao_exemplo = validacao.sugestao_exemplo
            final_matches.append(match)
        elif validacao and not validacao.e_valido:
            # Match REJEITADO pelo LLM
            logger.warning(f"LLM rejeitou match {match.nome_subsidio}: {validacao.justificativa}")
            # Não adiciona à lista final
        else:
            # Sem validação LLM (não deveria acontecer)
            logger.warning(f"Match sem validação LLM: {match.nome_subsidio}")
            final_matches.append(match)
            
            # verifica se há subsídios novos identificados pelo llm 
    
            if llm_validation.subsidios_novos: # verifica se a lista nao esta vazia
            
                # Adiciona subsídios NOVOS identificados pelo LLM
                for novo in llm_validation.subsidios_novos:
                    if novo.catalogo_id_sugerido:
                        filtered_df = catalog_df[catalog_df['subsidio_id'] == novo.catalogo_id_sugerido]
                        if not filtered_df.empty:
                            catalogo_info =filtered_df.iloc[0]
            
                            final_matches.append(SubsidyMatch(
                                subsidio_id=novo.catalogo_id_sugerido,
                                # nome_subsidio=catalogo_info['nome'],
                                # texto_original=novo.texto_solicitacao,
                                similarity_score=0.0,  # LLM identificou, não TF-IDF
                                llm_validated=True,
                                llm_confidence=llm_validation.confidence_geral,
                                texto_evidencia=novo.texto_evidencia,
                                justificativa_match=novo.justificativa,
                                sugestao_exemplo=novo.texto_solicitacao
                            ))
                        else:
                            logger.warning(f"Subsidio ID '{novo.catalogo_id_sugerido}' não encontrado no catálogo.")
                    else:
                        # adiciona como novo subsídio sem mapeamento no catalogo
                        final_matches.append(SubsidyMatch(
                                subsidio_id"N/A",
                                nome_subsidio="Novo Subsídio",
                                # texto_original=novo.texto_solicitacao,
                                similarity_score=0.0,  # LLM identificou, não TF-IDF
                                llm_validated=True,
                                llm_confidence=llm_validation.confidence_geral,
                                texto_evidencia=novo.texto_evidencia,
                                justificativa_match=novo.justificativa,
                                sugestao_exemplo=novo.texto_solicitacao
                            ))
                else:
                    logger.info("Nenhum subsídio novo identificado pelo LLM.")
                    
    # Subsídios não identificados = aqueles que o LLM também não conseguiu mapear
    # converte os objetos SubsidyMatch para dicionários
    final_matches_dict = [match.model_dump() for match in final_matches]

    subsidios_verdadeiramente_nao_identificados = [
        novo.texto_solicitacao for novo in llm_validation.subsidios_novos
        if novo.e_subsidio_novo and not novo.catalogo_id_sugerido
    ]

    # retorna o resutado como um dicionario serializável
    return {
        subsidios_solicitados=final_matches,
        total_subsidios=len(final_matches),
        subsidios_nao_identificados=subsidios_verdadeiramente_nao_identificados
    }


## 6.2 carrega o catálogo de sub em dataframe
### primeira versão da função, por algum motivo a segunda versão não funciona sem a primeira, mas o resultado da segunda é o utilizado
def load_catalog(catalog_path):
    with open(catalog_path, 'r') as f:
        json_data = json.load(f)

    # Transformar a estrutura do JSON em um DataFrame
    catalog_list = []
    for id_subsidio, detalhes in json_data["ID_SUBSIDIO"].items():
        catalog_list.append({
            "subsidio_id": id_subsidio,
            "nome": id_subsidio,
            "descricao": detalhes.get("Descricao", "N/A"),
            "exemplos": "; ".join(detalhes.get("Termos", []))
        })

    # Criar DataFrame
    catalog_df = pd.DataFrame(catalog_list)
    return catalog_df


# Carregar catálogo
catalog_path = "/home/sagemaker-user/SIMBA/03_12_limpo/data/KB/catalogo_subsidios.json"
data = pd.read_json(catalog_path)
catalog_df = load_catalog(catalog_path)
print(catalog_df.head())        


### segunda versão de load catalog

def load_catalog(catalog_path):
    with open(catalog_path, 'r') as f:
        json_data = json.load(f)

    # Transformar a estrutura do JSON em um DataFrame
    catalog_list = []
    for id_subsidio, detalhes in json_data["ID_SUBSIDIO"].items():
        # Substituir '.' por espaço no id_subsidio e formatar como "id_subsidio: descrição"
        id_formatado = id_subsidio.replace(".", " ")
        nome_formatado = f"{id_formatado}: {detalhes.get('Descricao', 'N/A')}"

        catalog_list.append({
            "subsidio_id": id_subsidio,
            "nome": nome_formatado,  # Formatar como "id_subsidio: descrição"
            "descricao": detalhes.get("Descricao", "N/A"),
            "exemplos": "; ".join(detalhes.get("Termos", []))
        })

    # Criar DataFrame
    catalog_df = pd.DataFrame(catalog_list)
    return catalog_df


# Carregar catálogo
catalog_path = "/home/sagemaker-user/SIMBA/03_12_limpo/data/KB/catalogo_subsidios.json"
data = pd.read_json(catalog_path)
catalog_df = load_catalog(catalog_path)
catalog_df

catalog_df.to_excel("/home/sagemaker-user/SIMBA/03_12_limpo/data/SAIDA/17_12_25/catalogo.xlsx")


## 6.3 executa

# Função exec_valida
def exec_valida(text, catalog_path, classificacao_llm, use_llm_validation):
    if text and isinstance(text, str) and text.strip() != "":
        try:
            resultados_valida = []

            # Extrai e valida subsídios usando o texto do ofício
            resultado_extracao = extract_and_match_subsidies_hybrid(
                text=text,
                classificacao_llm=classificacao_llm,
                catalog_path=catalog_path,
                use_llm_validation=True
            )

            resultados_valida.append({
                "resultado_extracao": resultado_extracao
            })
            return resultados_valida
        except Exception as e:
            return {"erro": str(e)}
    else:
        return {"status": "texto vazio ou nulo"}


# Função para processar os envolvidos
def processar_valida(row):
    catalog_path = "/home/sagemaker-user/SIMBA/03_12_limpo/data/KB/catalogo_subsidios.json"
    texto_base = row.get("texto_limpo", "")        # Obtém o texto base da coluna texto_limpo
    envolvidos = row.get("nome_cpf", {}).get("envolvidos", [])

    results_valida = []

    for envolvido in envolvidos:
        nome = envolvido.get("nome", "")
        cpf_cnpj = envolvido.get("cpf_cnpj", "")
        lista_subs = row.get("listaSubs", [{}])[0].get("subsidios", {})

        text = f"{texto_base}"
        classificacao_llm = lista_subs

        # Chama a função exec_valida para cada envolvido
        results_validacao = exec_valida(text, catalog_path, classificacao_llm, use_llm_validation=True)

        # Adiciona o resultado à lista de validações
        results_valida.append({
            "numero_documento_envolvido": cpf_cnpj,
            "tipo_documento": "",
            "nome_envolvido": nome,
            "id_cliente": "",
            "flag_relacionamento": "",
            "produtos": "",
            "subsidios_validados": results_validacao
        })

    return results_valida


### 6.3.1 executa paralelo

def valida_classificacoes(df_temp):
    rows = df_temp.to_dict(orient="records")

    with concurrent.futures.ThreadPoolExecutor(max_workers=300) as executor:
        resultados = list(executor.map(processar_valida, rows))

    df_temp["results_valida"] = resultados
    return df_temp


# Processa o DataFrame inteiro em paralelo
dados = valida_classificacoes(dados)

# Exibe o DataFrame atualizado
print(dados["results_valida"])





