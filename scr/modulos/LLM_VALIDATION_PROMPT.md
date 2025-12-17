# Implementação do Prompt LLM para Validação de Subsídios

Este documento descreve como implementar a validação LLM real na função `validate_subsidies_with_llm`.

---

## 📋 Objetivo

O LLM deve:
1. **Validar** se os matches do TF-IDF fazem sentido
2. **Identificar subsídios faltantes** que o TF-IDF perdeu
3. **Extrair evidências textuais** para alimentar catálogo de exemplos

---

## 🎯 Prompt Estruturado

```python
def validate_subsidies_with_llm(
    texto_oficio: str,
    tfidf_matches: List[SubsidyMatch],
    unmatched_fragments: List[str],
    catalogo_completo: pd.DataFrame
) -> LLMValidationResult:
    """
    Implementação REAL com smolagents
    """

    # Prepara informações do catálogo (primeiros 50 para não estourar contexto)
    catalogo_resumido = catalogo_completo.head(50).to_dict('records')
    catalogo_text = "\n".join([
        f"ID: {row['subsidio_id']} | Nome: {row['nome']} | Descrição: {row['descricao']}"
        for row in catalogo_resumido
    ])

    # Prepara matches do TF-IDF
    matches_text = "\n".join([
        f"Match {i+1}: {m.nome_subsidio} (ID: {m.subsidio_id}, Score: {m.similarity_score:.2f})\n"
        f"  Texto encontrado: \"{m.texto_original}\""
        for i, m in enumerate(tfidf_matches)
    ])

    # Prepara fragmentos não identificados
    fragments_text = "\n".join([
        f"- {frag}" for frag in unmatched_fragments
    ])

    prompt = f"""
Você é um especialista em análise de ofícios judiciais de quebra de sigilo bancário.

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

```json
{{
  "validacoes": [
    {{
      "subsidio_id": "1",
      "e_valido": true,
      "confidence": 0.95,
      "texto_evidencia": "Solicito extratos de conta corrente",
      "justificativa": "O ofício solicita explicitamente extratos de conta corrente, match correto",
      "sugestao_exemplo": "extratos de conta corrente;movimentações bancárias"
    }},
    {{
      "subsidio_id": "2",
      "e_valido": false,
      "confidence": 0.3,
      "texto_evidencia": "",
      "justificativa": "Este match não aparece no ofício, falso positivo do TF-IDF",
      "sugestao_exemplo": ""
    }}
  ],
  "subsidios_novos": [
    {{
      "texto_solicitacao": "informações sobre cartões corporativos",
      "texto_evidencia": "Determino o fornecimento de informações sobre cartões corporativos",
      "catalogo_id_sugerido": "3",
      "e_subsidio_novo": false,
      "justificativa": "Corresponde ao subsídio 'Cartão de Crédito' (ID 3) mas com wording diferente"
    }},
    {{
      "texto_solicitacao": "dados de criptomoedas",
      "texto_evidencia": "Solicito dados de transações em criptomoedas",
      "catalogo_id_sugerido": null,
      "e_subsidio_novo": true,
      "justificativa": "Subsídio totalmente novo, não existe no catálogo"
    }}
  ],
  "todos_subsidios_capturados": false,
  "confidence_geral": 0.85,
  "observacoes": "O ofício solicita 5 subsídios, mas o TF-IDF capturou apenas 3. Identifiquei 2 faltantes."
}}
```

## INSTRUÇÕES IMPORTANTES:
1. Seja rigoroso na validação - rejeite matches que não fazem sentido
2. Extraia a frase EXATA do ofício (não parafraseie)
3. A sugestão de exemplo deve ser curta e genérica para o catálogo
4. Se um fragmento não identificado é variante de um subsídio existente, mapeie para o catalogo_id
5. Confidence deve refletir sua certeza (0.0 = incerto, 1.0 = absoluto)
6. Retorne APENAS o JSON, sem texto adicional

"""

    # Chama LLM via smolagents com structured output
    from smolagents import LiteLLMModel

    llm = LiteLLMModel(
        model_id="gpt-4o",  # ou outro modelo compatível
        api_key="sua-api-key"
    )

    response = llm.complete(
        messages=[{"role": "user", "content": prompt}],
        response_format="json_object"  # Força resposta em JSON
    )

    # Parse JSON
    import json
    result_dict = json.loads(response)

    # Converte para modelo Pydantic
    return LLMValidationResult(**result_dict)
```

