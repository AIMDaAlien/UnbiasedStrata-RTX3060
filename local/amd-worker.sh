#!/bin/sh
set -eu
sdk=/home/USER/opt/rocm-venv/lib/python3.12/site-packages
export LD_LIBRARY_PATH="$sdk/_rocm_sdk_core/lib:$sdk/_rocm_sdk_libraries/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec /home/USER/opt/UnbiasedStrata/build-amd/strata-amd-worker "$@"
