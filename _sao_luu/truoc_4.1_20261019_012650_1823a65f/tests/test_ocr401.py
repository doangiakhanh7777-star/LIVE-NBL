"""Real offline OCR over rendered UI labels; not a native LIVE Studio test."""
import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
AVAILABLE=importlib.util.find_spec('rapidocr_onnxruntime') is not None
@unittest.skipUnless(AVAILABLE,'Install OCR test dependencies or use the bundled Windows OCR vendor')
class RealOCRTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from PIL import Image,ImageDraw,ImageFont
  import studio_vision as V
  font=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
  if not font.is_file():raise unittest.SkipTest('Rendered fixture requires DejaVu Sans')
  im=Image.new('RGB',(900,210),'white');draw=ImageDraw.Draw(im);face=ImageFont.truetype(str(font),26)
  for i,text in enumerate(['Khánh Car Auto 1','Sản phẩm này giá 100k nhé anh chị','Thêm bình luận...','00:10:21']):draw.text((10,i*48),text,font=face,fill='black')
  cls.rows=V.read_image(im)
  if len(cls.rows)!=4:raise AssertionError('Expected four OCR fixture labels: '+repr(cls.rows))
 def test_real_vietnamese_name(self):
  from studio_vision_logic import same_author
  self.assertTrue(same_author(self.rows[0]['text'],'Khánh Car Auto 1'))
 def test_real_price_draft(self):
  from studio_vision_logic import draft_state
  self.assertEqual(draft_state([self.rows[1]],'Sản phẩm này giá 100k nhé anh chị'),'expected')
  self.assertNotEqual(draft_state([self.rows[1]],'Sản phẩm này giá 900k nhé anh chị'),'expected')
 def test_real_placeholder(self):
  from studio_vision_logic import draft_state
  self.assertEqual(draft_state([self.rows[2]]),'empty')
 def test_real_clock(self):
  from studio_vision_logic import clock_reading
  self.assertEqual(clock_reading([self.rows[3]]),'00:10:21')
