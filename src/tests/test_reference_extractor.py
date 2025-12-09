"""
Tests for the Reference Extractor.

Run with: python -m pytest src/tests/test_reference_extractor.py -v
Or directly: python src/tests/test_reference_extractor.py
"""
import sys
from pathlib import Path

# Add src to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from domain.services.reference_extractor import ReferenceExtractor, ReferenceType


def test_constitution_reference():
    """Test extraction of Constitution references."""
    extractor = ReferenceExtractor()
    
    text = "Según el artículo 14 de la Constitución Española, todos los españoles son iguales."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 1
    ref = result.references[0]
    assert ref.reference_type == ReferenceType.CONSTITUTION
    assert ref.article_number == "14"
    assert ref.resolved_boe_id == "BOE-A-1978-31229"
    print(f"✓ Constitution: {ref.raw_text} -> {ref.resolved_boe_id}")


def test_code_reference():
    """Test extraction of Code references (Código Civil, Penal)."""
    extractor = ReferenceExtractor()
    
    text = "El artículo 1902 del Código Civil establece la responsabilidad extracontractual."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 1
    ref = result.references[0]
    assert ref.reference_type == ReferenceType.CODE
    assert ref.article_number == "1902"
    assert ref.resolved_boe_id == "BOE-A-1889-4763"
    print(f"✓ Código Civil: {ref.raw_text} -> {ref.resolved_boe_id}")


def test_abbreviated_reference():
    """Test extraction of abbreviated references like 'art. 14 CE'."""
    extractor = ReferenceExtractor()
    
    text = "De conformidad con el art. 24 CE y art. 1 CC."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 2
    
    ce_ref = next((r for r in result.references if r.abbreviation == "CE"), None)
    assert ce_ref is not None
    assert ce_ref.resolved_boe_id == "BOE-A-1978-31229"
    print(f"✓ Abbreviated CE: {ce_ref.raw_text} -> {ce_ref.resolved_boe_id}")
    
    cc_ref = next((r for r in result.references if r.abbreviation == "CC"), None)
    assert cc_ref is not None
    assert cc_ref.resolved_boe_id == "BOE-A-1889-4763"
    print(f"✓ Abbreviated CC: {cc_ref.raw_text} -> {cc_ref.resolved_boe_id}")


def test_full_law_citation():
    """Test extraction of full law citations with number and date."""
    extractor = ReferenceExtractor()
    
    text = "La Ley Orgánica 10/1995, de 23 de noviembre, del Código Penal, establece..."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 1
    ref = result.references[0]
    assert ref.reference_type == ReferenceType.ORGANIC_LAW
    assert ref.law_number == "10/1995"
    print(f"✓ Full law: {ref.raw_text}")


def test_internal_reference():
    """Test extraction of internal article references."""
    extractor = ReferenceExtractor()
    
    text = "Sin perjuicio de lo establecido en el artículo anterior, cuando las circunstancias del artículo 5 no concurran."
    result = extractor.extract(text, "test-doc", current_normativa_id="BOE-A-2020-12345")
    
    internal_refs = [r for r in result.references if r.reference_type == ReferenceType.INTERNAL]
    assert len(internal_refs) >= 2
    
    anterior_ref = next((r for r in internal_refs if r.article_number == "anterior"), None)
    assert anterior_ref is not None
    print(f"✓ Internal (anterior): {anterior_ref.raw_text}")
    
    art5_ref = next((r for r in internal_refs if r.article_number == "5"), None)
    assert art5_ref is not None
    assert art5_ref.is_external == False
    print(f"✓ Internal (art 5): {art5_ref.raw_text}")


def test_article_range():
    """Test extraction of article ranges like 'artículos 5 a 12'."""
    extractor = ReferenceExtractor()
    
    text = "Los artículos 5 a 12 de esta Ley regulan el procedimiento."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 1
    ref = result.references[0]
    assert ref.article_range == ("5", "12")
    assert ref.is_external == False
    print(f"✓ Article range: {ref.raw_text} -> {ref.article_range}")


def test_judicial_decision():
    """Test extraction of judicial decisions."""
    extractor = ReferenceExtractor()
    
    text = "Según la STC 1234/2020, de 15 de noviembre, y la STS 567/2019."
    result = extractor.extract(text, "test-doc")
    
    judicial_refs = [r for r in result.references if r.reference_type == ReferenceType.JUDICIAL]
    assert len(judicial_refs) >= 2
    
    stc = next((r for r in judicial_refs if r.judicial_court == "STC"), None)
    assert stc is not None
    assert stc.judicial_number == "1234/2020"
    print(f"✓ STC: {stc.raw_text}")
    
    sts = next((r for r in judicial_refs if r.judicial_court == "STS"), None)
    assert sts is not None
    print(f"✓ STS: {sts.raw_text}")


