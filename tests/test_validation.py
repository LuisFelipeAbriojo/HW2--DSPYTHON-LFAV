import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from src.validation import (
    SIN_CATEGORIA,
    check_district_containment,
    check_duplicate_codes,
    check_missing_coordinates,
    check_out_of_bbox,
    check_swapped_lat_lon,
    normalize_category,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("I-1", "I-1"),
        ("ii-1", "II-1"),
        ("III-E", "III-E"),
        ("II 2", "II-2"),
        ("0", SIN_CATEGORIA),
        ("", SIN_CATEGORIA),
        (None, SIN_CATEGORIA),
        ("GARBAGE", SIN_CATEGORIA),
    ],
)
def test_normalize_category(raw, expected):
    assert normalize_category(raw) == expected


def _facility_df(rows: list[dict]) -> pd.DataFrame:
    base = {"facility_code": 0, "lat": -12.0, "lon": -76.0, "ubigeo": "150101"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_check_missing_coordinates_flags_null_and_near_zero():
    df = _facility_df(
        [
            {"facility_code": 1, "lat": -12.0, "lon": -76.0},
            {"facility_code": 2, "lat": None, "lon": -76.0},
            {"facility_code": 3, "lat": 0.0, "lon": 0.0},
            {"facility_code": 4, "lat": -6e-8, "lon": -7e-7},
        ]
    )
    result, flagged, report = check_missing_coordinates(df)
    assert len(flagged) == 3
    assert report["n_flagged"] == 3
    assert result.loc[result["facility_code"] == 1, "has_valid_coords"].item()


def test_check_out_of_bbox_flags_points_outside_peru():
    df = _facility_df(
        [
            {"facility_code": 1, "lat": -12.0, "lon": -76.0},  # Lima, in bbox
            {"facility_code": 2, "lat": 40.0, "lon": -3.0},  # Madrid, out of bbox
        ]
    )
    df, _, _ = check_missing_coordinates(df)
    result, flagged, report = check_out_of_bbox(df)
    assert report["n_flagged"] == 1
    assert flagged["facility_code"].tolist() == [2]


def test_check_swapped_lat_lon_corrects_only_when_it_lands_in_peru():
    df = _facility_df(
        [
            # transposed: true point is (lat=-12.0, lon=-76.0), stored as (lat=-76.0, lon=-12.0)
            {"facility_code": 1, "lat": -76.0, "lon": -12.0},
            # genuinely out of Peru either way — must NOT be "corrected"
            {"facility_code": 2, "lat": 40.0, "lon": -3.0},
        ]
    )
    df, _, _ = check_missing_coordinates(df)
    df, _, _ = check_out_of_bbox(df)
    result, flagged, report = check_swapped_lat_lon(df)
    assert report["n_flagged"] == 1
    assert flagged["facility_code"].tolist() == [1]
    assert result.loc[result["facility_code"] == 1, "lat"].item() == -12.0
    assert result.loc[result["facility_code"] == 1, "lon"].item() == -76.0
    assert result.loc[result["facility_code"] == 2, "lat"].item() == 40.0


def test_check_duplicate_codes_drops_only_the_repeat():
    df = _facility_df(
        [
            {"facility_code": 100, "lat": -12.0, "lon": -76.0},
            {"facility_code": 100, "lat": -12.0, "lon": -76.0},
            {"facility_code": 200, "lat": -12.0, "lon": -76.0},
        ]
    )
    result, flagged, report = check_duplicate_codes(df)
    assert len(result) == 2
    assert report["n_flagged"] == 1
    assert report["n_involved_rows"] == 2


def test_check_district_containment_flags_point_outside_its_declared_district():
    # Two adjacent 1x1 degree "districts" — a facility whose UBIGEO says
    # district A but whose coordinate actually falls in district B.
    district_a = gpd.GeoDataFrame(
        {"IDDIST": ["010101"], "geometry": [box(-76.0, -12.0, -75.0, -11.0)]}, crs=4326
    )
    district_b = gpd.GeoDataFrame(
        {"IDDIST": ["010102"], "geometry": [box(-75.0, -12.0, -74.0, -11.0)]}, crs=4326
    )
    districts = pd.concat([district_a, district_b], ignore_index=True)
    districts = gpd.GeoDataFrame(districts, crs=4326)

    df = _facility_df(
        [
            {"facility_code": 1, "ubigeo": "010101", "lat": -11.5, "lon": -75.5},  # correctly inside A
            {"facility_code": 2, "ubigeo": "010101", "lat": -11.5, "lon": -74.5},  # claims A, actually in B
        ]
    )
    df, _, _ = check_missing_coordinates(df)
    df, _, _ = check_out_of_bbox(df)
    result, flagged, report = check_district_containment(df, districts)
    assert report["n_checkable"] == 2
    assert report["n_flagged"] == 1
    assert flagged["facility_code"].tolist() == [2]
