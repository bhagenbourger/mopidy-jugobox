from mopidy_jugobox import Extension


def test_get_default_config() -> None:
    ext = Extension()
    config = ext.get_default_config()
    assert "[jugobox]" in config
    assert "enabled = true" in config
    assert "nfc_enabled = true" in config
    assert 'config_path = "/etc/mopidy/jugobox.json"' in config


def test_get_config_schema() -> None:
    ext = Extension()
    schema = ext.get_config_schema()
    assert "nfc_enabled" in schema
    assert "config_path" in schema
