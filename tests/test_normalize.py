from __future__ import annotations

from server.normalize import (
    cer,
    clamp_length,
    is_ug,
    normalize_for_match,
    normalize_ug,
    split_sentences,
    wer,
)


def test_normalize_digits_and_punct():
    raw = "بۈگۈن ١٢ درەجە، يامغۇر؟"
    out = normalize_ug(raw)
    assert "12" in out
    assert "،" in out or "،" not in raw  # 阿拉伯逗号保留
    assert "؟" in out


def test_normalize_letter_variants():
    # 波斯 kaf 与阿拉伯 kaf 应该统一
    assert normalize_for_match("\u06a9") == normalize_for_match("\u0643")


def test_normalize_removes_invisibles():
    raw = "ئاي\u200cنۇر\u0640"
    assert "\u200c" not in normalize_ug(raw)
    assert "\u0640" not in normalize_ug(raw)


def test_is_ug():
    assert is_ug("بۈگۈن ھاۋا قانداق؟")
    assert not is_ug("今天天气怎么样")


def test_wer_identical_is_zero():
    text = "بۈگۈن ھاۋا ياخشى"
    assert wer(text, text) == 0.0


def test_wer_one_word_wrong():
    ref = "بۈگۈن ھاۋا ياخشى"
    hyp = "بۈگۈن ھاۋا ناچار"
    assert abs(wer(ref, hyp) - 1 / 3) < 1e-6


def test_cer_range():
    ref = "ياخشى"
    hyp = "ياخشا"
    value = cer(ref, hyp)
    assert 0 < value <= 1


def test_split_sentences_limit():
    text = "بىر. ئىككى. ئۈچ. تۆت."
    assert len(split_sentences(text, limit=3)) == 3


def test_clamp_length():
    text = "a" * 500
    assert len(clamp_length(text, 100)) <= 500
    assert len(clamp_length("سەلام.", 3)) == 3
