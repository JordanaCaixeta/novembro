# config.py
"""Configurações do sistema de processamento de ofícios"""

MODELS_CONFIG = {
    'fast': 'Qwen/Qwen2.5-Coder-32B-Instruct',
    'reasoning': 'deepseek-ai/DeepSeek-R1',
    'precision': 'gpt-4o'
}

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
    'api_url': 'xxx',
    'api_key': 'xx'
}