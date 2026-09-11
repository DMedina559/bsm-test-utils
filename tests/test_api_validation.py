import json
import urllib.request

import pytest


def test_mock_bedrock_api_matches_real_structure(mock_bedrock_api):
    """
    Fetches the real Bedrock download API response and compares its structure
    to our mock bedrock API fixture to ensure we keep up with upstream changes.
    """
    real_api_url = (
        "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
    )
    mock_api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"

    # 1. Fetch real API
    real_req = urllib.request.Request(real_api_url)
    try:
        with urllib.request.urlopen(real_req) as response:
            real_data = json.loads(response.read().decode())
    except urllib.error.URLError:
        pytest.skip("Could not reach real Minecraft API. Skipping validation test.")

    # 2. Fetch mock API
    mock_req = urllib.request.Request(mock_api_url)
    with urllib.request.urlopen(mock_req) as response:
        mock_data = json.loads(response.read().decode())

    # 3. Validate overall structure
    assert "result" in mock_data
    assert "links" in mock_data["result"]
    assert "result" in real_data
    assert "links" in real_data["result"]

    # 4. Extract link types
    mock_types = {item["downloadType"] for item in mock_data["result"]["links"]}
    real_types = {item["downloadType"] for item in real_data["result"]["links"]}

    # 5. Assert that our mock provides AT LEAST the types the real API provides.
    # It's okay if our mock provides extra dummy types (like serverJar),
    # but it shouldn't miss any critical ones from upstream.
    for r_type in real_types:
        assert (
            r_type in mock_types
        ), f"Upstream API added new downloadType: {r_type}, but it is missing from mock!"
