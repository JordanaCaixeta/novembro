# de_para_detector.py - NOVO MÓDULO

import re
from typing import List, Dict, Optional
from pydantic import BaseModel

class DeParaRequirement(BaseModel):
    """Modelo para requisitos de DE/PARA"""
    requer_de_para: bool
    subsidios_com_de_para: List[str]
    texto_evidencia: List[str]
    tipo_de_para: List[str]  # ['conta_origem', 'beneficiario', 'instituicao', etc]
    confidence: float

def detect_de_para_requirements(text: str, subsidios_identificados: List[Dict]) -> DeParaRequirement:
    """
    Detecta se o ofício solicita informações de origem/destino (DE/PARA)
    """
    requirement = DeParaRequirement(
        requer_de_para=False,
        subsidios_com_de_para=[],
        texto_evidencia=[],
        tipo_de_para=[],
        confidence=0.0
    )
    
    # Padrões que indicam necessidade de DE/PARA
    de_para_patterns = [
        # Padrões explícitos
        r'(?:origem\s+e\s+destino|DE[/-]PARA|de\s+para)',
        r'(?:conta\s+de\s+origem|conta\s+de\s+destino)',
        r'(?:remetente|destinatário|beneficiário)',
        r'(?:transferências?\s+(?:para|de|entre))',
        r'(?:identificação\s+do\s+(?:remetente|destinatário))',
        r'(?:dados?\s+do\s+(?:favorecido|recebedor))',
        
        # Padrões contextuais
        r'(?:incluindo|com|contendo)\s+(?:a\s+)?identificação\s+(?:dos?|das?)\s+(?:envolvidos?|partes?|contas?)',
        r'(?:discriminando|especificando|detalhando)\s+(?:origem|destino|beneficiário)',
        r'(?:CPF|CNPJ|nome|razão social)\s+do\s+(?:destinatário|beneficiário|favorecido)'
    ]
    
    evidencias = []
    tipos_identificados = set()
    
    for pattern in de_para_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            evidencias.append(match.group(0))
            
            # Identifica tipo de DE/PARA
            match_text = match.group(0).lower()
            if 'conta' in match_text:
                tipos_identificados.add('conta_origem_destino')
            if any(word in match_text for word in ['beneficiário', 'favorecido', 'destinatário']):
                tipos_identificados.add('beneficiario')
            if 'cpf' in match_text or 'cnpj' in match_text:
                tipos_identificados.add('identificacao_fiscal')
            if 'remetente' in match_text:
                tipos_identificados.add('remetente')
    
    if evidencias:
        requirement.requer_de_para = True
        requirement.texto_evidencia = list(set(evidencias))
        requirement.tipo_de_para = list(tipos_identificados)
        requirement.confidence = min(1.0, len(evidencias) * 0.3)
        
        # Associa com subsídios específicos
        requirement = associate_de_para_with_subsidios(
            requirement, text, subsidios_identificados
        )
    
    return requirement

def associate_de_para_with_subsidios(
    requirement: DeParaRequirement,
    text: str,
    subsidios: List[Dict]
) -> DeParaRequirement:
    """
    Associa requisito de DE/PARA com subsídios específicos
    """
    # Subsídios que tipicamente precisam de DE/PARA
    subsidios_tipicos_de_para = [
        'transferência', 'ted', 'doc', 'pix', 'remessa', 
        'pagamento', 'débito', 'crédito', 'movimentação'
    ]
    
    subsidios_com_de_para = []
    
    for subsidio in subsidios:
        subsidio_nome = subsidio.get('nome_subsidio', '').lower()
        subsidio_texto = subsidio.get('texto_original', '').lower()
        
        # Verifica se é um subsídio típico de DE/PARA
        if any(palavra in subsidio_nome or palavra in subsidio_texto 
               for palavra in subsidios_tipicos_de_para):
            subsidios_com_de_para.append(subsidio['subsidio_id'])
            continue
        
        # Verifica se o DE/PARA está mencionado próximo ao subsídio
        for evidencia in requirement.texto_evidencia:
            # Busca evidência próxima ao subsídio no texto
            pattern = f"{re.escape(subsidio_texto)}[^.]*{re.escape(evidencia)}"
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                subsidios_com_de_para.append(subsidio['subsidio_id'])
                break
    
    # Se não identificou subsídios específicos mas tem DE/PARA, aplica a todos
    if requirement.requer_de_para and not subsidios_com_de_para:
        subsidios_com_de_para = [s['subsidio_id'] for s in subsidios]
        requirement.confidence *= 0.7  # Reduz confidence por ser inferência
    
    requirement.subsidios_com_de_para = subsidios_com_de_para
    
    return requirement