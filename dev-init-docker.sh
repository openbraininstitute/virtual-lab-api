#!/bin/bash
set -o errexit
set -x

KC_SERVER_URI="http://keycloak:9090"
KC_REALM_NAME="obp-realm"
CLIENT_ID="obpapp"
CLIENT_SECRET="obp-secret"

# Register created realm on delta
echo "Registering realm in delta"
curl -XPUT \
  -H "Content-Type: application/json" \
  "http://delta:8080/v1/realms/obp-realm" \
  -d '{
        "name":"obp-realm",
        "openIdConfig":"http://keycloak:9090/realms/obp-realm/.well-known/openid-configuration"
      }'

echo "Initialize nexus"

python3 env-prep/init/init-docker.py

echo "📦 Initialize Vl database"
poetry run alembic upgrade head

echo "get access token"


  
# curl command to get the token
TOKEN_RESPONSE=$(curl -s -X POST \
"${KC_SERVER_URI}/realms/${KC_REALM_NAME}/protocol/openid-connect/token" \
-H 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode "client_id=${CLIENT_ID}" \
--data-urlencode "client_secret=${CLIENT_SECRET}" \
--data-urlencode 'username=test' \
--data-urlencode 'password=test' \
--data-urlencode 'grant_type=password' \
--data-urlencode 'scope=openid')

# extracting the access token using jq
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')
echo "$ACCESS_TOKEN"

poetry run uvicorn virtual_labs.api:app --reload