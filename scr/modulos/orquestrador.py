# 6. Orchestrator Agent Principal
# Coordena todo o fluxo considerando os cenários possíveis:

import uuid
from typing import List, Optional, Literal
from pydantic import BaseModel
from smolagents import CodeAgent, HfApiModel

# Importa funções e classes dos outros módulos
from scr.modulos.datamanagement import (
    InputClassification,
    analyze_input_structure,
    extract_oficio_content,
    extract_minimal_info_for_lookup
)
from scr.modulos.extract_envolvidos import (
    InvestigatedParty,
    extract_all_investigated_parties
)
from scr.modulos.extract_subsidios import (
    SubsidyMatch,
    extract_and_match_subsidies,
    extract_and_match_subsidies_hybrid  # NOVA versão com validação LLM
)
from scr.modulos.datas_management import (
    extract_all_dates,
    extract_period_from_text
)
from scr.modulos.carta_circular import extract_carta_circular
from scr.modulos.DE_PARA_detector import detect_de_para_requirements
from scr.modulos.instituicao_filter import filter_by_institution, FiltroInstituicaoResult

class WarrantProcessingResult(BaseModel):
    session_id: str
    input_classification: InputClassification
    tipo_oficio: Literal["primeiro_oficio", "reiteracao", "complemento", "nao_relevante", "indeterminado"]
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
        
        # NOVO: Tratamento para ofício complementar
        if classification.tipo_oficio == "complemento":
            alertas.append("OFÍCIO COMPLEMENTAR - Processamento adicional ao ofício anterior")
            # Processa normalmente mas com flag de complemento

        # STEP 2.5: Filtro de Instituição Financeira
        # Verifica se o ofício é relevante para o Banco X antes de processar
        filtro_result = filter_by_institution(input_text, nome_banco="Banco X")

        if not filtro_result.e_relevante_para_banco:
            alertas.append(f"OFÍCIO NÃO RELEVANTE: {filtro_result.motivo}")
            return WarrantProcessingResult(
                session_id=session_id,
                input_classification=classification,
                tipo_oficio="nao_relevante",
                deve_processar=False,
                investigados=[],
                subsidios=[],
                periodos=[],
                precisa_consulta_sistema=False,
                dados_para_consulta=None,
                confidence_geral=filtro_result.confidence,
                alertas=alertas
            )

        # Se relevante, log das instituições encontradas
        instituicoes_info = ", ".join([
            f"{inst.tipo}: {inst.nome}"
            for inst in filtro_result.instituicoes_mencionadas
        ])
        alertas.append(f"Instituições detectadas: {instituicoes_info}")
        alertas.append(f"Tipo de sigilo: {filtro_result.tipo_sigilo}")

        if filtro_result.tem_multiplos_destinatarios:
            alertas.append("MÚLTIPLOS DESTINATÁRIOS - Isolado trecho para instituição financeira")

        # STEP 3: Extração de conteúdo relevante
        if classification.tem_ocr_oficio or classification.tem_marcador_ocr:  # MODIFICADO
            # Tem o ofício (com ou sem marcador OCR), extrai o conteúdo limpo
            oficio_content = extract_oficio_content(input_text, classification)

            if oficio_content == "[OFICIO_NAO_ENCONTRADO]":
                alertas.append("Ofício mencionado mas não encontrado no texto")
                oficio_content = input_text  # Tenta processar tudo

            # Se o filtro isolou um trecho específico para o banco, usa esse trecho
            if filtro_result.trecho_relevante_para_banco:
                oficio_content = filtro_result.trecho_relevante_para_banco
                alertas.append("Processando apenas trecho relevante para instituição financeira")
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
                tipo_oficio=classification.tipo_oficio,  # MODIFICADO
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
        
        # Extrai e faz match de subsídios (VERSÃO HÍBRIDA com validação LLM)
        subsidies_result = extract_and_match_subsidies_hybrid(
            oficio_content,
            self.catalog_path,
            use_llm_validation=True  # SEMPRE usa LLM para máxima precisão
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
        
        # NOVO: Detecta Carta Circular
        carta_result = extract_carta_circular(
            oficio_content,
            [s.nome_subsidio for s in subsidies_result.subsidios_solicitados]
        )
        if carta_result.tem_carta_circular:
            alertas.append(f"Carta Circular detectada: {carta_result.total_cartas} referência(s)")
            # Atualiza subsídios com carta circular
            for subsidio in subsidies_result.subsidios_solicitados:
                for carta in carta_result.cartas_encontradas:
                    if subsidio.nome_subsidio in carta.subsidios_associados:
                        subsidio.carta_circular = f"CC {carta.numero}/{carta.ano or 'N/A'}"
        
        # NOVO: Detecta DE/PARA
        de_para = detect_de_para_requirements(
            oficio_content,
            [s.model_dump() for s in subsidies_result.subsidios_solicitados]
        )
        if de_para.requer_de_para:
            alertas.append(f"DE/PARA requerido para {len(de_para.subsidios_com_de_para)} subsídios")
            # Marca subsídios com DE/PARA
            for subsidio in subsidies_result.subsidios_solicitados:
                if subsidio.subsidio_id in de_para.subsidios_com_de_para:
                    subsidio.requer_de_para = True
        
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
        
        # NOVO: Ajuste de confidence para ofício complementar
        if classification.tipo_oficio == "complemento":
            confidence_geral *= 0.9  # Pequena redução por ser complementar
        
        return WarrantProcessingResult(
            session_id=session_id,
            input_classification=classification,
            tipo_oficio=classification.tipo_oficio,  # MODIFICADO: usa o tipo detectado
            deve_processar=True,
            investigados=parties_result.investigados,
            subsidios=subsidies_result.subsidios_solicitados,
            periodos=periodos,
            precisa_consulta_sistema=False,
            dados_para_consulta=None,
            confidence_geral=confidence_geral,
            alertas=alertas
        )