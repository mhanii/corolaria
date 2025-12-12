"""
Unit tests for Spanish number converter utility.
"""
import pytest
from src.utils.spanish_number_converter import (
    spanish_words_to_number,
    normalize_article_number,
    _parse_cardinal,
    _parse_ordinal,
)


class TestSpanishCardinalNumbers:
    """Test cardinal number conversion."""
    
    def test_units(self):
        """Test basic unit numbers 0-9."""
        assert spanish_words_to_number("cero") == 0
        assert spanish_words_to_number("uno") == 1
        assert spanish_words_to_number("un") == 1
        assert spanish_words_to_number("una") == 1
        assert spanish_words_to_number("dos") == 2
        assert spanish_words_to_number("tres") == 3
        assert spanish_words_to_number("cuatro") == 4
        assert spanish_words_to_number("cinco") == 5
        assert spanish_words_to_number("seis") == 6
        assert spanish_words_to_number("siete") == 7
        assert spanish_words_to_number("ocho") == 8
        assert spanish_words_to_number("nueve") == 9
    
    def test_teens(self):
        """Test numbers 10-19."""
        assert spanish_words_to_number("diez") == 10
        assert spanish_words_to_number("once") == 11
        assert spanish_words_to_number("doce") == 12
        assert spanish_words_to_number("trece") == 13
        assert spanish_words_to_number("catorce") == 14
        assert spanish_words_to_number("quince") == 15
        assert spanish_words_to_number("dieciséis") == 16
        assert spanish_words_to_number("dieciseis") == 16  # without accent
        assert spanish_words_to_number("diecisiete") == 17
        assert spanish_words_to_number("dieciocho") == 18
        assert spanish_words_to_number("diecinueve") == 19
    
    def test_twenties(self):
        """Test numbers 20-29."""
        assert spanish_words_to_number("veinte") == 20
        assert spanish_words_to_number("veintiuno") == 21
        assert spanish_words_to_number("veintiún") == 21
        assert spanish_words_to_number("veintidós") == 22
        assert spanish_words_to_number("veintidos") == 22
        assert spanish_words_to_number("veintitrés") == 23
        assert spanish_words_to_number("veintitres") == 23
        assert spanish_words_to_number("veinticuatro") == 24
        assert spanish_words_to_number("veinticinco") == 25
        assert spanish_words_to_number("veintiséis") == 26
        assert spanish_words_to_number("veintiseis") == 26
        assert spanish_words_to_number("veintisiete") == 27
        assert spanish_words_to_number("veintiocho") == 28
        assert spanish_words_to_number("veintinueve") == 29
    
    def test_tens(self):
        """Test round tens 30-90."""
        assert spanish_words_to_number("treinta") == 30
        assert spanish_words_to_number("cuarenta") == 40
        assert spanish_words_to_number("cincuenta") == 50
        assert spanish_words_to_number("sesenta") == 60
        assert spanish_words_to_number("setenta") == 70
        assert spanish_words_to_number("ochenta") == 80
        assert spanish_words_to_number("noventa") == 90
    
    def test_compound_tens(self):
        """Test compound numbers 31-99 with 'y'."""
        assert spanish_words_to_number("treinta y uno") == 31
        assert spanish_words_to_number("cuarenta y dos") == 42
        assert spanish_words_to_number("cincuenta y tres") == 53
        assert spanish_words_to_number("sesenta y cuatro") == 64
        assert spanish_words_to_number("setenta y cinco") == 75
        assert spanish_words_to_number("ochenta y seis") == 86
        assert spanish_words_to_number("noventa y nueve") == 99
    
    def test_hundreds(self):
        """Test round hundreds."""
        assert spanish_words_to_number("cien") == 100
        assert spanish_words_to_number("ciento") == 100
        assert spanish_words_to_number("doscientos") == 200
        assert spanish_words_to_number("doscientas") == 200
        assert spanish_words_to_number("trescientos") == 300
        assert spanish_words_to_number("cuatrocientos") == 400
        assert spanish_words_to_number("quinientos") == 500
        assert spanish_words_to_number("seiscientos") == 600
        assert spanish_words_to_number("setecientos") == 700
        assert spanish_words_to_number("ochocientos") == 800
        assert spanish_words_to_number("novecientos") == 900
    
    def test_compound_hundreds(self):
        """Test compound hundreds like from the edge case document."""
        assert spanish_words_to_number("ciento veintisiete") == 127
    
    def test_edge_case_articles(self):
        """Test the actual edge cases from issues/praser.txt."""
        assert spanish_words_to_number("cincuenta y uno") == 51
        assert spanish_words_to_number("cincuenta y dos") == 52
        assert spanish_words_to_number("cincuenta y tres") == 53
        assert spanish_words_to_number("cincuenta y cuatro") == 54


