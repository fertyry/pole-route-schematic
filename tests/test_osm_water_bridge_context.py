import pytest

from pole_route.domain.context import OSMFeatureCategory
from pole_route.domain.route import GeoPoint, Route
from pole_route.geometry.projection import MetricProjection
from pole_route.importers.osm_context import parse_osm_context
from pole_route.project.storage import osm_features_from_data, osm_features_to_data
from shapely.geometry import LineString


def _route():
    return Route("Main", "test.kml", (GeoPoint(100.0, 13.0), GeoPoint(100.0, 13.01)))


def _way(osm_id, points, tags):
    return {
        "type": "way", "id": osm_id,
        "geometry": [{"lon": lon, "lat": lat} for lon, lat in points],
        "tags": tags,
    }


def test_long_canal_gets_derived_display_geometry_without_losing_source():
    document = {"elements": [_way(
        10, ((99.98, 13.005), (100.02, 13.005)),
        {"waterway": "canal", "name": "คลองจริง"},
    )]}
    feature = parse_osm_context(document, _route()).features[0]
    projection = MetricProjection.for_points(_route().points)
    source_length = sum(
        LineString(
            projection.to_metric(point) for point in part.coordinates
        ).length for part in feature.parts
    )
    display_length = sum(
        LineString(
            projection.to_metric(point) for point in part.coordinates
        ).length for part in feature.render_parts
    )

    assert feature.parts != feature.display_parts
    assert 300.0 < display_length < source_length
    restored = osm_features_from_data(osm_features_to_data([feature]))[0]
    assert restored.parts == feature.parts
    assert restored.display_parts == feature.display_parts


def test_parallel_water_preserves_relevant_span_and_end_margins():
    document = {"elements": [_way(
        11, ((100.0004, 12.98), (100.0004, 13.03)),
        {"waterway": "river"},
    )]}
    feature = parse_osm_context(document, _route()).features[0]
    projection = MetricProjection.for_points(_route().points)
    display = LineString(
        projection.to_metric(point) for point in feature.render_parts[0].coordinates
    )
    main = LineString(projection.to_metric(point) for point in _route().points)

    assert display.length > main.length
    # The relevant core already includes the 100 m route corridor at each
    # endpoint; the water-specific 175 m margins extend that complete span.
    assert display.length == pytest.approx(main.length + 550.0, abs=25.0)


def test_crossing_water_keeps_context_on_both_sides_of_route():
    document = {"elements": [_way(
        12, ((99.98, 13.005), (100.02, 13.005)),
        {"waterway": "canal"},
    )]}
    feature = parse_osm_context(document, _route()).features[0]
    projection = MetricProjection.for_points(_route().points)
    main = LineString(projection.to_metric(point) for point in _route().points)
    display = LineString(
        projection.to_metric(point) for point in feature.render_parts[0].coordinates
    )
    crossing = main.interpolate(main.project(display.centroid))

    assert display.coords[0][0] < crossing.x < display.coords[-1][0]


def test_bridge_crossing_one_canal_gets_conservative_relationship():
    document = {"elements": [
        _way(10, ((99.999, 13.005), (100.001, 13.005)),
             {"waterway": "canal", "name:th": "คลองหนึ่ง"}),
        _way(20, ((99.9995, 13.005), (100.0005, 13.005)),
             {"highway": "primary", "bridge": "yes"}),
    ]}
    features = parse_osm_context(document, _route()).features
    bridge = next(item for item in features if item.category is OSMFeatureCategory.ROAD_BRIDGE)

    assert bridge.crosses_category is OSMFeatureCategory.CANAL
    assert bridge.crosses_source_id == "way/10"
    assert bridge.crosses_name == "คลองหนึ่ง"


def test_footbridge_crossing_one_river_gets_conservative_relationship():
    document = {"elements": [
        _way(30, ((99.999, 13.005), (100.001, 13.005)),
             {"waterway": "river", "name": "แม่น้ำจริง"}),
        _way(31, ((99.9995, 13.005), (100.0005, 13.005)),
             {"highway": "footway", "bridge": "yes"}),
    ]}
    features = parse_osm_context(document, _route()).features
    bridge = next(item for item in features if item.category is OSMFeatureCategory.FOOTBRIDGE)

    assert bridge.crosses_category is OSMFeatureCategory.RIVER
    assert bridge.crosses_source_id == "way/30"
    assert bridge.crosses_name == "แม่น้ำจริง"


def test_ambiguous_bridge_water_intersection_is_not_guessed():
    document = {"elements": [
        _way(10, ((99.999, 13.005), (100.001, 13.005)), {"waterway": "canal"}),
        _way(11, ((99.999, 13.005), (100.001, 13.005)), {"waterway": "river"}),
        _way(20, ((99.9995, 13.005), (100.0005, 13.005)),
             {"highway": "footway", "bridge": "yes"}),
    ]}
    bridge = next(
        item for item in parse_osm_context(document, _route()).features
        if item.category is OSMFeatureCategory.FOOTBRIDGE
    )

    assert bridge.crosses_category is None
    assert bridge.crosses_feature_key == ""


def test_nearby_non_crossing_bridge_does_not_get_water_relationship():
    document = {"elements": [
        _way(10, ((99.999, 13.005), (100.001, 13.005)), {"waterway": "canal"}),
        _way(20, ((99.9995, 13.00501), (100.0005, 13.00501)),
             {"highway": "footway", "bridge": "yes"}),
    ]}
    bridge = next(
        item for item in parse_osm_context(document, _route()).features
        if item.category is OSMFeatureCategory.FOOTBRIDGE
    )

    assert bridge.crosses_category is None
    assert bridge.crosses_source_id == ""


def test_water_polygon_display_clip_preserves_hole_and_source_polygon():
    relation = {
        "type": "relation",
        "id": 400,
        "tags": {"type": "multipolygon", "natural": "water", "water": "river"},
        "members": [
            {
                "type": "way", "role": "outer",
                "geometry": [
                    {"lat": 12.99, "lon": 99.999}, {"lat": 12.99, "lon": 100.001},
                    {"lat": 13.02, "lon": 100.001}, {"lat": 13.02, "lon": 99.999},
                    {"lat": 12.99, "lon": 99.999},
                ],
            },
            {
                "type": "way", "role": "inner",
                "geometry": [
                    {"lat": 13.004, "lon": 99.9998}, {"lat": 13.004, "lon": 100.0002},
                    {"lat": 13.006, "lon": 100.0002}, {"lat": 13.006, "lon": 99.9998},
                    {"lat": 13.004, "lon": 99.9998},
                ],
            },
        ],
    }

    feature = parse_osm_context({"elements": [relation]}, _route()).features[0]

    assert len(feature.parts[0].holes) == 1
    assert feature.display_parts
    assert len(feature.display_parts[0].holes) == 1
    assert feature.display_parts != feature.parts
