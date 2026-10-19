import assert from 'node:assert/strict';
import test from 'node:test';
import { optionPreviewModel, optionPreviewSvg, renderOptionPreview } from '../option-previews.js';

test('fixed English labels keep the automatic preview neutral and do not count as customization', () => {
  const settings = Object.freeze({ representation: 'auto', scene: 'auto', style: 'auto', density: 'auto', aspect: 'auto', language: 'en', explanatory_mode: 'auto' });
  const model = renderOptionPreview(null, settings);
  assert.equal(model.neutral, true);
  assert.equal(model.representation, 'auto');
  assert.deepEqual(model.labels, []);
  assert.match(optionPreviewSvg(model), /自动模式示意/);
  assert.deepEqual(settings, { representation: 'auto', scene: 'auto', style: 'auto', density: 'auto', aspect: 'auto', language: 'en', explanatory_mode: 'auto' });
});

test('untrusted imported settings cannot introduce markup or resource requests', () => {
  const attack = '</svg><script src="https://invalid.example/key"></script>';
  const model = optionPreviewModel({ representation: attack, scene: attack, style: attack, density: attack, aspect: attack, explanatory_mode: attack, language: attack });
  const svg = optionPreviewSvg(model, attack);
  assert.equal(model.neutral, true);
  assert.doesNotMatch(svg, /<script|invalid\.example|<image|href=|foreignObject/);
  assert.doesNotMatch(JSON.stringify(model), /invalid\.example/);
});

test('manual choices stay explicit while an illustrative fallback does not resolve auto', () => {
  const model = optionPreviewModel({ representation: 'auto', scene: 'concept', style: 'monochrome', aspect: 'A4', density: 'low', language: 'zh' });
  assert.equal(model.representation, 'auto');
  assert.equal(model.scene, 'concept');
  assert.equal(model.aspect, 'A4');
  assert.equal(model.language, 'zh');
  assert.ok(model.labels.includes('整体概念'));
  assert.ok(model.labels.includes('A4 纵向'));
  assert.ok(model.labels.includes('黑白印刷'));
  assert.ok(!model.labels.includes('中文标签'));
  assert.doesNotMatch(optionPreviewSvg(model), /grid|hatch|pattern|<image|href=/);
});
