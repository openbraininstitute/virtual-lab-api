#!/bin/bash

set -o errexit
set -x

KC_SERVER_URI="http://localhost:9090"
KC_REALM_NAME="obp-realm"
CLIENT_ID="obpapp"
CLIENT_SECRET="obp-secret"


chmod +x ./env-prep/init/init-aws.sh
ls -l ./env-prep/init/init-aws.sh

docker compose --env-file ./.env.local -f docker-system.yaml -p vlm up --wait
echo "Checking that delta is ready to accept connections..."
if ! curl --retry 30 --fail --retry-all-errors --retry-delay 2 -v "http://localhost:8080/v1/version"; then 
  docker compose --env-file ./.env.local -f docker-system.yaml -p vlm logs delta
  exit 1
fi 
echo "Delta is ready! 🚀"


# Register created realm on delta
echo "Registering realm in delta"
curl -XPUT \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/realms/obp-realm" \
  -d '{
        "name":"obp-realm",
        "openIdConfig":"http://keycloak:9090/realms/obp-realm/.well-known/openid-configuration"
      }'

echo "Initialize nexus"

python3 env-prep/init/init.py

echo "📦 Initialize Vl database"
make init-db
poetry run populate-tiers

echo "Creating system account in accounting service"
curl -X 'POST' \
  'http://localhost:8100/account/system' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "system"
}'

echo "get access token"

if [ "$IS_CI" == "True" ]; then
    echo "start dev server"
    make dev &

    echo "Checking that virtual lab server is ready to accept connections..."
    curl --retry 30 -f --retry-all-errors --retry-delay 2 -s -o /dev/null "http://localhost:8000/health"
    echo "Server is ready"
  
  else
  
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

  # check the OS and copy the access token to the clipboard
  OS=$(uname)
  if [ "$OS" == "Linux" ]; then
    echo "$ACCESS_TOKEN" | xclip -selection clipboard
    echo "Access token copied to clipboard (Linux)."
  elif [ "$OS" == "Darwin" ]; then
    echo "$ACCESS_TOKEN" | pbcopy
    echo "Access token copied to clipboard (macOS)."
  else
    echo "Unsupported OS for clipboard operation: $OS"
  fi

  echo "start dev server"
  make dev
fi