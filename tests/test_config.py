from src.config import load_config


def test_departments_match_config():
    cfg = load_config()
    assert cfg.department_names == ["Lambayeque", "Cusco", "Loreto"]


def test_region_types_cover_the_three_required_geographies():
    cfg = load_config()
    region_types = {d.region_type for d in cfg.departments}
    assert region_types == {"coastal", "andean", "amazonian"}


def test_resolutive_categories_exclude_level_i():
    cfg = load_config()
    assert set(cfg.resolutive_categories).isdisjoint(cfg.non_resolutive_categories)
    assert all(cat.startswith(("II", "III")) for cat in cfg.resolutive_categories)


def test_routing_engine_is_docker_free():
    cfg = load_config()
    assert cfg.routing["engine"] == "osmnx_networkx"


def test_paths_resolve_and_create_directories():
    cfg = load_config()
    for key in ["raw_dir", "processed_dir", "outputs_dir", "logs_dir"]:
        p = cfg.path(key)
        assert p.exists()
