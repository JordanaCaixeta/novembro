# 5. Agent de Extração de Datas Flexível
# Lida com múltiplos formatos de data:

from dateutil import parser
import locale

class DateExtraction(BaseModel):
    data_original: str
    data_normalizada: str  # Formato ISO: YYYY-MM-DD
    tipo: Literal["especifica", "periodo", "relativa"]
    confidence: float

@tool
def extract_all_dates(text: str) -> List[DateExtraction]:
    """
    Extrai todas as datas em diversos formatos
    """
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    dates = []
    
    # Padrões de data
    patterns = {
        'dd/mm/yyyy': r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b',
        'mes_ano': r'\b(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b',
        'periodo': r'(?:de|entre)\s+(.+?)\s+(?:a|até|e)\s+(.+?)(?:\.|,|\n)',
        'relativa': r'(últimos?\s+\d+\s+(?:dias?|meses?|anos?))',
        'ano_completo': r'\b(ano de \d{4}|exercício de \d{4})\b'
    }
    
    # Extrai datas no formato dd/mm/yyyy
    for match in re.finditer(patterns['dd/mm/yyyy'], text):
        try:
            date_str = match.group(1)
            # Tenta diferentes interpretações
            for sep in ['/', '-', '.']:
                if sep in date_str:
                    parts = date_str.split(sep)
                    if len(parts) == 3:
                        day, month, year = parts
                        if len(year) == 2:
                            year = '20' + year if int(year) < 30 else '19' + year
                        
                        normalized = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        dates.append(DateExtraction(
                            data_original=date_str,
                            data_normalizada=normalized,
                            tipo="especifica",
                            confidence=0.95
                        ))
                        break
        except:
            continue
    
    # Extrai mês/ano (dezembro de 2023)
    for match in re.finditer(patterns['mes_ano'], text, re.IGNORECASE):
        month_name = match.group(1)
        year = match.group(2)
        month_map = {
            'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
            'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
            'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
        }
        month_num = month_map.get(month_name.lower())
        if month_num:
            dates.append(DateExtraction(
                data_original=match.group(0),
                data_normalizada=f"{year}-{month_num}-01",  # Assume início do mês
                tipo="periodo",
                confidence=0.90
            ))
    
    # Extrai períodos relativos (últimos 90 dias)
    for match in re.finditer(patterns['relativa'], text, re.IGNORECASE):
        dates.append(DateExtraction(
            data_original=match.group(0),
            data_normalizada="[CALCULAR_RELATIVO]",  # Precisa ser calculado com base na data atual
            tipo="relativa",
            confidence=0.85
        ))
    
    return dates

def extract_period_from_text(text: str) -> Optional[dict]:
    """
    Extrai período (data inicial e final) do texto
    """
    dates = extract_all_dates(text)
    
    if len(dates) >= 2:
        # Se há duas datas, assume que é um período
        return {
            "inicio": dates[0].data_normalizada,
            "fim": dates[1].data_normalizada,
            "texto_original": text
        }
    elif len(dates) == 1 and dates[0].tipo == "periodo":
        # Se é um mês/ano, considera o mês completo
        date_parts = dates[0].data_normalizada.split('-')
        year = date_parts[0]
        month = date_parts[1]
        
        # Calcula último dia do mês
        if month in ['01', '03', '05', '07', '08', '10', '12']:
            last_day = '31'
        elif month in ['04', '06', '09', '11']:
            last_day = '30'
        else:  # Fevereiro
            last_day = '29' if int(year) % 4 == 0 else '28'
        
        return {
            "inicio": f"{year}-{month}-01",
            "fim": f"{year}-{month}-{last_day}",
            "texto_original": dates[0].data_original
        }
    
    return None