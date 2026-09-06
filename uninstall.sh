#!/bin/sh
set -eu

docker compose down --remove-orphans

echo "RPC demo containers and generated Compose images removed."
echo "The shared rpc-network and source files were preserved."
