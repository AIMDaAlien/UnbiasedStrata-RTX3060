# Model provenance and preparation

No weights or generated packs are included. [model-files.json](../snapshot/model-files.json) records locally read SHA-256 hashes and exact sizes for the actual shards, pack/tokenizer and MTP runtime files. These hashes identify local artifacts; they do not imply that upstream published matching prepared files.

The two filenames are:

- `Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf`
- `Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00002-of-00002.gguf`

The parent recorded GGUF source revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09` of [ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09). Fetch from that revision and compare downloaded hashes with the local inventory. Obey the model's license.

Prepared pack: `dense.bin`, `index.txt`, `native_experts.txt`, `expert-profile.bin`, and `tokenizer/`. Some packer versions also write `conversions.json` or `extra.bin`; retain their output. The local pack links to the existing prepared data and copies the expert profile; exported hashes follow those links, without publishing the blobs.

Prepared MTP: `experts.bin`, `dense.bin`, `dense.txt`, `draft_vocab.bin`. The local BF16 fetch metadata identifies Qwen/Qwen3.8-Flash-Next at `resolve/main`, but **an immutable source revision was not retained**. Do not invent one or treat today's main as proof of the historical source. The archived tensor manifest and inventory provide shard names, byte ranges and hashes, and the runtime files have fresh local hashes. This limits exact historical reproduction.

[UPSTREAM.md](../UPSTREAM.md) records the parent's preparation at Strata `6f32ec070f23ced9f50e704d854d775da52591ab`. The local tools checkout is `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`; its tool hashes are captured in `snapshot/preparation-tools.json`. To use the local tool version with its recorded CLI:

```sh
export STRATA_TOOLS_DIR="$HOME/src/Strata"
git clone https://github.com/Niko1221/Strata.git "$STRATA_TOOLS_DIR"
git -C "$STRATA_TOOLS_DIR" checkout a79080535d1b2a71a3419a0d97d8e7dca194b0f1
python3 -m venv "$HOME/.venvs/strata-pack"
. "$HOME/.venvs/strata-pack/bin/activate"
python3 -m pip install numpy regex
export STRATA_GGUF_PY="$PWD/third_party/llama.cpp/gguf-py"
export MODEL_DIR="$HOME/models/flash-iq3-xxs"
export PACK_DIR="$HOME/models/flash-pack"
export MTP_BASE="$HOME/models/flash-mtp"
python "$STRATA_TOOLS_DIR/tools/iq_pack.py" \
  --gguf "$MODEL_DIR/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf" --out "$PACK_DIR"
cp "$STRATA_TOOLS_DIR/data/expert-profile.bin" "$PACK_DIR/"
python "$STRATA_TOOLS_DIR/tools/mtp_fetch.py" fetch --out "$MTP_BASE"
python "$STRATA_TOOLS_DIR/tools/mtp_pack.py" --src "$MTP_BASE" --experts q2_0 --out "$MTP_BASE/mtp-q2_0.gguf"
python "$STRATA_TOOLS_DIR/tools/mtp_rt.py" --gguf "$MTP_BASE/mtp-q2_0.gguf" --out "$MTP_BASE/rt"
cp "$STRATA_TOOLS_DIR/data/draft_vocab.bin" "$MTP_BASE/rt/"
export MTP_DIR="$MTP_BASE/rt"
```

That `mtp_fetch.py` supports inventory/fetch, not the parent's documented `verify` command. It fetches selected tensor ranges from main rather than all BF16 shards. Pin its URL to a revision you obtain and record for any new preparation. Validate raw tensor hashes against the manifest and compare runtime artifacts with the local inventory; no new pack preparation was performed during packaging. The tested runtime artifacts were reused read-only for the smoke check.
