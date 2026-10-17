from __future__ import annotations

import asyncio

import pytest

from server.config import Settings, update_settings
from server.memory import Store
from server.pipeline import Pipeline


@pytest.fixture()
def pipeline(tmp_path):
    settings = Settings()
    settings.mode = "demo"
    settings.llm_api_key = ""
    settings.daily_limit = 60
    store = Store(tmp_path / "test.db")
    return Pipeline(settings, store), store, settings


def run(coro):
    return asyncio.run(coro)


def test_medical_question_uses_template(pipeline):
    app, _, _ = pipeline
    result = run(app.turn(audio=None, text="باشىم ئاغرىۋاتىدۇ", session_id="s1"))
    assert result.category == "medical"
    assert "دوختۇر" in result.reply_ug
    assert result.mode == "demo"


def test_emergency_question(pipeline):
    app, _, _ = pipeline
    result = run(app.turn(audio=None, text="كۆكرەم ئاغرىۋاتىدۇ، نەپەس ئالالمايۋاتىمەن", session_id="s1"))
    assert result.category == "emergency"


def test_normal_question_gets_reply(pipeline):
    app, _, _ = pipeline
    result = run(app.turn(audio=None, text="سىز كىم؟", session_id="s2"))
    assert result.category == "normal"
    assert result.reply_ug
    assert result.session_id == "s2"


def test_empty_input_asks_again(pipeline):
    app, _, _ = pipeline
    result = run(app.turn(audio=None, text="   ", session_id="s3"))
    assert result.category == "unclear"
    assert result.reply_ug


def test_messages_are_persisted(pipeline):
    app, store, _ = pipeline
    run(app.turn(audio=None, text="سىز كىم؟", session_id="s4"))
    messages = store.recent_messages("s4", 10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_daily_limit(pipeline):
    app, _, settings = pipeline
    settings.daily_limit = 1
    first = run(app.turn(audio=None, text="سىز كىم؟", session_id="s5"))
    assert first.category == "normal"
    second = run(app.turn(audio=None, text="سىز كىم؟", session_id="s5"))
    assert second.category == "limit"


def test_weather_question_uses_weather(monkeypatch, pipeline):
    app, _, _ = pipeline

    async def fake_weather(city):
        return {
            "city": "乌鲁木齐",
            "temp": 12,
            "code": 0,
            "desc_ug": "قۇياشلىق",
            "desc_zh": "晴",
        }

    monkeypatch.setattr("server.pipeline.weather.current", fake_weather)
    result = run(app.turn(audio=None, text="بۈگۈن ھاۋا قانداق؟", session_id="s6"))
    assert "ئۈرۈمچى" in result.reply_ug
    assert "12" in result.reply_ug


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("server.config._SETTINGS_FILE", tmp_path / "settings.json")
    import server.config as config

    config.reset_cache()
    updated = update_settings({"city": "喀什", "daily_limit": 30})
    assert updated.city == "喀什"
    assert updated.daily_limit == 30
    config.reset_cache()
