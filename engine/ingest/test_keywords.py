from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.ingest import keywords
from engine.ingest.keywords import detect_lang, extract_keywords

MALAY = (
    "Pekeliling ini menetapkan kadar elaun perjalanan baharu bagi semua pegawai awam yang "
    "menjalankan tugas rasmi di luar ibu pejabat. Tuntutan elaun perjalanan hendaklah "
    "dikemukakan dalam tempoh tiga puluh hari selepas perjalanan selesai. Setiap tuntutan "
    "mesti disertakan dengan resit asal dan kelulusan ketua jabatan. Kadar elaun perjalanan "
    "bagi kenderaan persendirian ialah tujuh puluh sen sekilometer. Pegawai yang gagal "
    "mengemukakan tuntutan dalam tempoh yang ditetapkan tidak layak menerima bayaran. "
    "Jabatan Kewangan akan menyemak setiap tuntutan sebelum bayaran dibuat kepada pegawai. "
    "Pekeliling ini berkuat kuasa mulai satu Januari dan menggantikan pekeliling terdahulu."
)

ENGLISH = (
    "This circular sets the new procurement threshold for direct purchase and quotation "
    "across all departments. Any purchase above the procurement threshold must go through "
    "a formal quotation process with at least three suppliers. The procurement committee "
    "reviews every quotation before an award is made. Officers must record each purchase "
    "in the procurement system within seven days. Purchases split to avoid the procurement "
    "threshold are a disciplinary offence. The finance department audits procurement "
    "records every quarter and reports findings to the management committee. This circular "
    "takes effect immediately and replaces the earlier circular on quotation limits."
)


def test_malay_paragraph() -> None:
    assert detect_lang(MALAY) == "ms"
    kws = extract_keywords(MALAY, "ms")
    assert any("elaun perjalanan" == k or "elaun" in k for k in kws)


def test_english_paragraph() -> None:
    assert detect_lang(ENGLISH) == "en"
    kws = extract_keywords(ENGLISH, "en")
    assert any("procurement" in k for k in kws)


def test_empty_text() -> None:
    assert extract_keywords("", "en") == []
    assert detect_lang("") == "en"
    assert detect_lang("  ... 123 !!") == "en"


def test_short_text_returns_no_keywords() -> None:
    assert extract_keywords("Kadar elaun perjalanan baharu bagi pegawai.", "ms") == []


def test_keywords_lowercase_unique_and_capped() -> None:
    kws = extract_keywords(ENGLISH, "en", top_k=3)
    assert 0 < len(kws) <= 3
    assert all(k == k.lower() for k in kws)
    assert len(kws) == len(set(kws))


def test_mixed_text_is_a_known_label() -> None:
    assert detect_lang(MALAY[:400] + " " + ENGLISH[:400]) in {"ms", "en", "mixed"}


def _fake_langs(monkeypatch: pytest.MonkeyPatch, *pairs: tuple[str, float]) -> None:
    langs = [SimpleNamespace(lang=code, prob=prob) for code, prob in pairs]
    monkeypatch.setattr(keywords, "detect_langs", lambda _text: langs)


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [
        ((("ms", 0.5), ("en", 0.45)), "mixed"),
        ((("id", 0.5), ("en", 0.45)), "mixed"),  # Indonesian counts as Malay
        ((("en", 0.55), ("ms", 0.4)), "mixed"),
        ((("en", 0.8), ("ms", 0.2)), "en"),  # second language under 0.3
        ((("ms", 0.69), ("en", 0.3)), "ms"),  # exactly 0.3 is not above the threshold
        ((("ms", 0.5), ("tl", 0.45)), "ms"),  # top two must be ms and en
        ((("fr", 0.9),), "en"),  # anything else falls back to en
    ],
)
def test_detect_lang_mixed_rule(
    monkeypatch: pytest.MonkeyPatch, pairs: tuple[tuple[str, float], ...], expected: str
) -> None:
    _fake_langs(monkeypatch, *pairs)
    assert detect_lang("any text") == expected
