// Run: node --test tests/
const test = require('node:test');
const assert = require('node:assert');
const N = require('../CHROME_NBL_LIVE/engine.js');

const rules = N.parse([
  'giá;gia | Giá có trong giỏ ạ',
  'ship;giao hàng | Shop giao toàn quốc',
  'giá sỉ | Giá sỉ inbox shop',
  'size | Size S đến XL',
  'sz | Size S đến XL',
].join('\n'), 'rule');

test('whole words only: "gia" no longer matches giao/giày/giảm', () => {
  assert.strictEqual(N.answer(rules, 'giày đẹp quá'), null);
  assert.strictEqual(N.answer(rules, 'giảm không shop'), null);
  assert.strictEqual(N.answer(rules, 'Giá bao nhiêu vậy'), 'Giá có trong giỏ ạ');
  assert.strictEqual(N.answer(rules, 'GIA?'), 'Giá có trong giỏ ạ');
});

test('most specific keyword wins', () => {
  assert.strictEqual(N.answer(rules, 'cho hỏi giá sỉ'), 'Giá sỉ inbox shop');
  assert.strictEqual(N.answer(rules, 'có giao hàng tỉnh ko'), 'Shop giao toàn quốc');
});

test('two rules with the same reply are not ambiguous', () => {
  assert.strictEqual(N.answer(rules, 'size sz nào vừa'), 'Size S đến XL');
});

test('equally specific different replies stay unanswered', () => {
  const tie = N.parse('mau | Có 3 màu\nship | Ship 2 ngày', 'rule');
  assert.strictEqual(N.answer(tie, 'mau gi ship sao'), null);
});
