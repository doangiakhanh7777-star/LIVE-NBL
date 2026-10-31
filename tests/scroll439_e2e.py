"""Chay that logic cuon cua content.js tren Chrome that, trang gio hang tai dan."""
import re, sys, pathlib
from playwright.sync_api import sync_playwright

SRC = pathlib.Path('/tmp/claude-0/-home-claude/b727ed40-005c-535a-8f19-167d05b905f0/scratchpad/p430/CHROME_NBL_LIVE/content.js').read_text(encoding='utf-8')

def grab(sig):
    i = SRC.index(sig)
    # cat den dau dong ke tiep bat dau bang 'function ', 'async function ', 'const ' hoac '//'
    m = re.compile(r'^(?:async function |function |const [A-Za-z]|// )', re.M).search(SRC, i + len(sig))
    return SRC[i:m.start()] if m else SRC[i:i+4000]

parts = [grab(s) for s in (
    'function actionButtons(card,kind)', 'function readNumber(el)',
    'function numberCells()', 'function numberRows()',
    'function scrollBoxes()', 'function listBox()',
    'function rowKey()', 'async function scrollTo(box,top)', 'async function rowOf(number',
    'async function waitOwner()',
)]
CODE = '''
window.host=document.createElement('div');          // khung bang dieu khien cua NBL
let cfg={},manualScrollAt=0;
const NUM_CELL='input[data-tid="m4b_input_number"]';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
const buttonName=b=>[b.innerText||'',b.getAttribute('aria-label')||''];
function $(){return null;}
function searchBox(){return [...document.querySelectorAll('input')].find(i=>/Tìm ID/.test(i.getAttribute('placeholder')||''))||null;}
''' + '\n'.join(parts) + '''
if(!/rowKey/.test(String(scrollTo)))throw new Error('BO TEST HONG: scrollTo khong phai ham cuon cua NBL');
window.NBLTEST={listBox,rowOf,numberCells,scrollBoxes,scrollTo,rowKey};
'''

fails = []
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1100, 'height': 800})
    pg.goto('file://' + str(pathlib.Path(__file__).parent / (sys.argv[1] if len(sys.argv) > 1 else 'cart.html')))
    pg.add_script_tag(content=CODE)

    box = pg.evaluate("()=>{const b=NBLTEST.listBox();return b?{id:b.id,tag:b.tagName,h:b.clientHeight}:null}")
    print('1. khung cuon NBL chon:', box)
    want_box = (sys.argv[2] if len(sys.argv) > 2 else 'list')
    if not box or box['id'] != want_box:
        fails.append('chon nham khung cuon: ' + str(box) + ' (phai la "' + want_box + '")')

    print('2. luc dau doc duoc bao nhieu o so:', pg.evaluate("()=>NBLTEST.numberCells().length"), '(trang moi tai chi co 20)')

    for want in (7, 35, 96, 120):
        r = pg.evaluate("async n=>{const row=await NBLTEST.rowOf(n);return row?{n:row.number,text:row.text.slice(0,40),pin:!!row.pin}:null}", want, )
        ok = r and r['n'] == want
        print(('   OK  ' if ok else '   HONG') + ' tim so %-4d ->' % want, r)
        if not ok:
            fails.append('khong tim duoc so %d (danh sach tai dan)' % want)

    r = pg.evaluate("async ()=>{const row=await NBLTEST.rowOf(999);return row?row.number:null}")
    print('3. tim so khong co (999) ->', r, '(phai la None)')
    if r is not None:
        fails.append('so 999 khong co trong gio ma van bao tim thay')

    top = pg.evaluate("()=>document.getElementById('list').scrollTop")
    print('4. cuon xong danh sach o vi tri:', top)
    b.close()

print()
if fails:
    print('HONG:'); [print(' -', f) for f in fails]; sys.exit(1)
print('DAT: chon dung khung cuon, tim duoc ca so cuoi danh sach tai dan.')
