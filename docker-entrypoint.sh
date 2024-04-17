#!/bin/bash

set -o errexit

alembic upgrade head
uvicorn --host=0.0.0.0 virtual_labs.api:app
