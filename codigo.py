import pandas as pd
from collections import defaultdict

def ler_colunas_excel(caminho_arquivo: str) -> list:
“”“Lê o Excel e retorna a lista de colunas disponíveis.”””
df = pd.read_excel(caminho_arquivo)
return df.columns.tolist()

def exibir_colunas(colunas: list, colunas_principais: list) -> None:
“”“Exibe as colunas disponíveis para seleção (excluindo as principais).”””
colunas_disponiveis = [c for c in colunas if c not in colunas_principais]
print(”\n” + “=”*60)
print(“COLUNAS DISPONÍVEIS PARA ASSOCIAR:”)
print(”=”*60)
for i, col in enumerate(colunas_disponiveis, 1):
print(f”  {i}. {col}”)
print(”=”*60)
return colunas_disponiveis

def selecionar_colunas(colunas_disponiveis: list, nivel: str) -> list:
“”“Permite ao usuário selecionar colunas para um nível específico.”””
print(f”\nSelecione as colunas que pertencem ao nível ‘{nivel}’”)
print(“Digite os números separados por vírgula (ex: 1,3,5) ou ‘enter’ para pular:”)

```
entrada = input("> ").strip()

if not entrada:
    return []

try:
    indices = [int(x.strip()) - 1 for x in entrada.split(",")]
    selecionadas = [colunas_disponiveis[i] for i in indices if 0 <= i < len(colunas_disponiveis)]
    print(f"  → Selecionadas para {nivel}: {selecionadas}")
    return selecionadas
except (ValueError, IndexError):
    print("  → Entrada inválida. Nenhuma coluna selecionada.")
    return []
```

def formatar_valor(coluna: str, valor) -> str:
“”“Formata um par coluna:valor para a string final.”””
if pd.isna(valor):
return f”{coluna}: N/A”
return f”{coluna}: {valor}”

def agregar_dados(df: pd.DataFrame,
colunas_pj: list,
colunas_cpf: list,
colunas_subsidio: list) -> dict:
“””
Agrega os dados do DataFrame em estrutura hierárquica.
Retorna um dicionário com as strings agregadas por numero_pj.
“””
resultado = defaultdict(lambda: {
‘info_pj’: ‘’,
‘cpfs’: defaultdict(lambda: {
‘info_cpf’: ‘’,
‘subsidios’: []
})
})

```
# Agrupa por numero_pj
for numero_pj, grupo_pj in df.groupby('numero_pj'):
    # Pega informações do PJ (primeira linha, pois são iguais)
    primeira_linha_pj = grupo_pj.iloc[0]
    info_pj_parts = [formatar_valor(col, primeira_linha_pj[col]) for col in colunas_pj]
    resultado[numero_pj]['info_pj'] = "; ".join(info_pj_parts) if info_pj_parts else ""
    
    # Agrupa por CPF dentro do PJ
    for cpf, grupo_cpf in grupo_pj.groupby('cpf'):
        # Pega informações do CPF (primeira linha do grupo CPF)
        primeira_linha_cpf = grupo_cpf.iloc[0]
        info_cpf_parts = [formatar_valor(col, primeira_linha_cpf[col]) for col in colunas_cpf]
        resultado[numero_pj]['cpfs'][cpf]['info_cpf'] = "; ".join(info_cpf_parts) if info_cpf_parts else ""
        
        # Itera por cada subsídio
        for _, linha in grupo_cpf.iterrows():
            id_subsidio = linha['id_subsidio']
            info_subsidio_parts = [formatar_valor('id_subsidio', id_subsidio)]
            info_subsidio_parts.extend([formatar_valor(col, linha[col]) for col in colunas_subsidio])
            resultado[numero_pj]['cpfs'][cpf]['subsidios'].append("; ".join(info_subsidio_parts))

return resultado
```

def gerar_string_final(dados_agregados: dict) -> dict:
“””
Gera a string final formatada para cada numero_pj.
Retorna um dicionário {numero_pj: string_concatenada}
“””
strings_finais = {}

```
for numero_pj, dados_pj in dados_agregados.items():
    partes = []
    
    # Adiciona info do PJ
    partes.append(f"numero_pj: {numero_pj}")
    if dados_pj['info_pj']:
        partes.append(dados_pj['info_pj'])
    
    # Adiciona cada CPF e seus subsídios
    for cpf, dados_cpf in dados_pj['cpfs'].items():
        partes.append(f"cpf: {cpf}")
        if dados_cpf['info_cpf']:
            partes.append(dados_cpf['info_cpf'])
        
        # Adiciona cada subsídio
        for subsidio_str in dados_cpf['subsidios']:
            partes.append(f"[{subsidio_str}]")
    
    strings_finais[numero_pj] = "; ".join(partes)

return strings_finais
```

