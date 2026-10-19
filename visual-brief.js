// Reader-facing explanations use source facts; they never assess generated pixels.
const KINDS = {
  'state-transition': { title: '状态如何转移', level: '状态与条件', goal: '看清各个状态、转移条件与状态中的动作。', direction: '状态与条件建立阅读顺序，每个条件放在对应箭头旁。' },
  'signal-time': { title: '信号与事件如何对应', level: '共同时间轴', goal: '把信号与事件放在同一时间轴上，看清各个时刻发生什么。', direction: '信号行与给定时刻对齐，采样值和区间变化保持区别。' },
  'mathematical-dependency': { title: '数据怎样变化', level: '运算与依赖', goal: '看清独立输入怎样进入运算，在哪里汇合，以及结果如何产生。', direction: '张量、算子与结果分开表达，形状、公式和依赖对应到各自对象。' },
  'stage-dependency': { title: '各阶段怎样协作', level: '阶段与交互', goal: '看清每个阶段处理什么，以及阶段间的依赖与交互。', direction: '功能顺序与周期时序分别表达，沿已有关系追踪数据与交互。' },
  'equivalent-resource-array': { title: '私有资源与共享服务', level: '整体与代表细节', goal: '看清真实实例各自拥有的资源，以及它们怎样使用共享服务。', direction: '实例按实际数量组织；相同资源用代表细节解释，私有与共享保持清楚边界。' },
  'ownership-network': { title: '资源如何组织', level: '归属与接口', goal: '看清资源属于哪里，以及主要关系怎样穿过这些边界。', direction: '资源按设计中的归属组织，主路径与外围接口建立阅读顺序。' },
  'control-distribution': { title: '指令与响应怎样传递', level: '控制与返回', goal: '看清各资源怎样接收指令，以及完成、恢复与反馈怎样返回。', direction: '指令分发与返回分别安排，每条关系保持独立的端点与方向。' },
  'fork-join-return': { title: '数据怎样流动', level: '分支与汇合', goal: '看清独立路径在哪里分开、在哪里汇合，以及结果流向。', direction: '独立路径与汇合建立阅读顺序，每条关系保持原来的端点与方向。' },
  'source-transform-sink': { title: '数据怎样流动', level: '输入到输出', goal: '看清输入经过哪些处理，最终到达哪里。', direction: '沿实际依赖组织阅读顺序，处理、存储与接口使用清楚的视觉层级。' },
  'procedure-branch-loop': { title: '流程怎样推进', level: '步骤与条件', goal: '看清操作、条件分支、循环与停止条件。', direction: '操作与判断分别表达，分支和循环条件放在对应路径上。' },
  'procedure-sequence': { title: '流程怎样推进', level: '步骤与输出', goal: '看清操作怎样依次推进，以及每一步产生什么结果。', direction: '用清楚的顺序连接实际步骤，保留给定输入、条件与输出。' },
};
const REPRESENTATIONS = { diagram: '工程图', product_render: '商业渲染', system_illustration: '系统示意' };

export function generationInstruction(figure = {}, representation = figure.representation || 'diagram', guideAvailable = Boolean(figure.structure_layout)) {
  if (figure.algorithm_flow_plan) return '将提示词直接交给 Image Gen。算法方案按张量、算子、分支与状态组织画面；成图后核对形状、运算和每条关键依赖。';
  if (representation === 'product_render') return '将提示词交给图片生成功能，按需要附上可选构图参考。产品外观、功能说明和系统关系按本次画面目标组织。';
  if (representation === 'system_illustration') return '将提示词交给图片生成功能，按需要附上构图参考。以清楚的功能区与主路径解释系统；概念分区不表示实测布局。';
  if (!guideAvailable) return '当前视图没有可用的受控结构底稿。先按画面安排中的范围与规划限制调整后重新编译，再使用新的提示词与底稿生图。';
  return '将结构底稿和提示词一起交给图片生成功能，保留模块归属、标签与连接方向。最终成图由 Image Gen 生成。';
}

