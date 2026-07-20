import pytest

from data_explorer_client import ApiConfig, DataExplorerClient


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
