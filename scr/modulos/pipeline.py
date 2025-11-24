# 7. Fluxo de Decisão e Tratamento de Casos Especiais

def main_processing_pipeline(input_text: str, catalog_path: str):
    """
    Pipeline principal com tratamento de todos os casos
    """
    orchestrator = WarrantOrchestrator(catalog_path)
    result = orchestrator.process_warrant(input_text)
    
    # Decisões baseadas no resultado
    if result.tipo_oficio == "reiteracao":
        # Marca para fila de alta prioridade mas não processa agora
        log_reiteracao(result.session_id)
        return {
            "status": "REITERACAO_IDENTIFICADA",
            "action": "Enviado para processamento prioritário",
            "session_id": result.session_id
        }
    
    if result.precisa_consulta_sistema:
        # Consulta sistema interno com os dados disponíveis
        if result.dados_para_consulta["pode_consultar_sistema"]:
            # Faz consulta no CCS/Sistema interno
            warrant_data = consultar_sistema_interno(result.dados_para_consulta)
            
            if warrant_data:
                # Reprocessa com dados completos
                return orchestrator.process_warrant(warrant_data["oficio_completo"])
            else:
                return {
                    "status": "DADOS_INSUFICIENTES",
                    "action": "Necessária intervenção manual",
                    "dados_disponiveis": result.dados_para_consulta
                }
    
    if result.deve_processar and result.confidence_geral >= 0.75:
        # Processa automaticamente
        return process_to_sisbajud(result)
    
    elif result.deve_processar and result.confidence_geral >= 0.50:
        # Envia para revisão humana com pré-processamento
        return {
            "status": "REVISAO_NECESSARIA",
            "confidence": result.confidence_geral,
            "alertas": result.alertas,
            "dados_extraidos": {
                "investigados": result.investigados,
                "subsidios": result.subsidios,
                "periodos": result.periodos
            }
        }
    
    else:
        # Confidence muito baixa, precisa análise manual completa
        return {
            "status": "ANALISE_MANUAL_COMPLETA",
            "reason": "Confidence abaixo do threshold mínimo",
            "alertas": result.alertas
        }