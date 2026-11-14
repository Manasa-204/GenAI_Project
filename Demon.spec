# -*- mode: python ; coding: utf-8 -*-
"""
Demon.spec
----------
PyInstaller specification file to compile main.py into a completely hidden,
headless Windows background tracker executable (Demon.exe).

Key configurations:
- Entry point: main.py
- console=False (or --noconsole): Prevents any Command Prompt or console window
  from appearing when the background service executes.
- Lightweight bundling: Zero heavy GUI/ML runtime overhead.
"""

import sys
import os

block_cipher = None

added_files = []
if os.path.exists('Grant_Hosts_Permission.bat'):
    added_files.append(('Grant_Hosts_Permission.bat', '.'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'sqlite3',
        'ctypes',
        'subprocess',
        'socket',
        'db_manager',
        'user_tracker',
        'enforcement',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'torch',
        'IPython',
        'PIL',
        'cv2',
        'mediapipe',
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
    name='Demon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                  # STRICTLY HEADLESS: No command prompt window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,                # Task Scheduler elevates with /rl HIGHEST directly
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Demon',
)
