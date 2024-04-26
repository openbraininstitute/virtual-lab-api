#!/bin/bash
set -e
echo "Checking that delta is ready to accept connections..."
curl --retry 30 -f --retry-all-errors --retry-delay 2 -s -o /dev/null "http://localhost:8080/v1/orgs"
echo "Delta is ready! 🚀"
echo "Registering realm in delta"
curl -XPUT \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/realms/obp-realm" \
  -d '{
        "name":"obp-realm",
        "openIdConfig":"http://localhost:9090/realms/obp-realm/.well-known/openid-configuration"
      }'
echo "Initialize nexus"
python3 env-prep/init/init.py
echo "📦 Initialize Vl database"
make init-db
