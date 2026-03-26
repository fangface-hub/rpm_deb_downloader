# -*- mode: python ; coding: utf-8 -*-

import os
import shutil

from PyInstaller.config import CONF


block_cipher = None

extra_datas = []
extra_binaries = []

if os.path.isfile('tools/bin/solv.py'):
    extra_datas.append(('tools/bin/solv.py', 'tools/bin'))

tools_tree = Tree('tools', prefix='tools')
licenses_tree = Tree('Licenses', prefix='Licenses')
locales_tree = Tree('locales', prefix='locales')


class CollectAndMoveDirs(COLLECT):
    """Place selected resource directories at dist root after collect step."""

    dirs_to_move = ('tools', 'Licenses', 'locales')

    @staticmethod
    def _merge_dir(src_dir, dst_dir):
        for child_name in os.listdir(src_dir):
            src_child = os.path.join(src_dir, child_name)
            dst_child = os.path.join(dst_dir, child_name)

            if os.path.isdir(src_child):
                os.makedirs(dst_child, exist_ok=True)
                CollectAndMoveDirs._merge_dir(src_child, dst_child)
                shutil.rmtree(src_child)
                continue

            if os.path.exists(dst_child):
                os.remove(dst_child)
            shutil.move(src_child, dst_child)

    def assemble(self):
        super().assemble()
        dist_dir = os.path.join(CONF['distpath'], self.name)

        for dirname in self.dirs_to_move:
            internal_dir = os.path.join(dist_dir, '_internal', dirname)
            root_dir = os.path.join(dist_dir, dirname)

            if not os.path.isdir(internal_dir):
                continue

            if not os.path.isdir(root_dir):
                shutil.move(internal_dir, root_dir)
                continue

            self._merge_dir(internal_dir, root_dir)
            shutil.rmtree(internal_dir)


a = Analysis(
    ['main_window.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=extra_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=True,
    name='RpmDebDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)

coll = CollectAndMoveDirs(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    tools_tree,
    licenses_tree,
    locales_tree,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RpmDebDownloader',
)
