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
        Process EU HTML document into domain models.
        
        Args:
            data: Dictionary with keys:
                - 'html': HTML content string
                - 'celex': CELEX number
                - 'language': Language code (optional)
                
        Returns:
            Tuple of (EUNormativa, change_events)
        """
        html_content = data.get('html') or data.get('content')
        celex = data.get('celex', '')
        
        if not html_content:
            logger.warning("No HTML content provided")
            return None, []
        
        # Handle bytes
        if isinstance(html_content, bytes):
            html_content = html_content.decode('utf-8')
        
        try:
            doc = lhtml.fromstring(html_content.encode('utf-8'))
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
