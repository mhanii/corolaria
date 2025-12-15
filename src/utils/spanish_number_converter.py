"""
Spanish written number to integer converter.

Handles both cardinal and ordinal numbers in Spanish text,
including compound numbers like "cincuenta y uno" (51) or
"ciento veintisiete" (127).

Used by the ingestion pipeline to normalize article names
like "Artículo cincuenta y uno" to clean numbers for indexing.
"""
import re
from typing import Optional


# Cardinal number words -> values
CARDINAL_UNITS = {
    "cero": 0, "uno": 1, "un": 1, "una": 1, "dos": 2, "tres": 3, 
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciséis": 16, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiún": 21, "veintidós": 22, 
    "veintidos": 22, "veintitrés": 23, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiséis": 26, "veintiseis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29,
}

CARDINAL_TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}

CARDINAL_HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300, "cuatrocientos": 400, 
    "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600, "setecientos": 700, 
    "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}

# Ordinal number words -> values (masculine and feminine forms)
ORDINAL_UNITS = {
    "primero": 1, "primera": 1, "primer": 1,
    "segundo": 2, "segunda": 2,
    "tercero": 3, "tercera": 3, "tercer": 3,
    "cuarto": 4, "cuarta": 4,
    "quinto": 5, "quinta": 5,
    "sexto": 6, "sexta": 6,
    "séptimo": 7, "septima": 7, "séptima": 7, "septimo": 7,
    "octavo": 8, "octava": 8,
    "noveno": 9, "novena": 9,
    "décimo": 10, "decima": 10, "décima": 10, "decimo": 10,
}

ORDINAL_TENS = {
    "undécimo": 11, "undecimo": 11, "undécima": 11, "undecima": 11,
    "duodécimo": 12, "duodecimo": 12, "duodécima": 12, "duodecima": 12,
    "decimotercero": 13, "decimotercera": 13, "décimo tercero": 13, "décima tercera": 13,
    "decimocuarto": 14, "decimocuarta": 14, "décimo cuarto": 14, "décima cuarta": 14,
    "decimoquinto": 15, "decimoquinta": 15, "décimo quinto": 15, "décima quinta": 15,
    "decimosexto": 16, "decimosexta": 16, "décimo sexto": 16, "décima sexta": 16,
    "decimoséptimo": 17, "decimoseptimo": 17, "decimoséptima": 17, "decimoseptima": 17,
    "decimoctavo": 18, "decimoctava": 18, "décimo octavo": 18, "décima octava": 18,
    "decimonoveno": 19, "decimonovena": 19, "décimo noveno": 19, "décima novena": 19,
    "vigésimo": 20, "vigesimo": 20, "vigésima": 20, "vigesima": 20,
    "trigésimo": 30, "trigesimo": 30, "trigésima": 30, "trigesima": 30,
    "cuadragésimo": 40, "cuadragesimo": 40, "cuadragésima": 40, "cuadragesima": 40,
    "quincuagésimo": 50, "quincuagesimo": 50, "quincuagésima": 50, "quincuagesima": 50,
    "sexagésimo": 60, "sexagesimo": 60, "sexagésima": 60, "sexagesima": 60,
    "septuagésimo": 70, "septuagesimo": 70, "septuagésima": 70, "septuagesima": 70,
    "octogésimo": 80, "octogesimo": 80, "octogésima": 80, "octogesima": 80,
    "nonagésimo": 90, "nonagesimo": 90, "nonagésima": 90, "nonagesima": 90,
    "centésimo": 100, "centesimo": 100, "centésima": 100, "centesima": 100,
}


def _parse_cardinal(text: str) -> Optional[int]:
    """
    Parse a Spanish cardinal number string to integer.
    
    Handles:
    - Simple numbers: "uno" -> 1, "veinte" -> 20
    - Compound tens: "treinta y uno" or "treinta_y_uno" -> 31
    - Hundreds: "ciento veintisiete" -> 127
    
    Returns None if the text cannot be parsed as a cardinal number.
    """
    # Normalize: lowercase, strip whitespace, convert underscores to spaces
    text = text.lower().strip().replace("_", " ")
    
    if not text:
        return None
    
    # Direct lookup for simple numbers
    if text in CARDINAL_UNITS:
        return CARDINAL_UNITS[text]
    if text in CARDINAL_TENS:
        return CARDINAL_TENS[text]
    if text in CARDINAL_HUNDREDS:
        return CARDINAL_HUNDREDS[text]
    
    total = 0
    remaining = text
    
    # Check for hundreds prefix (sort by length descending to match "ciento" before "cien")
    for word in sorted(CARDINAL_HUNDREDS.keys(), key=len, reverse=True):
        if remaining.startswith(word):
            total += CARDINAL_HUNDREDS[word]
            remaining = remaining[len(word):].strip()
            break
    
    # Handle remaining parts after hundreds
    if remaining:
        # First check for units (includes 1-29, covers veinti- forms)
        if remaining in CARDINAL_UNITS:
            total += CARDINAL_UNITS[remaining]
            remaining = ""
        # Then check for tens (30, 40, 50, etc.)
        elif remaining in CARDINAL_TENS:
            total += CARDINAL_TENS[remaining]
            remaining = ""
        else:
            # Check for compound tens like "treinta y uno"
            for word, value in CARDINAL_TENS.items():
                if remaining.startswith(word):
                    total += value
                    remaining = remaining[len(word):].strip()
                    # Handle "y uno", "y dos", etc.
                    if remaining.startswith("y "):
                        remaining = remaining[2:].strip()
                    break
            
            # Check for units in remaining
            if remaining:
                if remaining in CARDINAL_UNITS:
                    total += CARDINAL_UNITS[remaining]
                    remaining = ""
    
    # If we consumed everything and got a value, return it
    if not remaining and total > 0:
        return total
    
    return None


