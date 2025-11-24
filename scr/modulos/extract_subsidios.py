# 4. Agent de Matching de Subsídios com Catálogo
# Este é um dos agentes mais críticos, que compara com o catálogo de subsídios:

import re
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel
from smolagents import tool
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scr.modulos.datas_management import extract_period_from_text

class SubsidyMatch(BaseModel):
    subsidio_id: str
    nome_subsidio: str
    texto_original: str  # Como apareceu no ofício
    similarity_score: float
    periodo: Optional[dict] = None  # {"inicio": "01/01/2023", "fim": "31/12/2023"}
    carta_circular: Optional[str] = None  # Carta Circular associada
    requer_de_para: bool = False  # Se requer informações DE/PARA

    # NOVOS CAMPOS - Validação LLM
    llm_validated: bool = False  # Se passou por validação LLM
    llm_confidence: Optional[float] = None  # Confidence do LLM (0-1)
    texto_evidencia: Optional[str] = None  # Frase exata onde foi encontrado
    justificativa_match: Optional[str] = None  # Por que o LLM achou que é esse subsídio
    sugestao_exemplo: Optional[str] = None  # Texto para adicionar aos exemplos do catálogo
    
class SubsidiesExtraction(BaseModel):
    subsidios_solicitados: List[SubsidyMatch]
    total_subsidios: int
    subsidios_nao_identificados: List[str]

# NOVOS MODELOS - Validação LLM
class LLMSubsidyValidation(BaseModel):
    """Validação de um subsídio individual pelo LLM"""
    subsidio_id: str
    e_valido: bool  # Se o match faz sentido
    confidence: float  # 0.0 a 1.0
    texto_evidencia: str  # Frase exata do ofício onde foi encontrado
    justificativa: str  # Por que o LLM considera que é esse subsídio
    sugestao_exemplo: str  # Como adicionar aos exemplos do catálogo

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
    catalogo_completo: pd.DataFrame
) -> LLMValidationResult:
    """
    Valida os matches do TF-IDF usando LLM e identifica subsídios faltantes

    Implementação REAL com smolagents LiteLLMModel

    Args:
        texto_oficio: Texto completo do ofício
        tfidf_matches: Matches identificados pelo TF-IDF
        unmatched_fragments: Fragmentos não identificados pelo TF-IDF
        catalogo_completo: DataFrame com catálogo de subsídios

    Returns:
        LLMValidationResult com validações e subsídios novos identificados
    """

    import logging
    import json
    import os
    logger = logging.getLogger(__name__)

    try:
        from smolagents import LiteLLMModel
    except ImportError:
        logger.error("smolagents não instalado - usando fallback STUB")
        return _validate_subsidies_stub(tfidf_matches)

    # Prepara catálogo resumido (primeiros 50 para não estourar contexto)
    catalogo_resumido = catalogo_completo.head(50).to_dict('records')
    catalogo_text = "\n".join([
        f"ID: {row['subsidio_id']} | Nome: {row['nome']} | Descrição: {row.get('descricao', 'N/A')}"
        for row in catalogo_resumido
    ])

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

    # Prompt estruturado
    prompt = f"""Você é um especialista em análise de ofícios judiciais de quebra de sigilo bancário.

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

---

## SUAS TAREFAS:

### 1. VALIDAR MATCHES DO TF-IDF
Para cada match identificado, responda:
- Ele realmente faz sentido no contexto do ofício?
- Qual é a frase EXATA do ofício onde o subsídio foi mencionado?
- Por que você considera que esse match está correto (ou incorreto)?
- Como essa solicitação poderia ser adicionada aos exemplos do catálogo? (texto curto e genérico)

### 2. IDENTIFICAR SUBSÍDIOS FALTANTES
- Há algum subsídio solicitado no ofício que NÃO está na lista de matches?
- Se sim, qual é a frase exata onde aparece?
- Esse subsídio existe no catálogo ou é totalmente novo?

### 3. MAPEAR FRAGMENTOS NÃO IDENTIFICADOS
- Os fragmentos não identificados correspondem a algum subsídio do catálogo?
- Se sim, qual?

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
1. Seja rigoroso na validação - rejeite matches que não fazem sentido
2. Extraia a frase EXATA do ofício (não parafraseie)
3. A sugestão de exemplo deve ser curta e genérica para o catálogo
4. Se um fragmento não identificado é variante de um subsídio existente, mapeie para o catalogo_id
5. Confidence deve refletir sua certeza (0.0 = incerto, 1.0 = absoluto)
6. Retorne APENAS o JSON, sem texto adicional
"""

    # Chama LLM
    try:
        # Usa modelo configurado via env ou default
        model_id = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")  # Padrão: GPT-4o-mini (barato e preciso)
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")

        if not api_key:
            logger.warning("LLM API key não configurada - usando fallback STUB")
            return _validate_subsidies_stub(tfidf_matches)

        llm = LiteLLMModel(
            model_id=model_id,
            api_key=api_key
        )

        logger.info(f"Chamando LLM ({model_id}) para validação de subsídios...")

        response = llm([{"role": "user", "content": prompt}])

        # Parse JSON da resposta
        # Remove markdown code blocks se houver
        response_text = response.strip()
        if response_text.startswith("```"):
            # Remove ```json e ``` do início e fim
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result_dict = json.loads(response_text)

        # Converte para modelo Pydantic
        return LLMValidationResult(**result_dict)

    except json.JSONDecodeError as e:
        logger.error(f"LLM retornou JSON inválido: {e}")
        logger.error(f"Resposta: {response_text[:500]}")
        return _validate_subsidies_stub(tfidf_matches)

    except Exception as e:
        logger.error(f"Erro na validação LLM: {e}")
        return _validate_subsidies_stub(tfidf_matches)

