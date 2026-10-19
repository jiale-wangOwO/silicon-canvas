import assert from 'node:assert/strict';
import test from 'node:test';
import { diagramSummary, sourceSummary, strategySummary, generationInstruction } from '../visual-brief.js';

function diagram(kind, behavior = {}, additions = {}) {
  return { representation: 'diagram', diagram_design: { reading_strategy: { kind }, reading_question: 'Compiler default question', inventory: { same_hardware_expansions: [] } }, behavior_plan: behavior, ...additions };
}

test('reader summary distinguishes exact state, sampled-time, stage and topology tasks', () => {
  const state = diagramSummary(diagram('state-transition', { grammar: 'state-machine', objects: Array(6).fill({}), relations: Array(12).fill({}) }));
  assert.match(state.title, /状态/); assert.match(state.bullets[0], /6 个状态与 12 条转换/);
  const timing = diagramSummary(diagram('signal-time', { grammar: 'sampled-timing', axis: Array(8), rows: Array(6) }));
  assert.match(timing.title, /信号与事件/); assert.match(timing.bullets[0], /8 个采样点与 6 条信号/);
  assert.notEqual(timing.goal, state.goal);
  const stage = diagramSummary(diagram('stage-dependency'));
  assert.match(stage.bullets.join(' '), /功能顺序与周期时序分别表达/);
  const topology = diagramSummary(diagram('ownership-network', { grammar: 'logical-topology' }));
  assert.match(topology.title, /拓扑/); assert.match(topology.bullets.join(' '), /已有邻接/);
});

test('representative explanation identifies same hardware without counting every leaf as displayed', () => {
  const result = diagramSummary(diagram('equivalent-resource-array', {}, { diagram_design: { reading_strategy: { kind: 'equivalent-resource-array' }, inventory: { same_hardware_expansions: ['lane0'] } } }));
  assert.match(result.badge, /整体与代表细节/); assert.match(result.bullets.join(' '), /同一份硬件/);
  assert.doesNotMatch(JSON.stringify(result), /lane0|DGP1|source_hash|inventory|burden/);
});

test('source summary separates supplied facts and proposed nodes, edges and ownership', () => {
  const spec = { category: 'fsm', nodes: [{ origin: 'given' }, { origin: 'assumed' }], edges: [{ origin: 'assumed' }], groups: [{ origin: 'assumed' }] };
  assert.match(sourceSummary(spec), /输入结构已保留/);
  assert.match(sourceSummary(spec), /1 个状态、1 条关系、1 处分组为建议补全/);
  assert.match(sourceSummary({ nodes: [{ origin: 'assumed' }], edges: [{ origin: 'assumed' }] }), /当前为建议方案/);
  assert.match(sourceSummary({ nodes: [{ origin: 'given' }] }), /按输入保留/);
});

test('view explanation handles older projects, render views and source Chinese question safely', () => {
  assert.equal(diagramSummary({}), null);
  assert.equal(diagramSummary({ ...diagram('ownership-network'), render_brief: {} }), null);
  const result = diagramSummary(diagram('ownership-network', {}, { technical_annex: true, diagram_design: { reading_strategy: { kind: 'ownership-network' }, reading_question: '缓存与访存请求怎样协作？' } }));
  assert.equal(result.goal, '缓存与访存请求怎样协作？'); assert.match(result.badge, /选定细节/);
  assert.doesNotMatch(JSON.stringify(result), /通过验收|已通过|最终成图|score|quality|版本/);
});

test('source without a hold loop or return does not claim those structures are shown', () => {
  const result = diagramSummary(diagram('state-transition', { grammar: 'state-machine', objects: [{ id: 'idle' }, { id: 'done' }], relations: [{ source: 'idle', target: 'done' }] }));
  assert.doesNotMatch(result.bullets.join(' '), /保持环|重试|返回/);
  const held = diagramSummary(diagram('state-transition', { grammar: 'state-machine', objects: [{ id: 'idle' }], relations: [{ source: 'idle', target: 'idle' }] }));
  assert.match(held.bullets.join(' '), /保持环/);
});

