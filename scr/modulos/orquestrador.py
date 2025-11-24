# 6. Orchestrator Agent Principal
# Coordena todo o fluxo considerando os cenários possíveis:

class WarrantProcessingResult(BaseModel):
    session_id: str
    input_classification: InputClassification
    tipo_oficio: Literal["primeiro_oficio", "reiteracao"]
    deve_processar: bool
    investigados: List[InvestigatedParty]
    subsidios: List[SubsidyMatch]
    periodos: List[dict]
    precisa_consulta_sistema: bool
    dados_para_consulta: Optional[dict]
    confidence_geral: float
    alertas: List[str]

class WarrantOrchestrator(CodeAgent):
    def __init__(self, catalog_path: str):
        self.catalog_path = catalog_path
        super().__init__(
            model=HfApiModel("deepseek-ai/DeepSeek-R1"),
            name="warrant_orchestrator",
            description="Coordena processamento completo de ofícios",
            max_steps=30
        )
    
    def process_warrant(self, input_text: str) -> WarrantProcessingResult:
        """
        Processa o input completo, independente do formato
        """
        session_id = str(uuid.uuid4())
        alertas = []
        
        # STEP 1: Classificação inicial
        classification = analyze_input_structure(input_text)
        
        # STEP 2: Decisão de processamento baseado no tipo
        if classification.tipo_oficio == "reiteracao":
            alertas.append("REITERAÇÃO DETECTADA - Marcado para análise prioritária")
            # Por enquanto, não processa reiterações conforme requisito
            return WarrantProcessingResult(
                session_id=session_id,
                input_classification=classification,
                tipo_oficio="reiteracao",
                deve_processar=False,
                investigados=[],
                subsidios=[],
                periodos=[],
                precisa_consulta_sistema=False,
                dados_para_consulta=None,
                confidence_geral=classification.confidence_score,
                alertas=alertas
            )
        
        # STEP 3: Extração de conteúdo relevante
        if classification.tem_ocr_oficio:
            # Tem o ofício, extrai o conteúdo limpo
            oficio_content = extract_oficio_content(input_text, classification)
            
            if oficio_content == "[OFICIO_NAO_ENCONTRADO]":
                alertas.append("Ofício mencionado mas não encontrado no texto")
                oficio_content = input_text  # Tenta processar tudo
        else:
            # Não tem ofício completo, precisa consultar sistema
            minimal_info = extract_minimal_info_for_lookup(input_text)
            
            if not minimal_info["pode_consultar_sistema"]:
                alertas.append("Informações insuficientes para processamento")
                return WarrantProcessingResult(
                    session_id=session_id,
                    input_classification=classification,
                    tipo_oficio="indeterminado",
                    deve_processar=False,
                    investigados=[],
                    subsidios=[],
                    periodos=[],
                    precisa_consulta_sistema=True,
                    dados_para_consulta=minimal_info,
                    confidence_geral=0.3,
                    alertas=alertas
                )
            
            # Tem dados mínimos para consulta
            return WarrantProcessingResult(
                session_id=session_id,
                input_classification=classification,
                tipo_oficio="primeiro_oficio",
                deve_processar=False,
                investigados=[],
                subsidios=[],
                periodos=[],
                precisa_consulta_sistema=True,
                dados_para_consulta=minimal_info,
                confidence_geral=0.6,
                alertas=["Necessária consulta ao sistema interno para dados completos"]
            )
        
        # STEP 4: Processamento paralelo de extração
        # (Em produção, isso seria paralelizado de verdade)
        
        # Extrai investigados
        parties_result = extract_all_investigated_parties(oficio_content)
        if parties_result.tem_mais_investigados_possiveis:
            alertas.append("Possíveis investigados adicionais não capturados")
        
        # Extrai e faz match de subsídios
        subsidies_result = extract_and_match_subsidies(
            oficio_content, 
            self.catalog_path
        )
        if subsidies_result.subsidios_nao_identificados:
            alertas.append(f"{len(subsidies_result.subsidios_nao_identificados)} subsídios não identificados no catálogo")
        
        # Extrai datas/períodos
        dates = extract_all_dates(oficio_content)
        periodos = []
        for date in dates:
            if date.tipo == "periodo" or date.tipo == "especifica":
                periodo = extract_period_from_text(date.data_original)
                if periodo:
                    periodos.append(periodo)
        
        # STEP 5: Calcula confidence geral
        confidence_factors = [
            classification.confidence_score,
            1.0 if parties_result.investigados else 0.0,
            1.0 if subsidies_result.subsidios_solicitados else 0.5,
            min(s.similarity_score for s in subsidies_result.subsidios_solicitados) if subsidies_result.subsidios_solicitados else 0.5
        ]
        confidence_geral = sum(confidence_factors) / len(confidence_factors)
        
        # STEP 6: Validações finais
        if not parties_result.investigados:
            alertas.append("CRÍTICO: Nenhum investigado identificado")
            confidence_geral *= 0.5
        
        if not subsidies_result.subsidios_solicitados:
            alertas.append("CRÍTICO: Nenhum subsídio identificado")
            confidence_geral *= 0.5
        
        return WarrantProcessingResult(
            session_id=session_id,
            input_classification=classification,
            tipo_oficio="primeiro_oficio",
            deve_processar=True,
            investigados=parties_result.investigados,
            subsidios=subsidies_result.subsidios_solicitados,
            periodos=periodos,
            precisa_consulta_sistema=False,
            dados_para_consulta=None,
            confidence_geral=confidence_geral,
            alertas=alertas
        )