import json
import sys
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError
from slc_mcp.providers.aws import AWSCredentialProvider


def test_aws_missing_boto3_raises():
    saved_boto3 = sys.modules.pop("boto3", None)
    saved_botocore = sys.modules.pop("botocore", None)
    sys.modules["boto3"] = None  # type: ignore
    try:
        with pytest.raises(CredentialError, match="boto3 is required"):
            AWSCredentialProvider().get_credentials("device-1")
    finally:
        if saved_boto3 is not None:
            sys.modules["boto3"] = saved_boto3
        else:
            sys.modules.pop("boto3", None)
        if saved_botocore is not None:
            sys.modules["botocore"] = saved_botocore


def test_aws_returns_credentials():
    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    secret_data = {"ip": "10.2.2.2", "username": "admin", "password": "awspass"}
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}
    mock_botocore_exc = MagicMock()
    mock_botocore_exc.ClientError = Exception
    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore": MagicMock(), "botocore.exceptions": mock_botocore_exc}):
        creds = AWSCredentialProvider().get_credentials("slc9000-dc-b")
    assert creds == {"ip": "10.2.2.2", "username": "admin", "password": "awspass"}
    mock_client.get_secret_value.assert_called_once_with(SecretId="slc/slc9000-dc-b")


def test_aws_missing_secret_field_raises():
    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({"ip": "10.2.2.2"})
    }
    mock_botocore_exc = MagicMock()
    mock_botocore_exc.ClientError = Exception
    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore": MagicMock(), "botocore.exceptions": mock_botocore_exc}):
        with pytest.raises(CredentialError, match="missing field"):
            AWSCredentialProvider().get_credentials("device-1")
