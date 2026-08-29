"""Deterministic, proposal-only matching of PEA assets to imported PEA poles."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import asin, cos, radians, sin, sqrt

from pole_route.domain.pea_asset import (
    AssetMatchState,
    AssetPoleCandidate,
    PEAAsset,
    PEAAssetMatch,
)
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.domain.pea_ordering import PEAPoleOrdering


@dataclass(frozen=True, slots=True)
class AssetMatchPolicy:
    strong_metres: float = 5.0
    review_metres: float = 15.0
    candidate_metres: float = 50.0
    ambiguity_metres: float = 1.0
    max_candidates: int = 5


DEFAULT_ASSET_MATCH_POLICY = AssetMatchPolicy()


def match_pea_assets(
    assets: list[PEAAsset] | tuple[PEAAsset, ...],
    poles: list[PEAPoleRecord] | tuple[PEAPoleRecord, ...],
    ordering: PEAPoleOrdering | None = None,
    previous: list[PEAAssetMatch] | tuple[PEAAssetMatch, ...] = (),
    policy: AssetMatchPolicy = DEFAULT_ASSET_MATCH_POLICY,
    *,
    reset_confirmed: bool = False,
) -> tuple[PEAAssetMatch, ...]:
    entries = {entry.source_key: entry for entry in ordering.entries} if ordering else {}
    old = {item.asset_id: item for item in previous}
    results = []
    for asset in sorted(assets, key=lambda item: item.stable_id):
        prior = old.get(asset.stable_id)
        candidates = _candidates(asset, poles, entries, policy)
        if prior and prior.state is AssetMatchState.CONFIRMED and not reset_confirmed:
            keys = {item.pole_source_key for item in candidates}
            if prior.confirmed_pole_key and prior.confirmed_pole_key not in keys:
                pole = next((p for p in poles if p.source_key == prior.confirmed_pole_key), None)
                if pole is not None and asset.coordinate_valid:
                    candidates = tuple(
                        sorted((*candidates, _candidate(asset, pole, entries, policy)), key=_rank)
                    )
            results.append(replace(prior, candidates=candidates))
            continue
        eligible = [item for item in candidates if item.pole_included is not False]
        suggested = eligible[0] if eligible and eligible[0].distance_metres <= policy.review_metres else None
        if suggested is None:
            state = AssetMatchState.UNMATCHED
        elif len(eligible) > 1 and eligible[1].distance_metres - suggested.distance_metres <= policy.ambiguity_metres:
            state = AssetMatchState.AMBIGUOUS
        else:
            state = AssetMatchState.SUGGESTED
        results.append(PEAAssetMatch(
            asset_id=asset.stable_id,
            state=state,
            candidates=candidates,
            suggested_pole_key=suggested.pole_source_key if suggested else None,
            included=prior.included if prior else True,
        ))
    return tuple(results)


def _candidates(asset, poles, entries, policy):
    if not asset.coordinate_valid:
        return ()
    values = [_candidate(asset, pole, entries, policy) for pole in poles]
    return tuple(item for item in sorted(values, key=_rank) if item.distance_metres <= policy.candidate_metres)[:policy.max_candidates]


def _candidate(asset, pole, entries, policy):
    entry = entries.get(pole.source_key)
    distance = _distance(asset.latitude, asset.longitude, pole.latitude, pole.longitude)
    strength = (
        "strong" if distance <= policy.strong_metres
        else "review" if distance <= policy.review_metres
        else "weak"
    )
    return AssetPoleCandidate(
        pole_source_key=pole.source_key,
        pole_id=pole.source_id,
        distance_metres=distance,
        pole_order=(entry.confirmed_order or entry.review_order) if entry else None,
        pole_included=entry.included if entry else None,
        pole_qc=entry.qc_status.value if entry else "",
        strength=strength,
    )


def _rank(item):
    return item.distance_metres, item.pole_source_key


def _distance(lat1, lon1, lat2, lon2):
    radius = 6_371_008.8
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * radius * asin(sqrt(a))
