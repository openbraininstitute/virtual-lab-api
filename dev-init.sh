#!/bin/bash

set -o errexit

# Start containers
docker compose -f env-prep/docker-compose-dev.yml -p vlm-project up --wait


# Check that delta ready to accept connections
echo "Checking that delta is ready to accept connections..."
curl --retry 10 -f --retry-all-errors --retry-delay 2 -s -o /dev/null "http://localhost:8080/v1/version"
echo "Delta is ready! 🚀"

# Register created realm on delta
echo "Registering realm in delta"
curl -XPUT \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/realms/obp-realm" \
  -d '{
        "name":"obp-realm",
        "openIdConfig":"http://keycloak:8080/realms/obp-realm/.well-known/openid-configuration"
      }'

