# llm_client.py
"""
Cliente LLM para integração com ambiente Banco X usando IaraGenAI

Este módulo centraliza a configuração e criação de clientes LLM
para o ambiente do Banco X usando a biblioteca IaraGenAI.
"""
import os
import json
import logging
from typing import Any, Optional

import openai

from .config import BancoXConfig, get_model, MODEL_CONFIG

logger = logging.getLogger(__name__)

# Configurar chave da OpenAI (não requer chave real no ambiente Banco X)
os.environ.setdefault("OPEN_AI_KEY", "sk-no-key-required")


def _build_new_iara_client(*args, **kwargs):
    """
    Factory function para criar cliente IaraGenAI.
    Substitui o construtor padrão do openai.Client.
    """
    from iara_genai import IaraGenAI

    config = BancoXConfig.from_env()

    return IaraGenAI(
        client_id=config.client_id,
        client_secret=config.client_secret,
        environment=config.environment,
        provider=config.provider
    )


def setup_openai_client() -> None:
    """
    Configura o cliente OpenAI para usar IaraGenAI do Banco X.
    Deve ser chamado antes de usar qualquer funcionalidade de LLM.
    """
    openai.Client.__new__ = _build_new_iara_client


def get_iara_client() -> Any:
    """
    Cria e retorna uma instância do cliente IaraGenAI.

    Returns:
        Instância configurada do IaraGenAI
    """
    from iara_genai import IaraGenAI

    config = BancoXConfig.from_env()

    return IaraGenAI(
        client_id=config.client_id,
        client_secret=config.client_secret,
        environment=config.environment,
        provider=config.provider
    )


class IaraLLMModel:
    """
    Wrapper compatível com smolagents que usa IaraGenAI.
    Substitui HfApiModel e LiteLLMModel para uso no ambiente Banco X.
    """

    def __init__(self, model_type: str = "fast"):
        """
        Inicializa o modelo LLM.

        Args:
            model_type: Tipo do modelo ('fast', 'reasoning', 'precision')
                       ou nome direto do modelo (ex: 'gpt-5-nano')
        """
        # Se for um tipo conhecido, pega o modelo correspondente
        if model_type in MODEL_CONFIG:
            self.model_id = get_model(model_type)
            self.model_type = model_type
        else:
            # Assume que é o nome direto do modelo
            self.model_id = model_type
            self.model_type = "custom"

        self.client = get_iara_client()
        logger.info(f"IaraLLMModel inicializado com modelo: {self.model_id}")

    def __call__(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        Executa uma chamada de chat completion.

        Args:
            messages: Lista de mensagens no formato OpenAI
            **kwargs: Argumentos adicionais (response_format, temperature, etc.)

        Returns:
            Texto da resposta do modelo
        """
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.model_id,
                **kwargs
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Erro na chamada LLM ({self.model_id}): {e}")
            raise

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[dict] = None,
        **kwargs
    ) -> Any:
        """
        Executa chat completion e retorna resposta completa.

        Args:
            messages: Lista de mensagens
            response_format: Formato de resposta opcional
            **kwargs: Argumentos adicionais

        Returns:
            Objeto de resposta completo
        """
        request_params = {
            "messages": messages,
            "model": self.model_id,
            **kwargs
        }

        if response_format:
            request_params["response_format"] = response_format

        return self.client.chat.completions.create(**request_params)

    def chat_completion_json(
        self,
        messages: list[dict[str, str]],
        **kwargs
    ) -> dict:
        """
        Executa chat completion e retorna resposta parseada como JSON.

        Args:
            messages: Lista de mensagens
            **kwargs: Argumentos adicionais

        Returns:
            Resposta parseada como dicionário JSON
        """
        response = self.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            **kwargs
        )

        content = response.choices[0].message.content
        return json.loads(content)


class LLMClient:
    """
    Cliente wrapper para operações de LLM usando IaraGenAI.
    Fornece interface simplificada para chat completions.
    """

    def __init__(self, client: Optional[Any] = None):
        """
        Inicializa o cliente LLM.

        Args:
            client: Instância opcional do IaraGenAI. Se não fornecido,
                   cria uma nova instância.
        """
        self.client = client or get_iara_client()

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model_type: str = "fast",
        response_format: Optional[dict] = None,
        **kwargs
    ) -> Any:
        """
        Executa uma chat completion.

        Args:
            messages: Lista de mensagens no formato OpenAI
            model_type: Tipo do modelo ('fast', 'reasoning', 'precision')
            response_format: Formato de resposta opcional
            **kwargs: Argumentos adicionais para a API

        Returns:
            Resposta da API
        """
        model = get_model(model_type)

        request_params = {
            "messages": messages,
            "model": model,
            **kwargs
        }

        if response_format:
            request_params["response_format"] = response_format

        response = self.client.chat.completions.create(**request_params)
        return response

    def chat_completion_json(
        self,
        messages: list[dict[str, str]],
        model_type: str = "fast",
        **kwargs
    ) -> dict:
        """
        Executa chat completion e retorna resposta parseada como JSON.

        Args:
            messages: Lista de mensagens
            model_type: Tipo do modelo
            **kwargs: Argumentos adicionais

        Returns:
            Resposta parseada como dicionário JSON
        """
        response = self.chat_completion(
            messages=messages,
            model_type=model_type,
            response_format={"type": "json_object"},
            **kwargs
        )

        content = response.choices[0].message.content
        return json.loads(content)

    def simple_query(
        self,
        prompt: str,
        model_type: str = "fast",
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Executa uma query simples e retorna o texto da resposta.

        Args:
            prompt: Prompt do usuário
            model_type: Tipo do modelo
            system_prompt: Prompt de sistema opcional

        Returns:
            Texto da resposta
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.chat_completion(messages=messages, model_type=model_type)
        return response.choices[0].message.content


# =============================================================================
# FUNÇÕES DE CONVENIÊNCIA PARA SMOLAGENTS
# =============================================================================

def get_smolagents_model(model_type: str = "fast") -> IaraLLMModel:
    """
    Retorna um modelo compatível com smolagents usando IaraGenAI.

    Esta função substitui HfApiModel() e LiteLLMModel() do smolagents
    para usar o ambiente IaraGenAI do Banco X.

    Args:
        model_type: Tipo do modelo ('fast', 'reasoning', 'precision')

    Returns:
        IaraLLMModel configurado para uso com smolagents

    Exemplo:
        # Antes (com HfApiModel):
        model = HfApiModel("Qwen/Qwen2.5-Coder-32B-Instruct")

        # Agora (com IaraGenAI):
        model = get_smolagents_model("fast")
    """
    return IaraLLMModel(model_type=model_type)
