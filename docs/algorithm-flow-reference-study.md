# 算法与数据流图参考研究

审核日期：2026-10-11。此轮针对数据路径“有框、有线，但看不出运算和数据如何变化”的问题，补充算法论文原图。下面的构图观察来自逐页渲染和目视检查，而不是只读摘要或让模型猜测图形。

新增 10 幅参考，来自 8 篇论文。原图裁切直接保存在仓库根目录的 `reference_images/dataflow/`，保持既有目录分类；原 PDF 和检查脚本保存在忽略目录 `.local/algorithm_refs/`。发行包只包含 `src/silicon_canvas/reference_images/algorithm_manifest.json` 的来源与构图元数据，不包含第三方图片。清单记录精确 PDF 页码、图号、裁切框、像素尺寸，以及 PDF 与裁切文件 SHA-256；页码指 PDF 文件的第几页。

## 已检查的原图

| 来源与定位 | 本地裁切文件 | 可以迁移的构图方法 |
| --- | --- | --- |
| [FlashAttention，NeurIPS 2022，Fig. 1，PDF 第 2 页](https://proceedings.neurips.cc/paper_files/paper/2022/file/67d57c32e20fd0a7a302cb81d36e40d5-Paper-Conference.pdf#page=2) | `flashattention-2022-fig1-io-tiling.png` | Q、K、V 和输出使用分块矩阵形状；当前工作块突出，全量中间矩阵用虚线轮廓。外层与内层遍历、拷贝和计算分开编码。裁切保留内存层级与分块计算，排除性能柱状图。 |
| [Attention Is All You Need，Fig. 1，arXiv v7 PDF 第 3 页](https://arxiv.org/pdf/1706.03762v7#page=3) | `transformer-2017-fig1-encoder-decoder.png` | 编码器、解码器形成两个稳定的竖向列；残差绕行在操作外围，进入明确的 Add & Norm；重复层用代表块与 N×。跨列输入只进入对应注意力层。 |
| [Attention Is All You Need，Fig. 2，arXiv v7 PDF 第 4 页](https://arxiv.org/pdf/1706.03762v7#page=4) | `transformer-2017-fig2-attention-operators.png` | Q、K 短线汇入第一次 MatMul，V 走旁路进入最后一次 MatMul；缩放、可选掩码和 SoftMax 按依赖顺序排列。多头使用少量错位代表层、h 和 Concat，保留完整堆叠括号。 |
| [Mamba，Fig. 1，arXiv v2 PDF 第 3 页](https://arxiv.org/pdf/2312.00752v2#page=3) | `mamba-2024-fig1-state-selection.png` | 旧状态和新状态占据一条长横向状态轨；输入、读出和选择参数在下方形成不同的短通路。向量与状态块的形状承担解释，不必把所有东西装进同一种框。 |
| [Mamba，Fig. 3，arXiv v2 PDF 第 8 页](https://arxiv.org/pdf/2312.00752v2#page=8) | `mamba-2024-fig3-gated-block.png` | H3、Gated MLP 与 Mamba 共用框架、入口、出口和操作字典；主分支和门控分支在乘法圆点处相遇。线性投影、序列变换和非线性使用不同形状角色。 |
| [Mamba-2，ICML 2024 出版页](https://proceedings.mlr.press/v235/dao24a.html)，[Fig. 2，出版 PDF 第 7 页](https://raw.githubusercontent.com/mlresearch/v235/main/assets/dao24a/dao24a.pdf#page=7) | `mamba2-2024-fig2-projection-parallelism.png` | 顺序投影和并行投影保持同尺寸与同方向，读者可以直接比较参数依赖位置。旁路保持安静，归一化、激活和乘法是小算子；不能因“并行”自行加入时间或加速数值。 |
| [U-Net，Fig. 1，arXiv v1 PDF 第 2 页](https://arxiv.org/pdf/1505.04597v1#page=2) | `unet-2015-fig1-feature-pyramid.png` | 压缩与展开构成对称 U 形；空间分辨率决定层级，同分辨率的跳连水平对齐。特征图宽高、通道厚度、实心与空心状态表达数据变化；保留输入文字及操作图例。 |
| [ResNet，CVPR 2016，Fig. 2，PDF 第 2 页](https://openaccess.thecvf.com/content_cvpr_2016/papers/He_Deep_Residual_Learning_CVPR_2016_paper.pdf#page=2) | `resnet-2016-fig2-residual-merge.png` | 两个权重操作、一条 identity 旁路和明确加法节点即可讲清残差；激活在合流后。x、F(x) 和 F(x)+x 是数据值，weight layer 是操作，二者不能混为同类块。 |
| [FlashAttention-3，作者论文，Fig. 1，PDF 第 6 页](https://tridao.me/publications/flash3/flash3.pdf#page=6) | `flashattention3-2024-fig1-pingpong-schedule.png` | 两个 warpgroup 共用时间轴；GEMM0、Softmax、GEMM1 的顺序明确。同一次迭代在不同资源中保持同色，虚线对齐重叠边界。该图用较高分辨率的原生位图；同页 Fig. 2 的内嵌图分辨率更低，未选入清单。 |
| [Butterfly Factorizations，ICML 2019，Fig. 1，PDF 第 4 页](https://proceedings.mlr.press/v97/dao19a/dao19a.pdf#page=4) | `butterfly-2019-fig1-sparse-factor-patterns.png` | 四个同尺寸矩阵坐标系用一种红色展示从粗到细的递归稀疏模式。它是稀疏因子结构图，不是 FFT 信号流图；真实置换与旋转因子仍要来自输入。 |

已存在的 Eyeriss Fig. 5/6 和 MAESTRO 复用图继续作为卷积、空间映射和重用的补充，未重复下载。本轮侧重此前薄弱的张量操作、分支合流、状态递推、跨尺度特征和调度表达。构图可迁移，论文的具体尺寸、算子、存储层级和性能数据不能迁移到其他用户算法。

## 对 Silicon Canvas 数据流策略的要求

**先判断图要解释哪种关系，再选择图形语法。** 从算法概念到物理数据通路至少有四种不同的解释任务：值经过什么操作、哪些状态跨迭代保留、数据在哪个存储层驻留、操作如何分配到资源与时间。输入只要求算法流程时，不能强行加入 Fetch、Issue、DMA、寄存器或 HBM。输入只要求硬件路径时，也不能用几个数学公式替代实际接口。

| 要解释的关系 | 适合的图形与布局 | 不适合的默认处理 |
| --- | --- | --- |
| 张量变换与计算依赖 | 数据使用矩阵、向量、特征图形状；操作使用轻量算子块；沿一条明确的阅读方向组织主路径，操作数从相邻方向进入 | 每一步都变成同尺寸的圆角模块，把数据值与执行模块混合 |
| 分支、残差与门控 | 分叉处明确，侧分支占独立走廊；加法、乘法、拼接等合流必须有明确操作；合流后的归一化或激活按真实顺序保留 | 分支偷偷并入一根线，多个箭头交叉但没有明确端点 |
| 递推、scan 与累加 | 状态轨与当前输入、输出分开；用 `previous → update → next` 说明跨迭代携带，只在输入支持时展开少量时间步 | 绕整个算法画一个含糊的反馈环，无法知道保留哪个状态 |
| 分块、驻留与重用 | 一个代表 tile 和一条真实复用关系突出；标明已提供的层级边界；完整矩阵轮廓可以虚线弱化 | 因为某算法常用 SRAM，就给所有算法凭空生成一层 SRAM/DRAM 硬件 |
| 跨尺度特征变换 | 几何尺寸变化、分辨率层级、同层跳连和短操作图例配合；只标用户提供或可证明的维度 | 彩色立方体堆叠只有装饰性透视，无法辨认张量大小或跳连 |
| 并行调度与重叠 | 有来源的资源行、共同时间轴、迭代标识与对齐事件；没有定量数据则使用定性阶段视图 | 从计算 DAG 随意推断耗时条宽、气泡、带宽和流水线重叠 |

外观规则服务于这些语义：白底、深色文字、细而连续的主连接、较弱的旁路线、小范围强调色，以及足够的操作间距。颜色稳定对应“数据族、操作角色或迭代”中的一种语义，不同时承担三种含义。形状、位置、端点与短标签需要在灰度下仍可理解。

## 用于真实生图复核的重点

1. 在放大看文字前，读者能否指出输入、输出和主要依赖顺序；主运算链不能被外层标题带、图例与辅助容器压住。
2. 两输入操作是否保留两个入口；旁路是否跳过正确操作并在正确合流点进入；出现同一数据的多次使用时，是否明确是复用、拷贝还是多份独立输入。
3. 加法、乘法、拼接、归约、softmax、gate 等操作是否混淆；尤其检查合流前后顺序和状态的 old/new 版本。
4. 维度、掩码方向、置换、tile 标号与时间步只能来自语义来源。参考图是一种表达方法，不能提供本次算法缺少的事实。
5. 存储层级、物理执行资源与时间刻度分别有其来源；跨边界箭头要对应真实拷贝，不应把计算依赖误画成总线。
6. 对同一机制比较两种方案时固定共同坐标与算子字典，只突出差异；不为“复杂”画满所有头、所有通道或所有迭代。

这份研究给出可执行的审图标准和构图候选，不表示 Image Gen 已被证明能精确重现任意算法。后续样例应保留实际输入、生成提示词、原始图和逐条核对结果，用真实输出确认规则是否生效。
