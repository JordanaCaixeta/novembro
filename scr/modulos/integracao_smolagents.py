# 8. Integração com Smolagents - Configuração Completa
# Adaptado para ambiente Banco X com IaraGenAI
from smolagents import CodeAgent, ManagedAgent
import logging

from .llm_client import get_smolagents_model, IaraLLMModel
from .config import MODEL_CONFIG

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MultiAgentWarrantProcessor:
    def __init__(self, catalog_path: str, models_config: dict = None):

        # Configuração de modelos - usa IaraGenAI do Banco X
        # Modelos: gpt-5-nano (fast), gpt-5 (reasoning), gpt-5-mini (precision)
        self.models = models_config or {
            'fast': get_smolagents_model("fast"),           # gpt-5-nano
            'reasoning': get_smolagents_model("reasoning"), # gpt-5
            'precision': get_smolagents_model("precision")  # gpt-5-mini
        }
        
        # Agentes especializados
        self.agents = {
            'classifier': CodeAgent(
                tools=[analyze_input_structure, extract_minimal_info_for_lookup],
                model=self.models['fast'],
                name="input_classifier",
                max_steps=5
            ),
            
            'content_extractor': CodeAgent(
                tools=[extract_oficio_content],
                model=self.models['fast'],
                name="content_extractor",
                max_steps=5
            ),
            
            'party_extractor': CodeAgent(
                tools=[extract_all_investigated_parties, validate_cpf, validate_cnpj],
                model=self.models['precision'],
                name="party_extractor",
                max_steps=10
            ),
            
            'subsidy_matcher': CodeAgent(
                tools=[extract_and_match_subsidies],
                model=self.models['fast'],
                name="subsidy_matcher",
                max_steps=15
            ),
            
            'date_extractor': CodeAgent(
                tools=[extract_all_dates, extract_period_from_text],
                model=self.models['fast'],
                name="date_extractor",
                max_steps=10
            )
        }
        
        # Manager agent que coordena tudo
        managed_agents = [
            ManagedAgent(agent, name=name, description=f"Agent for {name}")
            for name, agent in self.agents.items()
        ]
        
        self.manager = CodeAgent(
            model=self.models['reasoning'],
            managed_agents=managed_agents,
            planning_interval=3,
            max_steps=30,
            name="warrant_manager"
        )
        
        self.catalog_path = catalog_path
    
    def process(self, input_text: str) -> dict:
        """
        Processa um texto de entrada completo
        """
        try:
            # Log inicial
            logger.info(f"Iniciando processamento de warrant")
            
            # Executa pipeline
            prompt = f"""
            Processe o seguinte texto que pode conter:
            1. Um ofício judicial completo
            2. Uma cadeia de emails sobre um ofício
            3. Fragmentos de informação sobre um ofício
            4. Uma reiteração de ofício anterior
            
            Identifique:
            - Tipo de conteúdo e se é primeiro ofício ou reiteração
            - Todos os investigados (sem limite de quantidade)
            - Todos os subsídios solicitados (comparando com catálogo em {self.catalog_path})
            - Todas as datas/períodos mencionados
            - Se há informação suficiente ou se precisa consultar sistema interno
            
            Texto:
            {input_text}
            """
            
            result = self.manager.run(prompt)
            
            # Parse e estrutura resultado
            return self._structure_result(result)
            
        except Exception as e:
            logger.error(f"Erro no processamento: {str(e)}")
            return {
                "status": "ERRO",
                "error": str(e),
                "requires_manual": True
            }
    
    def _structure_result(self, raw_result):
        """
        Estrutura o resultado bruto em formato padronizado
        """
        # Implementação específica dependendo do formato de saída do manager
        # Este é um exemplo simplificado
        return {
            "status": "PROCESSADO",
            "data": raw_result,
            "timestamp": datetime.now().isoformat()
        }

# Uso
if __name__ == "__main__":
    processor = MultiAgentWarrantProcessor(
        catalog_path="subsidios_catalog.csv"
    )
    
    # Exemplo de texto misto (email + ofício)
    input_text = """
    De: juridico@bancox.com.br
    Para: compliance@bancox.com.br
    Assunto: FW: Ofício Judicial - URGENTE
    
    Segue ofício recebido hoje.
    
    ---
    
    PODER JUDICIÁRIO
    1ª VARA CRIMINAL DE SÃO PAULO
    
    OFÍCIO Nº 1234/2024
    
    Processo nº 1234567-89.2024.8.26.0001
    
    DETERMINO a quebra de sigilo bancário de:
    
    1. JOÃO SILVA SANTOS, CPF 123.456.789-00
    2. MARIA OLIVEIRA, CPF 987.654.321-00  
    3. EMPRESA ABC LTDA, CNPJ 12.345.678/0001-90
    
    Período: janeiro de 2023 a dezembro de 2023
    
    Solicito o fornecimento de:
    - Extratos de conta corrente
    - Extratos de investimentos
    - Relação de cartões de crédito
    
    Prazo: 10 dias
    """
    
    result = processor.process(input_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))