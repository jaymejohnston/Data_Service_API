# Arctic Wolf API Clients

This directory contains production-grade Python client libraries for Arctic Wolf APIs, extracted from the getting-started notebooks.

## Modules

### `ticket_api_client.py`

Reusable client for the Arctic Wolf Ticket API with the following features:

- **Retry Logic**: Automatic exponential backoff for transient errors (429, 500, 502, 503, 504)
- **Connection Pooling**: Persistent HTTP session for better performance
- **Structured Errors**: `TicketApiError` exception with status code, error code, and description
- **Type Hints**: Full Python 3.10+ type annotations

#### Usage

Recommended: resolve the organization directly from the PAK instead of configuring
`organization_uuid` by hand (a URL or the wrong Organizations API field pasted in
here otherwise surfaces as a confusing error several calls later):

```python
from ticket_api_client import ArcticWolfTicketApiClient, TicketApiError
from organizations_client import prompt_for_organization_choice

# Auto-resolves when the PAK maps to exactly one organization. If it maps to
# more than one (MSP/parent-company PAKs), pass organization_uuid explicitly
# or on_multiple_organizations to choose interactively/programmatically.
client = ArcticWolfTicketApiClient.from_pak(
    pak_token="your_bearer_token",
    on_multiple_organizations=prompt_for_organization_choice,
)

# organization_uuid no longer needs to be passed to each call below - it's
# stored on the client - but you can still override it per-call if needed.
tickets = client.list_tickets(client.organization_uuid, limit=50)
```

Manual configuration is still supported if you already know the organization UUID
(the Organizations API's `id` field, not `customerID`) and POD/base URL:

```python
from ticket_api_client import ArcticWolfTicketApiClient, TicketApiError

client = ArcticWolfTicketApiClient(
    base_url="https://api.arcticwolf.com",
    token="your_bearer_token"
)

try:
    # List open tickets
    tickets = client.list_tickets(
        organization_uuid="your-org-uuid",
        status="OPEN",
        priority=["HIGH", "URGENT"],
        limit=50
    )
    
    # Get a specific ticket with comments
    ticket = client.get_ticket(
        organization_uuid="your-org-uuid",
        ticket_id=12345,
        include_comments=True
    )
    
    # Add a comment
    comment = client.add_comment(
        organization_uuid="your-org-uuid",
        ticket_id=12345,
        body="This is a comment"
    )
    
    # Close a ticket
    closed = client.close_ticket(
        organization_uuid="your-org-uuid",
        ticket_id=12345,
        comment="Closing as resolved"
    )
    
except TicketApiError as e:
    print(f"API Error: {e}")
```

### `data_explorer_client.py`

Reusable client for the Arctic Wolf Data Retrieval Service API with the following features:

- **Secure Configuration**: `ApiConfig` dataclass with token masking
- **Pagination**: Automatic handling of paginated results
- **Retry Logic**: Exponential backoff for transient errors
- **Query Builder**: Helper for constructing query parameters
- **Type Hints**: Full Python 3.10+ type annotations

#### Usage

Recommended: resolve the organization directly from the PAK instead of configuring
`organization_id` by hand:

```python
from data_explorer_client import ApiConfig, DataExplorerClient
from organizations_client import prompt_for_organization_choice
from datetime import datetime, timedelta, timezone

# Auto-resolves when the PAK maps to exactly one organization. If it maps to
# more than one (MSP/parent-company PAKs), pass organization_id explicitly
# or on_multiple_organizations to choose interactively/programmatically.
config = ApiConfig.from_pak(
    pak_token="your_pak_token",
    on_multiple_organizations=prompt_for_organization_choice,
)

client = DataExplorerClient(config)

# Build time range
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(hours=24)

# Simple query
params = client.build_query_parameters(
    start_time,
    end_time,
    ip_address=("EQ", "10.0.0.1")
)

result = client.execute_query(
    data_source="observations",
    query_id="observations-by-ip-address",
    parameters=params
)

# Paginated query
large_result = client.execute_query_with_pagination(
    data_source="observations",
    query_id="observations-by-ip-address",
    parameters=params,
    limit=100,
    max_results=5000
)
```

## Error Handling

Both clients include structured error handling:

```python
from ticket_api_client import TicketApiError

try:
    tickets = client.list_tickets(organization_uuid="...")
except TicketApiError as e:
    print(f"Status: {e.status_code}")
    print(f"Code: {e.code}")
    print(f"Description: {e.description}")
```

## Retry Behavior

Both clients automatically retry on transient errors with exponential backoff:

- **429 Too Many Requests**: Backs off 1s, 2s, 4s
- **500 Internal Server Error**: Same backoff
- **502 Bad Gateway**: Same backoff
- **503 Service Unavailable**: Same backoff
- **504 Gateway Timeout**: Same backoff

Configure retry count when initializing:

```python
# Default 3 attempts
client = ArcticWolfTicketApiClient(base_url, token)

# Custom: 5 attempts
client = ArcticWolfTicketApiClient(base_url, token, max_retries=5)
```

## Testing

Basic integration test example:

```python
import os
from ticket_api_client import ArcticWolfTicketApiClient, TicketApiError

base_url = os.getenv("BASE_URL")
token = os.getenv("PAK_TOKEN")
org_uuid = os.getenv("ORGANIZATION_UUID")

client = ArcticWolfTicketApiClient(base_url, token)

try:
    page = client.list_tickets(org_uuid, limit=1)
    print(f"✅ Connected. Total tickets: {page.get('meta', {}).get('total')}")
except TicketApiError as e:
    print(f"❌ Connection failed: {e}")
```

## Production Use

When deploying these clients to production:

1. **Secret Management**: Use environment variables or a secrets manager for tokens and credentials
2. **Logging**: Add structured logging (don't log tokens or sensitive data)
3. **Monitoring**: Track retry counts and error rates
4. **Circuit Breaking**: Consider adding circuit breaker logic for cascading failure prevention
5. **Rate Limiting**: Respect API rate limits (429 status codes)

Example with logging:

```python
import logging
from ticket_api_client import ArcticWolfTicketApiClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = ArcticWolfTicketApiClient(base_url, token)

try:
    tickets = client.list_tickets(org_uuid, status="OPEN")
    logger.info(f"Retrieved {len(tickets['results'])} tickets")
except Exception as e:
    logger.error(f"Failed to retrieve tickets: {e}", exc_info=True)
```

## Related Files

- `ticket_api-getting-started.ipynb`: Full notebook with examples and best practices
- `data_explorer-getting-started.ipynb`: Full notebook with query exploration examples

## Support

For issues or questions about the API, refer to:
- Arctic Wolf Documentation: https://docs.arcticwolf.com
- API Reference: Contact your Arctic Wolf account team
