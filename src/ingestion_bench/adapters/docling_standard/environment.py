"""Environment and model-footprint evidence collection for the
DOCLING_STANDARD_LOCAL adapter's baseline report (Stage 5A.2).

Stage 5A originally hand-typed this evidence (Python/OS/package versions,
CUDA availability, HF cache configuration, downloaded model families,
approximate storage footprint) into
reports/stage5a_docling_standard_baseline.md section 1 from a one-time
manual inspection. Stage 5A.2 restores it as data the runner actually
collects and regenerates on every run -- but never returns an absolute,
machine-specific filesystem path: cache locations are redacted to at most
a drive letter / mount point, and only redirected (non-default) caches
are reported as a location at all.

Read-only: never triggers a model download, never imports Docling/
docling-core document types (only config.py's version/summary helpers).
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import sys
from pathlib import Path

from . import config


def _redact_path_to_drive_or_mount(path_str: str) -> str:
    """Reports only WHERE a cache was redirected to (which drive on
    Windows, which top-level mount on POSIX) -- never the full path, per
    the Stage 5A.2 instruction not to expose the user's absolute
    filesystem paths."""
    path = Path(path_str)
    anchor = path.anchor
    if anchor and anchor not in ("/", ""):
        drive = anchor.rstrip("\\").rstrip("/")
        return f"{drive} (redirected, path redacted)"
    if anchor == "/":
        parts = path.parts
        first_segment = parts[1] if len(parts) > 1 else ""
        return f"/{first_segment} (redirected, path redacted)"
    return "(redirected, path redacted)"


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _torch_cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _default_hf_hub_cache_root() -> Path | None:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE)
    except Exception:
        return None


def _discover_downloaded_model_families_and_footprint() -> tuple[list[str], int | None]:
    """Scans the effective Hugging Face hub cache root for
    models--<org>--<repo> directories (the standard hub cache naming
    convention), keeping only repo ids that look like Docling's own model
    families (repo id contains "docling") -- the same HF cache root can
    also hold unrelated models cached by other parts of this repository
    (e.g. the separate GraphRAG POC's sentence-transformers embedding
    model), which must not be misreported as something Docling downloaded.
    Reports repo-id strings and a combined byte count only, never an
    absolute path. Returns ([], None) if no cache root is discoverable/
    readable, or none of its contents are Docling's own models."""
    cache_root_str = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if cache_root_str:
        cache_root = Path(cache_root_str)
        if (cache_root / "hub").is_dir():
            cache_root = cache_root / "hub"
    else:
        cache_root = _default_hf_hub_cache_root()

    if cache_root is None or not cache_root.is_dir():
        return [], None

    repo_ids: list[str] = []
    total_bytes = 0
    for entry in sorted(cache_root.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("models--"):
            continue
        repo_id = "/".join(entry.name[len("models--"):].split("--"))
        if "docling" not in repo_id.lower():
            continue
        repo_ids.append(repo_id)
        # Sum only blobs/ -- the hub cache's actual, deduplicated file
        # storage (matching how `huggingface-cli scan-cache` itself
        # reports size). snapshots/ entries are references into blobs/
        # (symlinks, or plain copies on filesystems without symlink
        # support) and would double-count the same physical bytes if
        # summed too.
        blobs_dir = entry / "blobs"
        if blobs_dir.is_dir():
            for file_path in blobs_dir.iterdir():
                if file_path.is_file():
                    try:
                        total_bytes += file_path.stat().st_size
                    except OSError:
                        pass

    return repo_ids, (total_bytes if repo_ids else None)


def collect_environment_evidence() -> dict:
    """One flat, JSON-serializable dict of restored Stage 5A.1 environment
    evidence -- every field here is either a version string, a boolean, a
    redacted location, or an approximate/rounded size; never an absolute
    filesystem path."""
    hf_home = os.environ.get("HF_HOME")
    hf_hub_cache = os.environ.get("HF_HUB_CACHE")
    external_cache_configured = bool(hf_home or hf_hub_cache)
    redacted_cache_location = (
        _redact_path_to_drive_or_mount(hf_hub_cache or hf_home) if external_cache_configured else None
    )

    model_families, footprint_bytes = _discover_downloaded_model_families_and_footprint()

    accelerator_device = config.effective_configuration_summary()["accelerator_device"]
    # Normalized to its plain value (e.g. "cpu") rather than left as an
    # AcceleratorDevice enum member -- str(enum_member) renders as
    # "AcceleratorDevice.CPU" by default in this Python version, which
    # would silently disagree with section 2's json.dumps rendering of
    # the same underlying value ("cpu", since json treats a (str, Enum)
    # member as its string content).
    effective_accelerator_device = accelerator_device.value if hasattr(accelerator_device, "value") else str(accelerator_device)

    return {
        "python_version": sys.version.split()[0],
        "os_platform": platform.platform(),
        "docling_version": config.docling_version(),
        "docling_core_version": config.docling_core_version(),
        "torch_version": _package_version("torch"),
        "torchvision_version": _package_version("torchvision"),
        "onnxruntime_version": _package_version("onnxruntime"),
        "rapidocr_version": _package_version("rapidocr"),
        "cuda_available": _torch_cuda_available(),
        "effective_accelerator_device": effective_accelerator_device,
        "external_hf_cache_configured": external_cache_configured,
        "redacted_hf_cache_location": redacted_cache_location,
        "downloaded_model_families": model_families,
        "approx_model_storage_footprint_mb": (
            round(footprint_bytes / (1024 * 1024)) if footprint_bytes else None
        ),
    }
