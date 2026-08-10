from extract_eml import resolve_write_headers


def test_resolve_write_headers_auto_always_writes_headers():
    write_headers, _ = resolve_write_headers(force_headers=None)
    assert write_headers is True


def test_resolve_write_headers_respects_forced_true():
    write_headers, _ = resolve_write_headers(force_headers=True)
    assert write_headers is True


def test_resolve_write_headers_respects_forced_false():
    write_headers, _ = resolve_write_headers(force_headers=False)
    assert write_headers is False
