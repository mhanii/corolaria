"""
EU Data Processor for FORMEX XML parsing.

Transforms FORMEX XML documents into EUNormativa domain models
with a shared Node tree structure.
"""

import logging
import re
import zipfile
import io
from typing import Optional, Tuple, List
from datetime import datetime
from lxml import etree

from src.application.pipeline.base import Step
from src.domain.models.eu_normativa import (
    EUNormativa, EUMetadata, EUAnalysis, EUReferencia,
    EUDocumentType, EUDocumentStatus, EUInstitution,
    celex_to_document_type
)
from src.domain.models.common.node import Node, NodeType, ArticleNode, StructureNode

logger = logging.getLogger(__name__)


class EUDataProcessor(Step):
    """
    Parses FORMEX XML to EUNormativa domain models.
    
    FORMEX (FORMalized EXchange of electronic documents) is the 
    standard XML format for EU legal texts.
    
    Structure overview:
    - <ACT> root element
    - <TITLE.GEN> document title
    - <PREAMBLE> contains citations and recitals
    - <ENACTING.TERMS> main body with articles
    - <FINAL> final provisions
    """
    
    # FORMEX namespaces (may vary by version)
    NAMESPACES = {
        'fmx': 'http://publications.europa.eu/resource/schema/fp/fmx/nfo#',
    }
    
    def __init__(self, name: str = "eu_data_processor", enable_table_parsing: bool = False):
        super().__init__(name)
        self.enable_table_parsing = enable_table_parsing
    
    def process(self, data: dict) -> Tuple[Optional[EUNormativa], List]:
        """
        Process EU document data into domain models.
        
        Args:
            data: Dictionary with keys:
                - 'content': FORMEX XML bytes (possibly zipped)
                - 'metadata': Metadata from branch notice (optional)
                - 'celex': CELEX number
                
        Returns:
            Tuple of (EUNormativa, change_events)
            change_events is currently empty for EU docs
        """
        content = data.get('content')
        metadata_dict = data.get('metadata', {})
        celex = data.get('celex', '')
        
        if not content:
            logger.warning("No content provided for EU document processing")
            return None, []
        
        # Extract XML from zip if necessary
        xml_content = self._extract_formex(content)
        if not xml_content:
            logger.warning("Could not extract FORMEX XML")
            return None, []
        
        try:
            root = etree.fromstring(xml_content)
        except etree.XMLSyntaxError as e:
            logger.error(f"Failed to parse FORMEX XML: {e}")
            return None, []
        
        # Build metadata
        metadata = self._build_metadata(root, metadata_dict, celex)
        
        # Build analysis (references, classifications)
        analysis = self._build_analysis(root)
        
        # Build content tree
        content_tree = self._build_content_tree(root, metadata.title)
        
        normativa = EUNormativa(
            id=celex or metadata.celex_number,
            metadata=metadata,
            analysis=analysis,
            content_tree=content_tree
        )
        
        logger.info(f"Parsed EU document: {normativa.id} with {self._count_articles(content_tree)} articles")
        
        return normativa, []
    
    def _extract_formex(self, content: bytes) -> Optional[bytes]:
        """Extract FORMEX XML from zip if necessary."""
        # Check if content is a zip file
        if content[:4] == b'PK\x03\x04':
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    # Find the main XML file
                    for name in zf.namelist():
                        if name.endswith('.xml') and 'META-INF' not in name:
                            return zf.read(name)
                    # Fallback: first XML file
                    for name in zf.namelist():
                        if name.endswith('.xml'):
                            return zf.read(name)
            except zipfile.BadZipFile:
                logger.warning("Invalid zip file")
                return None
        
        # Already XML
        return content
    
    def _build_metadata(self, root: etree._Element, metadata_dict: dict, celex: str) -> EUMetadata:
        """Extract metadata from FORMEX and branch notice."""
        
        # Try to get title from various FORMEX locations
        title = ""
        title_elem = root.find('.//TITLE') or root.find('.//TI.CJT') or root.find('.//TITLE.GEN')
        if title_elem is not None:
            title = self._get_text_content(title_elem)
        
        # Override with branch notice metadata if available
        title = metadata_dict.get('title', title) or title
        
        # Extract CELEX from document if not provided
        if not celex:
            dn_elem = root.find('.//BIB.INSTANCE//DN') or root.find('.//DN')
            if dn_elem is not None:
                celex = dn_elem.text or ''
        
        # Document type from CELEX
        doc_type = celex_to_document_type(celex)
        
        # Dates
        date_document = self._parse_date(metadata_dict.get('date_document'))
        date_publication = self._parse_date(metadata_dict.get('date_publication'))
        date_entry_into_force = self._parse_date(metadata_dict.get('date_entry_into_force'))
        
        # OJ reference
        oj_ref = None
        oj_elem = root.find('.//GR.SEQ//INT.REF.OJ') or root.find('.//LG.OJ')
        if oj_elem is not None:
            oj_ref = self._get_text_content(oj_elem)
        
        # Author/Institution
        author = None
        author_str = metadata_dict.get('author', '').upper()
        if 'COMMISSION' in author_str:
            author = EUInstitution.COMMISSION
        elif 'PARLIAMENT' in author_str:
            author = EUInstitution.PARLIAMENT
        elif 'COUNCIL' in author_str:
            author = EUInstitution.COUNCIL
        
        return EUMetadata(
            celex_number=celex,
            cellar_id=metadata_dict.get('cellar_id'),
            eli_uri=metadata_dict.get('eli'),
            document_type=doc_type,
            author=author,
            title=title,
            short_title=metadata_dict.get('short_title'),
            date_document=date_document,
            date_publication=date_publication,
            date_entry_into_force=date_entry_into_force,
            oj_reference=oj_ref,
            status=EUDocumentStatus.IN_FORCE,  # Default; can be updated from metadata
            is_consolidated=metadata_dict.get('consolidated', False),
            directory_codes=metadata_dict.get('directory_codes', []),
            eurovoc_descriptors=metadata_dict.get('eurovoc', []),
            url_eurlex=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
            last_modified=self._parse_date(metadata_dict.get('last_modified'))
        )
    
    def _build_analysis(self, root: etree._Element) -> EUAnalysis:
        """Extract analysis data from FORMEX."""
        legal_basis = []
        
        # Find legal basis citations in preamble
        for visa in root.findall('.//GR.VISA') or []:
            for ref in visa.findall('.//REF.DOC.OJ') or visa.findall('.//INT.REF'):
                celex_ref = ref.get('CELEX') or ref.get('REF') or ''
                text = self._get_text_content(ref)
                if celex_ref or text:
                    legal_basis.append(EUReferencia(
                        target_celex=celex_ref,
                        reference_type='legal_basis',
                        text=text
                    ))
        
        return EUAnalysis(
            legal_basis=legal_basis
        )
    
    def _build_content_tree(self, root: etree._Element, title: str) -> Node:
        """
        Build hierarchical Node tree from FORMEX content.
        
        Maps FORMEX elements to existing NodeType values for
        compatibility with BOE document structure.
        """
        # Create root node
        root_node = Node(
            id="root",
            name=title or "EU Document",
            level=0,
            node_type=NodeType.ROOT
        )
        
        # Find main content container
        enacting = root.find('.//ENACTING.TERMS') or root.find('.//BODY')
        
        if enacting is not None:
            self._process_structural_content(enacting, root_node, level=1)
        else:
            # Fallback: process entire root
            self._process_structural_content(root, root_node, level=1)
        
        return root_node
    
    def _process_structural_content(self, element: etree._Element, parent: Node, level: int):
        """Recursively process FORMEX structural elements."""
        
        for child in element:
            tag = self._clean_tag(child.tag)
            
            if tag in ('TITLE', 'TITRE'):
                # Title/Chapter structure
                node = self._create_title_node(child, level)
                if node:
                    parent.add_child(node)
                    self._process_structural_content(child, node, level + 1)
                    
            elif tag in ('CHAPTER', 'CHAPITRE'):
                node = self._create_chapter_node(child, level)
                if node:
                    parent.add_child(node)
                    self._process_structural_content(child, node, level + 1)
                    
            elif tag in ('SECTION',):
                node = self._create_section_node(child, level)
                if node:
                    parent.add_child(node)
                    self._process_structural_content(child, node, level + 1)
                    
            elif tag in ('ARTICLE',):
                node = self._create_article_node(child, level)
                if node:
                    parent.add_child(node)
                    
            elif tag in ('DIVISION', 'SUBDIV', 'PART'):
                # Generic division - map to appropriate type
                node = self._create_division_node(child, level, tag)
                if node:
                    parent.add_child(node)
                    self._process_structural_content(child, node, level + 1)
            
            elif tag in ('GR.SEQ', 'QUOT.S'):
                # Container elements - process children directly
                self._process_structural_content(child, parent, level)
    
    def _create_title_node(self, element: etree._Element, level: int) -> Optional[Node]:
        """Create a TITULO node from FORMEX TITLE element."""
        # Get title number/name
        no_elem = element.find('.//NO.TITLE') or element.find('.//NO.TI') or element.find('.//NO')
        ti_elem = element.find('.//TI.TITLE') or element.find('.//TI')
        
        number = no_elem.text.strip() if no_elem is not None and no_elem.text else ""
        title_text = self._get_text_content(ti_elem) if ti_elem is not None else ""
        
        name = f"{number}" if number else "Título"
        
        node = StructureNode(
            id=f"titulo_{number or level}",
            name=name,
            level=level,
            node_type=NodeType.TITULO,
            text=title_text
        )
        
        return node
    
    def _create_chapter_node(self, element: etree._Element, level: int) -> Optional[Node]:
        """Create a CAPITULO node from FORMEX CHAPTER element."""
        no_elem = element.find('.//NO.CHAPTER') or element.find('.//NO')
        ti_elem = element.find('.//TI.CHAPTER') or element.find('.//TI')
        
        number = no_elem.text.strip() if no_elem is not None and no_elem.text else ""
        title_text = self._get_text_content(ti_elem) if ti_elem is not None else ""
        
        name = f"Capítulo {number}" if number else "Capítulo"
        
        return StructureNode(
            id=f"capitulo_{number or level}",
            name=name,
            level=level,
            node_type=NodeType.CAPITULO,
            text=title_text
        )
    
    def _create_section_node(self, element: etree._Element, level: int) -> Optional[Node]:
        """Create a SECCION node from FORMEX SECTION element."""
        no_elem = element.find('.//NO.SECTION') or element.find('.//NO')
        ti_elem = element.find('.//TI.SECTION') or element.find('.//TI')
        
        number = no_elem.text.strip() if no_elem is not None and no_elem.text else ""
        title_text = self._get_text_content(ti_elem) if ti_elem is not None else ""
        
        name = f"Sección {number}" if number else "Sección"
        
        return StructureNode(
            id=f"seccion_{number or level}",
            name=name,
            level=level,
            node_type=NodeType.SECCION,
            text=title_text
        )
    
    def _create_article_node(self, element: etree._Element, level: int) -> Optional[ArticleNode]:
        """Create an ArticleNode from FORMEX ARTICLE element."""
        # Article number
        no_elem = element.find('.//NO.ARTICLE') or element.find('.//NO')
        ti_elem = element.find('.//TI.ARTICLE') or element.find('.//TI.ART')
        
        number = ""
        if no_elem is not None:
            number = no_elem.text.strip() if no_elem.text else ""
            # Clean up "Article 1" to just "1"
            number = re.sub(r'^Art[íi]culo\s*', '', number, flags=re.IGNORECASE)
            number = re.sub(r'^Article\s*', '', number, flags=re.IGNORECASE)
        
        title = self._get_text_content(ti_elem) if ti_elem is not None else ""
        
        # Get article content (paragraphs/alineas)
        content_parts = []
        for para in element.findall('.//ALINEA') or element.findall('.//P'):
            para_text = self._get_text_content(para)
            if para_text:
                content_parts.append(para_text.strip())
        
        # Also get numbered paragraphs
        for point in element.findall('.//POINT'):
            point_text = self._get_text_content(point)
            if point_text:
                content_parts.append(point_text.strip())
        
        full_text = "\n".join(content_parts)
        
        name = f"Artículo {number}" if number else f"Artículo {level}"
        
        return ArticleNode(
            id=f"articulo_{number or level}",
            name=name,
            level=level,
            node_type=NodeType.ARTICULO,
            text=full_text
        )
    
    def _create_division_node(self, element: etree._Element, level: int, tag: str) -> Optional[Node]:
        """Create a generic division node."""
        no_elem = element.find('.//NO')
        ti_elem = element.find('.//TI')
        
        number = no_elem.text.strip() if no_elem is not None and no_elem.text else ""
        title_text = self._get_text_content(ti_elem) if ti_elem is not None else ""
        
        # Map to closest NodeType
        if 'PART' in tag.upper():
            node_type = NodeType.LIBRO
            name = f"Parte {number}" if number else "Parte"
        else:
            node_type = NodeType.SECCION
            name = number or "División"
        
        return StructureNode(
            id=f"division_{number or level}",
            name=name,
            level=level,
            node_type=node_type,
            text=title_text
        )
    
    def _get_text_content(self, element: etree._Element) -> str:
        """Get all text content from element, including nested elements."""
        if element is None:
            return ""
        
        # Get all text including tail text of children
        texts = []
        
        if element.text:
            texts.append(element.text)
        
        for child in element:
            texts.append(self._get_text_content(child))
            if child.tail:
                texts.append(child.tail)
        
        return ' '.join(t.strip() for t in texts if t and t.strip())
    
    def _clean_tag(self, tag: str) -> str:
        """Remove namespace from tag."""
        if '}' in tag:
            return tag.split('}')[1]
        return tag
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None
        
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%Y%m%d',
            '%d-%m-%Y',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str[:10], fmt)
            except (ValueError, TypeError):
                continue
        
        return None
    
    def _count_articles(self, node: Node) -> int:
        """Count ArticleNode instances in tree."""
        count = 1 if node.node_type == NodeType.ARTICULO else 0
        for child in node.content or []:
            if isinstance(child, Node):
                count += self._count_articles(child)
        return count
