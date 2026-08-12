from unittest.mock import Mock, patch

import pytest

from data_explorer_client import (
    ApiConfig,
    DataExplorerClient,
    OrganizationInfo,
    OrganizationResolutionError,
)


def test_organization_id_rejects_url_pasted_by_mistake():
    """Regression test: an org URL/UUID pasted into organization_id must fail fast
    with a clear error instead of silently building a malformed request path that
    only surfaces as a cryptic 403 from the gateway."""
    with pytest.raises(ValueError, match="organization_id"):
        ApiConfig(
            base_url="https://example.test",
            organization_id="https://eloc.global-prod.arcticwolf.net/api/v1/organizations",
            pak_token="token",
        )


def test_organization_id_allows_letters_numbers_underscores_hyphens():
    config = ApiConfig(
        base_url="https://example.test",
        organization_id="sample-collp_01",
        pak_token="token",
    )
    assert config.organization_id == "sample-collp_01"


def _mock_organizations_response(orgs):
    response = Mock()
    response.status_code = 200
    response.json.return_value = orgs
    return response


@patch("organizations_client.requests.get")
def test_from_pak_auto_resolves_single_organization(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [{"id": "uuid-1", "customerID": "samplecollp", "name": "Sample Co Llp", "pod": "us001"}]
    )

    config = ApiConfig.from_pak(pak_token="token")

    assert config.organization_id == "samplecollp"
    assert config.pod == "us001"
    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer token"


@patch("organizations_client.requests.get")
def test_from_pak_requires_selection_for_multiple_organizations(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    with pytest.raises(OrganizationResolutionError, match="multiple organizations"):
        ApiConfig.from_pak(pak_token="token")


@patch("organizations_client.requests.get")
def test_from_pak_uses_on_multiple_organizations_callback(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [
            {"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"},
            {"id": "uuid-2", "customerID": "orgb", "name": "Org B", "pod": "us002"},
        ]
    )

    def pick_second(organizations: list[OrganizationInfo]) -> OrganizationInfo:
        return organizations[1]

    config = ApiConfig.from_pak(pak_token="token", on_multiple_organizations=pick_second)

    assert config.organization_id == "orgb"
    assert config.pod == "us002"


@patch("organizations_client.requests.get")
def test_from_pak_rejects_explicit_organization_id_not_in_list(mock_get):
    mock_get.return_value = _mock_organizations_response(
        [{"id": "uuid-1", "customerID": "orga", "name": "Org A", "pod": "us001"}]
    )

    with pytest.raises(OrganizationResolutionError, match="not among the organizations"):
        ApiConfig.from_pak(pak_token="token", organization_id="not-orga")


@patch("organizations_client.requests.get")
def test_from_pak_raises_on_non_200_response(mock_get):
    response = Mock()
    response.status_code = 401
    response.text = "unauthorized"
    mock_get.return_value = response

    with pytest.raises(Exception, match="401"):
        ApiConfig.from_pak(pak_token="bad-token")


def test_build_api_url_uses_openapi_operation_paths():
    config = ApiConfig(
        base_url="https://example.test",
        organization_id="org-123",
        pak_token="token",
    )
    client = DataExplorerClient(config)

    url = client._build_api_url(
        "executePredefinedQuery",
        dataSource="observations",
        queryId="observations-by-ip-address",
    )

    assert url == (
        "https://example.test/api/v1beta/organizations/org-123/"
        "data-sources/observations/predefined-queries/"
        "observations-by-ip-address/execute"
    )


def test_config_uses_pod_to_build_default_base_url():
    config = ApiConfig(
        organization_id="org-123",
        pak_token="token",
        pod="us001",
    )

    assert config.base_url == (
        "https://data-retrieval-service-prod.managedgw.us001-prod.arcticwolf.net"
    )
