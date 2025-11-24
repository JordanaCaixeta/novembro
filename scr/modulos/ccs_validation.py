# Validação CCS - Customer Custody System
# Valida se CPF/CNPJ tem vínculo com Banco X e recupera relacionamentos

import logging
from typing import List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime
from smolagents import tool

logger = logging.getLogger(__name__)

class ProdutoBancario(BaseModel):
    """Produto bancário vinculado ao CPF/CNPJ"""
    tipo: Literal["conta_corrente", "poupanca", "aplicacao", "cartao_credito", "emprestimo", "consorcio", "investimento", "cambio"]
    numero_conta: Optional[str] = None
    numero_produto: str
    status: Literal["ativo", "inativo", "encerrado"]
    data_abertura: str  # ISO format YYYY-MM-DD
    data_encerramento: Optional[str] = None
    tempo_relacionamento_dias: int  # Dias desde abertura
    saldo_atual: Optional[float] = None
    observacoes: Optional[str] = None

class RelacionamentoCCS(BaseModel):
    """Tipo de relacionamento do CPF/CNPJ com o banco"""
    tipo: Literal["titular", "co_titular", "procurador", "autorizado", "responsavel_legal", "representante", "avalista"]
    produto: ProdutoBancario
    data_inicio: str  # ISO format
    data_fim: Optional[str] = None
    ativo: bool

class CCSValidationResult(BaseModel):
    """Resultado da validação CCS"""
    cpf_cnpj: str
    tem_vinculo: bool
    tipo_pessoa: Literal["PF", "PJ"]
    nome_completo: Optional[str] = None  # Nome cadastrado no CCS
    relacionamentos: List[RelacionamentoCCS]
    produtos_ativos: List[ProdutoBancario]
    total_produtos: int
    cliente_desde: Optional[str] = None  # Data do relacionamento mais antigo
    tempo_relacionamento_total_dias: int
    observacoes: List[str]
    data_consulta: str
    api_disponivel: bool  # Se a API CCS respondeu

@tool
def get_ccs_relations(cpf_cnpj: str, incluir_inativos: bool = False) -> CCSValidationResult:
    """
    Valida CPF/CNPJ no sistema CCS (Customer Custody System) do Banco X

    Args:
        cpf_cnpj: CPF ou CNPJ para validar (com ou sem formatação)
        incluir_inativos: Se deve incluir produtos inativos/encerrados

    Returns:
        CCSValidationResult com dados do relacionamento

    Raises:
        Exception: Se API CCS não estiver disponível
    """

    logger.info(f"Validando CPF/CNPJ no CCS: {cpf_cnpj}")

    # Limpa formatação
    cpf_cnpj_limpo = cpf_cnpj.replace(".", "").replace("-", "").replace("/", "")

    # TODO: IMPLEMENTAR CHAMADA REAL À API CCS
    # Exemplo de integração:
    #
    # import requests
    #
    # ccs_api_url = os.getenv("CCS_API_URL")
    # ccs_api_key = os.getenv("CCS_API_KEY")
    #
    # response = requests.post(
    #     f"{ccs_api_url}/v1/customer/validate",
    #     headers={
    #         "Authorization": f"Bearer {ccs_api_key}",
    #         "Content-Type": "application/json"
    #     },
    #     json={
    #         "cpf_cnpj": cpf_cnpj_limpo,
    #         "include_inactive": incluir_inativos
    #     },
    #     timeout=5
    # )
    #
    # if response.status_code != 200:
    #     raise Exception(f"Erro na API CCS: {response.status_code}")
    #
    # data = response.json()

    # STUB: Simula resposta da API CCS
    # Em produção, substituir por chamada real

    try:
        # Simula detecção se é cliente
        # Em produção, isso vem da API real
        tem_vinculo = _simular_validacao_ccs(cpf_cnpj_limpo)

        if not tem_vinculo:
            # Não é cliente do banco
            return CCSValidationResult(
                cpf_cnpj=cpf_cnpj,
                tem_vinculo=False,
                tipo_pessoa="PF" if len(cpf_cnpj_limpo) == 11 else "PJ",
                nome_completo=None,
                relacionamentos=[],
                produtos_ativos=[],
                total_produtos=0,
                cliente_desde=None,
                tempo_relacionamento_total_dias=0,
                observacoes=["CPF/CNPJ não possui vínculo ativo com Banco X"],
                data_consulta=datetime.now().isoformat(),
                api_disponivel=True
            )

        # Simula dados de cliente (em produção, vem da API)
        produtos_simulados = [
            ProdutoBancario(
                tipo="conta_corrente",
                numero_conta="12345-6",
                numero_produto="000012345",
                status="ativo",
                data_abertura="2020-01-15",
                tempo_relacionamento_dias=1800,
                saldo_atual=5432.10,
                observacoes="Conta corrente padrão"
            ),
            ProdutoBancario(
                tipo="cartao_credito",
                numero_produto="5555****1234",
                status="ativo",
                data_abertura="2020-03-20",
                tempo_relacionamento_dias=1735,
                observacoes="Cartão de crédito internacional"
            )
        ]

        relacionamentos_simulados = [
            RelacionamentoCCS(
                tipo="titular",
                produto=produtos_simulados[0],
                data_inicio="2020-01-15",
                ativo=True
            ),
            RelacionamentoCCS(
                tipo="titular",
                produto=produtos_simulados[1],
                data_inicio="2020-03-20",
                ativo=True
            )
        ]

        return CCSValidationResult(
            cpf_cnpj=cpf_cnpj,
            tem_vinculo=True,
            tipo_pessoa="PF" if len(cpf_cnpj_limpo) == 11 else "PJ",
            nome_completo="[NOME_DO_CCS_AQUI]",  # Em produção, vem da API
            relacionamentos=relacionamentos_simulados,
            produtos_ativos=produtos_simulados,
            total_produtos=len(produtos_simulados),
            cliente_desde="2020-01-15",
            tempo_relacionamento_total_dias=1800,
            observacoes=[
                "Cliente ativo com múltiplos produtos",
                "Relacionamento de longa data"
            ],
            data_consulta=datetime.now().isoformat(),
            api_disponivel=True
        )

    except Exception as e:
        logger.error(f"Erro ao validar CCS: {e}")

        # Fallback: Retorna resultado indicando API indisponível
        return CCSValidationResult(
            cpf_cnpj=cpf_cnpj,
            tem_vinculo=False,  # Assume não tem vínculo se API falhar
            tipo_pessoa="PF" if len(cpf_cnpj_limpo) == 11 else "PJ",
            nome_completo=None,
            relacionamentos=[],
            produtos_ativos=[],
            total_produtos=0,
            cliente_desde=None,
            tempo_relacionamento_total_dias=0,
            observacoes=[f"Erro ao consultar CCS: {str(e)}"],
            data_consulta=datetime.now().isoformat(),
            api_disponivel=False
        )

