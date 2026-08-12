"""Arctic Wolf Ticket API client with retry logic and error handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional
import os
import re
import requests
import time

from api_url_utils import resolve_api_base_url
from organizations_client import OrganizationInfo, resolve_organization

# The Ticket API's organizationUuid path parameter is declared as `format: uuid`
# in its OpenAPI spec. Validate against that shape at the point of use so a
# pasted URL, customerID, or other wrong value fails fast with a clear message
# instead of a cryptic error from the gateway.
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _validate_organization_uuid(organization_uuid: Optional[str]) -> str:
    if not organization_uuid:
        raise ValueError(
            "organization_uuid is required - pass it explicitly, or construct the "
            "client with ArcticWolfTicketApiClient.from_pak(...) to resolve it "
            "automatically from your PAK."
        )
    if not _UUID_PATTERN.match(organization_uuid):
        raise ValueError(
            f"organization_uuid={organization_uuid!r} is invalid — it must be a UUID "
            "(e.g. 'cbcfa21a-42e5-4087-849d-7a97cbcc10a5'), not a URL, customerID, or "
            "other value. This is the 'id' field from the Organizations API response, "
            "not 'customerID'. Consider using "
            "ArcticWolfTicketApiClient.from_pak(pak_token) to resolve this automatically."
        )
    return organization_uuid


@dataclass
class TicketApiError(Exception):
    """Exception for Ticket API errors with structured error info."""
    status_code: int
    code: str | None = None
    description: str | None = None
    response_text: str | None = None

    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.code:
            parts.append(f"code={self.code}")
        if self.description:
            parts.append(f"description={self.description}")
        if self.response_text and not self.description:
            parts.append(f"response={self.response_text[:500]}")
        return " | ".join(parts)


class ArcticWolfTicketApiClient:
    """Arctic Wolf Ticket API client with built-in retry logic and connection pooling.

    Features:
    - Persistent HTTP session with connection pooling
    - Automatic retry on transient errors (429, 5xx) with exponential backoff
    - Bearer token authentication
    - Structured error handling
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        pod: str | None = None,
        organization_uuid: str | None = None,
    ) -> None:
        """Initialize the Ticket API client.

        Args:
            base_url: API base URL (e.g., https://api.arcticwolf.com)
            token: Bearer token for authentication
            timeout_seconds: Request timeout in seconds
            max_retries: Number of retry attempts for transient errors
            pod: Deployment POD used to derive the regional host when no base URL is provided
            organization_uuid: Default organization UUID to use when a method call
                omits it. Prefer building the client with from_pak(...) instead of
                setting this by hand - see _validate_organization_uuid for why.
        """
        resolved_base_url = base_url or os.getenv("DATA_RETRIEVAL_SERVICE_URL")
        if not resolved_base_url:
            spec_path = Path(__file__).resolve().parent / "api_definitions" / "ticket_api.json"
            resolved_base_url = resolve_api_base_url(
                spec_path=spec_path,
                pod=pod,
                env_url=None,
                fallback_template="https://ticket-api.managedgw.{POD}-prod.arcticwolf.net",
            )
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.organization_uuid = organization_uuid
        if not token:
            token = os.getenv("PAK_TOKEN", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "aw-ticket-api-client/1.0",
        })

    @classmethod
    def from_pak(
        cls,
        pak_token: str,
        *,
        organization_uuid: Optional[str] = None,
        pod: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        on_multiple_organizations: Optional[Callable[[List[OrganizationInfo]], OrganizationInfo]] = None,
    ) -> "ArcticWolfTicketApiClient":
        """Build a client by resolving the organization directly from the PAK.

        Calls the Organizations API with the PAK to discover which organization(s)
        it can access, instead of requiring organization_uuid to be configured by
        hand (easy to get wrong - see _validate_organization_uuid above).

        - If the PAK maps to exactly one organization, it's used automatically.
        - If it maps to more than one (MSP / parent-company PAKs), pass either
          organization_uuid explicitly or on_multiple_organizations - a callback
          that receives the list of OrganizationInfo and returns the one to use
          (e.g. organizations_client.prompt_for_organization_choice). Otherwise
          this raises OrganizationResolutionError rather than guessing.

        The resolved UUID is stored as the returned client's `organization_uuid`,
        so subsequent calls can omit it.
        """
        selected = resolve_organization(
            pak_token,
            key="id",
            value=organization_uuid,
            on_multiple_organizations=on_multiple_organizations,
        )

        return cls(
            base_url=base_url,
            token=pak_token,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            pod=pod or selected.pod,
            organization_uuid=selected.id,
        )

    @staticmethod
    def _normalize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize query parameters for the API."""
        if not params:
            return {}

        normalized: dict[str, Any] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                normalized[key] = str(value).lower()
            elif isinstance(value, (list, tuple, set)):
                normalized[key] = ",".join(str(item) for item in value)
            else:
                normalized[key] = value
        return normalized

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Make HTTP request with automatic retry on transient errors."""
        for attempt in range(self.max_retries):
            try:
                url = f"{self.base_url}{path}"
                response = self.session.request(
                    method=method,
                    url=url,
                    params=self._normalize_params(params),
                    json=json_body,
                    timeout=self.timeout_seconds,
                )

                if response.status_code >= 400:
                    code = None
                    description = None
                    try:
                        body = response.json()
                        code = body.get("code")
                        description = body.get("description")
                    except ValueError:
                        body = None
                    raise TicketApiError(
                        status_code=response.status_code,
                        code=code,
                        description=description,
                        response_text=response.text,
                    )

                if response.status_code == 204 or not response.content:
                    return None
                return response.json()

            except TicketApiError as e:
                # Retry on transient server errors
                if e.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⚠️ {e.status_code} error. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⚠️ Connection error. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise

        return None

    def list_tickets(
        self,
        organization_uuid: str,
        *,
        status: str | Iterable[str] | None = None,
        assignee_by_email: str | Iterable[str] | None = None,
        assignee_by_first_name: str | Iterable[str] | None = None,
        assignee_by_last_name: str | Iterable[str] | None = None,
        updated_before: str | None = None,
        updated_after: str | None = None,
        created_before: str | None = None,
        created_after: str | None = None,
        priority: str | Iterable[str] | None = None,
        ticket_type: str | Iterable[str] | None = None,
        offset: int = 0,
        limit: int = 20,
        include_comments: bool = False,
    ) -> dict[str, Any]:
        """List tickets for an organization with optional filters."""
        organization_uuid = _validate_organization_uuid(organization_uuid)
        path = f"/api/v1/organizations/{organization_uuid}/tickets"
        params = {
            "status": status,
            "assigneeByEmail": assignee_by_email,
            "assigneeByFirstName": assignee_by_first_name,
            "assigneeByLastName": assignee_by_last_name,
            "updatedBefore": updated_before,
            "updatedAfter": updated_after,
            "createdBefore": created_before,
            "createdAfter": created_after,
            "priority": priority,
            "type": ticket_type,
            "offset": offset,
            "limit": limit,
            "includeComments": include_comments,
        }
        return self._request("GET", path, params=params)

    def get_ticket(
        self,
        organization_uuid: str,
        ticket_id: int,
        *,
        include_comments: bool = False,
    ) -> dict[str, Any]:
        """Retrieve a single ticket by ID."""
        organization_uuid = _validate_organization_uuid(organization_uuid)
        path = f"/api/v1/organizations/{organization_uuid}/tickets/{ticket_id}"
        return self._request("GET", path, params={"includeComments": include_comments})

    def add_comment(
        self,
        organization_uuid: str,
        ticket_id: int,
        body: str,
    ) -> dict[str, Any]:
        """Add a public comment to a ticket."""
        organization_uuid = _validate_organization_uuid(organization_uuid)
        path = f"/api/v1/organizations/{organization_uuid}/tickets/{ticket_id}/comments"
        return self._request("POST", path, json_body={"body": body})

    def close_ticket(
        self,
        organization_uuid: str,
        ticket_id: int,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Close a ticket with optional closing comment."""
        organization_uuid = _validate_organization_uuid(organization_uuid)
        path = f"/api/v1/organizations/{organization_uuid}/tickets/{ticket_id}/close"
        json_body = {"comment": comment} if comment else {}
        return self._request("POST", path, json_body=json_body)

    def get_attachment_url(
        self,
        organization_uuid: str,
        ticket_id: int,
        attachment_id: int,
    ) -> dict[str, Any]:
        """Get a pre-signed download URL for an attachment."""
        organization_uuid = _validate_organization_uuid(organization_uuid)
        path = f"/api/v1/organizations/{organization_uuid}/tickets/{ticket_id}/attachments/{attachment_id}"
        return self._request("GET", path)
