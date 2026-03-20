# Preparing MCP Server Source Code

## 1. Create mcp-probe-service-properties.json file in the root of your MCP server source code.

## 2. Add the following properties to the file:
- project_code: The code of your MCP server.
- server_command: The command to start your MCP server.
- transport: The transport to use for your MCP server.
- service_url: The URL of your MCP server. (This should be the URL where the mcp-probe-service is running)
- test_env: The environment variables to use for your MCP server.
- test_data: The test data to use for your MCP server.

## Example:
```json
{
    "project_code": "library-server",
    "server_command": "uv run server.py",
    "transport": "stdio",
    "service_url": "http://localhost:8080",
    "test_env": {
        "EXAMPLE_ENV_VAR": "any_variable_required_for_your_mcp_server"
    },
    "test_data": {
        "available_books": [
        {"book_id": "B001", "title": "The Great Gatsby", "genre": "Classic"},
        {"book_id": "B002", "title": "Dune", "genre": "Science Fiction"},
        {"book_id": "B004", "title": "Pride and Prejudice", "genre": "Romance"}
        ],
        "checked_out_books": [
        {"book_id": "B003", "title": "Murder on the Orient Express", "genre": "Mystery"}
        ],
        "invalid_book_ids": ["B999", "INVALID", ""],
        "valid_user_names": ["Alice", "Bob"],
        "valid_genres": ["Classic", "Science Fiction", "Mystery", "Romance"],
        "invalid_genres": ["Cooking", "xyz_nonexistent"],
        "catalog_resource_uri": "library://catalog/inventory"
    }
}
```
