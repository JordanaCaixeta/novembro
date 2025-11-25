# config.py
"""Configurações do sistema de processamento de ofícios"""
import os
from dataclasses import dataclass
from typing import Literal

# =============================================================================
# CONFIGURAÇÃO DE MODELOS OPENAI - BANCO X
# =============================================================================

MODEL_CONFIG = {
    'fast': 'gpt-5-nano',        # Modelo rápido para tarefas simples
    'reasoning': 'gpt-5',         # Modelo para raciocínio complexo
    'precision': 'gpt-5-mini'     # Modelo para tarefas de precisão
}

# Alias para compatibilidade com código legado
MODELS_CONFIG = MODEL_CONFIG


# =============================================================================
# CONFIGURAÇÃO DO AMBIENTE BANCO X (IaraGenAI)
# =============================================================================

@dataclass
class BancoXConfig:
    """Configuração do ambiente Banco X"""
    client_id: str
    client_secret: str
    environment: Literal["dev", "hml", "prod"] = "dev"
    provider: str = "azure_openai"

    @classmethod
    def from_env(cls) -> "BancoXConfig":
        """Cria configuração a partir de variáveis de ambiente"""
        return cls(
            client_id=os.getenv("BANCO_X_CLIENT_ID", ""),
            client_secret=os.getenv("BANCO_X_CLIENT_SECRET", ""),
            environment=os.getenv("BANCO_X_ENVIRONMENT", "dev"),
            provider=os.getenv("BANCO_X_PROVIDER", "azure_openai")
        )


def get_model(model_type: Literal["fast", "reasoning", "precision"]) -> str:
    """
    Retorna o nome do modelo baseado no tipo solicitado.

    Args:
        model_type: Tipo do modelo ('fast', 'reasoning', 'precision')

    Returns:
        Nome do modelo OpenAI configurado
    """
    return MODEL_CONFIG.get(model_type, MODEL_CONFIG['fast'])


# =============================================================================
# THRESHOLDS E CONFIGURAÇÕES GERAIS
# =============================================================================

THRESHOLDS = {
    'auto_process': 0.75,
    'human_review': 0.50,
    'subsidy_match': 0.75
}

PATHS = {
    'catalog': 'data/subsidios_catalog.csv',
    'logs': 'logs/',
    'output': 'output/'
}

DATABASE_CONFIG = {
    'api_url': os.getenv("DATABASE_API_URL", ""),
    'api_key': os.getenv("DATABASE_API_KEY", "")
}

# Chave OpenAI (não requer chave real no ambiente Banco X)
os.environ.setdefault("OPEN_AI_KEY", "sk-no-key-required")