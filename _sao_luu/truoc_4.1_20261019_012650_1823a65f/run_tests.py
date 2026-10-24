"""Emit counts and prerequisites honestly, including every skipped test."""
import importlib.util,json,os,platform,re,shutil,subprocess,sys,time,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parent

def main():
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 if not os.environ.get('NBL_PWSH') and shutil.which('pwsh'):os.environ['NBL_PWSH']=shutil.which('pwsh')
 needed=['PySide6','rapidocr_onnxruntime','websockets','PIL']
 missing=[m for m in needed if importlib.util.find_spec(m) is None]
 report=dict(platform=platform.platform(),python=sys.version,missing_dependencies=missing,native_windows_live='NOT_TESTED',time=time.strftime('%Y-%m-%d %H:%M:%S'))
 if missing:
  report['error']='Install requirements-test.txt before counting a full regression pass.';code=2
 else:
  suite=unittest.defaultTestLoader.discover(str(BASE/'tests'));result=unittest.TextTestRunner(verbosity=2).run(suite)
  report['python_tests']=dict(run=result.testsRun,passed=result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),skipped=[dict(test=str(t),reason=r) for t,r in result.skipped],failures=[dict(test=str(t),trace=r) for t,r in result.failures+result.errors])
  node=shutil.which('node')
  if node:
   run=subprocess.run([node,'--test',*map(str,sorted((BASE/'tests').glob('*.test.js')))],capture_output=True,text=True,encoding='utf-8',errors='replace')
   report['javascript']=dict(exit_code=run.returncode,log=run.stdout+run.stderr)
  else:report['javascript']=dict(skipped='Node.js not found')
  code=0 if result.wasSuccessful() and not result.skipped and report.get('javascript',{}).get('exit_code')==0 else 1
 report['complete_development_pass']=code==0
 (BASE/'TEST_RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return code
if __name__=='__main__':sys.exit(main())
