# Bedrock Server Dummy

A dummy executable and configuration package designed to simulate a Minecraft Bedrock Dedicated Server. Used primarily for integration testing (e.g., testing the Bedrock Server Manager).

## Usage

```python
from bedrock_server_dummy import setup_dummy_server

# Copies the correct platform binary and dummy config files to the target directory.
setup_dummy_server("/path/to/test/server_dir")
```
