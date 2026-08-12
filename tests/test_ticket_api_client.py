from unittest.mock import Mock, patch

import pytest

from ticket_api_client import (
    ArcticWolfTicketApiClient,
    _validate_organization_uuid,
)
from organizations_client import OrganizationResolutionError


def test_validate_organization_uuid_rejects_url():
    with pytest.raises(ValueError, match="organization_uuid"):
        _validate_organization_uuid("https://eloc.global-prod.arcticwolf.net/api/v1/organizations")


def test_validate_organization_uuid_rejects_customer_id_shape():
    """Regression test: the Ticket API wants the 'id' field, not 'customerID' -
    a value that's valid for the Data Retrieval API should still be rejected here."""
    with pytest.raises(ValueError, match="organization_uuid"):
        _validate_organization_uuid("samplecollp")


def test_validate_organization_uuid_rejects_missing_value():
    with pytest.raises(ValueError, match="required"):
        _validate_organization_uuid(None)


def test_validate_organization_uuid_accepts_real_uuid():
    uuid = "cbcfa21a-42e5-4087-849d-7a97cbcc10a5"
    assert _validate_organization_uuid(uuid) == uuid


def test_list_tickets_rejects_bad_uuid_before_making_a_request():
    client = ArcticWolfTicketApiClient(base_url="https://example.test", token="tok")
    with pytest.raises(ValueError, match="organization_uuid"):
        client.list_tickets("not-a-uuid")


def test_get_ticket_rejects_bad_uuid_before_making_a_request():
    client = ArcticWolfTicketApiClient(base_url="https://example.test", token="tok")
    with pytest.raises(ValueError, match="organization_uuid"):
        client.get_ticket("not-a-uuid", 12345)


def test_normalize_params_joins_lists_and_drops_none():
    normalized = ArcticWolfTicketApiClient._normalize_params(
        {"status": ["OPEN", "PENDING"], "flag": True, "skip": None}
    )
    assert normalized == {"status": "OPEN,PENDING", "flag": "true"}


def _mock_organizations_response(orgs):
    response = Mock()
    response.status_code = 200
    response.json.return_value = orgs
    return response


@patch("organizations_client.requests.get")
def test_from_pak_resolves_single_organization(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [
            {
                "id": "cbcfa21a-42e5-4087-849d-7a97cbcc10a5",
                "customerID": "samplecollp",
                "name": "Sample Co",
                "pod": "us001",
            }
        ]
    )

    client = ArcticWolfTicketApiClient.from_pak(pak_token="token")

    assert client.organization_uuid == "cbcfa21a-42e5-4087-849d-7a97cbcc10a5"
    assert client.base_url == "https://ticket-api.managedgw.us001-prod.arcticwolf.net"


@patch("organizations_client.requests.get")
def test_from_pak_requires_selection_for_multiple_organizations(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [
            {"id": "11111111-1111-1111-1111-111111111111", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "22222222-2222-2222-2222-222222222222", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    with pytest.raises(OrganizationResolutionError, match="multiple organizations"):
        ArcticWolfTicketApiClient.from_pak(pak_token="token")


@patch("organizations_client.requests.get")
def test_from_pak_uses_on_multiple_organizations_callback(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [
            {"id": "11111111-1111-1111-1111-111111111111", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "22222222-2222-2222-2222-222222222222", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    client = ArcticWolfTicketApiClient.from_pak(
        pak_token="token",
        on_multiple_organizations=lambda orgs: orgs[1],
    )

    assert client.organization_uuid == "22222222-2222-2222-2222-222222222222"
    assert client.base_url == "https://ticket-api.managedgw.us002-prod.arcticwolf.net"
