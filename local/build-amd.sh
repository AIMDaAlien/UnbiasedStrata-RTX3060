#!/bin/sh
# Experimental, separate AMD build of this fork; does not replace the CUDA binary.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PATH="/opt/rocm/bin:$PATH"
if command -v rocm-sdk >/dev/null 2>&1; then
  rocm-sdk init
  ROCM_PATH=$(rocm-sdk path --root)
  export ROCM_PATH HIP_PATH="$ROCM_PATH"
  export CMAKE_PREFIX_PATH="$ROCM_PATH${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
fi
if ! command -v hipconfig >/dev/null 2>&1; then
  echo 'AMD build needs the ROCm HIP development toolkit, hipBLAS, and a HIP-capable Clang compiler.' >&2
  echo 'The ROCm toolkit is not currently available on PATH; no build was attempted.' >&2
  exit 1
fi
cmake -S . -B build-amd -DCMAKE_BUILD_TYPE=Release \
  -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_ENABLE_HIP=ON \
  -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_PORTABLE=OFF -DSTRATA_BUILD_TESTS=OFF \
  -DCMAKE_HIP_ARCHITECTURES=gfx1200 ${ROCM_PATH:+-DCMAKE_HIP_COMPILER_ROCM_ROOT=$ROCM_PATH}
cmake --build build-amd -j 8 --target native_expert_parity strata-amd-worker unbiased-strata
