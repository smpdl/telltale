def test_import_telltale():
    import telltale

    assert telltale is not None


def test_version_exists():
    import telltale

    assert isinstance(telltale.__version__, str)


def test_create_app_import():
    from app import create_app

    assert create_app is not None


def test_create_app_returns_object():
    from app import create_app

    assert create_app() is not None
