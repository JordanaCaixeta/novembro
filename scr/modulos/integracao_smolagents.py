# 8. Integracao com Smolagents - Configuracao Completa
# Usando apenas OpenAI 5 (o5) como modelo

from smolagents import CodeAgent, ManagedAgent, LiteLLMModel
from datetime import datetime
import logging
import json
import os

# Importa tools
from scr.modulos.datamanagement import analyze_input_structure, extract_minimal_info_for_lookup, extract_oficio_content
from scr.modulos.extract_envolvidos import extract_all_investigated_parties
from scr.modulos.extract_subsidios import extract_and_match_subsidies
from scr.modulos.datas_management import extract_all_dates, extract_period_from_text

# Configuracao de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_openai_model():
    """
    Retorna modelo OpenAI 5 configurado
    """
    model_id = os.getenv("OPENAI_MODEL", "o4-mini")  # OpenAI 5
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        return LiteLLMModel(model_id=model_id, api_key=api_key)
    else:
        return LiteLLMModel(model_id=model_id)


class MultiAgentWarrantProcessor:
    def __init__(self, catalog_path: str):

        # Configuracao de modelo - APENAS OpenAI 5
        self.model = get_openai_model()

        # Agentes especializados - todos usando OpenAI 5
        self.agents = {
            'classifier': CodeAgent(
                tools=[analyze_input_structure, extract_minimal_info_for_lookup],
                model=self.model,
                name="input_classifier",
                max_steps=5
            ),

            'content_extractor': CodeAgent(
                tools=[extract_oficio_content],
                model=self.model,
                name="content_extractor",
                max_steps=5
            ),

            'party_extractor': CodeAgent(
                tools=[extract_all_investigated_parties],
                model=self.model,
                name="party_extractor",
                max_steps=10
            ),

            'subsidy_matcher': CodeAgent(
                tools=[extract_and_match_subsidies],
                model=self.model,
                name="subsidy_matcher",
                max_steps=15
            ),

            'date_extractor': CodeAgent(
                tools=[extract_all_dates, extract_period_from_text],
                model=self.model,
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
            model=self.model,
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
            1. Um oficio judicial completo
            2. Uma cadeia de emails sobre um oficio
            3. Fragmentos de informacao sobre um oficio
            4. Uma reiteracao de oficio anterior

            Identifique:
            - Tipo de conteudo e se e primeiro oficio ou reiteracao
            - Todos os investigados (sem limite de quantidade)
            - Todos os subsidios solicitados (comparando com catalogo em {self.catalog_path})
            - Todas as datas/periodos mencionados
            - Se ha informacao suficiente ou se precisa consultar sistema interno

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
        # Implementacao especifica dependendo do formato de saida do manager
        # Este e um exemplo simplificado
        return {
            "status": "PROCESSADO",
            "data": raw_result,
            "timestamp": datetime.now().isoformat()
        }


# Uso
if __name__ == "__main__":
    processor = MultiAgentWarrantProcessor(
        catalog_path="data/subsidios_catalog.csv"
    )

    # Exemplo de texto misto (email + oficio)
    input_text = """
    De: juridico@bancox.com.br
    Para: compliance@bancox.com.br
    Assunto: FW: Oficio Judicial - URGENTE

    Segue oficio recebido hoje.

    ---

    PODER JUDICIARIO
    1 VARA CRIMINAL DE SAO PAULO

    OFICIO No 1234/2024

    Processo no 1234567-89.2024.8.26.0001

    DETERMINO a quebra de sigilo bancario de:

    1. JOAO SILVA SANTOS, CPF 123.456.789-00
    2. MARIA OLIVEIRA, CPF 987.654.321-00
    3. EMPRESA ABC LTDA, CNPJ 12.345.678/0001-90

    Periodo: janeiro de 2023 a dezembro de 2023

    Solicito o fornecimento de:
    - Extratos de conta corrente
    - Extratos de investimentos
    - Relacao de cartoes de credito

    Prazo: 10 dias
    """

    result = processor.process(input_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))
