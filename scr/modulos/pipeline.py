# 7. Fluxo de Decisão e Tratamento de Casos Especiais

import logging
from typing import Dict, Any
from scr.modulos.orquestrador import WarrantOrchestrator, WarrantProcessingResult

# Configuração de logging
logger = logging.getLogger(__name__)

def log_reiteracao(session_id: str):
    """
    Registra uma reiteração identificada no sistema
    """
    logger.warning(f"REITERAÇÃO detectada - Session ID: {session_id}")
    # TODO: Implementar envio para fila de alta prioridade

def log_complemento(session_id: str):
    """
    Registra um ofício complementar identificado
    """
    logger.info(f"Ofício COMPLEMENTAR detectado - Session ID: {session_id}")
    # TODO: Implementar marcação como complementar no sistema

def consultar_sistema_interno(dados_consulta: dict) -> Dict[str, Any]:
    """
    Consulta o sistema interno (CCS/Database) com dados mínimos
    """
    logger.info(f"Consultando sistema interno com dados: {dados_consulta}")
    # TODO: Implementar integração real com sistema CCS/Database
    # Por enquanto retorna None para simular ofício não encontrado
    return None

def process_to_sisbajud(result: WarrantProcessingResult) -> Dict[str, Any]:
    """
    Processa e envia os dados extraídos para o SISBAJUD
    """
    logger.info(f"Processando para SISBAJUD - Session: {result.session_id}")
    # TODO: Implementar integração real com SISBAJUD
    return {
        "status": "PROCESSADO_AUTOMATICAMENTE",
        "session_id": result.session_id,
        "action": "Enviado para SISBAJUD",
        "dados_extraidos": {
            "investigados": len(result.investigados),
            "subsidios": len(result.subsidios),
            "periodos": len(result.periodos),
            "confidence": result.confidence_geral
        }
    }

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
            "action": "Enviado para investigador",
            "session_id": result.session_id
        }
    
    # NOVO: Tratamento para ofício complementar
    if result.tipo_oficio == "complemento":
        # Processa mas marca como complementar
        log_complemento(result.session_id)
        
        # Se tem confidence alta, processa automaticamente
        if result.confidence_geral >= 0.75:
            return {
                "status": "COMPLEMENTO_PROCESSADO",
                "action": "enviado para o investigador",
                "session_id": result.session_id,
                "dados_extraidos": {
                    "investigados": len(result.investigados),
                    "subsidios": len(result.subsidios),
                    "alertas": result.alertas
                }
            }
        else:
            # Envia para revisão
            return {
                "status": "COMPLEMENTO_REVISAO",
                "action": "Ofício complementar requer revisão",
                "session_id": result.session_id,
                "confidence": result.confidence_geral,
                "alertas": result.alertas
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

# 8. Exemplo de Uso com Todas as Funcionalidades - ATUALIZADO

if __name__ == "__main__":
    # Configuração
    config = {
        'catalog_path': 'subsidios_catalog.csv',
        'models': {
            'fast': 'Qwen/Qwen2.5-Coder-32B-Instruct',
            'reasoning': 'deepseek-ai/DeepSeek-R1',
            'precision': 'gpt-4o'
        }
    }
    
    # NOVO: Exemplo com marcadores <<OCR>>
    exemplo_ocr = """
    De: juridico@bancox.com.br
    Para: compliance@bancox.com.br
    Assunto: Ofício Judicial - Urgente
    
    Segue ofício recebido.
    
    <<OCR>>
    PODER JUDICIÁRIO
    1ª VARA CRIMINAL DE SÃO PAULO
    
    OFÍCIO Nº 1234/2024
    
    Processo nº 1234567-89.2024.8.26.0001
    
    Investigados:
    1. JOÃO SILVA SANTOS, CPF 123.456.789-00
    2. MARIA OLIVEIRA, CPF 987.654.321-00
    
    DETERMINO a quebra de sigilo bancário no período de 
    janeiro de 2023 a dezembro de 2023.
    
    Solicito:
    - Extratos de conta corrente com DE/PARA
    - Cartões de crédito
    
    Conforme Carta Circular 4.123/2023.
    
    Prazo: 10 dias
    <<OCR>>
    """
    
    # NOVO: Exemplo de ofício complementar
    exemplo_complemento = """
    <<OCR>>
    PODER JUDICIÁRIO
    OFÍCIO COMPLEMENTAR Nº 5678/2024
    
    Em complemento ao Ofício nº 1234/2024, parcialmente atendido,
    SOLICITO ADICIONALMENTE:
    
    Investigado: JOÃO SILVA SANTOS, CPF 123.456.789-00
    
    - Informações de investimentos
    - Extratos de poupança
    
    Período: mesmo do ofício anterior
    <<OCR>>
    """
    
    # NOVO: Exemplo de reiteração
    exemplo_reiteracao = """
    <<OCR>>
    OFÍCIO - REITERAÇÃO
    
    REITERO a solicitação do Ofício nº 1234/2024, 
    NÃO ATENDIDO no prazo estabelecido.
    
    URGENTE - Prazo vencido há 15 dias
    <<OCR>>
    """
    
    # Processa cada exemplo
    print("="*60)
    print("EXEMPLO 1: Ofício com marcadores OCR")
    print("="*60)
    result1 = main_processing_pipeline(exemplo_ocr, config['catalog_path'])
    print(f"Status: {result1['status']}")
    print(f"Action: {result1['action']}")
    if 'dados_extraidos' in result1:
        print(f"Investigados: {result1['dados_extraidos']['investigados']}")
        print(f"Subsídios: {result1['dados_extraidos']['subsidios']}")
    print()
    
    print("="*60)
    print("EXEMPLO 2: Ofício Complementar")
    print("="*60)
    result2 = main_processing_pipeline(exemplo_complemento, config['catalog_path'])
    print(f"Status: {result2['status']}")
    print(f"Action: {result2['action']}")
    print()
    
    print("="*60)
    print("EXEMPLO 3: Reiteração")
    print("="*60)
    result3 = main_processing_pipeline(exemplo_reiteracao, config['catalog_path'])
    print(f"Status: {result3['status']}")
    print(f"Action: {result3['action']}")