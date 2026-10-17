from __future__ import annotations

from server.safety import analyze, post_check


def test_emergency():
    assert analyze("胸痛，喘不上气").category == "emergency"


def test_medical_not_emergency():
    assert analyze("血压高，吃什么药").category == "medical"


def test_religion():
    assert analyze("礼拜前能不能吃东西").category == "religion"


def test_policy():
    assert analyze("社保怎么交").category == "policy"


def test_normal():
    assert analyze("今天天气怎么样").category == "normal"
    assert analyze("بۈگۈن ھاۋا قانداق؟").category == "normal"


def test_uyghur_emergency():
    assert analyze("كۆكرەك ئاغرىۋاتىدۇ").category == "emergency"


def test_post_check_rejects_chinese():
    ok, reason = post_check("今天天气不错，出去玩吧")
    assert not ok
    assert reason == "not_uyghur"


def test_post_check_rejects_dosage():
    ok, reason = post_check("كۈنىگە 2 تال دورا ئىچىڭ")
    assert not ok
    assert reason == "dosage"


def test_post_check_accepts_uyghur():
    ok, reason = post_check("بۈگۈن ھاۋا ياخشى. ئىسسىق كىيىپ چىقىڭ.")
    assert ok, reason
