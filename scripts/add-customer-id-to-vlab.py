import psycopg2
from sshtunnel import SSHTunnelForwarder


def main():
    try:
        with SSHTunnelForwarder(
            ("ssh.shapes-registry.org", 22),
            ssh_private_key="/Users/meddah/.ssh/id_rsa",
            ssh_username="bilal",
            remote_bind_address=(
                "virtual-lab-manager-db-id.ctydazornca3.us-east-1.rds.amazonaws.com",
                5432,
            ),
        ) as server:
            server.start()
            print("server connected", server.local_bind_port)

            params = {
                "database": "vlm",
                "user": "vlm_user",
                "password": "pxoV1Sm0GopTlVe1NExgMP8mXp1iYPv",
                "host": "localhost",
                "port": server.local_bind_port,
            }

            conn = psycopg2.connect(**params)
            cur = conn.cursor()
            print("database connected")
            cur.execute("SELECT * from virtual_lab")
            d = cur.fetchone()
            print("d", d)
    except Exception as ex:
        print("Connection Failed", ex)


if __name__ == "__main__":
    main()
