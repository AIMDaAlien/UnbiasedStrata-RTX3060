#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="${CUDA_HOME:-/opt/cuda}/bin:$PATH"
cmake -S "$ROOT" -B "${BUILD_DIR:-$ROOT/build}" -DCMAKE_BUILD_TYPE=Release \
 -DSTRATA_ENABLE_CUDA=ON -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_PORTABLE=OFF \
 -DSTRATA_BUILD_TESTS=OFF -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build "${BUILD_DIR:-$ROOT/build}" -j "${BUILD_JOBS:-12}" --target unbiased-strata
