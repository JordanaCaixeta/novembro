# consulta_DI4.py
"""
Consulta de subsidios na base DI4 via Athena
Consulta por num_cpf_cnpj (tanto CPF quanto CNPJ no mesmo campo)
"""

import logging
import os
from typing import List, Optional
from pydantic import BaseModel
from smolagents import tool

logger = logging.getLogger(__name__)


class SubsidioDI4(BaseModel):
    """Subsidio retornado da base DI4"""
    cod_tipo_ctud: str
    des_tipo_info_ctud: str
    nom_prso_gest: Optional[str] = None
    flag_iu_docs_split: Optional[str] = None
    versao_di4: Optional[str] = None


class DI4ConsultaResult(BaseModel):
    """Resultado da consulta DI4"""
    num_cpf_cnpj: str
    encontrado: bool
    subsidios: List[SubsidioDI4]
    total_subsidios: int
    erro: Optional[str] = None


def _executar_query_athena(query: str) -> List[dict]:
    """
    Executa query no Athena e retorna resultados

    Args:
        query: Query SQL para executar

    Returns:
        Lista de dicionarios com resultados
    """
    import boto3

    # Configuracoes do Athena (via variaveis de ambiente)
    database = os.getenv("ATHENA_DATABASE", "database_di4")
    output_location = os.getenv("ATHENA_OUTPUT_LOCATION", "s3://athena-results/")
    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        athena_client = boto3.client('athena', region_name=region)

        # Inicia execucao da query
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': database},
            ResultConfiguration={'OutputLocation': output_location}
        )

        query_execution_id = response['QueryExecutionId']
        logger.info(f"Query iniciada: {query_execution_id}")

        # Aguarda conclusao
        import time
        while True:
            status_response = athena_client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            status = status_response['QueryExecution']['Status']['State']

            if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break
            time.sleep(0.5)

        if status != 'SUCCEEDED':
            error_msg = status_response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
            raise Exception(f"Query falhou: {error_msg}")

        # Obtem resultados
        results = athena_client.get_query_results(
            QueryExecutionId=query_execution_id
        )

        # Converte para lista de dicionarios
        columns = [col['Name'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
        rows = results['ResultSet']['Rows'][1:]  # Pula header

        data = []
        for row in rows:
            values = [cell.get('VarCharValue', '') for cell in row['Data']]
            data.append(dict(zip(columns, values)))

        return data

    except Exception as e:
        logger.error(f"Erro ao executar query Athena: {e}")
        raise


@tool
def consultar_subsidios_di4(num_cpf_cnpj: str) -> DI4ConsultaResult:
    """
    Consulta subsidios disponveis na base DI4 para um CPF ou CNPJ

    Args:
        num_cpf_cnpj: CPF ou CNPJ para consulta (com ou sem formatacao)

    Returns:
        DI4ConsultaResult com subsidios encontrados
    """
    logger.info(f"Consultando DI4 para: {num_cpf_cnpj}")

    # Limpa formatacao
    cpf_cnpj_limpo = num_cpf_cnpj.replace(".", "").replace("-", "").replace("/", "")

    try:
        # Query para buscar subsidios por CPF/CNPJ
        query = f"""
        SELECT
            cod_tipo_ctud,
            des_tipo_info_ctud,
            nom_prso_gest,
            flag_iu_docs_split,
            versao_di4
        FROM tb_subsidios_di4
        WHERE num_cpf_cnpj = '{cpf_cnpj_limpo}'
        """

        resultados = _executar_query_athena(query)

        if not resultados:
            logger.info(f"Nenhum subsidio encontrado para {cpf_cnpj_limpo}")
            return DI4ConsultaResult(
                num_cpf_cnpj=num_cpf_cnpj,
                encontrado=False,
                subsidios=[],
                total_subsidios=0
            )

        # Converte para modelo
        subsidios = []
        for row in resultados:
            subsidios.append(SubsidioDI4(
                cod_tipo_ctud=row.get('cod_tipo_ctud', ''),
                des_tipo_info_ctud=row.get('des_tipo_info_ctud', ''),
                nom_prso_gest=row.get('nom_prso_gest'),
                flag_iu_docs_split=row.get('flag_iu_docs_split'),
                versao_di4=row.get('versao_di4')
            ))

        logger.info(f"Encontrados {len(subsidios)} subsidios para {cpf_cnpj_limpo}")

        return DI4ConsultaResult(
            num_cpf_cnpj=num_cpf_cnpj,
            encontrado=True,
            subsidios=subsidios,
            total_subsidios=len(subsidios)
        )

    except Exception as e:
        logger.error(f"Erro na consulta DI4: {e}")
        return DI4ConsultaResult(
            num_cpf_cnpj=num_cpf_cnpj,
            encontrado=False,
            subsidios=[],
            total_subsidios=0,
            erro=str(e)
        )


# ============================================================================
# FUNCAO PARA VALIDACAO FUTURA - CONFERIR SUBSIDIOS EXTRAIDOS COM DI4
# ============================================================================
# TODO: Ativar quando tiver o id de referencia para associar aos subsidios
# achados no texto do oficio
#
# def validar_subsidios_com_di4(
#     subsidios_extraidos: List[dict],
#     cpf_cnpj: str
# ) -> dict:
#     """
#     Valida subsidios extraidos do oficio contra a base DI4
#
#     Args:
#         subsidios_extraidos: Lista de subsidios extraidos do texto do oficio
#         cpf_cnpj: CPF ou CNPJ do investigado
#
#     Returns:
#         Dicionario com validacao:
#         - subsidios_validos: subsidios que existem na base DI4
#         - subsidios_nao_encontrados: subsidios que nao foram encontrados
#         - match_por_id: mapping de subsidio_id do oficio para cod_tipo_ctud DI4
#     """
#     # Consulta DI4
#     di4_result = consultar_subsidios_di4(cpf_cnpj)
#
#     if not di4_result.encontrado:
#         return {
#             "cpf_cnpj": cpf_cnpj,
#             "di4_disponivel": False,
#             "subsidios_validos": [],
#             "subsidios_nao_encontrados": subsidios_extraidos,
#             "match_por_id": {},
#             "alertas": ["CPF/CNPJ nao encontrado na base DI4"]
#         }
#
#     # Cria set de cod_tipo_ctud disponiveis no DI4
#     codigos_di4 = {s.cod_tipo_ctud for s in di4_result.subsidios}
#     descricoes_di4 = {s.des_tipo_info_ctud.lower() for s in di4_result.subsidios}
#
#     subsidios_validos = []
#     subsidios_nao_encontrados = []
#     match_por_id = {}
#
#     for sub in subsidios_extraidos:
#         # TODO: Implementar logica de matching quando tiver o id de referencia
#         # Opcoes de matching:
#         # 1. Por codigo direto (subsidio_id == cod_tipo_ctud)
#         # 2. Por descricao (fuzzy match com des_tipo_info_ctud)
#         # 3. Por mapeamento pre-definido
#
#         sub_nome = sub.get('nome_subsidio', '').lower()
#         sub_id = sub.get('subsidio_id', '')
#
#         # Verifica match por descricao (simplificado)
#         matched = False
#         for di4_sub in di4_result.subsidios:
#             if sub_nome in di4_sub.des_tipo_info_ctud.lower():
#                 subsidios_validos.append(sub)
#                 match_por_id[sub_id] = di4_sub.cod_tipo_ctud
#                 matched = True
#                 break
#
#         if not matched:
#             subsidios_nao_encontrados.append(sub)
#
#     return {
#         "cpf_cnpj": cpf_cnpj,
#         "di4_disponivel": True,
#         "subsidios_validos": subsidios_validos,
#         "subsidios_nao_encontrados": subsidios_nao_encontrados,
#         "match_por_id": match_por_id,
#         "total_di4": di4_result.total_subsidios,
#         "alertas": []
#     }
# ============================================================================