// This is presentation of the compiler's selected strategy, not another planner.
// Imported older projects are recompiled before this record reaches the UI.
export function strategySummary(figure = {}, result = {}) {
  const shared = figure.figure_strategy || (result.figure_strategy?.figure_id === figure.id ? result.figure_strategy : null);
  if (!shared || typeof shared.purpose !== 'string' || !shared.purpose.trim() || typeof shared.how_to_read !== 'string') return null;
  const profile = KINDS[figure.diagram_design?.reading_strategy?.kind];
  const scope = shared.scope || {}, count = (key) => Number.isInteger(scope[key]) && scope[key] >= 0 ? scope[key] : null;
  const objects = count('top_level_objects') ?? count('visible_objects'), nested = count('nested_appearances');
  const relationships = count('visible_relationships'), deferred = count('deferred_relationships');
  const scopeLines = [];
  if (objects > 0 && relationships !== null) scopeLines.push(`本图有 ${objects} 个顶层对象${nested ? `，内部对象展示 ${nested} 处` : ''}，${relationships} 条可见关系。`);
  if (deferred) scopeLines.push(`另有 ${deferred} 条源关系未在本图展开，可在完整工程结构中核对。`);
  return { version: shared.version, title: profile?.title || '画面安排',
    badge: `${REPRESENTATIONS[shared.representation] || '视觉表达'} · ${figure.technical_annex ? '选定细节' : profile?.level || '按当前用途组织'}`,
    goal: shared.purpose, direction: shared.how_to_read, scope: scopeLines.join(' '),
    limitations: Array.isArray(shared.limitations) ? shared.limitations.filter((value) => typeof value === 'string' && value.trim()) : [],
    provenance: sourceSummary(result.spec) };
}

export function sourceSummary(spec = {}) {
  const nodes = Array.isArray(spec.nodes) ? spec.nodes : [], edges = Array.isArray(spec.edges) ? spec.edges : [];
  const groups = Array.isArray(spec.groups) ? spec.groups : [];
  const proposedNodes = nodes.filter((item) => item.origin === 'assumed').length;
  const proposedEdges = edges.filter((item) => item.origin === 'assumed').length;
  const proposedGroups = groups.filter((item) => item.origin === 'assumed').length;
  const unit = spec.category === 'fsm' ? '状态' : spec.category === 'timing' ? '信号' : spec.category === 'algorithm' ? '对象' : '模块';
  const proposed = [proposedNodes && `${proposedNodes} 个${unit}`, proposedEdges && `${proposedEdges} 条关系`, proposedGroups && `${proposedGroups} 处分组`].filter(Boolean);
  if (!proposed.length) return nodes.length || edges.length ? `${unit}与关系按输入保留，详细内容可在完整工程结构中核对。` : '';
  const known = nodes.some((item) => item.origin !== 'assumed') || edges.some((item) => item.origin !== 'assumed');
  return `${known ? '输入结构已保留；' : '当前为建议方案：'}${proposed.join('、')}为建议补全，可在完整工程结构中核对。`;
}

export function diagramSummary(figure = {}, result = {}) {
  const plan = figure.diagram_design;
  if (!plan || figure.render_brief) return null;
  const strategy = plan.reading_strategy || {}, behavior = figure.behavior_plan || {};
  let profile = KINDS[strategy.kind] || { title: '这张图怎样读', level: '结构与关系', goal: '围绕当前设计的阅读重点，组织资源、关系与必要细节。', direction: '通过层级、位置、文字与连接，让主要关系清楚可读。' };
  if (behavior.grammar === 'logical-topology') profile = { title: '拓扑如何连接', level: '实际邻接与接口', goal: '看清各节点的实际邻接、所属范围，以及外围资源的连接。', direction: '按已有邻接组织逻辑位置，不同方向与含义的关系分别保留。' };
  const bullets = [profile.direction];
  if (behavior.grammar === 'sampled-timing') {
    const samples = Array.isArray(behavior.axis) ? behavior.axis.length : 0, signals = Array.isArray(behavior.rows) ? behavior.rows.length : 0;
    if (samples && signals) bullets.unshift(`${samples} 个采样点与 ${signals} 条信号对齐，保留每个给定值。`);
  }
  if (behavior.grammar === 'state-machine') {
    const states = Array.isArray(behavior.objects) ? behavior.objects.length : 0, transitions = Array.isArray(behavior.relations) ? behavior.relations.length : 0;
    if (states) bullets[0] = `${states} 个状态${transitions ? `与 ${transitions} 条转换` : ''}，条件附在各自的转换上。`;
    if (behavior.relations?.some((item) => typeof item.source === 'string' && item.source === item.target)) bullets.push('保持环围绕对应状态，主流程与条件返回清楚区分。');
  }
  if (strategy.kind !== 'state-transition' && strategy.cycle_components?.length) bullets.push('返回通道独立安排，仍连接原来的资源。');
  if (plan.inventory?.same_hardware_expansions?.length) bullets.push('代表展开显示同一份硬件的细节；各真实实例继续保留在整体中。');
  const suppliedQuestion = typeof plan.reading_question === 'string' && /[\u3400-\u9fff]/.test(plan.reading_question) ? plan.reading_question : '';
  const representation = REPRESENTATIONS[figure.representation || 'diagram'] || '工程图';
  return { title: profile.title, badge: `${representation} · ${figure.technical_annex ? '选定细节' : profile.level}`, goal: suppliedQuestion || profile.goal,
    bullets, provenance: sourceSummary(result.spec) };
}