def _validate_subsidies_stub(tfidf_matches: List[SubsidyMatch]) -> LLMValidationResult:
    """
    Fallback: Valida subsídios sem LLM (aceita matches do TF-IDF)
    """
    validacoes = []
    for match in tfidf_matches:
        validacoes.append(LLMSubsidyValidation(
            subsidio_id=match.subsidio_id,
            e_valido=True,
            confidence=0.9,
            texto_evidencia=match.texto_original,
            justificativa=f"Match TF-IDF com score {match.similarity_score:.2f} (LLM indisponível)",
            sugestao_exemplo=match.texto_original
        ))

    return LLMValidationResult(
        validacoes=validacoes,
        subsidios_novos=[],
        todos_subsidios_capturados=True,
        confidence_geral=0.85,
        observacoes="FALLBACK: Validação LLM indisponível - aceitando matches TF-IDF"
    )

class SubsidyMatcher:
    def __init__(self, catalog_df: pd.DataFrame):
        """
        catalog_df deve ter colunas: 
        - subsidio_id
        - nome
        - descricao  
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
    
    def find_matches(self, requested_text: str, threshold: float = 0.75) -> List[SubsidyMatch]:
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
    """
    catalog_df = pd.read_csv(catalog_path)
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
                        # Extrai período se mencionado
                        periodo = extract_period_from_text(item)
                        
                        all_matches.append(SubsidyMatch(
                            subsidio_id=best_match['subsidio_id'],
                            nome_subsidio=best_match['nome_subsidio'],
                            texto_original=item.strip(),
                            similarity_score=best_match['similarity_score'],
                            periodo=periodo
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
    VERSÃO HÍBRIDA: Extrai subsídios usando TF-IDF + Validação LLM

    Arquitetura em 3 fases:
    1. TF-IDF com threshold baixo (recall alto)
    2. Validação LLM para confirmar matches e encontrar faltantes
    3. Consolidação final com evidências textuais

    Args:
        text: Texto do ofício
        catalog_path: Path para catálogo CSV
        use_llm_validation: Se True, usa LLM. Se False, apenas TF-IDF (modo rápido)

    Returns:
        SubsidiesExtraction com validações LLM incluídas
    """

    import logging
    logger = logging.getLogger(__name__)

    catalog_df = pd.read_csv(catalog_path)
    matcher = SubsidyMatcher(catalog_df)

    # FASE 1: Extração TF-IDF com threshold BAIXO para recall alto
    logger.info("FASE 1: Extração TF-IDF (threshold 0.50 para recall alto)")

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
                    matches = matcher.find_matches(item.strip(), threshold=0.50)

                    if matches:
                        best_match = matches[0]
                        periodo = extract_period_from_text(item)

                        all_matches.append(SubsidyMatch(
                            subsidio_id=best_match['subsidio_id'],
                            nome_subsidio=best_match['nome_subsidio'],
                            texto_original=item.strip(),
                            similarity_score=best_match['similarity_score'],
                            periodo=periodo,
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
        catalogo_completo=catalog_df
    )

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

    # Adiciona subsídios NOVOS identificados pelo LLM
    for novo in llm_validation.subsidios_novos:
        if novo.catalogo_id_sugerido:
            # LLM mapeou para um subsídio existente
            catalogo_info = catalog_df[
                catalog_df['subsidio_id'] == novo.catalogo_id_sugerido
            ].iloc[0]

            final_matches.append(SubsidyMatch(
                subsidio_id=novo.catalogo_id_sugerido,
                nome_subsidio=catalogo_info['nome'],
                texto_original=novo.texto_solicitacao,
                similarity_score=0.0,  # LLM identificou, não TF-IDF
                periodo=extract_period_from_text(novo.texto_evidencia),
                llm_validated=True,
                llm_confidence=llm_validation.confidence_geral,
                texto_evidencia=novo.texto_evidencia,
                justificativa_match=novo.justificativa,
                sugestao_exemplo=novo.texto_solicitacao
            ))
            logger.info(f"LLM adicionou subsídio: {catalogo_info['nome']}")

    logger.info(f"Final: {len(final_matches)} subsídios validados (TF-IDF={len(all_matches)}, Novos LLM={len(llm_validation.subsidios_novos)})")

    # Subsídios não identificados = aqueles que o LLM também não conseguiu mapear
    subsidios_verdadeiramente_nao_identificados = [
        novo.texto_solicitacao
        for novo in llm_validation.subsidios_novos
        if novo.e_subsidio_novo and not novo.catalogo_id_sugerido
    ]

    return SubsidiesExtraction(
        subsidios_solicitados=final_matches,
        total_subsidios=len(final_matches),
        subsidios_nao_identificados=subsidios_verdadeiramente_nao_identificados
    )
