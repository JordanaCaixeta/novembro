# Filtro de Instituição Financeira
# Determina se o ofício é relevante para instituição financeira (Banco X)

import re
from typing import List, Optional, Literal
from pydantic import BaseModel
from smolagents import tool

class InstituicaoMencionada(BaseModel):
    """Instituição mencionada no ofício"""
    tipo: Literal["banco_especifico", "instituicao_financeira", "bacen", "receita", "operadora", "policia", "outro", "indeterminado"]
    nome: Optional[str] = None  # Nome específico se mencionado
    trecho_relevante: str  # Onde foi mencionada
    e_destinatario_direto: bool  # Se é destinatário direto (Oficie-se...)
    confidence: float

class FiltroInstituicaoResult(BaseModel):
    """Resultado da análise de instituição"""
    e_relevante_para_banco: bool  # Se deve ser processado pelo Banco X
    motivo: str  # Por que é ou não relevante
    instituicoes_mencionadas: List[InstituicaoMencionada]
    tem_multiplos_destinatarios: bool
    tipo_sigilo: Literal["bancario", "fiscal", "telefonico", "misto", "indeterminado"]
    trecho_relevante_para_banco: Optional[str] = None  # Só o trecho para o banco (se houver)
    confidence: float

# Padrões de identificação
BANCOS_CONHECIDOS = [
    r'banco\s+x',  # Substituir por nome real
    r'bancos?',
    r'institui[çc][aã]o\s+financeira',
    r'institui[çc][õo]es\s+financeiras',
]

BACEN_PATTERNS = [
    r'bacen',
    r'banco\s+central',
    r'bc\b',
]

OUTRAS_INSTITUICOES = {
    'fiscal': [
        r'receita\s+federal',
        r'fazenda\s+nacional',
        r'rfb',
        r'sigilo\s+fiscal',
    ],
    'operadora': [
        r'operadora',
        r'telefonia',
        r'vivo',
        r'claro',
        r'tim',
        r'oi\b',
        r'sigilo\s+telef[oô]nico',
    ],
    'policia': [
        r'pol[íi]cia',
        r'delegacia',
        r'dpo',
    ]
}

def detect_institution_blocks(text: str) -> List[dict]:
    """
    Detecta blocos de solicitação por destinatário

    Procura padrões como:
    - "Oficie-se ao Banco X..."
    - "Oficie-se à Receita Federal..."
    - "Determino..."
    """

    blocks = []

    # Padrão 1: "Oficie-se ao/à [instituição]"
    oficie_pattern = r'(?:OFICIE-SE|OFICIE|EXPEÇA-SE)[^.]*?(?:AO|À|AOS|ÀS)\s+([^.,\n]+?)(?:[,.]|\n)'
    matches = re.finditer(oficie_pattern, text, re.IGNORECASE | re.MULTILINE)

    for match in matches:
        instituicao = match.group(1).strip()
        start = match.start()

        # Encontra o bloco de texto até o próximo "Oficie-se" ou fim
        next_oficie = re.search(r'OFICIE-SE', text[start+10:], re.IGNORECASE)
        if next_oficie:
            end = start + 10 + next_oficie.start()
        else:
            end = len(text)

        blocks.append({
            'tipo': 'oficie_se',
            'destinatario': instituicao,
            'trecho': text[start:end],
            'start': start,
            'end': end
        })

    # Padrão 2: "DETERMINO..." sem destinatário específico
    if not blocks:
        # Se não tem blocos específicos, considera tudo como genérico
        blocks.append({
            'tipo': 'generico',
            'destinatario': 'INDETERMINADO',
            'trecho': text,
            'start': 0,
            'end': len(text)
        })

    return blocks

def classify_institution(destinatario: str, trecho: str) -> InstituicaoMencionada:
    """
    Classifica o tipo de instituição mencionada
    """

    dest_lower = destinatario.lower()
    trecho_lower = trecho.lower()

    # Verifica bancos
    for pattern in BANCOS_CONHECIDOS:
        if re.search(pattern, dest_lower, re.IGNORECASE) or re.search(pattern, trecho_lower, re.IGNORECASE):
            return InstituicaoMencionada(
                tipo="banco_especifico" if "banco x" in dest_lower else "instituicao_financeira",
                nome=destinatario,
                trecho_relevante=trecho[:200],
                e_destinatario_direto=True,
                confidence=0.95
            )

    # Verifica BACEN
    for pattern in BACEN_PATTERNS:
        if re.search(pattern, dest_lower, re.IGNORECASE):
            return InstituicaoMencionada(
                tipo="bacen",
                nome="BACEN",
                trecho_relevante=trecho[:200],
                e_destinatario_direto=True,
                confidence=0.95
            )

    # Verifica outras instituições
    for tipo, patterns in OUTRAS_INSTITUICOES.items():
        for pattern in patterns:
            if re.search(pattern, dest_lower, re.IGNORECASE) or re.search(pattern, trecho_lower, re.IGNORECASE):
                return InstituicaoMencionada(
                    tipo=tipo,
                    nome=destinatario,
                    trecho_relevante=trecho[:200],
                    e_destinatario_direto=True,
                    confidence=0.90
                )

    # Indeterminado
    return InstituicaoMencionada(
        tipo="indeterminado",
        nome=destinatario,
        trecho_relevante=trecho[:200],
        e_destinatario_direto=True,
        confidence=0.5
    )

