"""
EU-specific domain models for EUR-Lex documents.

Parallel to BOE's NormativaCons, with shared Node tree structure
for unified graph representation.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from enum import Enum

from src.domain.models.common.node import Node, NodeType


class EUDocumentType(str, Enum):
    """Types of EU legal documents."""
    REGULATION = "REG"        # Directly applicable in all member states
    DIRECTIVE = "DIR"         # Requires national implementation
    DECISION = "DEC"          # Binding on addressees
    RECOMMENDATION = "REC"    # Non-binding
    OPINION = "OPI"           # Non-binding
    TREATY = "TRE"            # Primary EU law
    AGREEMENT = "AGR"         # International agreements
    OTHER = "OTH"


class EUInstitution(str, Enum):
    """EU institutions that can author documents."""
    PARLIAMENT = "EP"
    COUNCIL = "CONS"
    COMMISSION = "COM"
    COURT_OF_JUSTICE = "CJ"
    COURT_OF_AUDITORS = "CA"
    ECB = "ECB"
    COMMITTEE_OF_REGIONS = "COR"
    EESC = "EESC"  # European Economic and Social Committee
    JOINT = "JOINT"  # Multiple institutions


class EUDocumentStatus(str, Enum):
    """Current status of EU document."""
    IN_FORCE = "in_force"
    NO_LONGER_IN_FORCE = "no_longer_in_force"
    REPEALED = "repealed"
    AMENDED = "amended"
    PENDING = "pending"


@dataclass
class EUMetadata:
    """
    Metadata for EU legal documents.
    
    Similar to BOE's Metadata but with EU-specific fields.
    Uses CELLAR/EUR-Lex terminology.
    """
    # Identifiers
    celex_number: str                    # e.g., "32024R1234"
    cellar_id: Optional[str] = None      # CELLAR UUID
    eli_uri: Optional[str] = None        # European Legislation Identifier
    
    # Document classification
    document_type: EUDocumentType = EUDocumentType.OTHER
    author: Optional[EUInstitution] = None
    
    # Titles
    title: str = ""
    short_title: Optional[str] = None
    
    # Dates
    date_document: Optional[datetime] = None       # Date of the act
    date_publication: Optional[datetime] = None    # OJ publication date
    date_entry_into_force: Optional[datetime] = None
    date_end_validity: Optional[datetime] = None
    
    # Publication info
    oj_reference: Optional[str] = None   # Official Journal reference (e.g., "OJ L 123, 01/01/2024")
    oj_series: Optional[str] = None      # L (Legislation), C (Information), etc.
    
    # Status
    status: EUDocumentStatus = EUDocumentStatus.IN_FORCE
    is_consolidated: bool = False
    consolidated_date: Optional[datetime] = None
    
    # Subject matter
    directory_codes: List[str] = field(default_factory=list)  # Directory classification
    eurovoc_descriptors: List[str] = field(default_factory=list)  # EuroVoc terms
    
    # URLs
    url_eurlex: Optional[str] = None
    url_cellar: Optional[str] = None
    
    # Source tracking
    source: str = "EUR-Lex"
    last_modified: Optional[datetime] = None


@dataclass
class EUReferencia:
    """
    Reference to another EU document.
    
    Tracks legal basis, amendments, citations, etc.
    """
    target_celex: str                    # CELEX of referenced document
    reference_type: str                  # "legal_basis", "amends", "cites", etc.
    text: Optional[str] = None           # Human-readable reference text
    article: Optional[str] = None        # Specific article referenced


@dataclass
class EUAnalysis:
    """
    Analysis section for EU documents.
    
    Contains subject classifications and references.
    """
    eurovoc_terms: List[str] = field(default_factory=list)
    directory_codes: List[str] = field(default_factory=list)
    legal_basis: List[EUReferencia] = field(default_factory=list)
    amending_acts: List[EUReferencia] = field(default_factory=list)
    amended_by: List[EUReferencia] = field(default_factory=list)
    related_documents: List[EUReferencia] = field(default_factory=list)


@dataclass
class EUNormativa:
    """
    Main container for EU legal documents.
    
    Parallel to BOE's NormativaCons, using the same Node tree structure
    for the document content hierarchy.
    
    This enables:
    - Unified graph representation in Neo4j
    - Shared RAG/embedding infrastructure
    - Cross-source reference linking
    """
    id: str                              # Typically the CELEX number
    metadata: EUMetadata
    analysis: EUAnalysis
    content_tree: Node                   # Shared with BOE - enables unified graph
    
    @property
    def celex(self) -> str:
        """Convenience accessor for CELEX number."""
        return self.metadata.celex_number
    
    @property
    def title(self) -> str:
        """Convenience accessor for title."""
        return self.metadata.title
    
    @property
    def is_in_force(self) -> bool:
        """Check if document is currently in force."""
        return self.metadata.status == EUDocumentStatus.IN_FORCE


# =============================================================================
# EU-specific Node Types (extensions for FORMEX structure)
# =============================================================================

class EUNodeType(str, Enum):
    """
    Additional node types specific to EU document structure.
    
    These map to FORMEX elements and can be used alongside
    the existing NodeType enum.
    """
    # FORMEX-specific structural elements
    RECITAL = "recital"           # Considerando (preamble paragraph)
    CITATION = "citation"         # Legal basis citation in preamble
    ENACTING_TERMS = "enacting_terms"  # Main body container
    FINAL_PART = "final_part"     # Final provisions container
    
    # Can coexist with standard NodeType values
    # The Node tree uses base NodeType; these provide additional context


# =============================================================================
# Helper functions
# =============================================================================

def celex_to_document_type(celex: str) -> EUDocumentType:
    """
    Extract document type from CELEX number.
    
    CELEX format: [sector][year][type][number]
    Example: 32024R1234 → Regulation of 2024
    
    Sector 3 = Secondary legislation
    Type codes: R=Regulation, L=Directive, D=Decision, H=Recommendation, etc.
    """
    if not celex or len(celex) < 6:
        return EUDocumentType.OTHER
    
    # Type is typically the 5th character for sector 3 documents
    try:
        type_char = celex[5].upper()
        type_map = {
            'R': EUDocumentType.REGULATION,
            'L': EUDocumentType.DIRECTIVE,
            'D': EUDocumentType.DECISION,
            'H': EUDocumentType.RECOMMENDATION,
            'C': EUDocumentType.OPINION,
        }
        return type_map.get(type_char, EUDocumentType.OTHER)
    except IndexError:
        return EUDocumentType.OTHER


def parse_oj_reference(ref: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse Official Journal reference.
    
    Example: "OJ L 123, 01/01/2024, p. 1" 
    Returns: (series="L", number="123", date="01/01/2024")
    """
    import re
    
    match = re.match(r'OJ\s+([LC])\s+(\d+),?\s*(\d{2}/\d{2}/\d{4})?', ref or '')
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None
