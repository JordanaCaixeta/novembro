# config.py
"""Configuracoes do sistema de processamento de oficios"""

# Configuracao de modelos - APENAS OpenAI 5 (o5)
MODELS_CONFIG = {
    'default': 'o4-mini',  # OpenAI 5 / o5 - modelo padrao para todas as tarefas
}

# Thresholds de confidence para decisoes automaticas
THRESHOLDS = {
    'auto_process': 0.75,      # Confidence minima para processamento automatico
    'human_review': 0.50,      # Abaixo disso, requer revisao humana
    'subsidy_match': 0.75      # Threshold para match de subsidios
}

# Caminhos padrao
PATHS = {
    'catalog': 'data/subsidios_catalog.csv',
    'logs': 'logs/',
    'output': 'output/'
}

# Configuracoes de banco de dados / APIs
DATABASE_CONFIG = {
    # Athena (DI4)
    'athena_database': 'database_di4',
    'athena_output_location': 's3://athena-results/',
    'aws_region': 'us-east-1',
}

# Configuracoes OpenAI
OPENAI_CONFIG = {
    'model': 'o4-mini',  # OpenAI 5
    'max_tokens': 4096,
    'temperature': 0.1,  # Baixa temperatura para maior precisao
}
