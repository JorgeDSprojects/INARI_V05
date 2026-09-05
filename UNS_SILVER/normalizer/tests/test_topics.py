from app.topics import classify_topic


def test_descriptive_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_descriptive")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "descriptive"


def test_informative_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_informative")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "informative"


def test_analytical_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_analytical")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "analytical"


def test_unrecognized_suffix_is_other_and_unchanged():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_lifecycle")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_lifecycle"
    assert suffix == "other"


def test_suffix_can_apply_at_any_hierarchy_level():
    base, suffix = classify_topic("uns/v1/ACME/SITE/_analytical")
    assert base == "uns/v1/ACME/SITE"
    assert suffix == "analytical"
