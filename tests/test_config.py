"""Tests for recbar.config — config loading, defaults, migration."""

import json
import os
import tempfile


def test_load_config_defaults():
    """Config returns sane defaults when no file exists."""
    # Temporarily point to a nonexistent path
    import recbar.config as cfg
    original = cfg.CONFIG_PATH
    cfg.CONFIG_PATH = "/tmp/recbar_test_nonexistent_config.json"
    old_fallback = cfg._OLD_CONFIG
    cfg._OLD_CONFIG = "/tmp/recbar_test_nonexistent_old.json"
    try:
        result = cfg.load_config()
        assert result["position"] == "bottom"
        assert result["web_port"] == 7777
        assert result["obs_host"] == "localhost"
        assert result["obs_port"] == 4455
        assert result["mic_input_name"] == "Mic/Aux"
        assert result["disk_warn_gb"] == 5.0
        assert isinstance(result["scenes"], dict)
        assert isinstance(result["auto_scene_rules"], list)
    finally:
        cfg.CONFIG_PATH = original
        cfg._OLD_CONFIG = old_fallback


def test_load_config_from_file():
    """Config loads and merges user values from JSON file."""
    import recbar.config as cfg
    original = cfg.CONFIG_PATH

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "position": "top",
            "web_port": 9999,
            "mic_input_name": "Custom Mic",
        }, f)
        tmp_path = f.name

    cfg.CONFIG_PATH = tmp_path
    try:
        result = cfg.load_config()
        assert result["position"] == "top"
        assert result["web_port"] == 9999
        assert result["mic_input_name"] == "Custom Mic"
        # Defaults still present for unspecified keys
        assert result["obs_host"] == "localhost"
        assert result["disk_warn_gb"] == 5.0
    finally:
        cfg.CONFIG_PATH = original
        os.unlink(tmp_path)


def test_load_config_malformed_json():
    """Config handles malformed JSON gracefully (returns defaults)."""
    import recbar.config as cfg
    original = cfg.CONFIG_PATH

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{broken json,,}")
        tmp_path = f.name

    cfg.CONFIG_PATH = tmp_path
    try:
        result = cfg.load_config()
        assert result["position"] == "bottom"  # fell back to defaults
        assert result["web_port"] == 7777
    finally:
        cfg.CONFIG_PATH = original
        os.unlink(tmp_path)


def test_layout_zones_sum():
    """Layout zone percentages should sum to ~1.0."""
    from recbar.config import LAYOUT_ZONES
    total = sum(pct for _, pct in LAYOUT_ZONES)
    assert 0.99 <= total <= 1.01, f"Zone percentages sum to {total}, expected ~1.0"


def test_size_presets_exist():
    """All 3 size presets should exist with 4 values each."""
    from recbar.config import SIZE_PRESETS
    assert set(SIZE_PRESETS.keys()) == {1, 2, 3}
    for k, v in SIZE_PRESETS.items():
        assert len(v) == 4, f"Size preset {k} has {len(v)} values, expected 4"
