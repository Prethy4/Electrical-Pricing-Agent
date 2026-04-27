import re
from typing import Optional

def normalize_article_code(code: str) -> str:
    """
    Uniformise le code article : supprime les zéros non significatifs 
    et remplace les tirets par des points.
    Ex: '01.02-03.04' -> '1.2.3.4'
    """
    if not code:
        return ""
    # Sépare par point ou tiret
    segments = re.split(r'[\.\-]', code)
    # Supprime les zéros de tête de chaque segment (ex: 01 -> 1)
    norm_segs = [s.lstrip('0') if s.lstrip('0') else "0" for s in segments]
    return ".".join(norm_segs)

def extract_article_code(text: str) -> Optional[str]:
    """
    Extracts article codes with 1 to 4 segments (e.g., 0, 1.1, 1.1.1, 1.1.1.1).
    """
    # Capture 1 à 4 segments séparés par . ou - en évitant les sous-séquences de codes plus longs
    pattern = r'(?<![\d\.])(?:\b|^)(\d+[a-zA-Z]?(?:[\.\-]\d+[a-zA-Z]?){0,3})(?!(?:[\.\-]\d)|[\d])'
    match = re.search(pattern, text)
    if match:
        raw_code = match.group(1).replace(" ", "").strip('.')
        return normalize_article_code(raw_code)
    return None

def get_hierarchy_level(code: str) -> int:
    """
    Détermine la profondeur basée sur les segments (points ou tirets).
    """
    if not code: return 0
    return len(re.split(r'[\.\-]', code))