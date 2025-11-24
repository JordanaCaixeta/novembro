# database_integration.py - NOVO MÓDULO

import requests
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class SubsidioDatabase(BaseModel):
    """Modelo para subsídio retornado da base"""
    subsidio_id: str
    nome: str
    existe_base: bool
    cpf_cnpj_associado: str
    data_cadastro: Optional[str] = None

class DatabaseValidationResult(BaseModel):
    """Resultado da validação contra a base de dados"""
    investigado_cpf_cnpj: str
    investigado_existe: bool
    subsidios_validados: List[Dict]
    total_encontrados: int
    total_sem_id: int

class DatabaseIntegration:
    def __init__(self, api_url: str, api_key: str = None):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({'Authorization': f'Bearer {api_key}'})
    
    def validate_subsidios(
        self,
        cpf_cnpj_list: List[str],
        subsidios_extraidos: List[Dict]
    ) -> List[DatabaseValidationResult]:
        """
        Valida subsídios extraídos contra a base de dados
        """
        results = []
        
        for cpf_cnpj in cpf_cnpj_list:
            # Consulta a base para este CPF/CNPJ
            db_response = self._query_database(cpf_cnpj)
            
            if not db_response['success']:
                logger.error(f"Falha ao consultar base para {cpf_cnpj}")
                continue
            
            # Valida cada subsídio extraído
            subsidios_validados = []
            total_sem_id = 0
            
            for subsidio in subsidios_extraidos:
                validated = self._validate_single_subsidio(
                    subsidio,
                    cpf_cnpj,
                    db_response['data']
                )
                
                if validated['database_id'] == 'sem_id':
                    total_sem_id += 1
                
                subsidios_validados.append(validated)
            
            results.append(DatabaseValidationResult(
                investigado_cpf_cnpj=cpf_cnpj,
                investigado_existe=db_response['data']['cliente_existe'],
                subsidios_validados=subsidios_validados,
                total_encontrados=len(subsidios_validados) - total_sem_id,
                total_sem_id=total_sem_id
            ))
        
        return results
    
    def _query_database(self, cpf_cnpj: str) -> Dict:
        """
        Consulta a base de dados via API
        """
        try:
            endpoint = f"{self.api_url}/consulta"
            params = {'documento': cpf_cnpj}
            
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return {
                'success': True,
                'data': {
                    'cliente_existe': data.get('existe', False),
                    'subsidios_disponiveis': data.get('subsidios', []),
                    'relacionamentos': data.get('relacionamentos', [])
                }
            }
            
        except requests.RequestException as e:
            logger.error(f"Erro na consulta à base: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }
    
    def _validate_single_subsidio(
        self,
        subsidio_extraido: Dict,
        cpf_cnpj: str,
        db_data: Dict
    ) -> Dict:
        """
        Valida um subsídio individual contra a base
        """
        validated = {
            'subsidio_extraido': subsidio_extraido['nome_subsidio'],
            'subsidio_id_extraido': subsidio_extraido['subsidio_id'],
            'cpf_cnpj': cpf_cnpj,
            'database_id': 'sem_id',
            'database_nome': None,
            'match_score': 0.0,
            'periodo': subsidio_extraido.get('periodo'),
            'tem_de_para': False,
            'carta_circular': None
        }
        
        if not db_data or not db_data.get('subsidios_disponiveis'):
            return validated
        
        # Busca melhor match na base
        best_match = None
        best_score = 0.0
        
        for db_subsidio in db_data['subsidios_disponiveis']:
            score = self._calculate_similarity(
                subsidio_extraido['nome_subsidio'],
                db_subsidio['nome']
            )
            
            if score > best_score and score >= 0.7:  # Threshold mínimo
                best_score = score
                best_match = db_subsidio
        
        if best_match:
            validated['database_id'] = best_match['id']
            validated['database_nome'] = best_match['nome']
            validated['match_score'] = best_score
        
        return validated
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calcula similaridade entre duas strings (simplificado)
        """
        # Implementação básica - pode ser melhorada com Levenshtein ou similar
        str1_lower = str1.lower()
        str2_lower = str2.lower()
        
        if str1_lower == str2_lower:
            return 1.0
        
        # Verifica se uma string está contida na outra
        if str1_lower in str2_lower or str2_lower in str1_lower:
            return 0.8
        
        # Calcula overlap de palavras
        words1 = set(str1_lower.split())
        words2 = set(str2_lower.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0