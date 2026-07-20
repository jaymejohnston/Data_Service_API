from api_url_utils import resolve_api_base_url


def test_resolve_api_base_url_prefers_server_entry_for_pod(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        '{"servers": [{"url": "https://ticket-api.managedgw.us001-prod.arcticwolf.net", "description": "US001"}, {"url": "https://ticket-api.managedgw.us002-prod.arcticwolf.net", "description": "US002"}]}',
        encoding="utf-8",
    )

    url = resolve_api_base_url(spec_path=spec_path, pod="us001")

    assert url == "https://ticket-api.managedgw.us001-prod.arcticwolf.net"


def test_resolve_api_base_url_uses_environment_value_when_present(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text('{"servers": []}', encoding="utf-8")

    url = resolve_api_base_url(spec_path=spec_path, pod="us001", env_url="https://data-retrieval-service-prod.managedgw.${POD}-prod.arcticwolf.net")

    assert url == "https://data-retrieval-service-prod.managedgw.us001-prod.arcticwolf.net"
