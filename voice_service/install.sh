#!/usr/bin/env bash
# Installs the voice-service into its own venv, inside WSL2 on the GPU machine.
# Safe to run again: it reuses the venv and only upgrades what changed.
#
#   voice_service/install.sh
#
# JARVIS_VOICE_VENV   where the venv lives (default ~/.venvs/jarvis-voice; kept
#                     out of the checkout, which may sit on slow /mnt/c)
# JARVIS_TORCH_CUDA   which CUDA build of torch to install (default cu128)
set -euo pipefail

cd "$(dirname "$0")"
venv="${JARVIS_VOICE_VENV:-$HOME/.venvs/jarvis-voice}"
cuda="${JARVIS_TORCH_CUDA:-cu128}"

say() { printf '  voice-service install · %s\n' "$*"; }
die() { printf '  voice-service install · %s\n' "$*" >&2; exit 1; }

missing=()
command -v python3 >/dev/null 2>&1 || missing+=(python3)
command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
command -v gcc >/dev/null 2>&1 || missing+=(build-essential python3-dev)
if [ ${#missing[@]} -gt 0 ]; then
  die "missing: ${missing[*]}. Install them, then run this again:
      sudo apt update && sudo apt install -y ${missing[*]}"
fi
say "ffmpeg: $(command -v ffmpeg)"

py="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
python3 -c 'import sys; sys.exit(not (3, 10) <= sys.version_info[:2] <= (3, 12))' \
  || die "NeMo needs Python 3.10–3.12, this is $py"
say "python $py"

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  say "GPU: $(nvidia-smi -L | head -n1)"
else
  say "WARNING: nvidia-smi sees no GPU. In WSL2 the NVIDIA driver comes from Windows —"
  say "         install/update it there; the service will refuse to start without CUDA."
fi

if [ ! -x "$venv/bin/python" ]; then
  say "creating venv $venv"
  mkdir -p "$(dirname "$venv")"
  python3 -m venv "$venv" || die "could not create the venv. On Ubuntu:
      sudo apt install -y python3-venv"
fi
pip=("$venv/bin/python" -m pip)
"${pip[@]}" install --upgrade pip wheel
say "installing torch ($cuda build)"
"${pip[@]}" install --upgrade torch torchaudio --index-url "https://download.pytorch.org/whl/$cuda"
"${pip[@]}" install --upgrade Cython packaging
say "installing NeMo (this takes a while)"
# hold torch at the CUDA build just installed: if NeMo wants another one, fail
# loudly here rather than quietly swap in a different build from PyPI
pins="$(mktemp)"; trap 'rm -f "$pins"' EXIT
"${pip[@]}" freeze | grep -E '^(torch|torchaudio)==' > "$pins"
"${pip[@]}" install --upgrade -r requirements.txt -c "$pins"

"$venv/bin/python" - <<'PY'
import torch
import nemo.collections.asr  # noqa: F401
print(f"  voice-service install · torch {torch.__version__}, "
      f"CUDA {'available: ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOT available'}")
PY

say "downloading the Hearing model (Parakeet TDT 0.6B v3, ~2.5 GB, cached)"
"$venv/bin/python" -c 'from huggingface_hub import snapshot_download; snapshot_download("nvidia/parakeet-tdt-0.6b-v3")' \
  || say "WARNING: download failed; the service will try again when it starts"

say "done. Start it with: voice_service/start.sh"
