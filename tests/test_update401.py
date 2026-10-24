"""Runs the real update script against disposable fixtures, never an installed NBL.
Linux PowerShell is used for filesystem/rollback tests; Windows input is not simulated.
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile,unittest,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PWSH=os.environ.get('NBL_PWSH') or shutil.which('pwsh')
@unittest.skipUnless(PWSH and sys.platform!='win32','Requires Linux PowerShell for disposable executable fixtures')
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  self.src=self.base/'source';self.target=self.base/'installed';self.src.mkdir();(self.target/'runtime').mkdir(parents=True)
  (self.target/'app.py').write_text('old_version')
  self.exe=self.target/'runtime'/'python.exe';self.exe.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n');self.exe.chmod(0o755)
  self.wrapper=self.base/'run.ps1';self.wrapper.write_text("function global:Get-CimInstance {param([string]$ClassName,[string]$Filter) @()}\n& $args[0] -Source $args[1] -Target $args[2]\nexit $LASTEXITCODE\n")
  (self.src/'app.py').write_text('new_version');(self.src/'new_module.py').write_text('added_module');shutil.copy2(ROOT/'kiem_tra_cai_dat.py',self.src/'kiem_tra_cai_dat.py')
  (self.src/'CHROME_NBL_LIVE').mkdir();shutil.copy2(ROOT/'CHROME_NBL_LIVE'/'manifest.json',self.src/'CHROME_NBL_LIVE'/'manifest.json')
  self.manifest()
 def manifest(self):
  body={str(p.relative_to(self.src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.src.rglob('*') if p.is_file() and p.name!='SHA256.json'}
  (self.src/'SHA256.json').write_text(json.dumps(body))
 def run_update(self):return subprocess.run([PWSH,'-NoLogo','-NoProfile','-File',str(self.wrapper),str(ROOT/'cap_nhat.ps1'),str(self.src),str(self.target)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,env={**os.environ,'PYTHONPATH':str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')})
 def test_success_and_backup(self):
  r=self.run_update();self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual((self.target/'app.py').read_text(),'new_version')
  backups=list((self.target/'_sao_luu').glob('*/app.py'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),'old_version')
 def test_repeat_never_overwrites_old_backup(self):
  self.assertEqual(self.run_update().returncode,0);self.assertEqual(self.run_update().returncode,0)
  backups=list((self.target/'_sao_luu').glob('*/app.py'));self.assertEqual(len(backups),2);self.assertIn('old_version',[p.read_text() for p in backups])
 def test_bad_hash_changes_nothing(self):
  (self.src/'app.py').write_text('damaged');r=self.run_update();self.assertNotEqual(r.returncode,0);self.assertEqual((self.target/'app.py').read_text(),'old_version');self.assertFalse((self.target/'new_module.py').exists())
 def test_post_install_failure_rolls_back_and_removes_new_files(self):
  self.exe.write_text('#!/bin/sh\nexit 9\n');r=self.run_update();self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertEqual((self.target/'app.py').read_text(),'old_version');self.assertFalse((self.target/'new_module.py').exists());self.assertIn('DA KHOI PHUC',r.stdout)
 def test_bad_powershell_changes_nothing(self):
  (self.src/'bad.ps1').write_text('function broken {');self.manifest();r=self.run_update();self.assertNotEqual(r.returncode,0);self.assertEqual((self.target/'app.py').read_text(),'old_version')

if __name__=='__main__':unittest.main()
