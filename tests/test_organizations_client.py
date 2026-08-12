from unittest.mock import Mock, patch

import pytest

from organizations_client import (
    OrganizationResolutionError,
    OrganizationsApiError,
    fetch_organizations,
    resolve_organization,
)


def _mock_response(orgs, status=200, text=""):
    response = Mock()
    response.status_code = status
    response.json.return_value = orgs
    response.text = text
    return response


@patch("organizations_client.requests.get")
def test_fetch_organizations_parses_response(mock_get):
    mock_get.return_value = _mock_response(
        [{"id": "uuid-1", "customerID": "samplecollp", "name": "Sample Co", "pod": "us001"}]
    )

    organizations = fetch_organizations("token")

    assert len(organizations) == 1
    assert organizations[0].id == "uuid-1"
    assert organizations[0].customer_id == "samplecollp"
    assert organizations[0].pod == "us001"


@patch("organizations_client.requests.get")
def test_fetch_organizations_raises_on_non_200(mock_get):
    mock_get.return_value = _mock_response([], status=401, text="unauthorized")

    with pytest.raises(OrganizationsApiError, match="401"):
        fetch_organizations("token")


@patch("organizations_client.requests.get")
def test_resolve_organization_by_customer_id(mock_get):
    mock_get.return_value = _mock_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    org = resolve_organization("token", key="customer_id", value="orgb")
    assert org.id == "uuid-2"
    assert org.pod == "us002"


@patch("organizations_client.requests.get")
def test_resolve_organization_by_id(mock_get):
    mock_get.return_value = _mock_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    org = resolve_organization("token", key="id", value="uuid-1")
    assert org.customer_id == "orga"


@patch("organizations_client.requests.get")
def test_resolve_organization_rejects_unknown_value(mock_get):
    mock_get.return_value = _mock_response(
        [{"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"}]
    )

    with pytest.raises(OrganizationResolutionError, match="not among the organizations"):
        resolve_organization("token", key="customer_id", value="not-orga")


@patch("organizations_client.requests.get")
def test_resolve_organization_single_match_is_automatic(mock_get):
    mock_get.return_value = _mock_response(
        [{"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"}]
    )

    org = resolve_organization("token")
    assert org.customer_id == "orga"


@patch("organizations_client.requests.get")
def test_resolve_organization_multiple_without_selector_raises(mock_get):
    mock_get.return_value = _mock_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    with pytest.raises(OrganizationResolutionError, match="multiple organizations"):
        resolve_organization("token")


@patch("organizations_client.requests.get")
def test_resolve_organization_multiple_with_selector(mock_get):
    mock_get.return_value = _mock_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    org = resolve_organization("token", on_multiple_organizations=lambda orgs: orgs[1])
    assert org.customer_id == "orgb"


@patch("organizations_client.requests.get")
def test_resolve_organization_raises_when_no_organizations(mock_get):
    mock_get.return_value = _mock_response([])

    with pytest.raises(OrganizationResolutionError, match="not associated with any organization"):
        resolve_organization("token")
