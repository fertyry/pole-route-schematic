import json

import pytest

from pole_route.domain.context import OSMFeatureCategory, OSMGeometryKind
from pole_route.domain.route import GeoPoint, Route
from pole_route.importers.osm_context import (
    OSMFeatureParseWarning,
    fetch_osm_context,
    parse_osm_context,
)
from pole_route.ui.osm_context_worker import OSMContextWorker


def _main_route() -> Route:
    return Route("Main", "A003.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.01)))


def test_parse_osm_context_keeps_and_clips_nearby_roads_and_named_places() -> None:
    document = {
        "elements": [
            {"type": "node", "id": 1, "lat": 13.005, "lon": 99.999},
            {"type": "node", "id": 2, "lat": 13.005, "lon": 100.001},
            {"type": "node", "id": 3, "lat": 13.005, "lon": 100.02},
            {"type": "node", "id": 4, "lat": 13.006, "lon": 100.02},
            {
                "type": "way",
                "id": 10,
                "geometry": [
                    {"lat": 13.005, "lon": 99.999},
                    {"lat": 13.005, "lon": 100.001},
                ],
                "tags": {"highway": "residential", "name": "Soi Test"},
            },
            {"type": "way", "id": 11, "nodes": [3, 4], "tags": {"highway": "service"}},
            {
                "type": "node",
                "id": 20,
                "lat": 13.004,
                "lon": 100.0001,
                "tags": {"name": "Test School", "amenity": "school"},
            },
        ]
    }

    context = parse_osm_context(document, _main_route(), 15.0)

    assert [road.route.name for road in context.roads] == ["Soi Test"]
    assert context.roads[0].suggested_width_metres == 6.0
    assert context.roads[0].route.points[0].longitude > 99.999
    assert context.roads[0].route.points[-1].longitude < 100.001
    assert [(place.name, place.category) for place in context.places] == [("Test School", "school")]


def test_fetch_osm_context_uses_injected_transport() -> None:
    captured = []

    def fetcher(query: str) -> bytes:
        captured.append(query)
        return json.dumps({"elements": []}).encode()

    context = fetch_osm_context(_main_route(), fetcher=fetcher)

    assert context.roads == ()
    assert context.places == ()
    assert 'way["highway"]' in captured[0]
    assert "(around:15," in captured[0]
    assert 'way["highway"]["bridge"](around:100,' in captured[0]
    assert 'relation["waterway"="river"](around:100,' in captured[0]


def test_osm_context_keeps_only_true_connections_and_deduplicates_split_ways() -> None:
    document = {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "geometry": [
                    {"lat": 13.005, "lon": 99.9995},
                    {"lat": 13.005, "lon": 100.0},
                ],
                "tags": {"highway": "residential", "name": "Soi One"},
            },
            {
                "type": "way",
                "id": 2,
                "geometry": [
                    {"lat": 13.005, "lon": 100.0},
                    {"lat": 13.005, "lon": 100.0005},
                ],
                "tags": {"highway": "residential", "name": "Soi One"},
            },
            {
                "type": "way",
                "id": 3,
                "geometry": [
                    {"lat": 13.0, "lon": 100.00003},
                    {"lat": 13.01, "lon": 100.00003},
                ],
                "tags": {"highway": "residential", "name": "Parallel Road"},
            },
        ]
    }

    context = parse_osm_context(document, _main_route(), 15.0)

    assert [road.route.name for road in context.roads] == ["Soi One"]
    assert context.roads[0].recommended is True


def test_osm_context_keeps_soi_ending_at_wide_road_edge() -> None:
    document = {
        "elements": [
            {
                "type": "way",
                "id": 40,
                "geometry": [
                    {"lat": 13.005, "lon": 100.00009},
                    {"lat": 13.005, "lon": 100.001},
                ],
                "tags": {"highway": "residential", "name": "Edge Soi"},
            }
        ]
    }

    context = parse_osm_context(document, _main_route(), 15.0)

    assert [road.route.name for road in context.roads] == ["Edge Soi"]


def test_osm_context_worker_reports_success_and_finishes(qtbot, monkeypatch) -> None:
    import pole_route.ui.osm_context_worker as worker_module

    expected = parse_osm_context({"elements": []}, _main_route(), 15.0)
    monkeypatch.setattr(worker_module, "fetch_osm_context", lambda _route: expected)
    worker = OSMContextWorker(_main_route())

    with qtbot.waitSignal(worker.finished), qtbot.waitSignal(worker.succeeded) as succeeded:
        worker.run()

    assert succeeded.args == [expected]


