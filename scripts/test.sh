#!/usr/bin/env bash
# Disposable backend checks. Never run inside or start the application stack.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    printf 'Docker with Compose v2 is required for disposable backend tests.\n' >&2
    exit 1
fi

# A context/DOCKER_HOST can silently point at a production daemon. This workflow
# is authorized for local disposable resources only, not a remote Docker host.
if [[ -n "${DOCKER_CONTEXT:-}" || -z "${DOCKER_HOST:-}" ]]; then
    endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}') || {
        printf 'Cannot establish a local Docker endpoint; refusing to run tests.\n' >&2
        exit 1
    }
else
    endpoint=$DOCKER_HOST
fi
case "$endpoint" in
    unix:///*|npipe:////./pipe/*) ;;
    *) printf 'A local Docker endpoint is required; remote/ambiguous contexts are refused.\n' >&2; exit 1 ;;
esac

# The prefix is fixed; no app project/name/config is inherited from the caller.
project="fluxvpn-tests-$$-$RANDOM"
compose=(docker compose -f "$root/docker-compose.test.yml" -p "$project")
cleanup() {
    status=$?
    trap - EXIT
    if ! "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1; then
        printf 'Could not clean disposable test project %s; remove only that project.\n' "$project" >&2
        if [[ "$status" -eq 0 ]]; then status=1; fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Running disposable backend checks in project %s.\n' "$project"
"${compose[@]}" build worker-tests
"${compose[@]}" up -d --wait postgres-test redis-test
"${compose[@]}" run --rm --no-deps worker-tests
