"""Arctic Wolf Data Retrieval API client with pagination and retry logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, List, Dict
import os
import re
import requests
import json
import time

from api_url_utils import resolve_api_base_url


@dataclass
class ApiConfig:
    """Configuration for Data Retrieval API access.

    Token is never logged or printed in string representations.
    """
    organization_id: str
    pak_token: str
    base_url: Optional[str] = None
    pod: Optional[str] = None

    def __post_init__(self):
        if not self.organization_id or not self.pak_token:
            raise ValueError(
                "Missing required configuration. "
                "Set organization_id and pak_token."
            )

        if not self.base_url:
            self.base_url = self._build_base_url_from_environment()

    def _build_base_url_from_environment(self) -> str:
        """Derive the service base URL from the configured service URL or POD value."""
        if self.base_url:
            return self.base_url.rstrip("/")

        env_value = os.getenv("DATA_RETRIEVAL_SERVICE_URL")
        spec_path = Path(__file__).resolve().parent / "api_definitions" / "data_retrieval_api.json"
        return resolve_api_base_url(
            spec_path=spec_path,
            pod=self.pod,
            env_url=env_value,
            fallback_template="https://data-retrieval-service-prod.managedgw.{POD}-prod.arcticwolf.net",
        )

    def get_auth_headers(self) -> Dict[str, str]:
        """Return authentication headers for API requests."""
        return {
            "Authorization": f"Bearer {self.pak_token}",
            "Content-Type": "application/json"
        }

    def __repr__(self) -> str:
        """Safe representation without exposing token."""
        return (
            f"ApiConfig(base_url={self.base_url!r}, "
            f"organization_id={self.organization_id!r}, "
            f"pod={self.pod!r}, "
            f"pak_token=*****)"
        )


@dataclass
class DataExplorerError(Exception):
    """Exception for Data Retrieval API errors."""
    status_code: int
    message: str
    response_text: Optional[str] = None

    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}", self.message]
        if self.response_text and len(self.response_text) < 200:
            parts.append(f"response={self.response_text}")
        return " | ".join(parts)


class DataExplorerClient:
    """Arctic Wolf Data Retrieval API client with pagination and retry logic.
    
    Features:
    - Automatic pagination support
    - Retry logic for transient errors (502, 503, etc) with exponential backoff
    - Query parameter building helpers
    - Result analysis utilities
    """

    def __init__(self, config: ApiConfig, max_retries: int = 3):
        """Initialize the Data Explorer client.

        Args:
            config: ApiConfig instance with credentials
            max_retries: Number of retry attempts for transient errors
        """
        self.config = config
        self.max_retries = max_retries

    def _load_openapi_spec(self) -> Optional[Dict[str, Any]]:
        """Load the bundled OpenAPI definition for the Data Retrieval API."""
        spec_path = Path(__file__).resolve().parent / "api_definitions" / "data_retrieval_api.json"
        if not spec_path.exists():
            return None

        with spec_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _get_operation_path(self, operation_id: str) -> Optional[str]:
        """Look up the path template for an operation ID from the OpenAPI spec."""
        spec = self._load_openapi_spec()
        if not spec:
            return None

        for path_template, methods in spec.get("paths", {}).items():
            for _, operation in methods.items():
                if operation.get("operationId") == operation_id:
                    return path_template
        return None

    def _build_api_url(self, operation_id: str, **path_params: str) -> str:
        """Build a request URL from the OpenAPI path template and supplied path params."""
        path_template = self._get_operation_path(operation_id)
        if not path_template:
            raise ValueError(f"Unknown operation ID: {operation_id}")

        resolved_path = path_template
        replacements = {
            "organizationID": self.config.organization_id,
            "dataSource": path_params.get("dataSource", ""),
            "queryId": path_params.get("queryId", ""),
        }

        for key, value in replacements.items():
            if value is None:
                continue
            resolved_path = resolved_path.replace(f"{{{key}}}", str(value))

        missing_params = re.findall(r"\{([^}]+)\}", resolved_path)
        if missing_params:
            raise ValueError(f"Missing path parameter(s) for {operation_id}: {missing_params}")

        return f"{self.config.base_url.rstrip('/')}{resolved_path}"

    def _request_json(
        self,
        method: str,
        operation_id: str,
        *,
        data_source: Optional[str] = None,
        query_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        timeout: int = 60,
    ) -> Optional[Dict[str, Any]]:
        """Perform an API request using a path derived from the OpenAPI spec."""
        url = self._build_api_url(
            operation_id,
            dataSource=data_source,
            queryId=query_id,
        )

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.config.get_auth_headers(),
                    json=payload,
                    timeout=timeout,
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code in (502, 503, 504) and attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⚠️ {response.status_code} error. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise DataExplorerError(
                    status_code=response.status_code,
                    message="Request failed",
                    response_text=response.text[:200],
                )
            except DataExplorerError:
                raise
            except Exception as e:
                print(f"Error executing request: {e}")
                return None

        return None

    def list_data_sources(self) -> Optional[List[Dict[str, Any]]]:
        """List all data sources using the OpenAPI-defined endpoint."""
        result = self._request_json("GET", "listDataSources")
        return result if isinstance(result, list) else None

    def get_data_source_schema(self, data_source: str) -> Optional[Dict[str, Any]]:
        """Get the schema for a given data source."""
        return self._request_json("GET", "getDataSourceSchema", data_source=data_source)

    def list_predefined_queries(self, data_source: str) -> Optional[Dict[str, Any]]:
        """List predefined queries for a given data source."""
        return self._request_json("GET", "listPredefinedQueries", data_source=data_source)

    def describe_query(self, data_source: str, query_id: str) -> Optional[Dict[str, Any]]:
        """Describe a predefined query for a data source."""
        return self._request_json(
            "GET",
            "describePredefinedQuery",
            data_source=data_source,
            query_id=query_id,
        )

    def execute_query(
        self,
        data_source: str,
        query_id: str,
        parameters: List[Dict[str, Any]],
        response_columns: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute a predefined query against the Data Retrieval API.

        Args:
            data_source: Name of the data source (e.g., 'observations')
            query_id: ID of the predefined query
            parameters: Query parameters list
            response_columns: Optional list of columns to return

        Returns:
            Query result dict with 'results' and 'columns' keys, or None on error
        """
        url = self._build_api_url(
            "executePredefinedQuery",
            dataSource=data_source,
            queryId=query_id,
        )

        payload = {"parameters": parameters}
        if response_columns:
            payload["response_columns"] = response_columns

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    headers=self.config.get_auth_headers(),
                    json=payload,
                    timeout=60
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    if attempt < self.max_retries - 1 and response.status_code in (502, 503, 504):
                        wait_time = 2 ** attempt
                        print(f"⚠️ {response.status_code} error. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise DataExplorerError(
                            status_code=response.status_code,
                            message="Query execution failed",
                            response_text=response.text[:200]
                        )
            except DataExplorerError:
                raise
            except Exception as e:
                print(f"Error executing query: {e}")
                return None

        return None

    def execute_query_with_pagination(
        self,
        data_source: str,
        query_id: str,
        parameters: List[Dict[str, Any]],
        limit: int = 100,
        max_results: int = 1000
    ) -> Dict[str, Any]:
        """Execute a query with automatic pagination support and retry logic.

        Args:
            data_source: Name of the data source
            query_id: ID of the predefined query
            parameters: Base query parameters list
            limit: Results per page
            max_results: Maximum total results to retrieve

        Returns:
            Dict with 'columns' and 'results' keys containing all paginated results
        """
        all_results = []
        offset = 0
        columns = None
        print(f"🔄 Starting paginated query (limit={limit}, max_results={max_results})")

        while len(all_results) < max_results:
            paginated_params = parameters.copy()
            paginated_params.extend([
                {"name": "limit", "value": limit},
                {"name": "offset", "value": offset}
            ])

            result = self.execute_query(data_source, query_id, paginated_params)

            if not result or not result.get('results'):
                print(f"📄 No more results at offset {offset}")
                break

            all_results.extend(result['results'])
            columns = result['columns']

            if len(result['results']) < limit:
                print(f"📄 Reached end of results (got {len(result['results'])} < {limit})")
                break

            offset += limit
            print(f"📊 Retrieved {len(all_results)} results so far...")

        return {'columns': columns if columns else [], 'results': all_results}

    @staticmethod
    def build_query_parameters(
        start_time,
        end_time,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Build query parameters with time range and optional filters.

        Args:
            start_time: Query start time (datetime)
            end_time: Query end time (datetime)
            **kwargs: Additional filters as (operator, value) tuples
                      Example: ip_address=("EQ", "10.0.0.1")

        Returns:
            List of parameter dicts ready for API submission
        """
        params = [
            {"name": "start_time", "value": start_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"name": "end_time", "value": end_time.strftime("%Y-%m-%dT%H:%M:%SZ")}
        ]
        for name, (operator, value) in kwargs.items():
            params.append({
                "name": name,
                "comparisonOperator": operator,
                "value": value
            })
        return params
