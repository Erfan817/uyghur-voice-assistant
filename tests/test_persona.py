from __future__ import annotations

from server.persona import GLOSSARY, build_system_prompt, city_ug, fallback, greeting


def test_prompt_contains_profile():
    prompt = build_system_prompt(
        {"title": "ئاپا", "age": "72", "city": "喀什", "health": "高血压", "family": "阿迪力"}
    )
    assert "ئاپا" in prompt
    assert "喀什" in prompt
    assert "高血压" in prompt
    assert "قان بېسىمى" in prompt  # 术语表


def test_city_ug():
    assert city_ug("乌鲁木齐") == "ئۈرۈمچى"
    assert city_ug("乌鲁木齐市") == "ئۈرۈمچى"
    assert city_ug("某个小城") == "某个小城"


def test_greeting_without_weather():
    ug, zh = greeting("morning", None, {"title": "ئاپا"})
    assert "ئاپا" in ug
    assert zh


def test_greeting_with_weather():
    weather = {"city": "乌鲁木齐", "temp": 4, "desc_ug": "قۇياشلىق", "desc_zh": "晴"}
    ug, zh = greeting("evening", weather, {"title": "ئاپا"})
    assert "ئۈرۈمچى" in ug
    assert "4" in ug
    assert "4" in zh


def test_fallbacks_are_uyghur():
    for key in ("emergency", "medical", "religion", "policy", "unclear", "limit", "error"):
        ug, zh = fallback(key)
        assert ug.strip()
        assert zh.strip()


def test_glossary_has_health_terms():
    assert "血压" in GLOSSARY
    assert "医院" in GLOSSARY