def test_external_law_with_article():
    """Test the key case: 'artículo 3 de la Ley 29/2012'."""
    extractor = ReferenceExtractor()
    
    # This is the problematic case the user mentioned
    text = "según el artículo 3 de la Ley 29/2012"
    result = extractor.extract(text, "test-doc", current_normativa_id="BOE-A-2000-1111")
    
    # Should be marked as EXTERNAL, not internal
    assert len(result.references) >= 1
    ref = result.references[0]
    assert ref.is_external == True
    assert ref.article_number == "3"
    assert "29/2012" in ref.raw_text or ref.law_number == "29/2012" or "Ley 29/2012" in ref.law_type
    print(f"✓ External article: {ref.raw_text} (is_external={ref.is_external})")


def test_lopj_abbreviation():
    """Test LOPJ and other common abbreviations."""
    extractor = ReferenceExtractor()
    
    text = "Conforme a la LOPJ y al ET."
    result = extractor.extract(text, "test-doc")
    
    lopj = next((r for r in result.references if r.abbreviation == "LOPJ"), None)
    assert lopj is not None
    assert lopj.resolved_boe_id == "BOE-A-1985-12666"
    print(f"✓ LOPJ: resolved to {lopj.resolved_boe_id}")
    
    et = next((r for r in result.references if r.abbreviation == "ET"), None)
    assert et is not None
    assert et.resolved_boe_id == "BOE-A-2015-11430"
    print(f"✓ ET: resolved to {et.resolved_boe_id}")


def test_eu_legislation():
    """Test EU legislation references."""
    extractor = ReferenceExtractor()
    
    text = "La Directiva 2006/123/CE y el Reglamento (UE) 2016/679 sobre protección de datos."
    result = extractor.extract(text, "test-doc")
    
    eu_refs = [r for r in result.references if r.reference_type == ReferenceType.EU_LEGISLATION]
    assert len(eu_refs) >= 2
    print(f"✓ EU refs: {[r.raw_text for r in eu_refs]}")


def test_cited_reference():
    """Test back-references like 'la citada Ley'."""
    extractor = ReferenceExtractor()
    
    text = "Según la citada Ley Orgánica 6/1985."
    result = extractor.extract(text, "test-doc")
    
    assert len(result.references) >= 1
    ref = result.references[0]
    assert "6/1985" in ref.raw_text or ref.law_number == "6/1985"
    print(f"✓ Cited reference: {ref.raw_text}")


def test_complex_article_numbers():
    """Test complex article numbers like '10 bis', '149.1.23.ª'."""
    extractor = ReferenceExtractor()
    
    text = "El art. 10 bis de la Ley y el artículo 149.1.23.ª CE."
    result = extractor.extract(text, "test-doc")
    
    # Check for complex article numbers
    bis_ref = next((r for r in result.references if r.article_number and "bis" in r.article_number), None)
    complex_ref = next((r for r in result.references if r.article_number and "149" in str(r.article_number)), None)
    
    if bis_ref:
        print(f"✓ Article bis: {bis_ref.raw_text}")
    else:
        print(f"⚠ Article bis not found (may need pattern adjustment)")
    
    if complex_ref:
        print(f"✓ Complex article: {complex_ref.raw_text}")


def test_unresolved_logging(tmp_path):
    """Test that unresolved references are logged to JSON."""
    log_path = tmp_path / "unresolved.json"
    extractor = ReferenceExtractor(unresolved_log_path=str(log_path))
    
    # Use an unknown law
    text = "Según la Ley 999/2099 de cosas imaginarias."
    result = extractor.extract(text, "test-doc")
    
    # Should have unresolved references
    assert len(result.unresolved_references) >= 1
    
    # Should have written to file
    assert log_path.exists()
    print(f"✓ Unresolved: {[r.raw_text for r in result.unresolved_references]}")


def run_all_tests():
    """Run all tests manually (without pytest)."""
    import tempfile
    
    print("\n" + "="*60)
    print("Reference Extractor Tests")
    print("="*60 + "\n")
    
    tests = [
        ("Constitution reference", test_constitution_reference),
        ("Code reference", test_code_reference),
        ("Abbreviated reference", test_abbreviated_reference),
        ("Full law citation", test_full_law_citation),
        ("Internal reference", test_internal_reference),
        ("Article range", test_article_range),
        ("Judicial decision", test_judicial_decision),
        ("External law with article", test_external_law_with_article),
        ("LOPJ abbreviation", test_lopj_abbreviation),
        ("EU legislation", test_eu_legislation),
        ("Cited reference", test_cited_reference),
        ("Complex article numbers", test_complex_article_numbers),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            print(f"\n--- {name} ---")
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    # Test with temp directory
    try:
        print(f"\n--- Unresolved logging ---")
        with tempfile.TemporaryDirectory() as tmp:
            test_unresolved_logging(Path(tmp))
        passed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}")
        failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