def _way(osm_id: int, tags: dict, *, longitude: float = 100.00005) -> dict:
    return {
        "type": "way",
        "id": osm_id,
        "geometry": [
            {"lat": 13.004, "lon": longitude},
            {"lat": 13.006, "lon": longitude},
        ],
        "tags": tags,
    }


def test_road_bridge_requires_an_active_bridge_tag_and_preserves_real_name() -> None:
    document = {
        "elements": [
            _way(100, {"highway": "primary", "bridge": "yes", "name": "Bridge"}),
            _way(
                101,
                {
                    "highway": "secondary",
                    "bridge": "viaduct",
                    "name": "Bridge",
                    "name:th": "สะพานไทย",
                },
            ),
            _way(102, {"highway": "primary", "name": "Not a bridge"}),
            _way(103, {"highway": "primary", "bridge": "no"}),
            _way(104, {"highway": "primary", "bridge": "false"}),
            _way(105, {"highway": "primary", "bridge": "0"}),
            _way(106, {"highway": "primary", "bridge": "yes"}),
        ]
    }

    context = parse_osm_context(document, _main_route())
    bridges = [
        feature
        for feature in context.features
        if feature.category is OSMFeatureCategory.ROAD_BRIDGE
    ]

    assert [feature.osm_id for feature in bridges] == [106, 100, 101]
    assert bridges[0].name is None
    assert bridges[1].name == "Bridge"
    assert bridges[2].name == "สะพานไทย"
    assert all(
        feature.geometry_kind is OSMGeometryKind.LINESTRING for feature in bridges
    )


@pytest.mark.parametrize("highway", ["footway", "pedestrian"])
def test_footbridge_accepts_pedestrian_highways(highway: str) -> None:
    context = parse_osm_context(
        {"elements": [_way(200, {"highway": highway, "bridge": "yes"})]},
        _main_route(),
    )

    assert [(item.osm_id, item.category) for item in context.features] == [
        (200, OSMFeatureCategory.FOOTBRIDGE)
    ]
    assert context.roads == ()


def test_path_bridge_is_conservative_about_foot_access() -> None:
    document = {
        "elements": [
            _way(210, {"highway": "path", "bridge": "yes", "foot": "designated"}),
            _way(211, {"highway": "path", "bridge": "yes"}),
            _way(212, {"highway": "path", "bridge": "yes", "foot": "no"}),
            _way(213, {"highway": "path", "bridge": "yes", "access": "private"}),
        ]
    }

    context = parse_osm_context(document, _main_route())

    assert [feature.osm_id for feature in context.features] == [210, 211]
    assert context.roads == ()


def test_river_and_canal_way_geometry_is_not_clipped_to_road_context_length() -> None:
    river = _way(300, {"waterway": "river", "name:th": "แม่น้ำทดสอบ"})
    river["geometry"] = [
        {"lat": 13.003, "lon": 99.9995},
        {"lat": 13.005, "lon": 100.0002},
        {"lat": 13.007, "lon": 100.0008},
    ]
    canal = _way(301, {"waterway": "canal", "name": "Test Canal"})

    context = parse_osm_context({"elements": [river, canal]}, _main_route())
    by_id = {feature.osm_id: feature for feature in context.features}

    assert by_id[300].category is OSMFeatureCategory.RIVER
    assert by_id[300].name == "แม่น้ำทดสอบ"
    assert len(by_id[300].parts[0].coordinates) == 3
    assert by_id[300].parts[0].coordinates[0] == GeoPoint(99.9995, 13.003)
    assert by_id[301].category is OSMFeatureCategory.CANAL
    assert by_id[301].name == "Test Canal"
    assert context.roads == ()


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"natural": "water", "water": "river"}, OSMFeatureCategory.RIVER),
        ({"waterway": "riverbank"}, OSMFeatureCategory.RIVER),
        ({"natural": "water", "water": "canal"}, OSMFeatureCategory.CANAL),
    ],
)
def test_water_polygon_way_keeps_footprint(tags: dict, category: OSMFeatureCategory) -> None:
    element = {
        "type": "way",
        "id": 320,
        "geometry": [
            {"lat": 13.004, "lon": 99.9998},
            {"lat": 13.004, "lon": 100.0002},
            {"lat": 13.006, "lon": 100.0002},
            {"lat": 13.006, "lon": 99.9998},
            {"lat": 13.004, "lon": 99.9998},
        ],
        "tags": tags,
    }

    feature = parse_osm_context({"elements": [element]}, _main_route()).features[0]

    assert feature.category is category
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert len(feature.parts[0].coordinates) == 5