def _simular_validacao_ccs(cpf_cnpj: str) -> bool:
    """
    STUB: Simula validação no CCS

    Em produção, remover esta função completamente e usar apenas a API real.
    """

    # Simula que CPFs terminados em 00 não são clientes
    # Em produção, isso não existe - vem da API
    if cpf_cnpj.endswith("00"):
        return False

    return True

def enrich_party_with_ccs(party_data: dict, ccs_result: CCSValidationResult) -> dict:
    """
    Enriquece dados do investigado com informações do CCS

    Args:
        party_data: Dados extraídos do ofício
        ccs_result: Resultado da validação CCS

    Returns:
        dict com dados enriquecidos
    """

    enriched = party_data.copy()

    # Adiciona flag de validação CCS
    enriched["validado_ccs"] = True
    enriched["tem_vinculo_banco"] = ccs_result.tem_vinculo

    if ccs_result.tem_vinculo:
        # Enriquece com dados do CCS
        enriched["nome_ccs"] = ccs_result.nome_completo
        enriched["produtos_ativos"] = len(ccs_result.produtos_ativos)
        enriched["cliente_desde"] = ccs_result.cliente_desde
        enriched["tempo_relacionamento_dias"] = ccs_result.tempo_relacionamento_total_dias
        enriched["tipos_relacionamento"] = list(set([r.tipo for r in ccs_result.relacionamentos]))
        enriched["tipos_produtos"] = list(set([p.tipo for p in ccs_result.produtos_ativos]))
    else:
        enriched["nome_ccs"] = None
        enriched["produtos_ativos"] = 0
        enriched["alerta_ccs"] = "CPF/CNPJ não possui vínculo com Banco X"

    return enriched

def validate_all_parties_ccs(parties: List[dict], incluir_inativos: bool = False) -> List[dict]:
    """
    Valida todos os investigados no CCS e enriquece os dados

    Args:
        parties: Lista de investigados extraídos do ofício
        incluir_inativos: Se deve incluir produtos inativos

    Returns:
        Lista de investigados enriquecidos com dados do CCS
    """

    enriched_parties = []

    for party in parties:
        cpf_cnpj = party.get("cpf") or party.get("cnpj")

        if not cpf_cnpj:
            # Sem CPF/CNPJ, não pode validar
            party["validado_ccs"] = False
            party["tem_vinculo_banco"] = None
            party["alerta_ccs"] = "Sem CPF/CNPJ para validação"
            enriched_parties.append(party)
            continue

        try:
            ccs_result = get_ccs_relations(cpf_cnpj, incluir_inativos)
            enriched = enrich_party_with_ccs(party, ccs_result)
            enriched_parties.append(enriched)
        except Exception as e:
            logger.error(f"Erro ao validar {cpf_cnpj} no CCS: {e}")
            party["validado_ccs"] = False
            party["tem_vinculo_banco"] = None
            party["alerta_ccs"] = f"Erro na validação CCS: {str(e)}"
            enriched_parties.append(party)

    return enriched_parties
