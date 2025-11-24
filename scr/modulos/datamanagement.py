from smolagents import CodeAgent, tool, HfApiModel
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import re

# 1. Agent de Análise Inicial e Classificação do Input
# Este é o primeiro agente crítico que determina o que realmente chegou no sistema:

class InputClassification(BaseModel):
    """Classificação inicial do texto de entrada"""
    tipo_conteudo: Literal["oficio_completo", "email_chain", "fragmento", "indeterminado"]
    tem_ocr_oficio: bool
    tem_marcador_ocr: bool  # NOVO: detecta marcadores <<OCR>>
    tem_numero_processo: bool
    tem_dados_investigados: bool
    tipo_oficio: Literal["primeiro_oficio", "reiteracao", "complemento", "indeterminado"]  # MODIFICADO: adicionado "complemento"
    confidence_score: float
    fragmentos_identificados: List[str]  # Partes do texto categorizadas

@tool
def analyze_input_structure(text: str) -> InputClassification:
    """
    Analisa a estrutura do input para determinar o que foi recebido
    """
    classification = {
        "tipo_conteudo": "indeterminado",
        "tem_ocr_oficio": False,
        "tem_marcador_ocr": False,  # NOVO
        "tem_numero_processo": False,
        "tem_dados_investigados": False,
        "tipo_oficio": "indeterminado",
        "confidence_score": 0.0,
        "fragmentos_identificados": []
    }
    
    # Padrões para identificação
    patterns = {
        'email_headers': r'(From:|Para:|Subject:|Assunto:|De:|Date:|Data:)',
        'processo': r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}',
        'cpf': r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}',
        'cnpj': r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}',
        'oficio_markers': r'(PODER JUDICIÁRIO|OFÍCIO|MANDADO|VARA|COMARCA|JUIZ)',
        'reiteracao': r'(REITER|REITERA|REITERAÇÃO|URGENTE|PRAZO VENCIDO|NÃO ATENDIDO)',
        'complemento': r'(COMPLEMENTO|COMPLEMENTAR|ADICIONAL|INFORMAÇÕES ADICIONAIS|PARCIALMENTE ATENDIDO)',  # NOVO
        'ocr_markers': r'<<OCR>>.*?<<OCR>>'  # NOVO
    }
    
    # Detecta marcadores <<OCR>> - NOVO
    if re.search(patterns['ocr_markers'], text, re.DOTALL):
        classification["tem_marcador_ocr"] = True
        classification["fragmentos_identificados"].append("ocr_markers")
    
    # Detecta cadeia de emails
    if re.search(patterns['email_headers'], text, re.IGNORECASE):
        classification["tipo_conteudo"] = "email_chain"
        classification["fragmentos_identificados"].append("email_headers")
    
    # Detecta marcadores de ofício
    if re.search(patterns['oficio_markers'], text, re.IGNORECASE):
        classification["tem_ocr_oficio"] = True
        classification["tipo_conteudo"] = "oficio_completo" if not classification["tipo_conteudo"] == "email_chain" else "email_chain"
        classification["fragmentos_identificados"].append("oficio_content")
    
    # Detecta número do processo
    if re.search(patterns['processo'], text):
        classification["tem_numero_processo"] = True
        classification["fragmentos_identificados"].append("process_number")
    
    # Detecta dados de investigados
    if re.search(patterns['cpf'], text) or re.search(patterns['cnpj'], text):
        classification["tem_dados_investigados"] = True
        classification["fragmentos_identificados"].append("investigated_parties")
    
    # Detecta se é reiteração, complemento ou primeiro ofício - MODIFICADO
    if re.search(patterns['reiteracao'], text, re.IGNORECASE):
        classification["tipo_oficio"] = "reiteracao"
    elif re.search(patterns['complemento'], text, re.IGNORECASE):  # NOVO
        classification["tipo_oficio"] = "complemento"
    elif classification["tem_ocr_oficio"]:
        classification["tipo_oficio"] = "primeiro_oficio"
    
    # Calcula confidence score baseado em quantos elementos foram identificados - MODIFICADO
    identified_elements = sum([
        classification["tem_ocr_oficio"],
        classification["tem_marcador_ocr"],  # NOVO
        classification["tem_numero_processo"],
        classification["tem_dados_investigados"],
        len(classification["fragmentos_identificados"]) > 0
    ])
    classification["confidence_score"] = identified_elements / 5.0  # MODIFICADO: dividido por 5 agora
    
    return InputClassification(**classification)

# Agent de Classificação Inicial
input_classifier_agent = CodeAgent(
    tools=[analyze_input_structure],
    model=HfApiModel("Qwen/Qwen2.5-Coder-32B-Instruct"),
    name="input_classifier",
    description="Classifica o tipo de input recebido e identifica componentes principais"
)


# 2. Agent de Extração de Conteúdo Relevante - MODIFICADO
# Este agente extrai apenas as partes relevantes do texto, especialmente quando há cadeia de emails:

@tool
def extract_oficio_content(text: str, input_classification: InputClassification) -> str:
    """
    Extrai apenas o conteúdo do ofício de uma cadeia de emails ou texto misto
    Agora também processa marcadores <<OCR>>
    """
    if input_classification.tipo_conteudo == "oficio_completo" and not input_classification.tem_marcador_ocr:
        return text
    
    # NOVO: Se tem marcadores <<OCR>>, extrai o conteúdo entre eles
    if input_classification.tem_marcador_ocr:
        ocr_pattern = r'<<OCR>>(.*?)<<OCR>>'
        ocr_matches = re.findall(ocr_pattern, text, re.DOTALL)
        if ocr_matches:
            # Concatena todos os blocos OCR encontrados
            return '\n\n'.join(ocr_matches)
    
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