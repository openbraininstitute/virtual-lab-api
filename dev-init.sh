#!/bin/bash

set -o errexit
set -x
# Keycloak details - replace these with your actual values
KC_SERVER_URI="http://localhost:9090"
KC_REALM_NAME="obp-realm"
CLIENT_ID="obpapp"
CLIENT_SECRET="obp-secret"
COMPOSE_FILE="docker-compose.yml"
COMPOSE_FILE_CI="docker-compose.ci.yml"

# Parse command line arguments
ENV_FILE=""
USE_ENV_FILE=false

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --env-file) 
      ENV_FILE="$2"
      USE_ENV_FILE=true
      shift 
      ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
  shift
done

# Start containers
chmod +x ./env-prep/init/init-aws.sh
ls -l ./env-prep/init/init-aws.sh

# Use environment file only if specified
if [ "$USE_ENV_FILE" = true ]; then
  echo "Using environment file: $ENV_FILE"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p vlm-project up --wait
else
  echo "No environment file specified, using CI configuration"
  docker compose -f "$COMPOSE_FILE_CI" -p vlm-project up --wait
fi

# Check that delta ready to accept connections
echo "Checking that delta is ready to accept connections..."
if ! curl --retry 30 --fail --retry-all-errors --retry-delay 2 -v "http://localhost:8080/v1/version"; then 
  # Show delta logs if curl failed
  if [ "$USE_ENV_FILE" = true ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p vlm-project logs delta
  else
    docker compose -f "$COMPOSE_FILE_CI" -p vlm-project logs delta
  fi
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