@tool
def filter_by_institution(text: str, nome_banco: str = "Banco X") -> FiltroInstituicaoResult:
    """
    Filtra o ofício para determinar se é relevante para instituição financeira

    Args:
        text: Texto completo do ofício
        nome_banco: Nome do banco a ser considerado (padrão: "Banco X")

    Returns:
        FiltroInstituicaoResult com análise de relevância
    """

    import logging
    logger = logging.getLogger(__name__)

    # Atualiza padrões com nome real do banco
    global BANCOS_CONHECIDOS
    BANCOS_CONHECIDOS = [
        nome_banco.lower(),
        r'bancos?',
        r'institui[çc][aã]o\s+financeira',
        r'institui[çc][õo]es\s+financeiras',
    ]

    # PASSO 1: Detecta blocos por destinatário
    blocks = detect_institution_blocks(text)
    logger.info(f"Detectados {len(blocks)} blocos de solicitação")

    # PASSO 2: Classifica cada bloco
    instituicoes = []
    trechos_relevantes = []

    for block in blocks:
        inst = classify_institution(block['destinatario'], block['trecho'])
        instituicoes.append(inst)

        # Se é relevante para banco, guarda o trecho
        if inst.tipo in ["banco_especifico", "instituicao_financeira", "indeterminado"]:
            trechos_relevantes.append(block['trecho'])

    # PASSO 3: Detecta tipo de sigilo
    tipo_sigilo = "indeterminado"
    text_lower = text.lower()

    if re.search(r'sigilo\s+banc[aá]rio', text_lower):
        tipo_sigilo = "bancario"
    elif re.search(r'sigilo\s+fiscal', text_lower):
        tipo_sigilo = "fiscal"
    elif re.search(r'sigilo\s+telef[oô]nico', text_lower):
        tipo_sigilo = "telefonico"

    # Se menciona múltiplos tipos
    tipos_mencionados = []
    if re.search(r'sigilo\s+banc[aá]rio', text_lower):
        tipos_mencionados.append('bancario')
    if re.search(r'sigilo\s+fiscal', text_lower):
        tipos_mencionados.append('fiscal')
    if re.search(r'sigilo\s+telef[oô]nico', text_lower):
        tipos_mencionados.append('telefonico')

    if len(tipos_mencionados) > 1:
        tipo_sigilo = "misto"

    # PASSO 4: Decide se é relevante
    e_relevante = False
    motivo = ""
    confidence = 0.0

    # REGRA 1: Tem banco específico ou instituição financeira mencionada
    tem_banco = any(inst.tipo in ["banco_especifico", "instituicao_financeira"] for inst in instituicoes)

    # REGRA 2: É sigilo bancário ou indeterminado
    e_sigilo_bancario = tipo_sigilo in ["bancario", "indeterminado"]

    # REGRA 3: Não é exclusivamente para outras instituições
    so_outras_instituicoes = all(
        inst.tipo in ["fiscal", "operadora", "policia"]
        for inst in instituicoes
        if inst.tipo != "indeterminado"
    )

    # DECISÃO FINAL
    if so_outras_instituicoes and tipo_sigilo in ["fiscal", "telefonico"]:
        # Exclusivamente fiscal ou telefônico
        e_relevante = False
        motivo = f"Ofício exclusivamente para {tipo_sigilo}, não relevante para banco"
        confidence = 0.95
    elif tem_banco:
        # Menciona banco explicitamente
        e_relevante = True
        motivo = f"Ofício menciona {[i.nome for i in instituicoes if i.tipo in ['banco_especifico', 'instituicao_financeira']]}"
        confidence = 0.95
    elif e_sigilo_bancario and len(blocks) == 1 and blocks[0]['tipo'] == 'generico':
        # Sigilo bancário genérico (sem destinatário específico)
        e_relevante = True
        motivo = "Sigilo bancário sem destinatário específico - assume instituição financeira"
        confidence = 0.85
    elif tipo_sigilo == "misto":
        # Múltiplos tipos - isola apenas trecho bancário
        e_relevante = len(trechos_relevantes) > 0
        motivo = "Ofício misto - isolando apenas trechos para instituição financeira"
        confidence = 0.80
    else:
        # Caso ambíguo
        e_relevante = False
        motivo = "Ofício não contém solicitação clara para instituição financeira"
        confidence = 0.70

    # PASSO 5: Consolida trechos relevantes
    trecho_final = None
    if e_relevante and trechos_relevantes:
        trecho_final = "\n\n---\n\n".join(trechos_relevantes)
    elif e_relevante and not trechos_relevantes:
        # Assume ofício inteiro
        trecho_final = text

    return FiltroInstituicaoResult(
        e_relevante_para_banco=e_relevante,
        motivo=motivo,
        instituicoes_mencionadas=instituicoes,
        tem_multiplos_destinatarios=len(blocks) > 1,
        tipo_sigilo=tipo_sigilo,
        trecho_relevante_para_banco=trecho_final,
        confidence=confidence
    )

def validate_with_llm_if_ambiguous(
    filtro_result: FiltroInstituicaoResult,
    texto_oficio: str
) -> FiltroInstituicaoResult:
    """
    STUB: Validação LLM para casos ambíguos

    Se confidence < 0.80, usar LLM para confirmar

    TODO: Implementar chamada real ao LLM
    """

    if filtro_result.confidence >= 0.80:
        # Alta confiança, não precisa LLM
        return filtro_result

    # TODO: Implementar validação LLM para casos ambíguos
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Caso ambíguo (confidence {filtro_result.confidence:.2f}) - validação LLM não implementada")

    return filtro_result
