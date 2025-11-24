from smolagents import CodeAgent, tool
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import re

# 1. Agent de Análise Inicial e Classificação do Input
# Este é o primeiro agente crítico que determina o que realmente chegou no sistema:

class InputClassification(BaseModel):
    """Classificação inicial do texto de entrada"""
    tipo_conteudo: Literal["oficio_completo", "email_chain", "fragmento", "indeterminado"]
    tem_ocr_oficio: bool
    tem_numero_processo: bool
    tem_dados_investigados: bool
    tipo_oficio: Literal["primeiro_oficio", "reiteracao", "indeterminado"]
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
        'reiteracao': r'(REITER|REITERA|REITERAÇÃO|URGENTE|PRAZO VENCIDO|NÃO ATENDIDO)'
    }
    
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
    
    # Detecta se é reiteração
    if re.search(patterns['reiteracao'], text, re.IGNORECASE):
        classification["tipo_oficio"] = "reiteracao"
    elif classification["tem_ocr_oficio"]:
        classification["tipo_oficio"] = "primeiro_oficio"
    
    # Calcula confidence score baseado em quantos elementos foram identificados
    identified_elements = sum([
        classification["tem_ocr_oficio"],
        classification["tem_numero_processo"],
        classification["tem_dados_investigados"],
        len(classification["fragmentos_identificados"]) > 0
    ])
    classification["confidence_score"] = identified_elements / 4.0
    
    return InputClassification(**classification)

# Agent de Classificação Inicial
input_classifier_agent = CodeAgent(
    tools=[analyze_input_structure],
    model=HfApiModel("Qwen/Qwen2.5-Coder-32B-Instruct"),
    name="input_classifier",
    description="Classifica o tipo de input recebido e identifica componentes principais"
)