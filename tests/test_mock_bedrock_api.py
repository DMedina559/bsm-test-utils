import urllib.request
import json
import zipfile
from pathlib import Path

def test_mock_bedrock_api_fixture(mock_bedrock_api):
    """
    Tests that the mock_bedrock_api fixture correctly serves the download links JSON
    and that the URLs in the JSON point to valid zip files on the mock server.
    """
    api_url = f"{mock_bedrock_api.url}/api/v1.0/download/links"
    
    # 1. Fetch the JSON from the mock server
    req = urllib.request.Request(api_url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        
    # 2. Verify JSON structure
    assert "result" in data
    assert "links" in data["result"]
    links = {item["downloadType"]: item["downloadUrl"] for item in data["result"]["links"]}
    
    # 3. Verify specific links exist and point to our mock server
    assert "serverBedrockWindows" in links
    assert "serverBedrockLinux" in links
    assert "serverBedrockPreviewWindows" in links
    assert "serverBedrockPreviewLinux" in links
    
    assert mock_bedrock_api.url in links["serverBedrockLinux"]
    
    # 4. Verify we can actually download and extract one of the zips
    linux_url = links["serverBedrockLinux"]
    dest_path = mock_bedrock_api.directory / "downloaded_server.zip"
    
    urllib.request.urlretrieve(linux_url, dest_path)
    assert dest_path.exists()
    
    extract_dir = mock_bedrock_api.directory / "extracted"
    with zipfile.ZipFile(dest_path, "r") as zf:
        zf.extractall(extract_dir)
        
    assert (extract_dir / "server.properties").exists()
    assert (extract_dir / "bedrock_server").exists()