def test_water_multipolygon_relation_preserves_hole() -> None:
    relation = {
        "type": "relation",
        "id": 400,
        "tags": {
            "type": "multipolygon",
            "natural": "water",
            "water": "river",
            "name": "River",
            "name:th": "แม่น้ำหลายส่วน",
        },
        "members": [
            {
                "type": "way",
                "role": "outer",
                "geometry": [
                    {"lat": 13.004, "lon": 99.9995},
                    {"lat": 13.004, "lon": 100.0005},
                    {"lat": 13.006, "lon": 100.0005},
                    {"lat": 13.006, "lon": 99.9995},
                    {"lat": 13.004, "lon": 99.9995},
                ],
            },
            {
                "type": "way",
                "role": "inner",
                "geometry": [
                    {"lat": 13.0045, "lon": 99.9998},
                    {"lat": 13.0045, "lon": 100.0002},
                    {"lat": 13.0055, "lon": 100.0002},
                    {"lat": 13.0055, "lon": 99.9998},
                    {"lat": 13.0045, "lon": 99.9998},
                ],
            },
        ],
    }

    feature = parse_osm_context({"elements": [relation]}, _main_route()).features[0]

    assert feature.osm_type == "relation"
    assert feature.osm_id == 400
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert len(feature.parts[0].holes) == 1
    assert feature.name == "แม่น้ำหลายส่วน"


def test_malformed_relation_warns_without_losing_other_candidates() -> None:
    malformed = {
        "type": "relation",
        "id": 410,
        "tags": {"type": "multipolygon", "waterway": "canal"},
        "members": [{"type": "way", "role": "outer"}],
    }

    with pytest.warns(OSMFeatureParseWarning, match="canal relation/410"):
        context = parse_osm_context(
            {"elements": [malformed, _way(411, {"waterway": "canal"})]},
            _main_route(),
        )

    assert [feature.osm_id for feature in context.features] == [411]


def test_malformed_feature_identity_warns_without_losing_other_candidates() -> None:
    malformed = _way(420, {"waterway": "river"})
    malformed.pop("id")

    with pytest.warns(OSMFeatureParseWarning, match="invalid OSM identity"):
        context = parse_osm_context(
            {"elements": [malformed, _way(421, {"waterway": "river"})]},
            _main_route(),
        )

    assert [feature.osm_id for feature in context.features] == [421]


def test_duplicate_osm_feature_is_emitted_once_per_category() -> None:
    bridge = _way(500, {"highway": "primary", "bridge": "yes"})

    context = parse_osm_context({"elements": [bridge, bridge]}, _main_route())

    assert [
        (feature.osm_type, feature.osm_id, feature.category)
        for feature in context.features
    ] == [("way", 500, OSMFeatureCategory.ROAD_BRIDGE)]


def test_feature_corridor_filters_far_water_without_changing_road_corridor() -> None:
    near_road = _way(600, {"highway": "residential", "name": "Near road"})
    near_road["geometry"] = [
        {"lat": 13.005, "lon": 99.9995},
        {"lat": 13.005, "lon": 100.0005},
    ]
    far_canal = _way(
        601,
        {"waterway": "canal"},
        longitude=100.01,
    )

    context = parse_osm_context(
        {"elements": [near_road, far_canal]},
        _main_route(),
        15.0,
        feature_corridor_metres=100.0,
    )

    assert [road.route.name for road in context.roads] == ["Near road"]
    assert context.features == ()


def _closed_feature_way(osm_id: int, tags: dict, west=99.9998, east=100.0002) -> dict:
    return {
        "type": "way",
        "id": osm_id,
        "geometry": [
            {"lat": 13.004, "lon": west},
            {"lat": 13.004, "lon": east},
            {"lat": 13.006, "lon": east},
            {"lat": 13.006, "lon": west},
            {"lat": 13.004, "lon": west},
        ],
        "tags": tags,
    }


def test_building_way_keeps_unnamed_footprint_and_limited_tags() -> None:
    building = _closed_feature_way(
        700, {"building": "commercial", "levels": "3", "operator": "Private"}
    )

    feature = parse_osm_context({"elements": [building]}, _main_route()).features[0]

    assert feature.category is OSMFeatureCategory.BUILDING
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert feature.name is None
    assert feature.tags == (("building", "commercial"),)
    assert feature.osm_type == "way"


