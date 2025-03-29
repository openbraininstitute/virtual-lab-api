#!/bin/bash
set -e

# Environment variables set in docker-compose.yml
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
POSTGRES_MULTIPLE_DATABASES=${POSTGRES_MULTIPLE_DATABASES:-accounting_service,keycloak,vlm,postgres}

# Function to create a database if it doesn't exist
create_database() {
    local db=$1
    echo "Creating database: $db"
    # Check if database exists
    if psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -lqt | cut -d \| -f 1 | grep -qw $db; then
        echo "Database $db already exists"
    else
        echo "Creating database $db"
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -c "CREATE DATABASE $db;"
    fi
}

# Create databases defined in POSTGRES_MULTIPLE_DATABASES
echo "Creating multiple databases: $POSTGRES_MULTIPLE_DATABASES"
for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
    # Skip postgres database as it already exists by default
    if [ "$db" != "postgres" ]; then
        create_database $db
    fi
done

# Create keycloak user if it doesn't exist and grant privileges
echo "Creating keycloak user and granting privileges"
# Check if user exists
if psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_roles WHERE rolname='keycloak'" | grep -q 1; then
    echo "User keycloak already exists"
else
    echo "Creating user keycloak"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -c "CREATE USER keycloak WITH PASSWORD 'keycloak';"
fi

# Grant privileges to keycloak user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -c "GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak;"

echo "Database initialization completed successfully"