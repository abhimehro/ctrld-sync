#!/bin/bash
# Run pytest without cache warning in containers
# This suppresses the PytestCacheWarning that occurs when using non-root users in Docker

docker compose run --rm --entrypoint python ctrld-sync -m pytest "$@" -p no:cacheprovider
