#!/bin/sh
set -eu

NETWORK=rpc-network

docker network inspect "$NETWORK" >/dev/null 2>&1 || \
  docker network create --driver overlay --attachable --opt encrypted "$NETWORK" >/dev/null

docker compose up --detach --build --remove-orphans

echo "RPC demo deployed through Docker Compose."
echo "user-service:50051 <-> order-service:50051"
