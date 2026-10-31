"""Build the NBL LIVE NSIS installer (4.2.0+).

    python build_installer.py SRC DEPS OUT VERSION

SRC  = source tree (app.py, CHROME_NBL_LIVE, assets, ocr_models, …)
DEPS = a folder holding runtime/ and ocr_vendor/ (embedded Python + OCR libraries)
OUT  = build folder (setup.nsi, nbl.ico, header.bmp, wizard.bmp next to it are reused)

Trims what NBL never loads (QML/Quick/3D/WebEngine, Qt tools, headers, sympy,
OpenCV video/haar data, tests, caches) so the solid-LZMA installer is as small as
possible, writes SETUP_FILES.json, the uninstall list and the old-file cleanup list.
"""
import hashlib, json, os, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from peimports import imports

SKIP_TOP = {'tests', '__pycache__', '_sao_luu', 'SETUP_CHECK.log', 'TEST_RESULT.json', 'SHA256.json', 'SETUP_FILES.json',
            'BIEN_BAN_KHAC_PHUC_4.0.2.md', 'CAP_NHAT_4.0.2.bat', 'CAP_NHAT_4.1.bat', 'HUONG_DAN.md', 'HUONG_DAN_4.0.2.txt',
            'HUONG_DAN_SU_DUNG.pdf', 'KET_QUA_KIEM_TRA.txt', 'KET_QUA_KIEM_TRA_4.1.txt', 'THAY_DOI_4.1.txt', 'cap_nhat.ps1',
            'requirements-test.txt', 'run_tests.py', 'Uninstall.exe', 'NBL_LIVE.exe', 'runtime', 'ocr_vendor', '.git', '.github',
            'build', 'mobile', 'native', 'NBL_LIVE_HANDOFF.md', 'README.md', '.gitignore', '.gitattributes'}
QT_PYD = {'QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'QtMultimedia.pyd', 'QtMultimediaWidgets.pyd', 'QtNetwork.pyd', 'QtSvg.pyd'}
QT_PLUGINS = {'platforms', 'styles', 'imageformats', 'iconengines', 'multimedia', 'tls', 'networkinformation', 'generic'}
QT_DYNAMIC = {'opengl32sw.dll', 'd3dcompiler_47.dll'}           # loaded by name at run time, not imported
QT_DIRS_DROP = {'qml', 'metatypes', 'translations', 'resources', 'include', 'typesystems', 'glue', 'doc', 'lib', 'scripts', 'QtAsyncio'}
VENDOR_DROP = ['sympy', 'mpmath', 'cv2/data', 'cv2/opencv_videoio_ffmpeg4100_64.dll', 'onnxruntime/tools', 'onnxruntime/transformers',
               'onnxruntime/quantization', 'onnxruntime/datasets', 'numpy/tests', 'numpy/_core/tests', 'numpy/f2py', 'numpy/typing/tests']


def trim_qt(pyside, removed):
    shib = pyside.parent / 'shiboken6'
    local = {f.name.lower(): f for f in pyside.iterdir() if f.suffix.lower() == '.dll'}
    local.update({f.name.lower(): f for f in shib.iterdir() if f.suffix.lower() == '.dll'})
    roots = [pyside / n for n in QT_PYD if (pyside / n).exists()]
    for d in QT_PLUGINS:
        roots += [p for p in (pyside / 'plugins' / d).rglob('*.dll')]
    need, todo = set(), list(roots)
    while todo:
        for n in imports(todo.pop()):
            if n in local and n not in need:
                need.add(n); todo.append(local[n])
    for f in list(pyside.iterdir()):
        n = f.name
        drop = (f.is_dir() and n in QT_DIRS_DROP) or \
               (f.suffix.lower() == '.dll' and n.lower() not in need and n.lower() not in QT_DYNAMIC) or \
               (f.suffix.lower() == '.pyd' and n not in QT_PYD) or f.suffix.lower() in ('.exe', '.pyi', '.lib')
        if drop:
            removed.append(f); shutil.rmtree(f) if f.is_dir() else f.unlink()
    for d in (pyside / 'plugins').iterdir():
        if d.name not in QT_PLUGINS:
            removed.append(d); shutil.rmtree(d)


def main(src, deps, out, version):
    src, deps, out = Path(src), Path(deps), Path(out)
    app = out / 'app'
    if app.exists(): shutil.rmtree(app)
    app.mkdir(parents=True)
    for f in src.iterdir():
        if f.name in SKIP_TOP: continue
        (shutil.copytree(f, app / f.name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.*')) if f.is_dir() else shutil.copy2(f, app / f.name))
    for d in ('runtime', 'ocr_vendor'):
        shutil.copytree(deps / d, app / d, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyi'))
    removed = []
    # half-downloaded leftovers like ".Qt6Core.dll.yk4BPQ" (hidden temp files) are junk
    for p in sorted(app.rglob('.*'), key=lambda x: -len(x.parts)):
        if p.is_file():
            removed.append(p); p.unlink()
    trim_qt(app / 'runtime' / 'site-packages' / 'PySide6', removed)
    for rel in VENDOR_DROP:
        p = app / 'ocr_vendor' / rel
        if p.exists():
            removed.append(p); shutil.rmtree(p) if p.is_dir() else p.unlink()
    for p in list(app.rglob('*.dist-info')):
        for extra in ('RECORD', 'INSTALLER', 'REQUESTED'):
            (p / extra).unlink(missing_ok=True)
    # files an older install still has and 4.2.0 no longer ships
    rel_removed = sorted({str(p.relative_to(app)).replace('/', '\\') for p in removed})
    with open(out / 'cleanup_old.nsh', 'w', encoding='utf-8') as fh:
        for r in rel_removed:
            fh.write(('  RMDir /r "$INSTDIR\\%s"\n' if not Path(r).suffix else '  Delete "$INSTDIR\\%s"\n') % r)
    # integrity list checked after install by setup_verify.py
    manifest = {}
    for p in sorted(app.rglob('*')):
        if p.is_file():
            manifest[str(p.relative_to(app)).replace(os.sep, '/')] = hashlib.sha256(p.read_bytes()).hexdigest()
    (app / 'SETUP_FILES.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
    with open(out / 'uninstall_list.nsh', 'w', encoding='utf-8') as fh:
        for p in sorted(app.iterdir()):
            fh.write(('  RMDir /r "$INSTDIR\\%s"\n' if p.is_dir() else '  Delete "$INSTDIR\\%s"\n') % p.name)
        for extra in ('NBL_LIVE.exe', 'Uninstall.exe', 'SETUP_CHECK.log'):
            fh.write('  Delete "$INSTDIR\\%s"\n' % extra)
        for extra in ('__pycache__', '_sao_luu', 'tests'):
            fh.write('  RMDir /r "$INSTDIR\\%s"\n' % extra)
    size = sum(p.stat().st_size for p in app.rglob('*') if p.is_file())
    print('app', round(size / 1e6), 'MB,', len(manifest), 'files, trimmed', len(removed), 'entries')
    (out / 'size_kb.txt').write_text(str(size // 1024))


if __name__ == '__main__':
    main(*sys.argv[1:5])
