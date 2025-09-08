# create an admin user for local keycloak
## login to the server 
```shell
docker exec -it keycloak /opt/keycloak/bin/kcadm.sh \
  config credentials --server http://127.0.0.1:9090 --realm master \
  --user admin --password admin
```
## create a new user
```shell
  docker exec -it keycloak /opt/keycloak/bin/kcadm.sh \
  create users -r obp-realm \
  -s username=obp-admin -s enabled=true -s email=obp-admin@local
```
## set password
```shell
  docker exec -it keycloak /opt/keycloak/bin/kcadm.sh \
  set-password -r obp-realm --username obp-admin --new-password obp-admin
```
## add role as realm manager
```shell
  docker exec -it keycloak /opt/keycloak/bin/kcadm.sh \
  add-roles -r obp-realm --uusername obp-admin \
  --cclientid realm-management --rolename realm-admin
```