"""Shared helpers for resolving organization identity from a PAK.

Both the Data Retrieval API and the Ticket API authorize a PAK through the same
Organizations API - they just key off different fields in its response:

- Data Retrieval API's organizationID path segment wants the `customerID` field
  (e.g. "samplecollp").
- Ticket API's organizationUuid path segment wants the `id` field, a UUID
  (e.g. "cbcfa21a-42e5-4087-849d-7a97cbcc10a5").

Centralizing the lookup here means both data_explorer_client.py and
ticket_api_client.py resolve organizations the same way instead of maintaining
two copies of this logic that can drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional
import os
import requests

ORGANIZATIONS_API_DEFAULT_URL = "https://eloc.global-prod.arcticwolf.net/api/v1/organizations"


@dataclass(frozen=True)
class OrganizationInfo:
    """A single organization returned by the Organizations API for a PAK."""
    id: str
    customer_id: str
    name: str
    pod: str


class OrganizationResolutionError(Exception):
    """Raised when the organization for a PAK can't be unambiguously resolved."""


class OrganizationsApiError(Exception):
    """Raised when the Organizations API call itself fails (bad/expired PAK, etc)."""

    def __init__(self, status_code: int, response_text: str = ""):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(
            f"HTTP {status_code} calling the Organizations API | response={response_text[:200]}"
        )


def fetch_organizations(
    pak_token: str,
    organizations_api_url: Optional[str] = None,
    timeout: int = 30,
) -> List[OrganizationInfo]:
    """Call the Organizations API and return the organizations this PAK can access."""
    url = (
        organizations_api_url
        or os.getenv("ORGANIZATIONS_API_URL")
        or ORGANIZATIONS_API_DEFAULT_URL
    )
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {pak_token}", "Accept": "application/json"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise OrganizationsApiError(response.status_code, response.text)

    return [
        OrganizationInfo(
            id=org.get("id", ""),
            customer_id=org.get("customerID", ""),
            name=org.get("name", ""),
            pod=org.get("pod", ""),
        )
        for org in response.json()
    ]


def prompt_for_organization_choice(organizations: List[OrganizationInfo]) -> OrganizationInfo:
    """Interactively prompt the user to pick one organization (for notebook/CLI use)."""
    print(f"This PAK has access to {len(organizations)} organizations:")
    for i, org in enumerate(organizations, start=1):
        print(f"  {i}. {org.customer_id} — {org.name} (pod={org.pod})")

    while True:
        choice = input(f"Select an organization [1-{len(organizations)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(organizations):
            return organizations[int(choice) - 1]
        print("Invalid selection, try again.")


def resolve_organization(
    pak_token: str,
    *,
    key: str = "customer_id",
    value: Optional[str] = None,
    on_multiple_organizations: Optional[Callable[[List[OrganizationInfo]], OrganizationInfo]] = None,
    organizations_api_url: Optional[str] = None,
) -> OrganizationInfo:
    """Resolve exactly one OrganizationInfo for a PAK.

    `key` selects which OrganizationInfo field `value` is matched against when a
    value is supplied ("customer_id" for the Data Retrieval API, "id" for the
    Ticket API). If `value` is omitted:

    - Exactly one organization available -> it's used automatically.
    - More than one -> on_multiple_organizations(organizations) is called if
      provided (e.g. prompt_for_organization_choice); otherwise
      OrganizationResolutionError is raised rather than guessing.
    """
    organizations = fetch_organizations(pak_token, organizations_api_url)

    if not organizations:
        raise OrganizationResolutionError(
            "This PAK is not associated with any organization. Check that it hasn't "
            "expired and was created from the Unified Portal (not the MSP portal)."
        )

    if value:
        selected = next(
            (org for org in organizations if getattr(org, key) == value),
            None,
        )
        if not selected:
            available = ", ".join(getattr(org, key) for org in organizations)
            raise OrganizationResolutionError(
                f"{key}={value!r} is not among the organizations this PAK can access: {available}"
            )
        return selected

    if len(organizations) == 1:
        return organizations[0]

    if on_multiple_organizations:
        return on_multiple_organizations(organizations)

    available = "\n".join(
        f"  - {org.customer_id} (id={org.id}, pod={org.pod}, name={org.name})"
        for org in organizations
    )
    raise OrganizationResolutionError(
        "This PAK has access to multiple organizations. Pass an explicit organization "
        "identifier, or pass on_multiple_organizations to choose interactively "
        f"(e.g. prompt_for_organization_choice). Available organizations:\n{available}"
    )