class TestSpanishOrdinalNumbers:
    """Test ordinal number conversion."""
    
    def test_basic_ordinals(self):
        """Test basic ordinal numbers 1-10."""
        assert spanish_words_to_number("primero") == 1
        assert spanish_words_to_number("primera") == 1
        assert spanish_words_to_number("primer") == 1
        assert spanish_words_to_number("segundo") == 2
        assert spanish_words_to_number("segunda") == 2
        assert spanish_words_to_number("tercero") == 3
        assert spanish_words_to_number("tercera") == 3
        assert spanish_words_to_number("tercer") == 3
        assert spanish_words_to_number("cuarto") == 4
        assert spanish_words_to_number("cuarta") == 4
        assert spanish_words_to_number("quinto") == 5
        assert spanish_words_to_number("quinta") == 5
        assert spanish_words_to_number("sexto") == 6
        assert spanish_words_to_number("sexta") == 6
        assert spanish_words_to_number("séptimo") == 7
        assert spanish_words_to_number("séptima") == 7
        assert spanish_words_to_number("octavo") == 8
        assert spanish_words_to_number("octava") == 8
        assert spanish_words_to_number("noveno") == 9
        assert spanish_words_to_number("novena") == 9
        assert spanish_words_to_number("décimo") == 10
        assert spanish_words_to_number("décima") == 10
    
    def test_higher_ordinals(self):
        """Test ordinals 11-20."""
        assert spanish_words_to_number("undécimo") == 11
        assert spanish_words_to_number("duodécimo") == 12
        assert spanish_words_to_number("vigésimo") == 20


class TestNormalizeArticleNumber:
    """Test the main normalize_article_number function."""
    
    def test_numeric_articles(self):
        """Test standard numeric article names."""
        assert normalize_article_number("Artículo 14") == "14"
        assert normalize_article_number("Art. 1 bis") == "1 bis"
        assert normalize_article_number("Artículo 154.1") == "154"
        assert normalize_article_number("Artículo 51") == "51"
    
    def test_alphabetic_articles(self):
        """Test alphabetic article names from edge cases."""
        assert normalize_article_number("Artículo cincuenta y uno") == "51"
        assert normalize_article_number("Artículo cincuenta y dos") == "52"
        assert normalize_article_number("Artículo cincuenta y tres") == "53"
        assert normalize_article_number("Artículo cincuenta y cuatro") == "54"
        assert normalize_article_number("Artículo primero") == "1"
        assert normalize_article_number("Artículo ciento veintisiete") == "127"
    
    def test_case_insensitivity(self):
        """Test that conversion is case-insensitive."""
        assert normalize_article_number("ARTÍCULO CINCUENTA Y UNO") == "51"
        assert normalize_article_number("artículo cincuenta y uno") == "51"
    
    def test_non_article_names(self):
        """Test that non-article names return None."""
        assert normalize_article_number("Disposición adicional primera") is None
        assert normalize_article_number("") is None
        assert normalize_article_number(None) is None
    
    def test_bare_numbers(self):
        """Test normalization of bare number strings."""
        assert normalize_article_number("51") == "51"
        assert normalize_article_number("1 bis") == "1 bis"
        assert normalize_article_number("cincuenta y uno") == "51"
    
    def test_underscore_variants(self):
        """Test numbers with underscores (how tree_builder stores them)."""
        # tree_builder.py replaces spaces with underscores in article names
        assert normalize_article_number("treinta_y_uno") == "31"
        assert normalize_article_number("cincuenta_y_cuatro") == "54"
        assert normalize_article_number("ciento_veintisiete") == "127"
        assert normalize_article_number("vigésimo_primero") == "21"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
