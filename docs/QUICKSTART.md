# Quick start: tested NVIDIA profile

This recipe targets Linux x86-64, Ryzen 9 7950X and one RTX 3060 12 GiB. It compiles for the current CPU (`STRATA_PORTABLE=OFF`) and CUDA architecture 86. Build on the machine where you will run it; the executable is not CPU-portable. Allow approximately 76 GB for GGUFs, 1.5 GB for the pack, 0.8 GB for prepared MTP, plus source/build and intermediate preparation space. A fast local SSD matters for direct PLE I/O.

1. Install Git, Python 3, a C++20 compiler, CMake >=3.24 and CUDA toolkit >=12.8 with a compatible NVIDIA driver. Packaging was built with GCC 16.2.1, CUDA 13.3.73 and driver 610.57.04; historical hardware records are preserved beside each experiment. If CMake is unavailable, install it in a Python virtual environment:

```sh
python3 -m venv "$HOME/.venvs/strata-build"
. "$HOME/.venvs/strata-build/bin/activate"
python3 -m pip install cmake
```

2. Clone the snapshot with its pinned dependency:

```sh
git clone --branch rtx3060-snapshot --recurse-submodules https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060.git
cd UnbiasedStrata-RTX3060
CUDA_HOME=/opt/cuda BUILD_JOBS=12 sh scripts/build-rtx3060.sh
```

`CUDA_HOME`, `BUILD_JOBS` and `BUILD_DIR` are configurable. This builds `build/unbiased-strata` by default. Lower parallelism if compilation runs out of RAM.

3. Obtain and prepare the files in [MODELS.md](MODELS.md). Keep the two shards side by side. Set paths to your own directories:

```sh
export MODEL_DIR="$HOME/models/flash-iq3-xxs"
export PACK_DIR="$HOME/models/flash-pack"
export MTP_DIR="$HOME/models/flash-mtp/rt"
python3 local/launch.py --print-command
```

The packaged profile uses 196,608 context, 12 expert workers, direct PLE I/O, resident experts, int8 KV with a 32,768 resident window, four MTP drafts, fused prefill, chunk ceiling 16,384 and ring 512. Tile size stays automatic; the recorded machine resolved chunk size 10,496. AMD is disabled. Do not reuse these resource assumptions on a different machine without checking its memory and workload.

4. Confirm the GPU is free (`nvidia-smi`) and stop your own competing inference process. The recorded RTX 3060 was already capped at 100 W; this launcher does not change system power settings. Run under the recorded memory limits:

```sh
systemd-run --user --unit=strata-snapshot --collect \
  --property=MemoryMax=56G --property=MemorySwapMax=0 \
  --property=TimeoutStopSec=30 --property=KillMode=control-group \
  --setenv="MODEL_DIR=$MODEL_DIR" --setenv="PACK_DIR=$PACK_DIR" --setenv="MTP_DIR=$MTP_DIR" \
  /usr/bin/python3 "$PWD/local/launch.py"
journalctl --user -u strata-snapshot -f
```

Loading takes several minutes. The profile listens locally on port 18081; edit a copy of `profiles/rtx3060.json` and use `--config` to change it. For a custom build directory set `binary` in that copy. Environment placeholders and `~` expand in artifact paths. No production service or config is installed by this recipe.

```sh
curl http://127.0.0.1:18081/health
curl http://127.0.0.1:18081/v1/models
curl http://127.0.0.1:18081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 6 times 7?"}],"reasoning_effort":"medium","temperature":0,"max_tokens":2048}'
systemctl --user stop strata-snapshot.service
```

The API supports chat completions, streaming and OpenAI-format tools; `/tokenize` counts the rendered chat request. Reasoning is returned separately in `reasoning_content`. Temperature zero uses greedy decoding and does not forward the seed to the engine. One conversation/request runs at a time.

## Troubleshooting and rollback

Missing artifact errors: check environment variables and every file listed in MODELS.md. Unset placeholders are rejected. An OOM or pinning failure: inspect the journal, desktop RAM usage and GPU ownership; 196K context is a tested profile, not a universal guarantee. No readiness: wait for loading and inspect logs rather than repeatedly starting servers. Upstream reported shard read failures on network volumes; use local disk. CUDA compiler not found: set `CUDA_HOME` and check the toolkit/driver pair.

Stop the temporary unit to roll back. Remove this separate checkout and your copied profile if desired; your original installation was never replaced. Existing users should preserve their old binary/config first and restore both with inference stopped if they manually integrate this snapshot. Historical rollback paths in the exported notes describe the experiment machine, not portable commands.
