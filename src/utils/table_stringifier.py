"""
Table Stringifier Utility.

Converts parsed table dictionaries from BOE XML to human-readable strings
suitable for embedding and RAG retrieval.

Table dict structure from xmltodict (after XML parsing):
{
    '@class': 'tabla',
    'tr': [
        {'td': [{'p': 'Header1'}, {'p': 'Header2'}]},  # Row 1
        {'td': [{'p': 'Description'}, {'p': '100,38'}]},  # Row 2
        ...
    ]
}

Or with tbody:
{
    '@class': 'tabla',
    'tbody': {
        'tr': [...]
    }
}
"""
from typing import Any, Dict, List, Optional, Union


def _deep_extract_text(obj: Any) -> str:
    """
    Recursively extract all text content from a nested structure.
    
    Handles:
    - Strings
    - Dicts with various keys (p, em, #text, etc.)
    - Lists of the above
    - Nested combinations
    
    Args:
        obj: Any nested structure
        
    Returns:
        Concatenated text content
    """
    if obj is None:
        return ""
    
    if isinstance(obj, str):
        return obj.strip()
    
    if isinstance(obj, dict):
        texts = []
        
        # Check for direct text content
        if '#text' in obj:
            texts.append(str(obj['#text']).strip())
        
        # Check common content keys
        for key in ['p', 'em', 'strong', 'span', 'a']:
            if key in obj:
                texts.append(_deep_extract_text(obj[key]))
        
        # If no recognized keys found, try all non-@ keys
        if not texts:
            for key, value in obj.items():
                # Skip non-string keys and attribute keys
                if isinstance(key, str) and not key.startswith('@'):
                    texts.append(_deep_extract_text(value))
        
        return ' '.join(t for t in texts if t)
    
    if isinstance(obj, list):
        texts = [_deep_extract_text(item) for item in obj]
        return ' '.join(t for t in texts if t)
    
    return str(obj).strip()


def _extract_row_cells(row: Any) -> List[str]:
    """
    Extract all cell texts from a table row.
    
    Args:
        row: Row dict with 'td' key containing cells
        
    Returns:
        List of cell text strings
    """
    if row is None:
        return []
    
    if isinstance(row, dict):
        # Get 'td' content - the cells
        td_content = row.get('td', [])
        
        if isinstance(td_content, list):
            # td_content is a list of cell dicts
            return [_deep_extract_text(cell) for cell in td_content]
        else:
            # Single cell
            return [_deep_extract_text(td_content)]
    
    if isinstance(row, list):
        return [_deep_extract_text(cell) for cell in row]
    
    return [_deep_extract_text(row)]


def _get_rows_from_table(table_dict: Dict[str, Any]) -> List[Any]:
    """
    Extract rows from table dict, handling various structures.
    
    Handles:
    - Direct 'tr' key
    - Nested in 'tbody'
    - Multiple tbody elements
    
    Args:
        table_dict: Parsed table dictionary
        
    Returns:
        List of row elements
    """
    # Try direct 'tr' first
    rows = table_dict.get('tr', [])
    if rows:
        return rows if isinstance(rows, list) else [rows]
    
    # Try 'tbody'
    tbody = table_dict.get('tbody', {})
    if isinstance(tbody, dict):
        rows = tbody.get('tr', [])
        return rows if isinstance(rows, list) else [rows]
    elif isinstance(tbody, list):
        # Multiple tbody elements
        all_rows = []
        for tb in tbody:
            if isinstance(tb, dict):
                tb_rows = tb.get('tr', [])
                if isinstance(tb_rows, list):
                    all_rows.extend(tb_rows)
                else:
                    all_rows.append(tb_rows)
        return all_rows
    
    return []


def stringify_table(table_dict: Dict[str, Any], format: str = "markdown") -> str:
    """
    Convert a parsed table dictionary to a human-readable string.
    
    Args:
        table_dict: Table dictionary from XML parsing
        format: Output format - "markdown" (default) or "lines"
        
    Returns:
        Stringified table content in markdown table format
        
    Example input:
        {'@class': 'tabla', 'tr': [
            {'td': [{'p': ''}, {'p': 'Euros'}]},
            {'td': [{'p': 'Patent fee'}, {'p': '100,38'}]}
        ]}
        
    Example output (markdown format):
        | Concepto | Euros |
        |----------|-------|
        | Patent fee | 100,38 |
    """
    if not table_dict or not isinstance(table_dict, dict):
        return ""
    
    rows = _get_rows_from_table(table_dict)
    if not rows:
        return ""
    
    # Determine number of columns from first row with content
    max_cols = 0
    parsed_rows = []
    
    for row in rows:
        cells = _extract_row_cells(row)
        # Replace empty cells with dash for clarity
        cells = [c.strip() if c and c.strip() else "-" for c in cells]
        if any(c != "-" for c in cells):  # Skip fully empty rows
            parsed_rows.append(cells)
            max_cols = max(max_cols, len(cells))
    
    if not parsed_rows or max_cols == 0:
        return ""
    
    # Normalize all rows to have same number of columns
    normalized_rows = []
    for cells in parsed_rows:
        while len(cells) < max_cols:
            cells.append("-")
        normalized_rows.append(cells)
    
    output_lines = []
    
    if format == "markdown":
        # First row as header
        header_row = normalized_rows[0]
        output_lines.append("| " + " | ".join(header_row) + " |")
        
        # Separator row
        separator = "|" + "|".join(["---" for _ in range(max_cols)]) + "|"
        output_lines.append(separator)
        
        # Data rows
        for cells in normalized_rows[1:]:
            output_lines.append("| " + " | ".join(cells) + " |")
    else:
        # Lines format (fallback)
        for cells in normalized_rows:
            non_empty = [c for c in cells if c != "-"]
            if len(non_empty) == 1:
                output_lines.append(non_empty[0])
            elif len(non_empty) == 2:
                output_lines.append(f"{non_empty[0]}: {non_empty[1]}")
            else:
                output_lines.append(" | ".join(non_empty))
    
    return "\n".join(output_lines)


def stringify_element_content(content: Any) -> str:
    """
    Stringify element content, handling both strings and table dicts.
    
    This is the main entry point for the data processing pipeline.
    
    Args:
        content: Either a string or a table dict
        
    Returns:
        String content suitable for text processing
    """
    if content is None:
        return ""
    
    if isinstance(content, str):
        return content
    
    if isinstance(content, dict):
        # Check if it looks like a table
        if 'tr' in content or 'tbody' in content:
            return stringify_table(content)
        
        # Could be other structured content - extract all text
        return _deep_extract_text(content)
    
    # List or other - try to extract text
    return _deep_extract_text(content)
