#!/bin/bash

set -o errexit
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


# Use environment file only if specified
if [ "$USE_ENV_FILE" = true ]; then
  echo "Using environment file: $ENV_FILE"
  COMPOSE_BASE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p vlm-project)
else
  echo "No environment file specified, using CI configuration"
  COMPOSE_BASE=(docker compose -f "$COMPOSE_FILE_CI" -p vlm-project)
fi

"${COMPOSE_BASE[@]}" up --wait

# Wait for Keycloak to be ready and realm to be imported
echo "Waiting for Keycloak to be ready..."
KEYCLOAK_READY="false"
for i in {1..60}; do
  if curl -s -f "$KC_SERVER_URI/realms/$KC_REALM_NAME" > /dev/null 2>&1; then
    echo "Keycloak is ready!"
    KEYCLOAK_READY="true"
    break
  fi
  echo "Waiting for Keycloak... ($i/60)"
  sleep 2
done

if [ "$KEYCLOAK_READY" != "true" ]; then
  echo "Keycloak did not become ready in time." >&2
  "${COMPOSE_BASE[@]}" ps || true
  "${COMPOSE_BASE[@]}" logs --no-color keycloak || true
  exit 1
fi

# Additional wait to ensure realm is fully imported
sleep 5

# disable SSL requirement on the master realm so the admin console is accessible over HTTP locally
echo "disabling SSL requirement on master realm..."
echo "🔐 Configuring Keycloak admin credentials..."
docker exec keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:9090 \
  --realm master \
  --user admin \
  --password admin
docker exec keycloak /opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE
echo "✅ Master realm SSL requirement disabled"

echo "🔧 Disabling email/profile verification for test realm..."
docker exec keycloak /opt/keycloak/bin/kcadm.sh update realms/obp-realm -s verifyEmail=false
docker exec keycloak /opt/keycloak/bin/kcadm.sh update authentication/required-actions/VERIFY_EMAIL -r obp-realm -s enabled=false
docker exec keycloak /opt/keycloak/bin/kcadm.sh update authentication/required-actions/VERIFY_PROFILE -r obp-realm -s enabled=false
echo "✅ VERIFY_EMAIL and VERIFY_PROFILE disabled"

echo "📋 Registering custom user profile attributes..."
cat > /tmp/kc-user-profile.json <<'EOF'
{
  "unmanagedAttributePolicy": "ADMIN_EDIT",
  "attributes": [
    {
      "name": "username",
      "displayName": "${username}",
      "permissions": { "view": ["admin", "user"], "edit": ["admin"] },
      "validations": { "length": { "min": 3, "max": 255 }, "username-prohibited-characters": {} }
    },
    {
      "name": "email",
      "displayName": "${email}",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "email": {}, "length": { "max": 255 } }
    },
    {
      "name": "firstName",
      "displayName": "${firstName}",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "length": { "max": 255 }, "person-name-prohibited-characters": {} }
    },
    {
      "name": "lastName",
      "displayName": "${lastName}",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "length": { "max": 255 }, "person-name-prohibited-characters": {} }
    },
    {
      "name": "country",
      "displayName": "Country",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {}
    },
    {
      "name": "street",
      "displayName": "Street",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {}
    },
    {
      "name": "postal_code",
      "displayName": "Postal Code",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {}
    },
    {
      "name": "locality",
      "displayName": "Locality",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {}
    },
    {
      "name": "region",
      "displayName": "Region",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {}
    },
    {
      "name": "plan",
      "displayName": "Subscription Plan",
      "permissions": { "view": ["admin", "user"], "edit": ["admin"] },
      "multivalued": true,
      "validations": { "multivalued": { "min": 0, "max": 64 } }
    },
    {
      "name": "virtual_lab_id",
      "displayName": "Virtual Lab ID",
      "permissions": { "view": ["admin", "user"], "edit": ["admin"] },
      "multivalued": true,
      "validations": { "multivalued": { "min": 0, "max": 64 } }
    }
  ]
}
EOF
docker cp /tmp/kc-user-profile.json keycloak:/tmp/kc-user-profile.json
docker exec keycloak /opt/keycloak/bin/kcadm.sh update realms/obp-realm/users/profile -r obp-realm -f /tmp/kc-user-profile.json
rm -f /tmp/kc-user-profile.json
echo "✅ User profile attributes registered (country, street, postal_code, locality, region, plan, virtual_lab_id)"

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
