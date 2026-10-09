def test_fuzz_fallback_ratio_partial_tokenset():
    from app.modules.document_import.matching import matcher

    assert hasattr(matcher.fuzz, "ratio")
    assert hasattr(matcher.fuzz, "partial_ratio")
    assert hasattr(matcher.fuzz, "token_set_ratio")

    assert matcher.fuzz.ratio("قدرة المحرك", "قدرة المحرك") == 100
    assert matcher.fuzz.partial_ratio("قدرة المحرك", "قدرة المحرك") == 100

    # partial
    assert matcher.fuzz.partial_ratio("المحرك قدرة", "قدرة المحرك") >= 70

    # token set
    assert matcher.fuzz.token_set_ratio("قدرة المحرك 150 ك.وات", "قدرة المحرك 150 kW") >= 70

    # dissimilar
    assert matcher.fuzz.ratio("قدرة", "طول") < 70
    assert matcher.fuzz.partial_ratio("قدرة", "طول") < 70
