# Agente para Detecção de Carta Circular

import re
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class CartaCircular(BaseModel):
    """Modelo para Carta Circular identificada"""
    numero: str
    ano: Optional[str] = None
    texto_original: str
    subsidios_associados: List[str] = Field(default_factory=list)
    aplica_todos_subsidios: bool = False
    confidence: float

class CartaCircularExtraction(BaseModel):
    """Resultado da extração de cartas circulares"""
    cartas_encontradas: List[CartaCircular]
    total_cartas: int
    tem_carta_circular: bool

def extract_carta_circular(text: str, subsidios_identificados: List[str] = None) -> CartaCircularExtraction:
    """
    Extrai referências a Cartas Circulares e associa com subsídios
    """
    cartas = []
    
    # Padrões para identificar Carta Circular
    patterns = [
        r'(?:Carta\s+Circular|CC|C\.C\.)\s*(?:n[º°]?\s*)?(\d+)(?:[/-](\d{2,4}))?',
        r'(?:conforme|segundo|de acordo com)\s+(?:a\s+)?Carta\s+Circular\s*(?:n[º°]?\s*)?(\d+)',
        r'CC\s*(\d+)(?:[/-](\d{2,4}))?'
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for match in matches:
            numero = match.group(1)
            ano = match.group(2) if len(match.groups()) > 1 and match.group(2) else None
            
            # Se ano tem 2 dígitos, converte para 4
            if ano and len(ano) == 2:
                ano = '20' + ano if int(ano) < 50 else '19' + ano
            
            carta = CartaCircular(
                numero=numero,
                ano=ano,
                texto_original=match.group(0),
                confidence=0.9
            )
            
            # Tenta associar com subsídios
            carta = associate_carta_with_subsidios(
                carta, text, match, subsidios_identificados
            )
            
            cartas.append(carta)
    
    # Remove duplicatas baseadas em número + ano
    unique_cartas = {}
    for carta in cartas:
        key = f"{carta.numero}_{carta.ano or 'NA'}"
        if key not in unique_cartas or carta.confidence > unique_cartas[key].confidence:
            unique_cartas[key] = carta
    
    return CartaCircularExtraction(
        cartas_encontradas=list(unique_cartas.values()),
        total_cartas=len(unique_cartas),
        tem_carta_circular=len(unique_cartas) > 0
    )

def associate_carta_with_subsidios(
    carta: CartaCircular, 
    full_text: str, 
    match_obj: re.Match,
    subsidios_list: List[str]
) -> CartaCircular:
    """
    Associa Carta Circular com subsídios específicos ou todos
    """
    if not subsidios_list:
        return carta
    
    # Pega contexto ao redor da menção da carta (100 chars antes e depois)
    start = max(0, match_obj.start() - 100)
    end = min(len(full_text), match_obj.end() + 100)
    context = full_text[start:end]
    
    # Verifica se aplica a todos os subsídios
    if re.search(r'(?:todos?|demais|listados?|acima|abaixo|seguintes?)', context, re.IGNORECASE):
        carta.aplica_todos_subsidios = True
        carta.subsidios_associados = subsidios_list
    else:
        # Tenta identificar subsídios específicos mencionados perto da carta
        subsidios_proximos = []
        
        for subsidio in subsidios_list:
            # Verifica se o subsídio está mencionado no contexto
            if subsidio.lower() in context.lower():
                subsidios_proximos.append(subsidio)
        
        if subsidios_proximos:
            carta.subsidios_associados = subsidios_proximos
        else:
            # Se não identificar específicos, pode aplicar a todos
            carta.aplica_todos_subsidios = True
            carta.subsidios_associados = subsidios_list
            carta.confidence *= 0.8  # Reduz confidence por ser inferência
    
    return carta