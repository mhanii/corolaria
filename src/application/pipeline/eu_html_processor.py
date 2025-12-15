"""
EU HTML Parser for EUR-Lex documents.

Parses HTML from EUR-Lex public endpoint into domain models.
This is an alternative to FORMEX parsing, working with the HTML format
available without SOAP credentials.
"""

import re
import logging
from typing import Optional, Tuple, List
from datetime import datetime
from lxml import html as lhtml

from src.application.pipeline.base import Step
from src.domain.models.eu_normativa import (
    EUNormativa, EUMetadata, EUAnalysis,
    EUDocumentType, EUDocumentStatus,
    celex_to_document_type
)
from src.domain.models.common.node import Node, NodeType, ArticleNode, StructureNode

logger = logging.getLogger(__name__)


class EUHTMLProcessor(Step):
    """
    Parses EUR-Lex HTML to EUNormativa domain models.
    
    This parser handles the HTML format from:
    https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}
    
    HTML Structure:
    - .ti-section-1, .ti-section-2: Title/Chapter headings
    - .ti-art: Article title (Artículo N)
    - .sti-art: Article subtitle
    - .normal: Article content paragraphs
    - .doc-ti: Document title
    
    OJ (Official Journal) format (for regulations/directives):
    - .oj-ti-art: Article title
    - .oj-sti-art, .eli-title: Article subtitle
    - .oj-ti-section-1, .oj-ti-section-2: Section titles
    - .oj-normal: Content paragraphs
    - Empty class div: Content paragraphs (common in OJ format)
    """
    
    # CSS class patterns - support both treaty and OJ formats
    TITLE_CLASSES = ['ti-section-1', 'ti-section-2', 'ti-grseq-1', 
                     'oj-ti-section-1', 'oj-ti-section-2']
    ARTICLE_TITLE_CLASSES = ['ti-art', 'oj-ti-art']  # Multiple possible classes
    ARTICLE_SUBTITLE_CLASSES = ['sti-art', 'oj-sti-art', 'eli-title']
    CONTENT_CLASSES = ['normal', 'oj-normal']
    DOC_TITLE_CLASS = 'doc-ti'
    
    def __init__(self, name: str = "eu_html_processor"):
        super().__init__(name)
    
    def process(self, data: dict) -> Tuple[Optional[EUNormativa], List]:
        """
        Process EU document into domain models.
        
        Supports two formats:
        1. HTML from EUR-Lex public endpoint
        2. Text format from local cached files ([TITULO], [ARTICULO] markers)
        
        Args:
            data: Dictionary with keys:
                - 'html': HTML/text content string
                - 'celex': CELEX number
                - 'language': Language code (optional)
                - 'source': 'local' or 'eurlex' (optional)
                
        Returns:
            Tuple of (EUNormativa, change_events)
        """
        content = data.get('html') or data.get('content')
        celex = data.get('celex', '')
        source = data.get('source', 'eurlex')
        
        if not content:
            logger.warning("No HTML content provided")
            return None, []
        
        # Handle bytes
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        # Detect format: text format uses [TITULO], [ARTICULO] markers
        if self._is_text_format(content):
            logger.info(f"Detected text format for {celex}, using text parser")
            return self._parse_text_format(content, celex)
        
        # HTML format
        try:
            doc = lhtml.fromstring(content.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return None, []
        
        # Build metadata
        metadata = self._build_metadata(doc, celex)
        
        # Build analysis (minimal for HTML)
        analysis = EUAnalysis()
        
        # Build content tree
        content_tree = self._build_content_tree(doc, metadata.title)
        
        normativa = EUNormativa(
            id=celex,
            metadata=metadata,
            analysis=analysis,
            content_tree=content_tree
        )
        
        article_count = self._count_articles(content_tree)
        logger.info(f"Parsed EU HTML document: {celex} with {article_count} articles")
        
        return normativa, []
    
    def _is_text_format(self, content: str) -> bool:
        """Check if content is in local text format (not HTML)."""
        # Text format starts with header or has [TITULO]/[ARTICULO] markers
        if content.strip().startswith('=' * 10):
            return True
        if '[TITULO]' in content[:1000] or '[ARTICULO]' in content[:2000]:
            return True
        # HTML typically starts with < and has html/body tags
        if content.strip().startswith('<') and ('<html' in content[:500].lower() or '<body' in content[:500].lower()):
            return False
        return '[ARTICULO]' in content  # Fallback check
    
    def _parse_text_format(self, content: str, celex: str) -> Tuple[Optional[EUNormativa], List]:
        """Parse local cached text format into domain models."""
        lines = content.split('\n')
        
        # Extract header metadata
        title = ""
        doc_type = None
        
        for line in lines[:10]:
            if line.startswith('TÍTULO:'):
                title = line.replace('TÍTULO:', '').strip()
            elif line.startswith('TIPO:'):
                type_str = line.replace('TIPO:', '').strip()
                if 'TREATY' in type_str:
                    doc_type = EUDocumentType.TREATY
                elif 'REGULATION' in type_str:
                    doc_type = EUDocumentType.REGULATION
                elif 'DIRECTIVE' in type_str:
                    doc_type = EUDocumentType.DIRECTIVE
        
        # Build metadata
        metadata = EUMetadata(
            celex_number=celex,
            document_type=doc_type or celex_to_document_type(celex),
            title=title or f"EU Document {celex}",
            url_eurlex=f"https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{celex}"
        )
        
        # Build content tree from text markers
        root_node = Node(
            id="root",
            name=title or "EU Document",
            level=0,
            node_type=NodeType.ROOT
        )
        
        current_titulo = None
        current_capitulo = None
        article_counter = 0
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('[TITULO]'):
                titulo_name = line.replace('[TITULO]', '').strip()
                current_titulo = StructureNode(
                    id=f"titulo_{titulo_name[:20]}",
                    name=titulo_name,
                    level=1,
                    node_type=NodeType.TITULO,
                    text=""
                )
                root_node.add_child(current_titulo)
                current_capitulo = None  # Reset chapter
                
            elif line.startswith('[CAPITULO]'):
                capitulo_name = line.replace('[CAPITULO]', '').strip()
                current_capitulo = StructureNode(
                    id=f"capitulo_{capitulo_name[:20]}",
                    name=capitulo_name,
                    level=2,
                    node_type=NodeType.CAPITULO,
                    text=""
                )
                if current_titulo:
                    current_titulo.add_child(current_capitulo)
                else:
                    root_node.add_child(current_capitulo)
                    
            elif line.startswith('[ARTICULO]'):
                article_counter += 1
                # Parse article header: "Artículo N: Title"
                article_header = line.replace('[ARTICULO]', '').strip()
                
                # Extract article number and title
                match = re.match(r'Artículo\s+(\d+)(?:\s*:\s*(.+))?', article_header, re.IGNORECASE)
                if match:
                    art_num = match.group(1)
                    art_title = match.group(2) or ""
                else:
                    art_num = str(article_counter)
                    art_title = article_header
                
                # Collect article content until next marker
                article_text_lines = []
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line.startswith('[') and next_line.endswith(']'):
                        # Don't consume this line, break
                        i -= 1
                        break
                    if next_line.startswith('[TITULO]') or next_line.startswith('[CAPITULO]') or next_line.startswith('[ARTICULO]'):
                        i -= 1
                        break
                    if next_line:
                        article_text_lines.append(next_line)
                    i += 1
                
                article_text = '\n'.join(article_text_lines)
                
                article_node = ArticleNode(
                    id=f"{celex}_art_{art_num}",
                    name=f"Artículo {art_num}" + (f": {art_title}" if art_title else ""),
                    level=3,
                    node_type=NodeType.ARTICULO,
                    text=article_text
                )
                
                # Add to appropriate parent
                if current_capitulo:
                    current_capitulo.add_child(article_node)
                elif current_titulo:
                    current_titulo.add_child(article_node)
                else:
                    root_node.add_child(article_node)
            
            i += 1
        
        normativa = EUNormativa(
            id=celex,
            metadata=metadata,
            analysis=EUAnalysis(),
            content_tree=root_node
        )
        
        article_count = self._count_articles(root_node)
        logger.info(f"Parsed EU text document: {celex} with {article_count} articles")
        
        return normativa, []

    
    def _build_metadata(self, doc, celex: str) -> EUMetadata:
        """Extract metadata from HTML document."""
        
        # Try to find document title
        title = ""
        title_els = doc.xpath(f'//*[@class="{self.DOC_TITLE_CLASS}"]')
        if title_els:
            title = title_els[0].text_content().strip()
        
        # Fallback: look for first heading
        if not title:
            h1s = doc.xpath('//h1')
            if h1s:
                title = h1s[0].text_content().strip()
        
        # Fallback: use <title> tag
        if not title:
            title_tags = doc.xpath('//title')
            if title_tags:
                title = title_tags[0].text_content().strip()
        
        # Document type from CELEX
        doc_type = celex_to_document_type(celex)
        
        # Check if it's a treaty (sector 1)
        if celex.startswith('1'):
            doc_type = EUDocumentType.TREATY
        
        return EUMetadata(
            celex_number=celex,
            title=title[:500] if title else f"EU Document {celex}",
            document_type=doc_type,
            status=EUDocumentStatus.IN_FORCE,
            source="EUR-Lex",
            url_eurlex=f"https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{celex}"
        )
    
    def _build_content_tree(self, doc, title: str) -> Node:
        """
        Build hierarchical Node tree from HTML content.
        
        Uses document order via xpath to handle articles across multiple div containers.
        """
        root_node = Node(
            id="root",
            name=title or "EU Document",
            level=0,
            node_type=NodeType.ROOT
        )
        
        # Build xpath for all structural elements (both treaty and OJ formats)
        title_xpath = ' or '.join([f'@class="{tc}"' for tc in self.TITLE_CLASSES])
        article_xpath = ' or '.join([f'@class="{ac}"' for ac in self.ARTICLE_TITLE_CLASSES])
        
        all_elements = doc.xpath(f'//*[{title_xpath} or {article_xpath}]')
        
        if not all_elements:
            return root_node
        
        current_title = None
        article_count = 0
        
        for elem in all_elements:
            cls = elem.get('class', '')
            
            # Section/Title
            if cls in self.TITLE_CLASSES:
                text = elem.text_content().strip()
                if text:
                    level = 1 if 'section-1' in cls or 'grseq-1' in cls else 2
                    
                    current_title = StructureNode(
                        id=f"titulo_{len(root_node.content or [])}",
                        name=text[:100],
                        level=level,
                        node_type=NodeType.TITULO if level == 1 else NodeType.CAPITULO,
                        text=""
                    )
                    root_node.add_child(current_title)
            
            # Article
            elif cls in self.ARTICLE_TITLE_CLASSES:
                text = elem.text_content().strip()
                if text:
                    article_count += 1
                    
                    # Extract article number
                    match = re.search(r'Artículo\s+(\d+)', text, re.IGNORECASE)
                    if not match:
                        match = re.search(r'Article\s+(\d+)', text, re.IGNORECASE)
                    art_num = match.group(1) if match else str(article_count)
                    
                    # Collect content from following siblings
                    article_name = f"Artículo {art_num}"
                    content_parts = []
                    
                    sib = elem.getnext()
                    while sib is not None:
                        sib_cls = sib.get('class', '')
                        
                        # Stop at next article or section
                        if sib_cls in self.ARTICLE_TITLE_CLASSES or sib_cls in self.TITLE_CLASSES:
                            break
                        
                        # Article subtitle
                        if sib_cls in self.ARTICLE_SUBTITLE_CLASSES:
                            subtitle = sib.text_content().strip()
                            if subtitle:
                                article_name = f"Artículo {art_num}: {subtitle[:50]}"
                        
                        # Content paragraph - check for content classes or empty p/div
                        elif sib_cls in self.CONTENT_CLASSES or (sib.tag in ('p', 'div') and not sib_cls):
                            para_text = sib.text_content().strip()
                            if para_text:
                                content_parts.append(para_text)
                        
                        sib = sib.getnext()
                    
                    # Create article node
                    article_node = ArticleNode(
                        id=f"articulo_{art_num}",
                        name=article_name,
                        level=current_title.level + 1 if current_title else 2,
                        node_type=NodeType.ARTICULO,
                        text='\n'.join(content_parts)
                    )
                    
                    # Add to current title or root
                    if current_title:
                        current_title.add_child(article_node)
                    else:
                        root_node.add_child(article_node)
        
        return root_node
    
    def _count_articles(self, node: Node) -> int:
        """Count ArticleNode instances in tree."""
        count = 1 if node.node_type == NodeType.ARTICULO else 0
        for child in node.content or []:
            if isinstance(child, Node):
                count += self._count_articles(child)
        return count