@pytest.mark.parametrize(
    ("osm_id", "semantic_tags", "expected_categories"),
    [
        (
            998986400,
            {"amenity": "place_of_worship"},
            {OSMFeatureCategory.BUILDING, OSMFeatureCategory.POI},
        ),
        (
            705,
            {"amenity": "fuel"},
            {OSMFeatureCategory.BUILDING, OSMFeatureCategory.FUEL},
        ),
        (
            706,
            {"shop": "supermarket"},
            {OSMFeatureCategory.BUILDING, OSMFeatureCategory.SHOP},
        ),
    ],
)
def test_building_preserves_each_supported_semantic_category(
    osm_id: int,
    semantic_tags: dict,
    expected_categories: set[OSMFeatureCategory],
) -> None:
    feature_way = _closed_feature_way(
        osm_id,
        {
            "building": "yes",
            "name": "Fo Guang Shan",
            "name:th": "วัดไท่ฮัว ฝอกวงซัน",
            **semantic_tags,
        },
    )

    context = parse_osm_context({"elements": [feature_way]}, _main_route())

    assert {feature.category for feature in context.features} == expected_categories
    assert {feature.identity for feature in context.features} == {("way", osm_id)}
    assert {feature.name for feature in context.features} == {"วัดไท่ฮัว ฝอกวงซัน"}
    assert all(
        feature.geometry_kind is OSMGeometryKind.POLYGON
        for feature in context.features
    )


def test_a005_place_of_worship_keeps_building_footprint_candidate() -> None:
    a005_building = _closed_feature_way(
        998986400,
        {
            "building": "yes",
            "amenity": "place_of_worship",
            "name": "วัดไท่ฮัว ฝอกวงซัน",
        },
    )

    context = parse_osm_context({"elements": [a005_building]}, _main_route())

    assert sum(
        item.category is OSMFeatureCategory.BUILDING for item in context.features
    ) == 1
    assert sum(item.category is OSMFeatureCategory.POI for item in context.features) == 1


def test_building_prefers_thai_name_and_uses_footprint_corridor_intersection() -> None:
    intersecting = _closed_feature_way(
        701,
        {"building": "yes", "name": "English", "name:th": "อาคารทดสอบ"},
        west=100.0008,
        east=100.002,
    )
    outside = _closed_feature_way(
        702, {"building": "yes"}, west=100.002, east=100.003
    )

    context = parse_osm_context({"elements": [intersecting, outside]}, _main_route())

    assert [(item.osm_id, item.name) for item in context.features] == [
        (701, "อาคารทดสอบ")
    ]
    assert context.features[0].parts[0].coordinates[-1] == GeoPoint(100.0008, 13.004)


def test_split_building_multipolygon_is_stitched_and_preserves_hole() -> None:
    relation = {
        "type": "relation",
        "id": 703,
        "tags": {"type": "multipolygon", "building": "yes"},
        "members": [
            {"role": "outer", "geometry": [
                {"lat": 13.004, "lon": 99.9995}, {"lat": 13.004, "lon": 100.0005}
            ]},
            {"role": "outer", "geometry": [
                {"lat": 13.006, "lon": 100.0005}, {"lat": 13.004, "lon": 100.0005}
            ]},
            {"role": "outer", "geometry": [
                {"lat": 13.006, "lon": 99.9995}, {"lat": 13.006, "lon": 100.0005}
            ]},
            {"role": "outer", "geometry": [
                {"lat": 13.004, "lon": 99.9995}, {"lat": 13.006, "lon": 99.9995}
            ]},
            {"role": "inner", "geometry": [
                {"lat": 13.0045, "lon": 99.9998},
                {"lat": 13.0045, "lon": 100.0002},
                {"lat": 13.0055, "lon": 100.0002},
                {"lat": 13.0055, "lon": 99.9998},
                {"lat": 13.0045, "lon": 99.9998},
            ]},
        ],
    }

    feature = parse_osm_context({"elements": [relation]}, _main_route()).features[0]

    assert feature.osm_type == "relation"
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert len(feature.parts[0].holes) == 1


def test_malformed_split_building_relation_warns_and_does_not_crash() -> None:
    relation = {
        "type": "relation",
        "id": 704,
        "tags": {"type": "multipolygon", "building": "yes"},
        "members": [{"role": "outer", "geometry": [
            {"lat": 13.004, "lon": 100.0}, {"lat": 13.005, "lon": 100.0001}
        ]}],
    }

    with pytest.warns(OSMFeatureParseWarning, match="building relation/704"):
        context = parse_osm_context({"elements": [relation]}, _main_route())

    assert context.features == ()


