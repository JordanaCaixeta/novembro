# 6. Orchestrator Agent Principal
# Coordena todo o fluxo considerando os cenarios possiveis:

import uuid
from typing import List, Optional, Literal
from pydantic import BaseModel
from smolagents import CodeAgent, LiteLLMModel
import os

# Importa funcoes e classes dos outros modulos
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
    extract_and_match_subsidies_hybrid  # NOVA versao com validacao LLM
)
from scr.modulos.datas_management import (
    extract_all_dates,
    extract_period_from_text
)
from scr.modulos.carta_circular import extract_carta_circular
from scr.modulos.DE_PARA_detector import detect_de_para_requirements
from scr.modulos.instituicao_filter import filter_by_institution, FiltroInstituicaoResult

# CCS REMOVIDO - Tool nao disponivel no momento
# from scr.modulos.ccs_validation import (
#     get_ccs_relations,
#     validate_all_parties_ccs,
#     CCSValidationResult
# )

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

        # Configura modelo OpenAI 5 (o5)
        model_id = os.getenv("OPENAI_MODEL", "o4-mini")  # OpenAI 5 / o5
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key:
            model = LiteLLMModel(model_id=model_id, api_key=api_key)
        else:
            # Fallback sem API key configurada
            model = LiteLLMModel(model_id=model_id)

        super().__init__(
            model=model,
            name="warrant_orchestrator",
            description="Coordena processamento completo de oficios",
            max_steps=30
        )

    def process_warrant(self, input_text: str) -> WarrantProcessingResult:
        """
        Processa o input completo, independente do formato
        """
        session_id = str(uuid.uuid4())
        alertas = []

        # STEP 1: Classificacao inicial
        classification = analyze_input_structure(input_text)

        # STEP 2: Decisao de processamento baseado no tipo
        if classification.tipo_oficio == "reiteracao":
            alertas.append("REITERACAO DETECTADA - Marcado para analise prioritaria")
            # Por enquanto, nao processa reiteracoes conforme requisito
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

        # Tratamento para oficio complementar
        if classification.tipo_oficio == "complemento":
            alertas.append("OFICIO COMPLEMENTAR - Processamento adicional ao oficio anterior")
            # Processa normalmente mas com flag de complemento

        # STEP 2.5: Filtro de Instituicao Financeira
        # Verifica se o oficio e relevante para o Banco X antes de processar
        filtro_result = filter_by_institution(input_text, nome_banco="Banco X")

        if not filtro_result.e_relevante_para_banco:
            alertas.append(f"OFICIO NAO RELEVANTE: {filtro_result.motivo}")
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

        # Se relevante, log das instituicoes encontradas
        instituicoes_info = ", ".join([
            f"{inst.tipo}: {inst.nome}"
            for inst in filtro_result.instituicoes_mencionadas
        ])
        alertas.append(f"Instituicoes detectadas: {instituicoes_info}")
        alertas.append(f"Tipo de sigilo: {filtro_result.tipo_sigilo}")

        if filtro_result.tem_multiplos_destinatarios:
            alertas.append("MULTIPLOS DESTINATARIOS - Isolado trecho para instituicao financeira")

        # STEP 3: Extracao de conteudo relevante
        if classification.tem_ocr_oficio or classification.tem_marcador_ocr:
            # Tem o oficio (com ou sem marcador OCR), extrai o conteudo limpo
            oficio_content = extract_oficio_content(input_text, classification)

            if oficio_content == "[OFICIO_NAO_ENCONTRADO]":
                alertas.append("Oficio mencionado mas nao encontrado no texto")
                oficio_content = input_text  # Tenta processar tudo

            # Se o filtro isolou um trecho especifico para o banco, usa esse trecho
            if filtro_result.trecho_relevante_para_banco:
                oficio_content = filtro_result.trecho_relevante_para_banco
                alertas.append("Processando apenas trecho relevante para instituicao financeira")
        else:
            # Nao tem oficio completo, precisa consultar sistema
            minimal_info = extract_minimal_info_for_lookup(input_text)

            if not minimal_info["pode_consultar_sistema"]:
                alertas.append("Informacoes insuficientes para processamento")
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

            # Tem dados minimos para consulta
            return WarrantProcessingResult(
                session_id=session_id,
                input_classification=classification,
                tipo_oficio=classification.tipo_oficio,
                deve_processar=False,
                investigados=[],
                subsidios=[],
                periodos=[],
                precisa_consulta_sistema=True,
                dados_para_consulta=minimal_info,
                confidence_geral=0.6,
                alertas=["Necessaria consulta ao sistema interno para dados completos"]
            )

        # STEP 4: Processamento paralelo de extracao
        # (Em producao, isso seria paralelizado de verdade)

        # Extrai investigados
        parties_result = extract_all_investigated_parties(oficio_content)
        if parties_result.tem_mais_investigados_possiveis:
            alertas.append("Possiveis investigados adicionais nao capturados")

        # CCS REMOVIDO - Validacao CCS desabilitada temporariamente
        # A validacao de clientes sera feita via DI4 quando disponivel
        investigados_validados = parties_result.investigados
        # tem_pelo_menos_um_cliente = False  # Removido - sem CCS

        # for party in parties_result.investigados:
        #     party_dict = party.model_dump()
        #     cpf_cnpj = party_dict.get("cpf") or party_dict.get("cnpj")
        #
        #     if cpf_cnpj:
        #         try:
        #             ccs_result = get_ccs_relations(cpf_cnpj)
        #             # ... resto da validacao CCS ...
        #         except Exception as e:
        #             ...

        # Extrai e faz match de subsidios (VERSAO HIBRIDA com validacao LLM)
        subsidies_result = extract_and_match_subsidies_hybrid(
            oficio_content,
            self.catalog_path,
            use_llm_validation=True  # SEMPRE usa LLM para maxima precisao
        )
        if subsidies_result.subsidios_nao_identificados:
            alertas.append(f"{len(subsidies_result.subsidios_nao_identificados)} subsidios nao identificados no catalogo")

        # Extrai datas/periodos
        dates = extract_all_dates(oficio_content)
        periodos = []
        for date in dates:
            if date.tipo == "periodo" or date.tipo == "especifica":
                periodo = extract_period_from_text(date.data_original)
                if periodo:
                    periodos.append(periodo)

        # Detecta Carta Circular
        carta_result = extract_carta_circular(
            oficio_content,
            [s.nome_subsidio for s in subsidies_result.subsidios_solicitados]
        )
        if carta_result.tem_carta_circular:
            alertas.append(f"Carta Circular detectada: {carta_result.total_cartas} referencia(s)")
            # Atualiza subsidios com carta circular
            for subsidio in subsidies_result.subsidios_solicitados:
                for carta in carta_result.cartas_encontradas:
                    if subsidio.nome_subsidio in carta.subsidios_associados:
                        subsidio.carta_circular = f"CC {carta.numero}/{carta.ano or 'N/A'}"

        # Detecta DE/PARA
        de_para = detect_de_para_requirements(
            oficio_content,
            [s.model_dump() for s in subsidies_result.subsidios_solicitados]
        )
        if de_para.requer_de_para:
            alertas.append(f"DE/PARA requerido para {len(de_para.subsidios_com_de_para)} subsidios")
            # Marca subsidios com DE/PARA
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

        # STEP 6: Validacoes finais
        if not parties_result.investigados:
            alertas.append("CRITICO: Nenhum investigado identificado")
            confidence_geral *= 0.5

        if not subsidies_result.subsidios_solicitados:
            alertas.append("CRITICO: Nenhum subsidio identificado")
            confidence_geral *= 0.5

        # CCS REMOVIDO - Ajuste de confidence baseado em CCS desabilitado
        # if parties_result.investigados and not tem_pelo_menos_um_cliente:
        #     confidence_geral *= 0.6
        #     alertas.append("ALERTA: Quebra de sigilo para nao-clientes do banco")
        # elif tem_pelo_menos_um_cliente:
        #     confidence_geral *= 1.1
        #     confidence_geral = min(confidence_geral, 1.0)

        # Ajuste de confidence para oficio complementar
        if classification.tipo_oficio == "complemento":
            confidence_geral *= 0.9  # Pequena reducao por ser complementar

        return WarrantProcessingResult(
            session_id=session_id,
            input_classification=classification,
            tipo_oficio=classification.tipo_oficio,
            deve_processar=True,
            investigados=parties_result.investigados,
            subsidios=subsidies_result.subsidios_solicitados,
            periodos=periodos,
            precisa_consulta_sistema=False,
            dados_para_consulta=None,
            confidence_geral=confidence_geral,
            alertas=alertas
        )
