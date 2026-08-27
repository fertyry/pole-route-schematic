from pole_route.domain.physical_pole import build_physical_pole_mapping


def _labels(mapping):
    return {item.source_pole_id: item.display_label for item in mapping.assignments}


def test_physical_poles_are_numbered_continuously_after_merges() -> None:
    mapping = build_physical_pole_mapping(
        ["1", "2", "3", "4", "5", "6"],
        [frozenset({"1", "2"}), frozenset({"4", "5"})],
    )
    assert _labels(mapping) == {
        "1": "P1", "2": "P1", "3": "P2", "4": "P3", "5": "P3", "6": "P4"
    }


def test_transformer_rack_uses_two_labels_and_accessory_uses_none() -> None:
    mapping = build_physical_pole_mapping(
        ["20", "24", "25", "90", "26"],
        transformer_rack_groups=[frozenset({"24", "25", "90"})],
        transformer_rack_leg_pairs=[("24", "25")],
    )
    assert _labels(mapping) == {
        "20": "P1", "24": "P2", "25": "P3", "90": "-", "26": "P4"
    }


def test_rack_without_explicit_legs_does_not_infer_physical_poles() -> None:
    mapping = build_physical_pole_mapping(
        ["24", "25", "90", "26"],
        transformer_rack_groups=[frozenset({"24", "25", "90"})],
    )
    assert _labels(mapping) == {"24": "-", "25": "-", "90": "-", "26": "P1"}
