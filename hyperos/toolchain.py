"""Thin wrappers around optional external tools (NASM, QEMU, xorriso...)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

TOOLS = {
    "nasm": "assemble custom bootloaders and kernels",
    "qemu-system-i386": "run your systems in a virtual machine",
    "xorriso": "remaster downloaded ISOs while keeping every boot method",
    "gcc": "compile C kernels",
    "ld": "link C kernels",
    "make": "build Linux kernels and GRUB from source",
    "tar": "unpack downloaded sources",
}


def which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def status() -> Dict[str, Dict[str, object]]:
    return {t: {"found": bool(which(t)), "path": which(t), "purpose": p} for t, p in TOOLS.items()}


@dataclass
class BuildResult:
    ok: bool
    output: bytes = b""
    log: str = ""
    errors: List[Dict[str, object]] = field(default_factory=list)


_NASM_ERR = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<kind>error|warning)?:?\s*(?P<msg>.*)$")


def assemble(source: str, fmt: str = "bin", include_dir: Optional[str] = None) -> BuildResult:
    """Assemble NASM source text and return the binary plus parsed errors."""
    nasm = which("nasm")
    if not nasm:
        return BuildResult(False, log="NASM is not installed. Install it (e.g. 'sudo apt install nasm') "
                                      "or use the built-in HyperBoot/HyperKernel templates which need no tools.")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "source.asm")
        out = os.path.join(tmp, "out.bin")
        with open(src, "w") as fh:
            fh.write(source)
        cmd = [nasm, "-f", fmt, src, "-o", out]
        if include_dir:
            cmd.insert(1, f"-I{include_dir.rstrip('/')}/")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        errors = []
        for line in (proc.stderr or "").splitlines():
            m = _NASM_ERR.match(line)
            if m:
                errors.append({"line": int(m.group("line")), "kind": m.group("kind") or "error",
                               "message": m.group("msg")})
        log = (proc.stderr or "").replace(src, "source.asm")
        if proc.returncode != 0 or not os.path.exists(out):
            return BuildResult(False, log=log or "assembly failed", errors=errors)
        with open(out, "rb") as fh:
            data = fh.read()
        return BuildResult(True, data, log or f"assembled {len(data)} bytes", errors)


def run_qemu(image: str, iso: bool = False, extra: Optional[List[str]] = None) -> subprocess.Popen:
    qemu = which("qemu-system-i386") or which("qemu-system-x86_64")
    if not qemu:
        raise RuntimeError("QEMU is not installed (try 'sudo apt install qemu-system-x86').")
    args = [qemu, "-m", "32"]
    args += ["-cdrom", image, "-boot", "d"] if iso else ["-drive", f"format=raw,file={image},if=floppy", "-boot", "a"]
    return subprocess.Popen(args + (extra or []))