def salvar_resultado(strings_finais: dict, caminho_saida: str) -> None:
“”“Salva o resultado em um arquivo CSV ou TXT.”””
# Cria DataFrame com resultado
df_resultado = pd.DataFrame([
{‘numero_pj’: pj, ‘string_agregada’: string}
for pj, string in strings_finais.items()
])

```
# Salva como CSV
df_resultado.to_csv(caminho_saida, index=False, sep=';', encoding='utf-8-sig')
print(f"\n✓ Resultado salvo em: {caminho_saida}")
```

def processar_excel(caminho_arquivo: str, caminho_saida: str = None, modo_interativo: bool = True):
“””
Função principal que processa o Excel.

```
Args:
    caminho_arquivo: Caminho do arquivo Excel de entrada
    caminho_saida: Caminho do arquivo de saída (opcional)
    modo_interativo: Se True, pergunta ao usuário quais colunas associar
"""
# Colunas principais (chaves de agrupamento)
colunas_principais = ['numero_pj', 'cpf', 'id_subsidio']

print("\n" + "="*60)
print("AGREGADOR DE DADOS EXCEL")
print("="*60)

# Lê o Excel
print(f"\nLendo arquivo: {caminho_arquivo}")
df = pd.read_excel(caminho_arquivo)
print(f"✓ {len(df)} linhas encontradas")
print(f"✓ {len(df.columns)} colunas encontradas")

# Verifica se as colunas principais existem
for col in colunas_principais:
    if col not in df.columns:
        raise ValueError(f"Coluna obrigatória '{col}' não encontrada no Excel!")

# Exibe e seleciona colunas
colunas_disponiveis = exibir_colunas(df.columns.tolist(), colunas_principais)

if modo_interativo:
    print("\n" + "-"*60)
    print("ASSOCIAÇÃO DE COLUNAS")
    print("-"*60)
    print("Associe cada coluna ao nível hierárquico correspondente:")
    print("  • PJ: colunas com info igual para todo numero_pj")
    print("  • CPF: colunas com info igual para cada cpf dentro do PJ")
    print("  • SUBSÍDIO: colunas que mudam para cada id_subsidio")
    print("-"*60)
    
    colunas_pj = selecionar_colunas(colunas_disponiveis.copy(), "NUMERO_PJ")
    
    # Remove as já selecionadas
    colunas_restantes = [c for c in colunas_disponiveis if c not in colunas_pj]
    colunas_cpf = selecionar_colunas(colunas_restantes.copy(), "CPF")
    
    # Remove as já selecionadas
    colunas_restantes = [c for c in colunas_restantes if c not in colunas_cpf]
    colunas_subsidio = selecionar_colunas(colunas_restantes.copy(), "ID_SUBSIDIO")
else:
    # Modo não interativo: todas as colunas vão para subsídio
    colunas_pj = []
    colunas_cpf = []
    colunas_subsidio = colunas_disponiveis

# Processa os dados
print("\n" + "-"*60)
print("PROCESSANDO DADOS...")
print("-"*60)

dados_agregados = agregar_dados(df, colunas_pj, colunas_cpf, colunas_subsidio)
strings_finais = gerar_string_final(dados_agregados)

print(f"✓ {len(strings_finais)} grupos (numero_pj) processados")

# Mostra preview
print("\n" + "-"*60)
print("PREVIEW (primeiros 2 registros):")
print("-"*60)
for i, (pj, string) in enumerate(list(strings_finais.items())[:2]):
    print(f"\nPJ {pj}:")
    print(f"  {string[:500]}{'...' if len(string) > 500 else ''}")

# Salva resultado
if caminho_saida is None:
    caminho_saida = caminho_arquivo.replace('.xlsx', '_agregado.csv').replace('.xls', '_agregado.csv')

salvar_resultado(strings_finais, caminho_saida)

return strings_finais
```

# ============================================================

# CONFIGURAÇÃO - ALTERE AQUI

# ============================================================

if **name** == “**main**”:
# Caminho do seu arquivo Excel
ARQUIVO_ENTRADA = “seu_arquivo.xlsx”  # <– ALTERE AQUI

```
# Caminho do arquivo de saída (opcional)
ARQUIVO_SAIDA = "resultado_agregado.csv"  # <-- ALTERE AQUI

# Modo interativo (True = pergunta quais colunas, False = automático)
MODO_INTERATIVO = True

try:
    resultado = processar_excel(
        caminho_arquivo=ARQUIVO_ENTRADA,
        caminho_saida=ARQUIVO_SAIDA,
        modo_interativo=MODO_INTERATIVO
    )
    print("\n✓ Processamento concluído com sucesso!")
    
except FileNotFoundError:
    print(f"\n✗ Erro: Arquivo '{ARQUIVO_ENTRADA}' não encontrado!")
    print("  Verifique o caminho e tente novamente.")
    
except Exception as e:
    print(f"\n✗ Erro durante o processamento: {e}")
```