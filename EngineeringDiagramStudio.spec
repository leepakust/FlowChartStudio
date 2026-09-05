from pathlib import Path
from importlib.metadata import distribution
import sys
root = Path(SPECPATH)
notices = [(str(Path(sys.base_prefix) / 'LICENSE.txt'), 'licenses/Python')]
for package in ('matplotlib', 'Pillow', 'numpy', 'contourpy', 'cycler',
                'fonttools', 'kiwisolver', 'packaging', 'pyparsing',
                'python-dateutil', 'six', 'pywin32'):
    dist = distribution(package)
    for file in dist.files or ():
        if 'license' in file.name.lower() or 'copying' in file.name.lower():
            notices.append((str(dist.locate_file(file)),
                            str(Path('licenses') / package / Path(str(file)).parent)))
a = Analysis([str(root / 'studio_launcher.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'examples'), 'examples'),
                                  (str(root / 'schemas'), 'schemas')] + notices,
             hiddenimports=['win32clipboard', 'matplotlib.backends.backend_svg',
                            'matplotlib.backends.backend_pdf'],
             hookspath=[], hooksconfig={'matplotlib': {'backends': ['Agg']}},
             runtime_hooks=[], excludes=['pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='EngineeringDiagramStudio', debug=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='EngineeringDiagramStudio')
