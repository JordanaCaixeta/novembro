
# 2. Agent de Extração de Conteúdo Relevante
# Este agente extrai apenas as partes relevantes do texto, especialmente quando há cadeia de emails:

@tool
def extract_oficio_content(text: str, input_classification: InputClassification) -> str:
    """
    Extrai apenas o conteúdo do ofício de uma cadeia de emails ou texto misto
    """
    if input_classification.tipo_conteudo == "oficio_completo":
        return text
    
    if input_classification.tipo_conteudo == "email_chain":
        # Estratégia: encontrar o bloco mais longo que contém marcadores de ofício
        blocks = text.split('\n\n')
        oficio_blocks = []
        
        for block in blocks:
            if any(marker in block.upper() for marker in ['PODER JUDICIÁRIO', 'OFÍCIO', 'VARA', 'COMARCA']):
                oficio_blocks.append(block)
        
        if oficio_blocks:
            # Concatena blocos contíguos que parecem ser do ofício
            return '\n\n'.join(oficio_blocks)
    
    # Se não conseguir extrair, retorna marcador especial
    return "[OFICIO_NAO_ENCONTRADO]"

@tool  
def extract_minimal_info_for_lookup(text: str) -> dict:
    """
    Extrai informações mínimas para consulta no sistema interno
    quando não há ofício completo
    """
    info = {
        "numeros_processo": [],
        "cpfs": [],
        "cnpjs": [],
        "nomes": [],
        "pode_consultar_sistema": False
    }
    
    # Extrai números de processo
    processos = re.findall(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}', text)
    info["numeros_processo"] = list(set(processos))
    
    # Extrai CPFs
    cpfs = re.findall(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', text)
    info["cpfs"] = [re.sub(r'[^\d]', '', cpf) for cpf in set(cpfs)]
    
    # Extrai CNPJs
    cnpjs = re.findall(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', text)
    info["cnpjs"] = [re.sub(r'[^\d]', '', cnpj) for cnpj in set(cnpjs)]
    
    # Tenta extrair nomes (heurística simples)
    # Busca por padrões como "Investigado: NOME COMPLETO"
    nomes_pattern = r'(?:Investigado|Requerido|CPF|Nome)[:\s]+([A-Z][A-Z\s]{3,50})'
    nomes = re.findall(nomes_pattern, text)
    info["nomes"] = [nome.strip() for nome in nomes]
    
    # Determina se tem informação suficiente para consulta
    info["pode_consultar_sistema"] = bool(
        info["numeros_processo"] or info["cpfs"] or info["cnpjs"]
    )
    
    return info