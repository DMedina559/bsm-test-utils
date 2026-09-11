def test_mock_http_server_fixture(mock_http_server):
    assert mock_http_server.url.startswith("http://127.0.0.1:")
    
    # Test serving a file
    test_file = mock_http_server.directory / "hello.txt"
    test_file.write_text("world")
    
    import urllib.request
    with urllib.request.urlopen(f"{mock_http_server.url}/hello.txt") as response:
        assert response.read().decode() == "world"

def test_dummy_server_zip_fixture(dummy_server_zip):
    zip_path = dummy_server_zip(version="1.20.0.01")
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"

def test_behavior_pack_fixtures(valid_behavior_pack, invalid_behavior_pack, valid_behavior_pack_zip):
    assert valid_behavior_pack.is_dir()
    assert invalid_behavior_pack.is_dir()
    assert valid_behavior_pack_zip.is_file()
    assert valid_behavior_pack_zip.suffix == ".mcpack"

def test_new_bundle_fixtures(valid_mcaddon_zip, valid_mcworld_zip):
    assert valid_mcaddon_zip.is_file()
    assert valid_mcaddon_zip.suffix == ".mcaddon"
    
    assert valid_mcworld_zip.is_file()
    assert valid_mcworld_zip.suffix == ".mcworld"
