#!/bin/bash

set -o errexit
# Keycloak details - replace these with your actual values
KC_SERVER_URI="http://localhost:9090"
KC_REALM_NAME="obp-realm"
CLIENT_ID="obpapp"
CLIENT_SECRET="obp-secret"

echo "Enter username (test, test-1 or test-2)"
read -p -r fullname

TOKEN_RESPONSE=$(curl -s -X POST \
"${KC_SERVER_URI}/realms/${KC_REALM_NAME}/protocol/openid-connect/token" \
-H 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode "client_id=${CLIENT_ID}" \
--data-urlencode "client_secret=${CLIENT_SECRET}" \
--data-urlencode "username=${fullname}" \
--data-urlencode 'password=test' \
--data-urlencode 'grant_type=password' \
--data-urlencode 'scope=openid')

# extracting the access token using jq
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')
echo "Access token:"
echo "$ACCESS_TOKEN"