@pytest.mark.parametrize(
    ("osm_id", "tags", "category"),
    [
        (710, {"amenity": "fuel"}, OSMFeatureCategory.FUEL),
        (711, {"shop": "mall"}, OSMFeatureCategory.SHOP),
        (712, {"shop": "department_store"}, OSMFeatureCategory.SHOP),
        (713, {"shop": "supermarket"}, OSMFeatureCategory.SHOP),
        (714, {"amenity": "hospital"}, OSMFeatureCategory.POI),
        (715, {"amenity": "school"}, OSMFeatureCategory.POI),
        (716, {"amenity": "university"}, OSMFeatureCategory.POI),
        (717, {"amenity": "marketplace"}, OSMFeatureCategory.POI),
        (718, {"amenity": "place_of_worship"}, OSMFeatureCategory.POI),
        (719, {"tourism": "museum"}, OSMFeatureCategory.POI),
        (720, {"tourism": "attraction"}, OSMFeatureCategory.POI),
        (721, {"leisure": "stadium"}, OSMFeatureCategory.POI),
        (722, {"leisure": "sports_centre"}, OSMFeatureCategory.POI),
    ],
)
def test_selected_fuel_shop_and_poi_nodes_are_point_features(
    osm_id: int, tags: dict, category: OSMFeatureCategory
) -> None:
    node = {"type": "node", "id": osm_id, "lat": 13.005, "lon": 100.0001, "tags": tags}

    feature = parse_osm_context({"elements": [node]}, _main_route()).features[0]

    assert feature.category is category
    assert feature.geometry_kind is OSMGeometryKind.POINT
    assert feature.name is None
    assert feature.identity == ("node", osm_id)


def test_fuel_way_is_polygon_and_uses_real_thai_name() -> None:
    fuel = _closed_feature_way(
        730, {"amenity": "fuel", "name": "Station", "name:th": "ปั๊มทดสอบ"}
    )

    feature = parse_osm_context({"elements": [fuel]}, _main_route()).features[0]

    assert feature.category is OSMFeatureCategory.FUEL
    assert feature.geometry_kind is OSMGeometryKind.POLYGON
    assert feature.name == "ปั๊มทดสอบ"


@pytest.mark.parametrize("tags", [{"shop": "convenience"}, {"amenity": "restaurant"}, {"amenity": "cafe"}])
def test_ordinary_shop_and_food_poi_are_not_features(tags: dict) -> None:
    node = {"type": "node", "id": 740, "lat": 13.005, "lon": 100.0, "tags": tags}

    assert parse_osm_context({"elements": [node]}, _main_route()).features == ()


def test_duplicate_new_feature_is_emitted_once_per_identity_and_category() -> None:
    fuel = {"type": "node", "id": 750, "lat": 13.005, "lon": 100.0, "tags": {"amenity": "fuel"}}

    context = parse_osm_context({"elements": [fuel, fuel]}, _main_route())

    assert [(item.osm_type, item.osm_id, item.category) for item in context.features] == [
        ("node", 750, OSMFeatureCategory.FUEL)
    ]


def test_duplicate_multi_category_match_is_emitted_once_per_category() -> None:
    building_poi = _closed_feature_way(
        751, {"building": "yes", "amenity": "place_of_worship"}
    )

    context = parse_osm_context(
        {"elements": [building_poi, building_poi]}, _main_route()
    )

    assert [
        (item.osm_type, item.osm_id, item.category) for item in context.features
    ] == [
        ("way", 751, OSMFeatureCategory.BUILDING),
        ("way", 751, OSMFeatureCategory.POI),
    ]


def test_new_feature_query_is_restricted_to_intended_categories() -> None:
    captured: list[str] = []
    fetch_osm_context(
        _main_route(),
        fetcher=lambda query: captured.append(query) or b'{"elements": []}',
    )

    query = captured[0]
    assert 'way["building"](around:100,' in query
    assert 'relation["building"](around:100,' in query
    assert 'nwr["amenity"="fuel"](around:100,' in query
    assert 'nwr["shop"~"^(mall|department_store|supermarket)$"]' in query
    assert 'nwr["amenity"="restaurant"]' not in query
    assert 'nwr["amenity"="cafe"]' not in query
