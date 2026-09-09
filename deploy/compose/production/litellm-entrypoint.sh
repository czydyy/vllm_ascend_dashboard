#!/bin/sh
# Reload the file-backed LiteLLM configuration without restarting the rest of
# the dashboard stack. LiteLLM 1.91 has no /config/reload API and dynamic model
# endpoints require LiteLLM's own DB, which this deployment deliberately omits.
set -eu

config_path="${LITELLM_CONFIG_PATH:-/app/litellm_config.yaml}"
port="${LITELLM_PORT:-4000}"
poll_seconds="${LITELLM_CONFIG_POLL_INTERVAL_SECONDS:-1}"
child_pid=""

config_checksum() {
    sha256sum "$config_path" | awk '{print $1}'
}

start_litellm() {
    litellm --config "$config_path" --port "$port" &
    child_pid="$!"
}

stop_litellm() {
    if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
        kill -TERM "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    child_pid=""
}

shutdown() {
    stop_litellm
    exit 0
}

trap shutdown INT TERM

last_checksum="$(config_checksum)"
start_litellm

while :; do
    sleep "$poll_seconds"

    # Let Docker's restart policy handle an unexpected proxy exit instead of
    # creating a detached orphan process.
    if ! kill -0 "$child_pid" 2>/dev/null; then
        wait "$child_pid" 2>/dev/null || true
        exit 1
    fi

    current_checksum="$(config_checksum)"
    if [ "$current_checksum" != "$last_checksum" ]; then
        echo "LiteLLM runtime config changed; restarting proxy process" >&2
        stop_litellm
        last_checksum="$current_checksum"
        start_litellm
    fi
done
