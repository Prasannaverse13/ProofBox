#!/usr/bin/env bash
# Safety net: remove any sandbox that outlived its job. The API also does this on start.
docker ps -aq --filter label=proofbox=1 | xargs -r docker rm -f -v
