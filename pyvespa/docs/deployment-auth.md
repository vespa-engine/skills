# pyvespa Deployment and Authentication

Load this reference when deploying an `ApplicationPackage` to Vespa Cloud (with token or mTLS auth) or troubleshooting Docker-based local deploys.

## Local Docker

```python
from vespa.deployment import VespaDocker

vespa_docker = VespaDocker(port=8080)
app = vespa_docker.deploy(app_package)  # Returns Vespa instance

# Reconnect to existing container
vespa_docker = VespaDocker.from_container_name_or_id("vespa-container-name")
```

Docker needs at least **4 GB memory** allocated.

## Vespa Cloud

```python
from vespa.deployment import VespaCloud

vespa_cloud = VespaCloud(
    tenant="my-tenant",
    application="my-app",
    application_package=app_package,
    auth_client_token_id="my-token-id",  # For token-based data plane auth
)

# Deploy to dev
app = vespa_cloud.deploy()

# Or connect to existing deployment
app = vespa_cloud.get_application(endpoint_type="token")
```

## Auth Modes

- **Control plane**: API key file via `key_location` or `key_content` param.
- **Data plane (mTLS)**: auto-generated cert, or provide via `Vespa(cert=..., key=...)`.
- **Data plane (token)**: set `auth_client_token_id` + `VESPA_CLOUD_SECRET_TOKEN` env var, then use `endpoint_type="token"` in `get_application()`.
