# Type Safety and Node ID Format

## Current Implementation

### Node ID Format
Node IDs are **strings** in the format `{normativa_id}_{number}`, e.g.:
- `BOE-A-1978-31229_44`
- `BOE-A-2015-10566_1`

This format combines the parent normativa ID with a sequential number for uniqueness.

### Type Hints
All adapter methods and API endpoints now use `str` for node/article IDs:

```python
# Adapter methods (src/infrastructure/graphdb/adapter.py)
get_article_by_id(node_id: str)
get_article_versions(article_id: str)
get_article_with_context(article_id: str, ...)
get_article_rich_text(article_id: str)
get_version_text(node_id: str)
get_all_next_versions(node_id: str)
get_previous_version(node_id: str)
get_latest_version(article_id: str)
get_referred_articles(article_id: str, ...)

# API endpoints (src/api/v1/article_endpoints.py)
GET /api/v1/article/{node_id}         # node_id: str
GET /api/v1/article/{node_id}/versions  # node_id: str
```

## Files Modified

- `src/infrastructure/graphdb/adapter.py` - All node ID parameters use `str`
- `src/api/v1/article_endpoints.py` - Path parameters accept `str`
- `src/domain/services/chat_service.py` - `_get_next_versions` uses `str`
