import json
import os
import urllib.request

import pytest

RECORDED_MINECRAFT_API_RESPONSE = {
    "result": {
        "links": [
            {
                "downloadType": "serverBedrockWindows",
                "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-win/bedrock-server-1.26.45.1.zip",
            },
            {
                "downloadType": "serverBedrockLinux",
                "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.45.1.zip",
            },
            {
                "downloadType": "serverBedrockPreviewWindows",
                "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-win-preview/bedrock-server-1.26.60.23.zip",
            },
            {
                "downloadType": "serverBedrockPreviewLinux",
                "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-linux-preview/bedrock-server-1.26.60.23.zip",
            },
        ]
    }
}


def test_mock_bedrock_api_matches_recorded_structure(mock_bedrock_api):
    """
    Validates our mock bedrock API against a recorded upstream response structure
    without making live network calls during standard test runs.
    """
    mock_api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"
    mock_req = urllib.request.Request(mock_api_url)
    with urllib.request.urlopen(mock_req, timeout=5) as response:
        mock_data = json.loads(response.read().decode("utf-8"))

    assert "result" in mock_data
    assert "links" in mock_data["result"]

    mock_types = {item["downloadType"] for item in mock_data["result"]["links"]}
    recorded_types = {
        item["downloadType"]
        for item in RECORDED_MINECRAFT_API_RESPONSE["result"]["links"]
    }

    for r_type in recorded_types:
        assert r_type in mock_types


@pytest.mark.upstream_api
def test_mock_bedrock_api_matches_live_upstream(mock_bedrock_api, request):
    """
    Opt-in live validation against the official Minecraft download API with a bounded timeout.
    Run with `--run-upstream-api` or `BSM_RUN_UPSTREAM_API=1`.
    """
    if not (
        request.config.getoption("--run-upstream-api")
        or os.environ.get("BSM_RUN_UPSTREAM_API") == "1"
    ):
        pytest.skip(
            "Live upstream API validation is opt-in (use --run-upstream-api or BSM_RUN_UPSTREAM_API=1)."
        )

    real_api_url = (
        "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
    )
    mock_api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"

    real_req = urllib.request.Request(real_api_url)
    try:
        with urllib.request.urlopen(real_req, timeout=5.0) as response:
            real_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        pytest.skip("Could not reach real Minecraft API within timeout.")

    mock_req = urllib.request.Request(mock_api_url)
    with urllib.request.urlopen(mock_req, timeout=5.0) as response:
        mock_data = json.loads(response.read().decode("utf-8"))

    mock_types = {item["downloadType"] for item in mock_data["result"]["links"]}
    real_types = {item["downloadType"] for item in real_data["result"]["links"]}

    for r_type in real_types:
        assert (
            r_type in mock_types
        ), f"Upstream API added new downloadType: {r_type}, missing from mock!"