---

## 🔧 Integração com smolagents CodeAgent

Se quiser usar via CodeAgent (recomendado):

```python
from smolagents import CodeAgent, tool

@tool
def validate_subsidies_llm_tool(
    texto_oficio: str,
    matches_json: str,  # JSON string dos matches
    catalog_json: str   # JSON string do catálogo
) -> str:
    """
    Tool para ser chamada por um CodeAgent de validação

    Returns:
        JSON string com validações
    """
    # Implementação similar ao prompt acima
    # Retorna JSON string
    pass

# Cria agente especializado em validação
validation_agent = CodeAgent(
    tools=[validate_subsidies_llm_tool],
    model=LiteLLMModel("gpt-4o"),
    name="subsidy_validator",
    description="Valida extração de subsídios de ofícios judiciais"
)

# Usa o agente
result = validation_agent.run(
    f"Valide os seguintes matches: {matches_json}"
)
```

---

## 📊 Exemplo de Uso

```python
# No orquestrador, já está configurado para chamar:
subsidies_result = extract_and_match_subsidies_hybrid(
    oficio_content,
    catalog_path,
    use_llm_validation=True  # ← Ativa validação LLM
)

# Resultados incluirão:
for subsidio in subsidies_result.subsidios_solicitados:
    print(f"Subsídio: {subsidio.nome_subsidio}")
    print(f"  LLM Validado: {subsidio.llm_validated}")
    print(f"  Confidence: {subsidio.llm_confidence}")
    print(f"  Evidência: {subsidio.texto_evidencia}")
    print(f"  Justificativa: {subsidio.justificativa_match}")
    print(f"  Sugestão para catálogo: {subsidio.sugestao_exemplo}")
```

---

## 🎯 Alimentando o Catálogo de Exemplos

Use as sugestões do LLM para enriquecer o catálogo:

```python
# Exporta sugestões para atualizar catálogo
sugestoes_para_catalogo = []

for subsidio in subsidies_result.subsidios_solicitados:
    if subsidio.llm_validated and subsidio.sugestao_exemplo:
        sugestoes_para_catalogo.append({
            'subsidio_id': subsidio.subsidio_id,
            'novo_exemplo': subsidio.sugestao_exemplo,
            'fonte_oficio': session_id
        })

# Salva para revisão humana antes de adicionar ao catálogo
import pandas as pd
pd.DataFrame(sugestoes_para_catalogo).to_csv('sugestoes_catalogo.csv', index=False)
```

---

## ⚙️ Configurações Recomendadas

### Modelo LLM:
- **Produção**: `gpt-4o` ou `claude-3-5-sonnet` (alta precisão)
- **Desenvolvimento**: `gpt-4o-mini` (mais barato, ainda preciso)
- **Alternativa**: `deepseek-chat` (barato, bom em português)

### Parâmetros:
```python
llm_config = {
    'temperature': 0.1,  # Baixa temperatura para consistência
    'max_tokens': 4096,  # Suficiente para JSON de validação
    'response_format': 'json_object'  # Força JSON
}
```

---

## 🐛 Tratamento de Erros

```python
try:
    llm_validation = validate_subsidies_with_llm(...)
except json.JSONDecodeError as e:
    logger.error(f"LLM retornou JSON inválido: {e}")
    # Fallback: aceita matches do TF-IDF sem validação
    llm_validation = create_fallback_validation(tfidf_matches)
except Exception as e:
    logger.error(f"Erro na validação LLM: {e}")
    # Fallback
    llm_validation = create_fallback_validation(tfidf_matches)
```

---

**Status**: 🟡 STUB implementado | ⚠️ Integração LLM real necessária
