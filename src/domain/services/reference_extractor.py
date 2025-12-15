"""
Reference Extractor for Spanish Legal Documents.

Extracts citations and references from legal text following the conventions
established by the "Directrices de técnica normativa" (Guidelines on Normative Technique).

Handles:
- Constitution and Statutes of Autonomy (CE, EA)
- State Laws (Ley, Ley Orgánica)
- Delegated Legislation (Real Decreto-ley, Decreto Legislativo)
- Regulations (Real Decreto, Orden)
- Judicial Decisions (STC, STS, SAN, STSJ)
- Internal article references
- Abbreviated law references (LOPJ, CC, CP, etc.)
"""
import re
import json
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ReferenceType(Enum):
    """Classification of legal reference types."""
    INTERNAL = "internal"           # Reference within the same law
    CONSTITUTION = "constitution"   # Constitución Española
    ORGANIC_LAW = "organic_law"     # Ley Orgánica
    LAW = "law"                     # Ley (ordinary)
    ROYAL_DECREE_LAW = "royal_decree_law"     # Real Decreto-ley
    LEGISLATIVE_DECREE = "legislative_decree"  # Decreto Legislativo / Real Decreto Legislativo
    ROYAL_DECREE = "royal_decree"   # Real Decreto
    ORDER = "order"                 # Orden ministerial
    STATUTE_OF_AUTONOMY = "statute_of_autonomy"  # Estatuto de Autonomía
    CODE = "code"                   # Código Civil, Código Penal, etc.
    JUDICIAL = "judicial"           # STC, STS, SAN, STSJ
    ABBREVIATED = "abbreviated"     # LOPJ, LEC, LECrim, etc.
    EU_LEGISLATION = "eu_legislation"  # Directive, Regulation
    EU_TREATY = "eu_treaty"         # TFUE, TUE
    UNKNOWN = "unknown"


@dataclass
class ExtractedReference:
    """A single extracted legal reference."""
    raw_text: str                     # Original matched text
    reference_type: ReferenceType     # Classification
    article_number: Optional[str] = None   # Base article number: "143", "53", "10 bis"
    apartado: Optional[str] = None    # Subsection: "2" (from 143.2 or 53, 2)
    article_range: Optional[Tuple[str, str]] = None  # For "artículos 5 a 12"
    law_type: Optional[str] = None    # e.g., "Ley Orgánica", "Real Decreto"
    law_number: Optional[str] = None  # e.g., "10/1995", "3/2007"
    law_date: Optional[str] = None    # e.g., "de 23 de noviembre"
    law_title: Optional[str] = None   # e.g., "del Código Penal"
    abbreviation: Optional[str] = None  # e.g., "CE", "LOPJ", "CC"
    judicial_court: Optional[str] = None  # e.g., "STC", "STS"
    judicial_number: Optional[str] = None  # e.g., "1234/2020"
    is_external: bool = True          # False if internal reference
    resolved_boe_id: Optional[str] = None  # If we can resolve it
    start_pos: int = 0                # Position in source text
    end_pos: int = 0                  # End position in source text
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d['reference_type'] = self.reference_type.value
        return d


