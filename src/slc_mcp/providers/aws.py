import json

from slc_mcp.providers import CredentialProvider, CredentialError


class AWSCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            raise CredentialError(
                "boto3 is required for the aws provider: pip install boto3"
            )
        secret_name = f"slc/{device_id}"
        sm_client = boto3.client("secretsmanager")
        try:
            response = sm_client.get_secret_value(SecretId=secret_name)
            data = json.loads(response["SecretString"])
        except ClientError as exc:
            raise CredentialError(
                f"AWS Secrets Manager read failed for {secret_name}: "
                f"{exc.response['Error']['Code']}"
            ) from exc
        except Exception as exc:
            raise CredentialError(
                f"AWS Secrets Manager error for {secret_name}: {exc}"
            ) from exc
        for field in ("ip", "username", "password"):
            if not data.get(field):
                raise CredentialError(
                    f"AWS secret {secret_name} missing field: {field!r}"
                )
        return {"ip": data["ip"], "username": data["username"], "password": data["password"]}
