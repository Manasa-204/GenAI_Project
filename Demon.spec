# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all dynamic assets and binary protobuf graphs for MediaPipe
mediapipe_datas = collect_data_files('mediapipe')
mediapipe_submodules = collect_submodules('mediapipe')

added_files = [
    ('Grant_Hosts_Permission.bat', '.'),
    ('README.md', '.'),
] + mediapipe_datas

a = Analysis(
    ['desktop_app.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'cv2',
        'mediapipe',
        'requests',
        'pygetwindow',
        'sqlite3',
        'webview',
        'clr',
        'pythonnet',
        'clr_loader',
        'matplotlib',
        'matplotlib.pyplot',
    ] + mediapipe_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'IPython'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
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
