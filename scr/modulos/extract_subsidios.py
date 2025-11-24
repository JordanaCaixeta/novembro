# 4. Agent de Matching de Subsídios com Catálogo
# Este é um dos agentes mais críticos, que compara com o catálogo de subsídios: 

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class SubsidyMatch(BaseModel):
    subsidio_id: str
    nome_subsidio: str
    texto_original: str  # Como apareceu no ofício
    similarity_score: float
    periodo: Optional[dict] = None  # {"inicio": "01/01/2023", "fim": "31/12/2023"}
    
class SubsidiesExtraction(BaseModel):
    subsidios_solicitados: List[SubsidyMatch]
    total_subsidios: int
    subsidios_nao_identificados: List[str]

class SubsidyMatcher:
    def __init__(self, catalog_df: pd.DataFrame):
        """
        catalog_df deve ter colunas: 
        - subsidio_id
        - nome
        - descricao  
        - exemplos (lista de strings de como é pedido)
        """
        self.catalog = catalog_df
        
        # Prepara corpus para TF-IDF
        corpus = []
        self.id_mapping = []
        
        for idx, row in catalog_df.iterrows():
            # Combina nome, descrição e exemplos
            text_representation = f"{row['nome']} {row['descricao']}"
            if isinstance(row['exemplos'], list):
                text_representation += " " + " ".join(row['exemplos'])
            corpus.append(text_representation)
            self.id_mapping.append(row['subsidio_id'])
        
        # Cria vetorizador TF-IDF
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(3, 5),
            lowercase=True
        )
        self.catalog_vectors = self.vectorizer.fit_transform(corpus)
    
    def find_matches(self, requested_text: str, threshold: float = 0.75) -> List[SubsidyMatch]:
        """
        Encontra subsídios correspondentes no catálogo
        """
        # Vetoriza o texto solicitado
        request_vector = self.vectorizer.transform([requested_text])
        
        # Calcula similaridades
        similarities = cosine_similarity(request_vector, self.catalog_vectors)[0]
        
        # Encontra melhores matches
        matches = []
        for idx, score in enumerate(similarities):
            if score >= threshold:
                matches.append({
                    'subsidio_id': self.id_mapping[idx],
                    'nome_subsidio': self.catalog.iloc[idx]['nome'],
                    'similarity_score': float(score)
                })
        
        return sorted(matches, key=lambda x: x['similarity_score'], reverse=True)

@tool
def extract_and_match_subsidies(text: str, catalog_path: str) -> SubsidiesExtraction:
    """
    Extrai todos os subsídios solicitados e faz matching com catálogo
    """
    catalog_df = pd.read_csv(catalog_path)
    matcher = SubsidyMatcher(catalog_df)
    
    # Padrões para encontrar blocos de solicitação
    request_patterns = [
        r'(?:DETERMINO|SOLICITO|REQUEIRO|OFICIE-SE)(.+?)(?:\n\n|$)',
        r'(?:forneça|disponibilize|informe|apresente)(.+?)(?:\.|;|\n)',
        r'(?:extratos?|saldos?|movimenta[çã][õo]es?)(.+?)(?:\.|;|\n)'
    ]
    
    all_matches = []
    unmatched = []
    
    for pattern in request_patterns:
        requests = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        
        for request in requests:
            # Quebra em itens individuais se houver lista
            items = re.split(r'[;,]|\n-|\n\d+\.', request)
            
            for item in items:
                if len(item.strip()) > 10:  # Ignora fragmentos muito curtos
                    matches = matcher.find_matches(item.strip())
                    
                    if matches:
                        best_match = matches[0]
                        # Extrai período se mencionado
                        periodo = extract_period_from_text(item)
                        
                        all_matches.append(SubsidyMatch(
                            subsidio_id=best_match['subsidio_id'],
                            nome_subsidio=best_match['nome_subsidio'],
                            texto_original=item.strip(),
                            similarity_score=best_match['similarity_score'],
                            periodo=periodo
                        ))
                    else:
                        unmatched.append(item.strip())
    
    return SubsidiesExtraction(
        subsidios_solicitados=all_matches,
        total_subsidios=len(all_matches),
        subsidios_nao_identificados=unmatched
    )