@dataclass
class ExtractionResult:
    """Result of reference extraction from a document."""
    source_document_id: str
    references: List[ExtractedReference] = field(default_factory=list)
    unresolved_references: List[ExtractedReference] = field(default_factory=list)
    extraction_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ReferenceExtractor:
    """
    Extracts legal references from Spanish legal documents.
    
    Uses comprehensive regex patterns based on official Spanish legal citation
    conventions. Unresolved references are logged to a JSON file for debugging.
    """
    
    # Well-known laws with their BOE IDs
    KNOWN_LAWS: Dict[str, str] = {
        # Constitution
        "ce": "BOE-A-1978-31229",
        "constitución": "BOE-A-1978-31229",
        "constitución española": "BOE-A-1978-31229",
        
        # Major Codes
        "cc": "BOE-A-1889-4763",
        "código civil": "BOE-A-1889-4763",
        "cp": "BOE-A-1995-25444",
        "código penal": "BOE-A-1995-25444",
        "c. de c.": "BOE-A-1885-6627",
        "código de comercio": "BOE-A-1885-6627",
        
        # Procedural Laws
        "lec": "BOE-A-2000-323",
        "ley de enjuiciamiento civil": "BOE-A-2000-323",
        "lecrim": "BOE-A-1882-6036",
        "lecr": "BOE-A-1882-6036",
        "ley de enjuiciamiento criminal": "BOE-A-1882-6036",
        
        # Organic Laws
        "lopj": "BOE-A-1985-12666",
        "ley orgánica del poder judicial": "BOE-A-1985-12666",
        "lo 6/1985": "BOE-A-1985-12666",
        "lotc": "BOE-A-1979-23709",
        "ley orgánica del tribunal constitucional": "BOE-A-1979-23709",
        "loreg": "BOE-A-1985-11672",
        "ley orgánica del régimen electoral general": "BOE-A-1985-11672",
        "lopdgdd": "BOE-A-2018-16673",
        "lopd": "BOE-A-2018-16673",
        
        # Administrative Law
        "lpac": "BOE-A-2015-10565",
        "ley 39/2015": "BOE-A-2015-10565",
        "lrjsp": "BOE-A-2015-10566",
        "ley 40/2015": "BOE-A-2015-10566",
        "ljca": "BOE-A-1998-16718",
        
        # Labor Law
        "et": "BOE-A-2015-11430",
        "estatuto de los trabajadores": "BOE-A-2015-11430",
        "lgss": "BOE-A-2015-11724",
        "ley general de la seguridad social": "BOE-A-2015-11724",
        
        # Tax Law
        "lgt": "BOE-A-2003-23186",
        "ley general tributaria": "BOE-A-2003-23186",
        "lirpf": "BOE-A-2006-20764",
        "lis": "BOE-A-2014-12328",
        "liva": "BOE-A-1992-28740",
        
        # Other Important Laws
        "lph": "BOE-A-1960-10906",
        "ley de propiedad horizontal": "BOE-A-1960-10906",
        "lau": "BOE-A-1994-26003",
        "ley de arrendamientos urbanos": "BOE-A-1994-26003",
        "lh": "BOE-A-1946-2453",
        "ley hipotecaria": "BOE-A-1946-2453",
        "lsc": "BOE-A-2010-10544",
        "ley de sociedades de capital": "BOE-A-2010-10544",
    }
    
    def __init__(self, unresolved_log_path: Optional[str] = None):
        """
        Initialize the reference extractor.
        
        Args:
            unresolved_log_path: Path to JSON file for logging unresolved references.
                                 Defaults to 'data/unresolved_references.json'
        """
        self.unresolved_log_path = Path(
            unresolved_log_path or "data/unresolved_references.json"
        )
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile all regex patterns for reference extraction."""
        
        # Common building blocks - article number pattern
        # Distinguishes thousand separators from apartados:
        # - "1.428" → captures "1.428" (3 digits after dot = thousand separator)
        # - "12.2" → captures "12" (1-2 digits after dot = apartado, not captured)
        # - "149.1.23.ª" → captures "149" (apartados chain, not captured)
        self._article_num = r"""
            (?P<article_num>
                \d+                           # Base number: 14, 149, 1902
                (?:\.\d{3})*                  # Thousand separators (captured): 1.428, 10.000
                (?:\s*(?:bis|ter|qu[aá]ter|quinquies|sexies|septies|octies))?  # Latin suffixes
            )
            (?:[\.,]\d{1,2})*                 # Apartados (NOT captured): .1, .23, ,2
            (?:[\.,][ªº]|º|ª)?                # Ordinal markers (NOT captured): .ª, º
        """
        
        # Month names for date parsing
        self._months = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
        
        # Pattern 1: Full law citation - captures only the identifier
        # "Ley Orgánica 10/1995" or "Ley 41/2003, de 18 de noviembre"
        # Does NOT capture title text to avoid incorrect captures
        self._full_law_pattern = re.compile(
            r"""
            (?P<law_type>
                Ley\s+Org[aá]nica |
                Real\s+Decreto-ley |
                Real\s+Decreto\s+Legislativo |
                Decreto\s+Legislativo |
                Real\s+Decreto |
                Decreto-ley |
                Decreto |
                Ley |
                Orden\s+(?:Ministerial\s+)?(?:[A-Z]{3}/)?
            )
            \s*
            (?P<law_number>\d{1,4}/\d{4})          # 10/1995, 3/2007
            (?:
                ,?\s*de\s+\d{1,2}\s+de\s+""" + self._months + r"""  # Optional date: , de 23 de noviembre
            )?
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
        
        # Pattern 2: Article with external law reference
        # "artículo 14 de la Constitución Española"
        # "art. 1902 del Código Civil"
        # "artículo 3 de la Ley 29/2012"
        self._article_with_law_pattern = re.compile(
            r"""
            (?:art[íi]culo|art\.?)\s*""" + self._article_num + r"""
            \s+
            (?:de\s+)?(?:la\s+|el\s+|los\s+|las\s+|del\s+)?  # Handle 'del' = de + el
            (?P<law_ref>
                # Constitution
                Constituci[oó]n(?:\s+Espa[nñ]ola)? |
                
                # Codes (handle 'del Código')
                C[oó]digo\s+(?:Civil|Penal|de\s+Comercio) |
                
                # Procedural Laws with abbreviations
                Ley\s+de\s+Enjuiciamiento\s+(?:Civil|Criminal) |
                
                # Statutes of Autonomy
                Estatuto\s+de\s+(?:Autonom[ií]a\s+)?(?:de\s+)?[A-ZÁÉÍÓÚ][a-záéíóúñ]+ |
                
                # Worker's Statute
                Estatuto\s+de\s+(?:los\s+)?Trabajadores |
                
                # Specific law with number (Ley, Ley Orgánica, Real Decreto, etc.)
                (?:Ley\s+Org[aá]nica|Real\s+Decreto(?:-ley)?|Decreto(?:-ley)?|Ley)\s+\d{1,4}/\d{4}
            )
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
        
        # Pattern 3: Abbreviated law references
        # "art. 14 CE", "art. 1902 CC", "art. 1.428 de la LEC", "según la LOPJ"
        # Note: Negative lookbehind (?<!\() prevents matching CE in "Reglamento (CE)"
        self._abbreviated_pattern = re.compile(
            r"""
            (?:
                # With article number: "art. 14 CE" or "artículo 1.428 de la LEC"
                (?:art[íi]culo|art\.?)\s*""" + self._article_num + r"""
                (?:\s+(?:del?\s+)?(?:la\s+|el\s+)?)?  # Optional "de la", "del", "de", etc.
            )?
            (?<!\()  # Negative lookbehind: not preceded by (
            (?P<abbreviation>
                CE | CC | CP | ET |
                LEC | LECrim | LECr |
                LOPJ | LOTC | LOREG |
                LPAC | LRJSP | LJCA |
                LGT | LIRPF | LIS | LIVA |
                LPH | LAU | LH | LSC |
                LGSS | LOPDGDD | LOPD |
                EA  # Estatuto de Autonomía (context-dependent)
            )
            (?!\w)  # Negative lookahead to avoid matching partial words
            """,
            re.VERBOSE | re.UNICODE
        )
        
        # Pattern 4: Internal references (no external law mentioned)
        # "artículo 143.2" → captures article=143 (ignores .2 apartado)
        # "artículo anterior" → relative reference
        # "artículos 96, 782 y 808" → list of base article numbers
        
        # Base article: just the number, optionally followed by bis/ter
        base_article = r'\d+(?:\s*(?:bis|ter|qu[aá]ter|quinquies|sexies|septies|octies))?'
        
        self._internal_article_pattern = re.compile(
            r"""
            (?:el\s+|la\s+|los\s+|las\s+|en\s+el\s+|en\s+los\s+|del\s+)?
            (?:art[íÍi]culos?|arts?\.?)\s*
            (?:
                # Range: "artículos 5 a 12"
                (?P<range_start>""" + base_article + r""")\s*(?:a|al)\s*(?P<range_end>""" + base_article + r""") |
                
                # Relative: "artículo anterior", "artículo siguiente"
                (?P<relative>anterior|siguiente|precedente) |
                
                # Single article: "artículo 143" (ignores any .2 or , 2 after it)
                (?P<article_num>""" + base_article + r""")
            )
            # Ignore apartado after article number (just consume it, don't capture)
            (?:[,\.\s]+\d+[ºª\.]?)?
            (?:
                \s+(?:de\s+)?(?:esta|este|la\s+presente|el\s+presente)\s+
                (?:Ley|Real\s+Decreto|Decreto|Orden|Reglamento|Código|Constitución)
            )?
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
        
        # Pattern 5: Judicial decisions
        # "STC 1234/2020", "STS 567/2019, de 15 de marzo"
        self._judicial_pattern = re.compile(
            r"""
            (?P<court>
                STC |           # Tribunal Constitucional
                STS |           # Tribunal Supremo
                STSJ |          # Tribunales Superiores de Justicia
                SAN |           # Audiencia Nacional
                SAP |           # Audiencia Provincial
                SJPI |          # Juzgado de Primera Instancia
                ATC |           # Auto del Tribunal Constitucional
                ATS             # Auto del Tribunal Supremo
            )
            \s*
            (?P<decision_number>\d+/\d{4})
            (?:
                ,?\s*de\s+\d{1,2}\s+de\s+""" + self._months + r"""
            )?
            """,
            re.VERBOSE | re.UNICODE
        )
        
        # Pattern 6: EU legislation
        # "Directiva 2006/123/CE", "Reglamento (UE) 2016/679", "Reglamento (CE) n.º 1221/2009"
        self._eu_pattern = re.compile(
            r"""
            (?P<eu_type>
                Directiva |
                Reglamento |
                Decisi[oó]n
            )
            \s*
            (?:\([A-Z]+\)\s*)?    # Optional (UE), (CE), etc.
            (?:n\.?º?\s*)?        # Optional "n.º" prefix
            (?P<eu_number>\d{2,4}/\d+(?:/[A-Z]+)?)
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
        
        # Pattern 6b: EU Treaties (TFUE, TUE)
        # "artículos 101 y 102 del Tratado de Funcionamiento de la Unión Europea"
        # "artículo 2 del Tratado de la Unión Europea"
        self._eu_treaty_pattern = re.compile(
            r"""
            (?:
                (?:los\s+)?(?:art[íi]culos?|arts?\.?)\s*
                (?P<article_list>\d+(?:\s*(?:,|y)\s*\d+)*)\s+
            )?
            (?:del?\s+)?
            (?P<treaty_name>
                Tratado\s+de\s+Funcionamiento\s+de\s+la\s+Uni[oó]n\s+Europea |
                Tratado\s+de\s+la\s+Uni[oó]n\s+Europea |
                TFUE | TUE
            )
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
        
        # Pattern 7: "Citada" references (back-references to previously mentioned laws)
        # "la citada Ley Orgánica 6/1985", "según la mencionada Ley"
        self._cited_pattern = re.compile(
            r"""
            (?:la\s+|el\s+)?
            (?:citad[ao]|mencionad[ao]|referid[ao]|expresad[ao])\s+
            (?P<cited_law_type>
                Ley\s+Org[aá]nica |
                Real\s+Decreto(?:-ley)? |
                Decreto(?:-ley)? |
                Ley |
                Orden |
                Constituci[oó]n
            )
            (?:\s+(?P<cited_number>\d{1,4}/\d{4}))?
            """,
            re.IGNORECASE | re.VERBOSE | re.UNICODE
        )
    
    def extract(
        self, 
        text: str, 
        source_document_id: str,
        current_normativa_id: Optional[str] = None,
        current_article_number: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract all legal references from the given text.
        
        Args:
            text: The legal text to analyze
            source_document_id: ID of the document being analyzed
            current_normativa_id: BOE ID of the current document (for internal refs)
            current_article_number: Current article number (for resolving 'anterior')
            
        Returns:
            ExtractionResult containing all found references
        """
        result = ExtractionResult(source_document_id=source_document_id)
        
        # Track positions to avoid overlapping matches
        matched_ranges: List[Tuple[int, int]] = []
        
        def is_overlapping(start: int, end: int) -> bool:
            for s, e in matched_ranges:
                if not (end <= s or start >= e):
                    return True
            return False
        
        def add_match(ref: ExtractedReference):
            if not is_overlapping(ref.start_pos, ref.end_pos):
                matched_ranges.append((ref.start_pos, ref.end_pos))
                result.references.append(ref)
        
        # Extract in order of specificity (most specific first)
        
        # 1. Article with external law reference (Must be before Full Law)
        for match in self._article_with_law_pattern.finditer(text):
            ref = self._parse_article_with_law_match(match)
            add_match(ref)

        # 2. EU Legislation (Must be before Abbreviated to handle /CE suffix)
        for match in self._eu_pattern.finditer(text):
            ref = self._parse_eu_match(match)
            add_match(ref)
        
        # 2b. EU Treaties (TFUE, TUE with article references)
        for match in self._eu_treaty_pattern.finditer(text):
            ref = self._parse_eu_treaty_match(match)
            add_match(ref)

        # 3. Judicial decisions
        for match in self._judicial_pattern.finditer(text):
            ref = self._parse_judicial_match(match)
            add_match(ref)

        # 4. Full law citations
        for match in self._full_law_pattern.finditer(text):
            ref = self._parse_full_law_match(match)
            add_match(ref)
        
        # 5. Abbreviated references
        for match in self._abbreviated_pattern.finditer(text):
            ref = self._parse_abbreviated_match(match)
            add_match(ref)
        
        # 6. Cited/mentioned references
        for match in self._cited_pattern.finditer(text):
            ref = self._parse_cited_match(match)
            add_match(ref)
        
        # 7. Internal references (only those not already captured)
        for match in self._internal_article_pattern.finditer(text):
            if not is_overlapping(match.start(), match.end()):
                ref = self._parse_internal_match(match, current_normativa_id, current_article_number)
                add_match(ref)
        
        # Attempt to resolve references
        for ref in result.references:
            self._try_resolve(ref)
            if ref.is_external and ref.resolved_boe_id is None:
                result.unresolved_references.append(ref)
        
        # Log unresolved references
        if result.unresolved_references:
            self._log_unresolved(result)
        
        logger.debug(
            f"Extracted {len(result.references)} references from {source_document_id}, "
            f"{len(result.unresolved_references)} unresolved"
        )
        
        return result

    # ... (skipping methods in between to next match) ...

    def _log_unresolved(self, result: ExtractionResult) -> None:
        """Log unresolved references to JSON file for debugging."""
        self.unresolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data or create new
        if self.unresolved_log_path.exists():
            with open(self.unresolved_log_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {"unresolved": []}
        else:
            data = {"unresolved": []}
        
        # Append new unresolved references
        for ref in result.unresolved_references:
            entry = {
                "source_document": result.source_document_id,
                "extraction_time": result.extraction_timestamp,
                "reference": ref.to_dict()
            }
            data["unresolved"].append(entry)
        
        # Write back
        with open(self.unresolved_log_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Logged {len(result.unresolved_references)} unresolved references")

    
    def _parse_full_law_match(self, match: re.Match) -> ExtractedReference:
        """Parse a full law citation match."""
        law_type = match.group("law_type").strip()
        ref_type = self._classify_law_type(law_type)
        
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ref_type,
            law_type=law_type,
            law_number=match.group("law_number"),
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_judicial_match(self, match: re.Match) -> ExtractedReference:
        """Parse a judicial decision match."""
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ReferenceType.JUDICIAL,
            judicial_court=match.group("court"),
            judicial_number=match.group("decision_number"),
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_eu_match(self, match: re.Match) -> ExtractedReference:
        """Parse an EU legislation match."""
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ReferenceType.EU_LEGISLATION,
            law_type=match.group("eu_type"),
            law_number=match.group("eu_number"),
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_eu_treaty_match(self, match: re.Match) -> ExtractedReference:
        """Parse an EU treaty match (TFUE, TUE)."""
        treaty_name = match.group("treaty_name")
        article_list = match.group("article_list") if match.group("article_list") else None
        
        # Normalize treaty name to abbreviation
        if "funcionamiento" in treaty_name.lower():
            abbrev = "TFUE"
        elif "unión" in treaty_name.lower() or "union" in treaty_name.lower():
            abbrev = "TUE"
        else:
            abbrev = treaty_name.upper()
        
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ReferenceType.EU_TREATY,
            article_number=article_list,
            abbreviation=abbrev,
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_article_with_law_match(self, match: re.Match) -> ExtractedReference:
        """Parse an article reference with external law specification."""
        law_ref = match.group("law_ref").lower()
        
        # Determine reference type from the law reference
        if "constitució" in law_ref or "constitucio" in law_ref:
            ref_type = ReferenceType.CONSTITUTION
        elif "código" in law_ref or "codigo" in law_ref:
            ref_type = ReferenceType.CODE
        elif "estatuto" in law_ref:
            if "autonomía" in law_ref or "autonomia" in law_ref:
                ref_type = ReferenceType.STATUTE_OF_AUTONOMY
            else:
                ref_type = ReferenceType.LAW  # Estatuto de los Trabajadores
        elif "ley orgánica" in law_ref or "ley organica" in law_ref:
            ref_type = ReferenceType.ORGANIC_LAW
        else:
            ref_type = ReferenceType.LAW
        
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ref_type,
            article_number=match.group("article_num"),
            law_type=match.group("law_ref"),
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_abbreviated_match(self, match: re.Match) -> ExtractedReference:
        """Parse an abbreviated law reference."""
        abbrev = match.group("abbreviation").upper()
        article_num = match.group("article_num") if "article_num" in match.groupdict() else None
        
        # Determine type from abbreviation
        if abbrev == "CE":
            ref_type = ReferenceType.CONSTITUTION
        elif abbrev in ("CC", "CP"):
            ref_type = ReferenceType.CODE
        elif abbrev.startswith("L"):  # LOPJ, LEC, etc.
            ref_type = ReferenceType.ORGANIC_LAW if abbrev.startswith("LO") else ReferenceType.LAW
        elif abbrev == "ET":
            ref_type = ReferenceType.LAW
        elif abbrev == "EA":
            ref_type = ReferenceType.STATUTE_OF_AUTONOMY
        else:
            ref_type = ReferenceType.ABBREVIATED
        
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ref_type,
            article_number=article_num,
            abbreviation=abbrev,
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_cited_match(self, match: re.Match) -> ExtractedReference:
        """Parse a 'citada/mencionada' back-reference."""
        law_type = match.group("cited_law_type").strip()
        ref_type = self._classify_law_type(law_type)
        
        return ExtractedReference(
            raw_text=match.group(0),
            reference_type=ref_type,
            law_type=law_type,
            law_number=match.group("cited_number") if match.group("cited_number") else None,
            is_external=True,
            start_pos=match.start(),
            end_pos=match.end()
        )
    
    def _parse_internal_match(
        self, 
        match: re.Match, 
        current_normativa_id: Optional[str],
        current_article_number: Optional[str] = None
    ) -> ExtractedReference:
        """Parse an internal article reference.
        
        Args:
            match: Regex match object
            current_normativa_id: BOE ID of current normativa
            current_article_number: Current article number (for resolving 'anterior')
        """
        ref = ExtractedReference(
            raw_text=match.group(0),
            reference_type=ReferenceType.INTERNAL,
            is_external=False,
            start_pos=match.start(),
            end_pos=match.end()
        )
        
        # Handle different match types
        if match.group("range_start") and match.group("range_end"):
            ref.article_range = (match.group("range_start"), match.group("range_end"))
        elif match.group("relative"):
            relative = match.group("relative").lower()
            # Try to resolve relative reference using current article number
            if current_article_number and current_article_number.isdigit():
                current_num = int(current_article_number)
                if relative in ("anterior", "precedente"):
                    ref.article_number = str(current_num - 1)
                elif relative == "siguiente":
                    ref.article_number = str(current_num + 1)
            else:
                ref.article_number = relative  # Keep as "anterior" if can't resolve
        elif match.group("article_num"):
            ref.article_number = match.group("article_num")
        
        # Set resolved ID if we know the current normativa
        if current_normativa_id and ref.article_number:
            # Don't create full ID for relative references that couldn't be resolved
            if ref.article_number not in ("anterior", "siguiente", "precedente"):
                ref.resolved_boe_id = current_normativa_id
        
        return ref
    
    def _classify_law_type(self, law_type: str) -> ReferenceType:
        """Classify a law type string into a ReferenceType."""
        lt = law_type.lower().strip()
        
        if "orgánica" in lt or "organica" in lt:
            return ReferenceType.ORGANIC_LAW
        elif "decreto-ley" in lt or "decreto ley" in lt:
            return ReferenceType.ROYAL_DECREE_LAW
        elif "decreto legislativo" in lt:
            return ReferenceType.LEGISLATIVE_DECREE
        elif "real decreto" in lt:
            return ReferenceType.ROYAL_DECREE
        elif "decreto" in lt:
            return ReferenceType.ROYAL_DECREE  # Fallback for "Decreto"
        elif "orden" in lt:
            return ReferenceType.ORDER
        elif "constitución" in lt or "constitucion" in lt:
            return ReferenceType.CONSTITUTION
        elif "ley" in lt:
            return ReferenceType.LAW
        else:
            return ReferenceType.UNKNOWN
    
    def _try_resolve(self, ref: ExtractedReference) -> None:
        """Attempt to resolve a reference to a BOE ID."""
        if not ref.is_external:
            return
        
        # Check abbreviation first
        if ref.abbreviation:
            key = ref.abbreviation.lower()
            if key in self.KNOWN_LAWS:
                ref.resolved_boe_id = self.KNOWN_LAWS[key]
                return
        
        # Check law type + number
        if ref.law_type and ref.law_number:
            # Normalize: "Ley Orgánica 10/1995" -> "lo 10/1995"
            type_abbrev = self._abbreviate_law_type(ref.law_type)
            key = f"{type_abbrev} {ref.law_number}".lower()
            if key in self.KNOWN_LAWS:
                ref.resolved_boe_id = self.KNOWN_LAWS[key]
                return
        
        # Check law type alone (for Constitution, Codes)
        if ref.law_type:
            key = ref.law_type.lower().strip()
            if key in self.KNOWN_LAWS:
                ref.resolved_boe_id = self.KNOWN_LAWS[key]
                return
    
    def _abbreviate_law_type(self, law_type: str) -> str:
        """Convert full law type to abbreviation."""
        lt = law_type.lower().strip()
        
        if "ley orgánica" in lt or "ley organica" in lt:
            return "lo"
        elif "real decreto-ley" in lt:
            return "rdl"
        elif "real decreto legislativo" in lt or "decreto legislativo" in lt:
            return "rdleg"
        elif "real decreto" in lt:
            return "rd"
        elif "decreto" in lt:
            return "d"
        elif "orden" in lt:
            return "o"
        elif "ley" in lt:
            return "l"
        else:
            return lt
    
    def _log_unresolved(self, result: ExtractionResult) -> None:
        """Log unresolved references to JSON file for debugging."""
        self.unresolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data or create new
        if self.unresolved_log_path.exists():
            with open(self.unresolved_log_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {"unresolved": []}
        else:
            data = {"unresolved": []}
        
        # Append new unresolved references
        for ref in result.unresolved_references:
            entry = {
                "source_document": result.source_document_id,
                "extraction_time": result.extraction_timestamp,
                "reference": ref.to_dict()
            }
            data["unresolved"].append(entry)
        
        # Write back
        with open(self.unresolved_log_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Logged {len(result.unresolved_references)} unresolved references")
