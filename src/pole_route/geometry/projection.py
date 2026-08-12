"""Project geographic coordinates into a local UTM metric CRS."""

from dataclasses import dataclass

from pyproj import CRS, Transformer

from pole_route.domain.route import GeoPoint


@dataclass(frozen=True, slots=True)
class MetricProjection:
    """Forward/inverse WGS84 and local UTM transformation."""

    crs: CRS
    _forward: Transformer
    _inverse: Transformer

    @classmethod
    def for_points(cls, points: tuple[GeoPoint, ...]) -> "MetricProjection":
        if not points:
            raise ValueError("At least one geographic point is required")
        mean_longitude = sum(point.longitude for point in points) / len(points)
        mean_latitude = sum(point.latitude for point in points) / len(points)
        zone = min(60, max(1, int((mean_longitude + 180) // 6) + 1))
        epsg = (32600 if mean_latitude >= 0 else 32700) + zone
        crs = CRS.from_epsg(epsg)
        return cls(
            crs,
            Transformer.from_crs("EPSG:4326", crs, always_xy=True),
            Transformer.from_crs(crs, "EPSG:4326", always_xy=True),
        )

    @property
    def name(self) -> str:
        return self.crs.name

    def to_metric(self, point: GeoPoint) -> tuple[float, float]:
        x, y = self._forward.transform(point.longitude, point.latitude)
        return float(x), float(y)

    def to_geographic(self, x: float, y: float) -> GeoPoint:
        longitude, latitude = self._inverse.transform(x, y)
        return GeoPoint(float(longitude), float(latitude))

