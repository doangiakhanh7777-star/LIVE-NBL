import json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import benchmark_studio_ocr as B
class BenchmarkTests(unittest.TestCase):
 def test_twenty_duplicates_do_not_count_as_twenty_screenshots(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);Image.new('RGB',(50,50),'white').save(p/'one.png')
   (p/'labels.json').write_text(json.dumps(dict(source='studio_capture',samples=[dict(file='one.png',expected='Xem gio hang')]*20)),encoding='utf-8')
   with patch.object(B,'read_image',return_value=[{'text':'Xem gio hang'}]):r=B.run(p/'labels.json',p/'result.json')
   self.assertEqual(r['unique_images'],1);self.assertFalse(r['twenty_real_screenshots_supplied']);self.assertEqual(r['native_live_acceptance'],'NOT_PERFORMED')
 def test_generated_images_do_not_become_native_evidence(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);samples=[]
   for i in range(20):
    name=str(i)+'.png';Image.new('RGB',(50,50),(i,0,0)).save(p/name);samples.append(dict(file=name,expected='Xem gio hang'))
   (p/'labels.json').write_text(json.dumps(dict(source='synthetic',samples=samples)),encoding='utf-8')
   with patch.object(B,'read_image',return_value=[{'text':'Xem gio hang'}]):r=B.run(p/'labels.json',p/'result.json')
   self.assertEqual(r['unique_images'],20);self.assertFalse(r['twenty_real_screenshots_supplied'])
if __name__=='__main__':unittest.main()