def _parse_ordinal(text: str) -> Optional[int]:
    """
    Parse a Spanish ordinal number string to integer.
    
    Handles:
    - Simple ordinals: "primero" -> 1, "décimo" -> 10
    - Compound ordinals: "vigésimo primero" or "vigésimo_primero" -> 21
    
    Returns None if the text cannot be parsed as an ordinal number.
    """
    # Normalize: lowercase, strip whitespace, convert underscores to spaces
    text = text.lower().strip().replace("_", " ")
    
    if not text:
        return None
    
    # Direct lookup for simple ordinals
    if text in ORDINAL_UNITS:
        return ORDINAL_UNITS[text]
    if text in ORDINAL_TENS:
        return ORDINAL_TENS[text]
    
    # Try compound ordinals like "vigésimo primero"
    parts = text.split()
    if len(parts) == 2:
        tens_word, unit_word = parts
        tens_value = ORDINAL_TENS.get(tens_word)
        unit_value = ORDINAL_UNITS.get(unit_word)
        if tens_value is not None and unit_value is not None and tens_value >= 20:
            return tens_value + unit_value
    
    return None


def spanish_words_to_number(text: str) -> Optional[int]:
    """
    Convert Spanish written number to integer.
    
    Handles both cardinal and ordinal numbers.
    
    Examples:
        "cincuenta y uno" -> 51
        "ciento veintisiete" -> 127
        "primero" -> 1
        "vigésimo tercero" -> 23
        
    Args:
        text: Spanish number text (case-insensitive)
        
    Returns:
        Integer value or None if not a valid Spanish number
    """
    if not text:
        return None
    
    text = text.lower().strip()
    
    # Try cardinal first (more common for article numbers)
    result = _parse_cardinal(text)
    if result is not None:
        return result
    
    # Fall back to ordinal
    result = _parse_ordinal(text)
    if result is not None:
        return result
    
    return None


def normalize_article_number(name: str) -> Optional[str]:
    """
    Extract and normalize article number from an article name.
    
    Handles both numeric and Spanish written numbers.
    
    Examples:
        "Artículo 14" -> "14"
        "Art. 1 bis" -> "1 bis"
        "Artículo 154.1" -> "154"
        "Artículo cincuenta y uno" -> "51"
        "Artículo primero" -> "1"
        "Disposición adicional primera" -> None (not a numbered article)
        
    Args:
        name: Full article name/title
        
    Returns:
        Normalized number string or None
    """
    if not name:
        return None
    
    # First, try numeric pattern (existing behavior)
    # Match: number (with optional dots) + optional suffix (bis, ter, quater, etc.)
    # "1.428" → "1428", "544 ter" → "544 ter"
    match = re.search(
        r'(\d+(?:\.\d+)*)(?:\s*(bis|ter|quater|quinquies|sexies|septies|octies|novies))?',
        name, 
        re.IGNORECASE
    )
    if match:
        num = match.group(1)
        suffix = match.group(2)
        # Remove dots from article number (1.428 → 1428)
        clean_num = num.replace('.', '')
        if suffix:
            return f"{clean_num} {suffix.lower()}"
        return clean_num
    
    # No numeric match - try Spanish written number
    # Extract the number part after "Artículo" or "Art."
    article_match = re.match(
        r'^(?:Artículo|Articulo|Art\.?)\s+(.+?)(?:\s*\.\s*|$)',
        name.strip(),
        re.IGNORECASE
    )
    
    if article_match:
        number_text = article_match.group(1).strip()
        result = spanish_words_to_number(number_text)
        if result is not None:
            return str(result)
    
    # Also check for standalone written numbers (without "Artículo" prefix)
    # This handles cases where the name field only contains the number part
    result = spanish_words_to_number(name.strip())
    if result is not None:
        return str(result)
    
    return None
