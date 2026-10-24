"""Local deployment check; no desktop input, browser operation, or network use."""
import ast,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent

def check():
 for stream in (sys.stdout,sys.stderr):
  if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
 for path in BASE.glob('*.py'):ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
 import PySide6.QtMultimedia
 import websockets.sync.server
 from studio_vision import _engine,ocr_model_info
 _engine()
 manifest=json.loads((BASE/'CHROME_NBL_LIVE'/'manifest.json').read_text(encoding='utf-8'))
 if manifest['version']!='4.0.2':raise RuntimeError('Tien ich Chrome khong dung phien ban 4.0.2')
 print('DA KIEM TRA: ma Python, thu vien video, ket noi Chrome, mo hinh OCR.')
 print(ocr_model_info()[1])
if __name__=='__main__':
 try:check()
 except Exception as error:
  print('KIEM TRA CHUA DAT: '+str(error),file=sys.stderr);sys.exit(1)
