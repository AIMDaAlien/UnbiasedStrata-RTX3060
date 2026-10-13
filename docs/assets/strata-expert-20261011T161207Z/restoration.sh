#!/bin/bash
# Manual restoration only. Production Strata is deliberately excluded.
# GPU model services were observed at different times; choose one: ornith, swift, or none.
set -e
case "${1:-none}" in
  ornith) inference_service=llama-ornith.service ;;
  swift) inference_service=llama-server.service ;;
  none) inference_service= ;;
  *) echo 'Usage: bash restoration.sh [ornith|swift|none]' >&2; exit 2 ;;
esac
systemctl --user start hermes-gateway.service paperclipai.service philosopher-bridge.service philosopher-harness.service philosopher-mdns.service model-energy-sampler.service headroom-proxy.service
systemctl --user start bench-campaign.timer app-autoupdate.timer session-persist.timer
docker start librechat-mongo librechat
if [[ -n "$inference_service" ]]; then systemctl --user start "$inference_service"; fi
# Optional applications, if wanted:
# /home/USER/Work/clop-linux/.venv/bin/python -m clop_linux.app
# opencode
