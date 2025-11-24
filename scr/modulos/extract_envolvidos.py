# 3. Agent de Extração de Investigados (Multi-Entity)
# Este agente lida com múltiplos investigados sem limite pré-definido:

class InvestigatedParty(BaseModel):
    nome: str
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    tipo: Literal["pessoa_fisica", "pessoa_juridica"]
    confidence: float

class InvestigatedPartiesExtraction(BaseModel):
    investigados: List[InvestigatedParty]
    total_encontrado: int
    tem_mais_investigados_possiveis: bool

@tool
def extract_all_investigated_parties(text: str) -> InvestigatedPartiesExtraction:
    """
    Extrai TODOS os investigados mencionados, sem limite de quantidade
    """
    investigados = []
    processed_ids = set()  # Para evitar duplicatas
    
    # Estratégia 1: Buscar em blocos estruturados
    # Ex: "INVESTIGADOS: 1. João Silva CPF 123.456.789-00"
    structured_pattern = r'(?:INVESTIGAD[OA]S?|REQUERID[OA]S?|PARTE[S]?)[:\s]+(.+?)(?:\n\n|DETERMINO|OFICIE-SE)'
    matches = re.findall(structured_pattern, text, re.IGNORECASE | re.DOTALL)
    
    for match in matches:
        lines = match.split('\n')
        for line in lines:
            party = extract_party_from_line(line)
            if party and party['id'] not in processed_ids:
                investigados.append(party)
                processed_ids.add(party['id'])
    
    # Estratégia 2: Buscar CPFs/CNPJs soltos no texto
    cpf_pattern = r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:,\s*)?(?:CPF|C\.P\.F\.)[:\s]*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})'
    cnpj_pattern = r'(\b[A-Z].+?)\s*(?:,\s*)?(?:CNPJ|C\.N\.P\.J\.)[:\s]*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})'
    
    for nome, cpf in re.findall(cpf_pattern, text):
        cpf_clean = re.sub(r'[^\d]', '', cpf)
        if cpf_clean not in processed_ids:
            investigados.append(InvestigatedParty(
                nome=nome.strip(),
                cpf=cpf_clean,
                tipo="pessoa_fisica",
                confidence=0.9
            ))
            processed_ids.add(cpf_clean)
    
    for nome, cnpj in re.findall(cnpj_pattern, text):
        cnpj_clean = re.sub(r'[^\d]', '', cnpj)
        if cnpj_clean not in processed_ids:
            investigados.append(InvestigatedParty(
                nome=nome.strip(),
                cnpj=cnpj_clean,
                tipo="pessoa_juridica",
                confidence=0.9
            ))
            processed_ids.add(cnpj_clean)
    
    # Detecta se pode haver mais investigados não capturados
    tem_mais = bool(re.search(r'(?:e outros|et al|demais|\.\.\.|entre outros)', text, re.IGNORECASE))
    
    return InvestigatedPartiesExtraction(
        investigados=investigados,
        total_encontrado=len(investigados),
        tem_mais_investigados_possiveis=tem_mais
    )