from __future__ import annotations

from engine.index.supersession import resolve_supersession
from engine.testing import FakeStore, make_document

A, B, C = "000000000000000a", "000000000000000b", "000000000000000c"


def store_with(*docs: dict) -> FakeStore:
    store = FakeStore()
    for doc in docs:
        store.upsert_document(doc)
    return store


def state(store: FakeStore, doc_id: str) -> tuple[str, str | None]:
    doc = store.get_document(doc_id)
    return doc["status"], doc["superseded_by"]


def doc(
    doc_id: str,
    title: str,
    year: int | None,
    supersedes: list[str] | None = None,
    filename: str | None = None,
    **fields,
) -> dict:
    return make_document(
        doc_id,
        title=title,
        year=year,
        supersedes=supersedes or [],
        filename=filename or f"{doc_id}.pdf",
        **fields,
    )


def test_newer_circular_supersedes_older():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == [(A, B)]
    assert state(store, A) == ("superseded", B)
    assert state(store, B) == ("current", None)


def test_english_circular_reference():
    store = store_with(
        doc(A, "Procurement Circular No. 5/2021: Quotation Thresholds", 2021),
        doc(B, "Procurement Circular No. 7/2023", 2023, ["Circular No. 5/2021"]),
    )
    assert resolve_supersession(store) == [(A, B)]


def test_reference_that_matches_nothing_marks_nothing():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Perolehan Bil. 9/2019"]),
    )
    assert resolve_supersession(store) == []
    assert state(store, A) == ("current", None)


def test_same_series_different_number_is_not_hit():
    # partial_ratio scores these 95; only the reference number tells them apart.
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 1/2023 Had Tuntutan", 2023),
        doc(C, "Pekeliling Kewangan Bil. 12/2022", 2022),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == []
    assert state(store, A) == ("current", None)
    assert state(store, C) == ("current", None)


def test_number_can_match_the_filename():
    store = store_with(
        doc(A, "Pekeliling Kewangan Kadar Elaun", 2022, filename="pekeliling-kewangan-2-2022.pdf"),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == [(A, B)]


def test_leading_zero_in_number():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 02/2022", 2022),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == [(A, B)]


def test_reference_without_number_uses_fuzzy_only():
    store = store_with(
        doc(A, "Garis Panduan Keselamatan Siber Jabatan", 2021),
        doc(C, "SOP Perolehan Sebut Harga", 2021),
        doc(B, "Garis Panduan Keselamatan Siber 2023", 2023, ["Garis Panduan Keselamatan Siber"]),
    )
    assert resolve_supersession(store) == [(A, B)]
    assert state(store, C) == ("current", None)


def test_year_guard():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2023", 2023),
        doc(B, "Pekeliling Kewangan Bil. 1/2021", 2021, ["Pekeliling Kewangan Bil. 2/2023"]),
    )
    assert resolve_supersession(store) == []
    assert state(store, A) == ("current", None)


def test_unknown_year_skips_the_guard():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", None),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == [(A, B)]


def test_never_supersedes_itself():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert resolve_supersession(store) == []
    assert state(store, A) == ("current", None)


def test_running_twice_is_stable():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    first = resolve_supersession(store)
    snapshot = store.list_documents()
    assert resolve_supersession(store) == first
    assert store.list_documents() == snapshot


def test_newest_replacement_wins():
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022),
        doc(C, "Pekeliling Kewangan Bil. 1/2025", 2025, ["Pekeliling Kewangan Bil. 2/2022"]),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, ["Pekeliling Kewangan Bil. 2/2022"]),
    )
    assert sorted(resolve_supersession(store)) == [(A, B), (A, C)]
    assert state(store, A) == ("superseded", C)


def test_mark_is_cleared_when_its_reference_is_gone():
    # Re-tagging B dropped the reference, so A is no longer superseded.
    store = store_with(
        doc(A, "Pekeliling Kewangan Bil. 2/2022", 2022, status="superseded", superseded_by=B),
        doc(B, "Pekeliling Kewangan Bil. 3/2024", 2024, []),
    )
    assert resolve_supersession(store) == []
    assert state(store, A) == ("current", None)


def test_draft_status_is_left_alone():
    store = store_with(doc(A, "Draf Pekeliling Kewangan", None, status="draft"))
    resolve_supersession(store)
    assert state(store, A) == ("draft", None)
