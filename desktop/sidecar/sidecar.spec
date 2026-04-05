# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the InferenceChain desktop sidecar.
# Produces a --onedir bundle at dist/sidecar/ containing sidecar.exe
# plus all shared libraries (torch, fastapi, uvicorn, cryptography …).
#
# Build:
#   cd desktop/sidecar
#   pyinstaller sidecar.spec

import sys
from pathlib import Path

block_cipher = None

# Hidden imports required by uvicorn, fastapi, and our route modules.
# PyInstaller cannot detect dynamic/lazy imports automatically.
hidden_imports = [
    # uvicorn internals
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.middleware.proxy_headers",
    # h11 (HTTP/1.1 parser used by uvicorn)
    "h11",
    "h11._connection",
    "h11._events",
    # starlette / fastapi internals
    "starlette.middleware.cors",
    "starlette.routing",
    "starlette.responses",
    "starlette.background",
    "starlette.middleware.base",
    "fastapi.responses",
    "fastapi.middleware.cors",
    # pydantic v2
    "pydantic.deprecated.class_validators",
    "pydantic_core",
    # anyio (async backend used by starlette/fastapi)
    "anyio",
    "anyio._backends._asyncio",
    # aiofiles
    "aiofiles",
    "aiofiles.os",
    "aiofiles.threadpool",
    # cryptography – Ed25519 signing
    "cryptography.hazmat.backends.openssl.backend",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "cryptography.hazmat.primitives.serialization",
    # our own route + training modules (loaded at runtime via string paths)
    "routes.validate",
    "routes.train",
    "routes.chain",
    "training.arch_sandbox",
    "training.dataset_loader",
    "training.trainer",
]

a = Analysis(
    ["main.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Strip test/benchmark code to reduce size
        "pytest",
        "setuptools",
        "distutils",
        "doctest",
        "pdb",
        "profile",
        "cProfile",
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    # No visible console window — Electron captures stdout/stderr via pipe
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    name="sidecar",
)
