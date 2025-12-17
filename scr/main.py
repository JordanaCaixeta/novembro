# main.py
"""
Pipeline principal para processamento de oficios a partir de CSV
Entrada: CSV separado por ; com coluna txt_arqu_juri contendo o texto do oficio
"""

import pandas as pd
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from scr.modulos.orquestrador import WarrantOrchestrator, WarrantProcessingResult
from scr.modulos.consulta_DI4 import consultar_subsidios_di4, DI4ConsultaResult

# Configuracao de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def carregar_csv_oficios(csv_path: str, separator: str = ';') -> pd.DataFrame:
    """
    Carrega CSV com oficios para processamento

    Args:
        csv_path: Caminho para o arquivo CSV
        separator: Separador do CSV (padrao: ;)

    Returns:
        DataFrame com os oficios
    """
    logger.info(f"Carregando CSV: {csv_path}")

    df = pd.read_csv(csv_path, sep=separator, encoding='utf-8')

    # Valida coluna obrigatoria
    if 'txt_arqu_juri' not in df.columns:
        raise ValueError("CSV deve conter coluna 'txt_arqu_juri' com o texto do oficio")

    logger.info(f"Carregados {len(df)} oficios do CSV")
    return df


def processar_oficio(
    texto_oficio: str,
    catalog_path: str,
    consultar_di4: bool = True
) -> Dict[str, Any]:
    """
    Processa um unico oficio

    Args:
        texto_oficio: Texto do oficio (coluna txt_arqu_juri)
        catalog_path: Caminho para catalogo de subsidios
        consultar_di4: Se deve consultar base DI4 (padrao: True)

    Returns:
        Dicionario com resultado do processamento
    """
    resultado = {
        "timestamp": datetime.now().isoformat(),
        "status": "PROCESSANDO",
        "extracoes": None,
        "subsidios_di4": None,
        "alertas": []
    }

    try:
        # PASSO 1: Processa com orquestrador
        orchestrator = WarrantOrchestrator(catalog_path)
        processamento = orchestrator.process_warrant(texto_oficio)

        resultado["extracoes"] = {
            "session_id": processamento.session_id,
            "tipo_oficio": processamento.tipo_oficio,
            "deve_processar": processamento.deve_processar,
            "investigados": [inv.model_dump() for inv in processamento.investigados],
            "subsidios": [sub.model_dump() for sub in processamento.subsidios],
            "periodos": processamento.periodos,
            "confidence_geral": processamento.confidence_geral,
            "alertas": processamento.alertas
        }

        # PASSO 2: Consulta DI4 para cada CPF/CNPJ extraido (se habilitado)
        if consultar_di4 and processamento.investigados:
            cpfs_cnpjs = []
            for inv in processamento.investigados:
                if inv.cpf:
                    cpfs_cnpjs.append(inv.cpf)
                if inv.cnpj:
                    cpfs_cnpjs.append(inv.cnpj)

            if cpfs_cnpjs:
                resultado["subsidios_di4"] = []
                for doc in cpfs_cnpjs:
                    try:
                        di4_result = consultar_subsidios_di4(doc)
                        resultado["subsidios_di4"].append(di4_result.model_dump())
                    except Exception as e:
                        logger.warning(f"Erro ao consultar DI4 para {doc}: {e}")
                        resultado["alertas"].append(f"Erro consulta DI4 para {doc}: {str(e)}")

        # Define status final
        if processamento.deve_processar:
            resultado["status"] = "PROCESSADO"
        else:
            resultado["status"] = "NAO_PROCESSAVEL"
            resultado["alertas"].extend(processamento.alertas)

    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        resultado["status"] = "ERRO"
        resultado["alertas"].append(f"Erro critico: {str(e)}")

    return resultado


def processar_csv_completo(
    csv_path: str,
    catalog_path: str,
    output_path: Optional[str] = None,
    consultar_di4: bool = True
) -> List[Dict[str, Any]]:
    """
    Processa todos os oficios de um CSV

    Args:
        csv_path: Caminho para CSV de entrada
        catalog_path: Caminho para catalogo de subsidios
        output_path: Caminho para salvar resultados (opcional)
        consultar_di4: Se deve consultar base DI4

    Returns:
        Lista com resultados de cada oficio
    """
    # Carrega CSV
    df = carregar_csv_oficios(csv_path)

    resultados = []
    total = len(df)

    for idx, row in df.iterrows():
        logger.info(f"Processando oficio {idx + 1}/{total}")

        texto_oficio = row['txt_arqu_juri']

        # Pula linhas vazias
        if pd.isna(texto_oficio) or not str(texto_oficio).strip():
            logger.warning(f"Linha {idx + 1}: texto vazio, pulando...")
            resultados.append({
                "linha": idx + 1,
                "status": "VAZIO",
                "extracoes": None
            })
            continue

        # Processa oficio
        resultado = processar_oficio(
            texto_oficio=str(texto_oficio),
            catalog_path=catalog_path,
            consultar_di4=consultar_di4
        )
        resultado["linha"] = idx + 1

        # Adiciona outras colunas do CSV se existirem
        for col in df.columns:
            if col != 'txt_arqu_juri':
                resultado[f"csv_{col}"] = row[col] if not pd.isna(row[col]) else None

        resultados.append(resultado)

    # Salva resultados se output_path fornecido
    if output_path:
        logger.info(f"Salvando resultados em: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)

    # Estatisticas finais
    processados = sum(1 for r in resultados if r.get("status") == "PROCESSADO")
    erros = sum(1 for r in resultados if r.get("status") == "ERRO")
    vazios = sum(1 for r in resultados if r.get("status") == "VAZIO")

    logger.info(f"Processamento concluido: {processados} processados, {erros} erros, {vazios} vazios")

    return resultados


# Exemplo de uso
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Processa oficios de quebra de sigilo')
    parser.add_argument('--csv', type=str, required=True, help='Caminho para CSV de entrada (separador ;)')
    parser.add_argument('--catalog', type=str, default='data/subsidios_catalog.csv', help='Caminho para catalogo de subsidios')
    parser.add_argument('--output', type=str, help='Caminho para salvar resultados JSON')
    parser.add_argument('--no-di4', action='store_true', help='Desabilita consulta DI4')

    args = parser.parse_args()

    resultados = processar_csv_completo(
        csv_path=args.csv,
        catalog_path=args.catalog,
        output_path=args.output,
        consultar_di4=not args.no_di4
    )

    print(f"\nTotal processados: {len(resultados)}")
