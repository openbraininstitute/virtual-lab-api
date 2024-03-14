#!/bin/sh
echo "get into the docker container"
docker exec -ti keycloak bash

KC_CLIENT_ID="obpapp"
KC_CLIENT_SECRET="obp-secret"
KC_REALM_NAME="obp-realm"

echo "move to bin folder of keycloak"
cd /opt/keycloak/bin/ || exit

echo "1️⃣ Login to the keycloak account"
./kcadm.sh config credentials --server http://localhost:8080/ --realm master --user admin --password admin
echo "2️⃣ create the realm $KC_REALM_NAME"
./kcadm.sh create realms -s realm=$KC_REALM_NAME -s enabled=true --server http://localhost:8080/
echo "3️⃣create a new client 'obp', you can give it another label"
./kcadm.sh create clients -r $KC_REALM_NAME -s clientId=$KC_CLIENT_ID -s enabled=true -s clientAuthenticatorType=client-secret -s secret=$KC_CLIENT_SECRET
echo "4️⃣ get the client id for $KC_CLIENT_ID"
# Run the command to get the client data
output=$(./kcadm.sh get clients -r $KC_CLIENT_ID --fields id,clientId)

echo "5️⃣ update the client configuration to enable the service account."
./kcadm.sh update clients/"$id" -r $KC_REALM_NAME -s 'redirectUris=["*"]'  -s serviceAccountsEnabled=true

echo "6️⃣ get service account token"
echo "🅿️ $BasicAuth: btoa($KC_CLIENT_ID:$KC_CLIENT_SECRET)"
# Execute the curl command and store the response in a variable
curl --location --request POST \
    "http://localhost:8088/realms/$KC_REALM_NAME/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -H 'Authorization: Basic $BasicAuth' \
    --data-urlencode 'grant_type=client_credentials'

echo "7️⃣ create dummy users"
./kcadm.sh create users -r $KC_REALM_NAME -s username=test-1 -s enabled=true
./kcadm.sh create users -r $KC_REALM_NAME -s username=test-2 -s enabled=true
./kcadm.sh create users -r $KC_REALM_NAME -s username=test-3 -s enabled=true
