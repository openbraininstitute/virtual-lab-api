# Get an admin token
TOKEN=$(curl -s -X POST "http://localhost:9090/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=admin" \
  -d "grant_type=password" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List all user IDs
curl -s "http://localhost:9090/admin/realms/obp-realm/users?max=1000" \
  -H "Authorization: Bearer $TOKEN" | python -c "
import sys, json
users = json.load(sys.stdin)
for u in users:
    print(u['id'])
"

# country attribute alongside each ID:
curl -s "http://localhost:9090/admin/realms/obp-realm/users?max=1000" \
  -H "Authorization: Bearer $TOKEN" | python -c "
import sys, json
users = json.load(sys.stdin)
for u in users:
    country = u.get('attributes', {}).get('country', [''])[0] if u.get('attributes') else ''
    print(f\"{u['id']}  {u.get('email', '—'):30s}  country={country}\")
"
