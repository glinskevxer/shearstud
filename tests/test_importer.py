"""The exchange format, which is validated hard because it is the way in."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shearstud.errors import GeometryError, InputError
from shearstud.store import importer

pytestmark = pytest.mark.store


def plate(label: str, width: float, height: float, y: float) -> dict[str, Any]:
    return {"label": label, "width_in": width, "height_in": height, "y_center_in": y}


def document() -> dict[str, Any]:
    return {
        "number": "18-SH-0473",
        "name": "Salt Fork Creek",
        "year_built": 1968,
        "spans": [90.0],
        "continuous": False,
        "effective_width_rule": "tributary",
        "girders": [
            {
                "girder_id": "G1",
                "girder_index": 0,
                "spacing_left_ft": 0.0,
                "spacing_right_ft": 8.0,
                "overhang_ft": 3.5,
                "slab_thickness_in": 8.0,
                "haunch_in": 2.0,
                "deck_fc_ksi": 4.0,
                "runs": [
                    {
                        "from_station_ft": 0.0,
                        "to_station_ft": 90.0,
                        "label": "PG52",
                        "plates": [
                            plate("bottom", 18.0, 1.5, 0.75),
                            plate("web", 0.5625, 52.0, 27.5),
                            plate("top", 16.0, 1.0, 54.0),
                        ],
                    }
                ],
                "details": [
                    {
                        "detail_id": "D1",
                        "kind": "cover_plate_end",
                        "category_name": "E",
                        "station_ft": 24.0,
                        "fibre": "bottom",
                        "note": "ground smooth",
                    }
                ],
            },
            {
                "girder_id": "G2",
                "girder_index": 1,
                "spacing_left_ft": 8.0,
                "spacing_right_ft": 8.0,
                "slab_thickness_in": 8.0,
                "haunch_in": 2.0,
                "runs": [
                    {
                        "from_station_ft": 0.0,
                        "to_station_ft": 90.0,
                        "plates": [
                            plate("bottom", 18.0, 1.5, 0.75),
                            plate("web", 0.5625, 52.0, 27.5),
                            plate("top", 16.0, 1.0, 54.0),
                        ],
                    }
                ],
            },
        ],
    }


def test_a_document_builds_a_structure() -> None:
    s = importer.from_document(document())
    assert str(s.number) == "18-SH-0473"
    assert s.name == "Salt Fork Creek"
    assert s.girder_count == 2
    assert s.length_ft == pytest.approx(90.0)


def test_the_girders_keep_their_layout() -> None:
    s = importer.from_document(document())
    assert s.girder("G1").is_exterior
    assert not s.girder("G2").is_exterior


def test_the_section_comes_through_with_its_properties() -> None:
    s = importer.from_document(document())
    section = s.girder("G1").section_at(45.0)
    assert section.label == "PG52"
    assert len(section) == 3
    assert section.inertia_in4 > 10000.0


def test_a_run_without_a_label_gets_one() -> None:
    s = importer.from_document(document())
    assert s.girder("G2").section_at(45.0).label == "G2-0"


def test_the_details_come_through_with_their_notes() -> None:
    s = importer.from_document(document())
    assert s.girder("G1").detail("D1").note == "ground smooth"


def test_a_girder_with_no_details_is_allowed() -> None:
    s = importer.from_document(document())
    assert s.girder("G2").details == ()


def test_the_deck_width_is_derived_from_the_layout() -> None:
    s = importer.from_document(document())
    # Half of one eight foot bay plus a three and a half foot overhang.
    assert s.girder("G1").deck.effective_width_in == pytest.approx((4.0 + 3.5) * 12.0)


def test_a_continuous_unit_comes_through_continuous() -> None:
    doc = document()
    doc["spans"] = [90.0, 90.0]
    doc["continuous"] = True
    for girder in doc["girders"]:
        girder["runs"][0]["to_station_ft"] = 180.0
    s = importer.from_document(doc)
    assert s.spans.continuous
    assert s.length_ft == pytest.approx(180.0)


def test_the_round_trip_gives_back_the_same_structure() -> None:
    original = importer.from_document(document())
    again = importer.from_document(importer.to_document(original))
    assert str(again.number) == str(original.number)
    assert again.girder_count == original.girder_count
    assert again.girder("G1").section_at(45.0).inertia_in4 == pytest.approx(
        original.girder("G1").section_at(45.0).inertia_in4
    )


def test_the_round_trip_keeps_the_details() -> None:
    original = importer.from_document(document())
    again = importer.from_document(importer.to_document(original))
    assert again.girder("G1").detail("D1").station_ft == pytest.approx(24.0)


@pytest.mark.parametrize("key", ["number", "name", "spans", "girders"])
def test_a_missing_top_level_key_is_refused(key: str) -> None:
    doc = document()
    del doc[key]
    with pytest.raises(InputError):
        importer.from_document(doc)


def test_an_unknown_top_level_key_is_refused() -> None:
    doc = document()
    doc["designer"] = "someone"
    with pytest.raises(InputError, match="unknown key 'designer'"):
        importer.from_document(doc)


def test_an_unknown_girder_key_is_refused() -> None:
    doc = document()
    doc["girders"][0]["camber_in"] = 2.0
    with pytest.raises(InputError, match="unknown key 'camber_in'"):
        importer.from_document(doc)


def test_a_misspelled_plate_key_is_refused() -> None:
    # The whole reason unknown keys are rejected: this plate would otherwise
    # come through with no thickness at all.
    doc = document()
    doc["girders"][0]["runs"][0]["plates"][0]["thicknes_in"] = 1.5
    with pytest.raises(InputError, match="unknown key 'thicknes_in'"):
        importer.from_document(doc)


def test_a_missing_plate_dimension_is_refused() -> None:
    doc = document()
    del doc["girders"][0]["runs"][0]["plates"][0]["height_in"]
    with pytest.raises(InputError, match="missing 'height_in'"):
        importer.from_document(doc)


def test_a_plate_with_no_thickness_is_refused_by_the_plate_class() -> None:
    doc = document()
    doc["girders"][0]["runs"][0]["plates"][0]["height_in"] = 0.0
    with pytest.raises(GeometryError):
        importer.from_document(doc)


def test_a_girder_with_no_runs_is_refused() -> None:
    doc = document()
    doc["girders"][0]["runs"] = []
    with pytest.raises(InputError, match="at least one section run"):
        importer.from_document(doc)


def test_a_run_with_no_plates_is_refused() -> None:
    doc = document()
    doc["girders"][0]["runs"][0]["plates"] = []
    with pytest.raises(InputError, match="at least one plate"):
        importer.from_document(doc)


def test_a_structure_with_no_girders_is_refused() -> None:
    doc = document()
    doc["girders"] = []
    with pytest.raises(InputError, match="at least one girder"):
        importer.from_document(doc)


def test_spans_that_are_not_a_list_are_refused() -> None:
    doc = document()
    doc["spans"] = 90.0
    with pytest.raises(InputError, match="must be a list"):
        importer.from_document(doc)


def test_an_unknown_detail_category_is_refused() -> None:
    doc = document()
    doc["girders"][0]["details"][0]["category_name"] = "Q"
    with pytest.raises(InputError, match="unknown detail category"):
        importer.from_document(doc)


def test_reading_from_disk_works(tmp_path: Path) -> None:
    path = tmp_path / "structure.json"
    path.write_text(json.dumps(document()), encoding="utf-8")
    s = importer.read(path)
    assert s.name == "Salt Fork Creek"


def test_reading_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="no structure document"):
        importer.read(tmp_path / "gone.json")


def test_reading_a_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "structure.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError, match="not valid JSON"):
        importer.read(path)


def test_reading_a_json_array_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "structure.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(InputError, match="must be an object"):
        importer.read(path)


def test_writing_and_reading_back_round_trips(tmp_path: Path) -> None:
    original = importer.from_document(document())
    path = tmp_path / "out" / "structure.json"
    importer.write(path, original)
    again = importer.read(path)
    assert str(again.number) == str(original.number)
    assert again.girder_count == original.girder_count


def test_the_written_document_is_indented_for_a_readable_diff(tmp_path: Path) -> None:
    path = tmp_path / "structure.json"
    importer.write(path, importer.from_document(document()))
    text = path.read_text(encoding="utf-8")
    assert '\n  "name"' in text
    assert text.endswith("\n")