test('one shared strategy surface preserves the actual purpose and reading method across forms', () => {
  for (const representation of ['diagram', 'product_render', 'system_illustration']) {
    const figure = { id: 'main', figure_strategy: { version: 'FS1', figure_id: 'main', representation,
      purpose: 'Explain these actual interfaces', how_to_read: 'Begin at the supplied input and follow each independent branch.',
      scope: { source_nodes: 13, source_relationships: 16, visible_objects: 5, visible_relationships: 4, deferred_relationships: 7 },
      limitations: ['The selected overview does not expand the internal mechanism.'], planning_status: 'limited', actual_image_status: 'not_reviewed' } };
    const summary = strategySummary(figure, { spec: { nodes: [{ origin: 'given' }] } });
    assert.equal(summary.goal, figure.figure_strategy.purpose);
    assert.equal(summary.direction, figure.figure_strategy.how_to_read);
    assert.match(summary.scope, /5 个顶层对象.*4 条可见关系.*7 条源关系未在本图展开/);
    assert.deepEqual(summary.limitations, figure.figure_strategy.limitations);
    assert.doesNotMatch(JSON.stringify(summary), /已通过|审美得分|出版质量|认证/);
  }
});

test('switching to an annex cannot accidentally reuse the primary strategy', () => {
  const primary = { figure_id: 'primary', purpose: 'Whole system', how_to_read: 'Overview', representation: 'product_render' };
  assert.equal(strategySummary({ id: 'detail' }, { figure_strategy: primary }), null);
  const annex = { id: 'detail', technical_annex: true, figure_strategy: { figure_id: 'detail', purpose: 'Actual return path', how_to_read: 'Follow the supplied endpoints', representation: 'diagram', scope: { visible_objects: 3, visible_relationships: 2, deferred_relationships: 0 } } };
  assert.equal(strategySummary(annex, { figure_strategy: primary }).goal, 'Actual return path');
  assert.match(strategySummary(annex).badge, /工程图 · 选定细节/);
});

test('older projects fall back without invented scope or a false zero-object product', () => {
  assert.equal(strategySummary(diagram('ownership-network')), null);
  assert.equal(strategySummary({ id: 'old' }, { figure_strategy: { figure_id: 'old', purpose: 42 } }), null);
  const hero = strategySummary({ id: 'hero', figure_strategy: { purpose: 'Present the product', how_to_read: 'One complete product subject', representation: 'product_render', scope: { visible_objects: 0, visible_relationships: 0, deferred_relationships: 2 } } });
  assert.doesNotMatch(hero.scope, /0 个顶层对象/); assert.match(hero.scope, /2 条源关系/);
});

test('nested appearances are not mistaken for a count of physical hardware instances', () => {
  const summary = strategySummary({ figure_strategy: { purpose: 'Show ownership', how_to_read: 'Expand one actual owner', representation: 'diagram', scope: { top_level_objects: 4, visible_objects: 4, nested_appearances: 12, leaf_appearances: 13, visible_relationships: 4 } } });
  assert.match(summary.scope, /4 个顶层对象.*内部对象展示 12 处.*4 条可见关系/);
  assert.doesNotMatch(summary.scope, /12 个硬件|只有 4|4 个模块/);
});

test('generation handoff distinguishes missing engineering guide, required guide and prompt-only forms', () => {
  assert.match(generationInstruction({ representation: 'diagram' }), /没有可用.*重新编译/);
  assert.match(generationInstruction({ representation: 'diagram', structure_layout: {} }), /底稿和提示词一起/);
  assert.match(generationInstruction({ representation: 'diagram', structure_layout: {} }, 'diagram', false), /没有可用/);
  assert.match(generationInstruction({ representation: 'product_render' }), /可选构图参考/);
  assert.match(generationInstruction({ algorithm_flow_plan: {} }), /提示词直接交给 Image Gen/);
  assert.doesNotMatch(generationInstruction({ representation: 'system_illustration' }), /重新编译|没有可用/);
});
