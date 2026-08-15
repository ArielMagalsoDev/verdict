from verdict.fixtures import RESEARCH, SOURCES


def test_every_verified_quote_is_verbatim():
    for facts in RESEARCH.values():
        for fact in facts:
            slug = fact["source_url"].rsplit("/", 1)[-1]
            assert fact["quote"].lower() in SOURCES[slug].lower()


def test_injection_is_not_a_fact():
    values = " ".join(str(f["value"]) for f in RESEARCH["Brightpath Logistics"])
    assert "score" not in values.lower()
    assert "ignore" not in values.lower()
