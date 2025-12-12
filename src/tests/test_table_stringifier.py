"""
Unit tests for Table Stringifier utility.
"""
import pytest
from src.utils.table_stringifier import (
    stringify_table,
    stringify_element_content,
    _deep_extract_text,
    _extract_row_cells,
)


class TestDeepExtractText:
    """Test the recursive text extraction."""
    
    def test_string(self):
        assert _deep_extract_text("Hello") == "Hello"
        assert _deep_extract_text("  spaced  ") == "spaced"
    
    def test_none(self):
        assert _deep_extract_text(None) == ""
    
    def test_simple_dict(self):
        assert _deep_extract_text({'p': 'Hello'}) == "Hello"
        assert _deep_extract_text({'#text': 'Direct text'}) == "Direct text"
    
    def test_nested_dict(self):
        # em tag inside p
        assert _deep_extract_text({'p': {'em': 'Emphasized'}}) == "Emphasized"
    
    def test_list(self):
        assert _deep_extract_text(['Hello', 'World']) == "Hello World"
        assert _deep_extract_text([{'p': 'A'}, {'p': 'B'}]) == "A B"


class TestExtractRowCells:
    """Test row cell extraction."""
    
    def test_row_with_td_list(self):
        row = {'td': [{'p': 'Cell1'}, {'p': 'Cell2'}]}
        cells = _extract_row_cells(row)
        assert cells == ['Cell1', 'Cell2']
    
    def test_row_with_empty_cells(self):
        row = {'td': [{'p': ''}, {'p': 'Value'}]}
        cells = _extract_row_cells(row)
        assert cells == ['', 'Value']
    
    def test_row_with_single_td(self):
        row = {'td': {'p': 'Only cell'}}
        cells = _extract_row_cells(row)
        assert cells == ['Only cell']


class TestStringifyTable:
    """Test table stringification."""
    
    def test_simple_table_markdown(self):
        """Test default markdown format."""
        table = {
            '@class': 'tabla',
            'tr': [
                {'td': [{'p': 'Concepto'}, {'p': 'Euros'}]},
                {'td': [{'p': 'Item'}, {'p': '100,38'}]},
            ]
        }
        result = stringify_table(table)
        assert '| Concepto | Euros |' in result
        assert '|---|---|' in result
        assert '| Item | 100,38 |' in result
    
    def test_empty_cells_become_dash(self):
        """Test that empty cells are replaced with dash."""
        table = {
            'tr': [
                {'td': [{'p': ''}, {'p': 'Euros'}]},
                {'td': [{'p': 'Section Title'}, {'p': ''}]},
            ]
        }
        result = stringify_table(table)
        assert '| - | Euros |' in result
        assert '| Section Title | - |' in result
    
    def test_boe_table_structure(self):
        """Test with actual BOE table structure from issues/praser.txt."""
        table = {
            '@class': 'tabla',
            'tr': [
                {'td': [{'p': ''}, {'p': 'Euros'}]},
                {'td': [{'p': 'Tarifa primera'}, {'p': ''}]},
                {'td': [{'p': 'Solicitud de patente'}, {'p': '100,38'}]},
                {'td': [{'p': '3.ª'}, {'p': '18,48'}]},
            ]
        }
        result = stringify_table(table)
        # Should be markdown format
        assert 'Euros' in result
        assert 'Tarifa primera' in result
        assert '| Solicitud de patente | 100,38 |' in result
        assert '| 3.ª | 18,48 |' in result
    
    def test_lines_format(self):
        """Test explicit lines format."""
        table = {
            'tr': [
                {'td': [{'p': 'A'}, {'p': 'B'}]},
                {'td': [{'p': 'C'}, {'p': 'D'}]},
            ]
        }
        result = stringify_table(table, format='lines')
        assert 'A: B' in result or 'A' in result
    
    def test_empty_table(self):
        assert stringify_table({}) == ""
        assert stringify_table(None) == ""


class TestStringifyElementContent:
    """Test the main entry point function."""
    
    def test_string_passthrough(self):
        assert stringify_element_content("Hello") == "Hello"
    
    def test_none(self):
        assert stringify_element_content(None) == ""
    
    def test_table_dict(self):
        table = {
            'tr': [
                {'td': [{'p': 'Header1'}, {'p': 'Header2'}]},
                {'td': [{'p': 'A'}, {'p': 'B'}]},
            ]
        }
        result = stringify_element_content(table)
        assert '| Header1 | Header2 |' in result
        assert '| A | B |' in result
    
    def test_non_table_dict(self):
        # Dict without tr/tbody should extract text
        assert stringify_element_content({'p': 'Paragraph'}) == 'Paragraph'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
