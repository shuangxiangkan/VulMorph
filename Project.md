# VulMorph 项目路线设计

## 1. 项目定位

VulMorph 关注的问题是：

> **功能相似的 C/C++ 第三方库，可能因为相似的设计模式、算法实现、输入语义或内存管理方式，存在同源但语法不同的漏洞根因。**

项目目标不是做普通代码克隆检测，而是做：

> **跨库漏洞根因迁移与候选漏洞发现。**

也就是说，给定一个已知 CVE 及其补丁，系统尝试抽象出与具体库无关的漏洞根因模式，再把这个模式迁移到同类库中，发现潜在的同类漏洞。

示例：

```text
已知：zlib 的 inflate() 存在整数溢出
根因：窗口大小计算中发生类型截断，随后影响内存分配

问题：zstd / lz4 / brotli / minizip 中
是否存在类似的“窗口大小计算 + 类型截断 + 分配/拷贝”的危险路径？
```

核心难点是：

- 代码语法可能完全不同。
- API 名称和数据结构不同。
- 触发路径不同。
- 但根因模式可能相同。

因此，本项目的核心贡献应放在“漏洞根因抽象”和“跨库候选检索”上。

---

## 2. 推荐研究假设

建议把项目假设收敛成一个可验证的版本：

> 对于同一功能族的 C/C++ 库，已知漏洞补丁中体现出的数据流约束变化，可以被抽象成库无关的根因模式，并用于检索其他同类库中的高风险候选代码。

这个表述比“找未知漏洞”更适合作为论文或系统目标，因为它可以评估：

- 根因模式是否能从 patch 中提取出来。
- 模式是否能迁移到其他库。
- 候选检索是否比普通代码相似度更有效。
- 最终是否能发现真实 bug 或潜在 CVE。

---

## 3. 总体路线

推荐采用三阶段路线：

```text
阶段一：小规模 MVP
    手工选 CVE -> 手工抽象根因 -> 手工/半自动检索 -> 验证假设

阶段二：半自动系统
    CVE/patch 采集 -> 程序切片/数据流摘要 -> LLM 根因描述 -> 静态分析查询/向量检索

阶段三：规模化评估
    多库族数据集 -> baseline 对比 -> 消融实验 -> 漏洞验证/报告
```

不要一开始就做全自动系统。这个方向最大的不确定性在于“跨库根因迁移是否真的有效”，所以第一阶段应该优先验证假设，而不是堆工具链。

---

## 4. 阶段一：MVP 验证

### 4.1 选择一个库族

建议优先选择压缩库族：

- zlib
- zstd
- lz4
- brotli
- minizip
- libarchive 中的压缩相关模块

原因：

- 都是 C/C++。
- 功能语义相近。
- 历史漏洞较多。
- 常见漏洞类型集中在整数溢出、边界检查、缓冲区读写、解压炸弹、状态机错误。
- 输入格式相对明确，后续适合 fuzzing 验证。

先不要同时做 XML、图像、加密等多个方向，否则问题空间会迅速失控。

### 4.2 选择 5-10 个种子 CVE

每个 CVE 尽量满足：

- 有明确修复 commit。
- patch 较小，能定位到关键函数。
- 漏洞类型清楚，例如 CWE-190、CWE-787、CWE-125。
- 有公开描述或复现材料更好。

每条种子记录建议整理为：

```json
{
  "cve": "CVE-XXXX-YYYY",
  "source_library": "zlib",
  "vulnerable_version": "x.y.z",
  "fixed_version": "x.y.z",
  "patch_commit": "commit url",
  "affected_function": "inflate",
  "cwe": "CWE-190",
  "buggy_behavior": "integer overflow before allocation",
  "security_impact": "out-of-bounds write / denial of service"
}
```

### 4.3 手工抽象根因模式

第一阶段建议不要急着让 LLM 或某个静态分析工具全自动抽象。先人工产出 5-10 条高质量模式，形成项目的“黄金样本”。

推荐的根因模式格式：

```json
{
  "pattern_id": "INT_TRUNC_ALLOC_001",
  "vulnerability_class": "integer truncation before allocation",
  "source": "externally influenced size or length",
  "transform": [
    "cast to narrower integer type",
    "shift or multiplication",
    "unchecked arithmetic result"
  ],
  "sink": "memory allocation / memcpy / buffer indexing",
  "missing_constraint": [
    "no upper bound check before cast",
    "no overflow check before multiplication"
  ],
  "negative_evidence": [
    "explicit max size guard",
    "checked arithmetic helper"
  ],
  "cwe": ["CWE-190", "CWE-681"]
}
```

这个格式很重要，因为它同时服务于：

- LLM 分析提示词。
- 静态分析查询生成。
- 检索结果解释。
- 评估标注。

### 4.4 在目标库中找候选

第一阶段可以采用三种低成本方法并行：

- 关键词检索：找 `malloc`、`calloc`、`realloc`、`memcpy`、`<<`、类型转换、长度字段。
- 静态分析/数据流查询：找从参数/输入字段到分配、拷贝、索引的路径。
- LLM 辅助阅读：给候选函数和根因模式，让模型判断是否匹配。

第一阶段的目标不是召回全部漏洞，而是回答：

> 已知漏洞的根因，能不能在另一个同类库中找到语义相似的危险代码？

如果 5-10 个种子 CVE 中完全没有可迁移样例，需要及时调整方向，例如改做“同库跨版本漏洞模式检测”或“同类库 patch 缺失检测”。

---

## 5. 阶段二：半自动系统设计

阶段一验证成立后，再开始搭建系统。

### 5.1 数据采集模块

输入：

- CVE ID
- NVD 描述
- GitHub/GitLab 修复 commit
- 漏洞版本和修复版本
- CWE 标签

输出：

- before 函数
- after 函数
- patch diff
- 受影响语句
- 元数据 JSON

建议先支持 GitHub commit，不必一开始覆盖所有来源。

### 5.2 Patch 定位模块

目标是从 patch 中定位安全相关变化。

优先关注这些变化类型：

- 新增边界检查。
- 新增整数溢出检查。
- 修改类型宽度。
- 修改分配大小计算。
- 修改 `memcpy` / `memmove` / `strcpy` / buffer indexing。
- 新增错误返回路径。
- 新增状态机合法性检查。

输出安全相关的 changed statements，用于后续切片。

### 5.3 程序切片模块

使用可替换的程序分析工具提取漏洞相关数据流。Joern/CPG 可以作为一个实现选项，但不应成为项目路线的前提。

目标是得到统一的数据流摘要：

```text
source -> transform -> constraint -> sink
```

其中：

- source：外部输入、文件字段、网络字段、API 参数。
- transform：cast、shift、加减乘、长度换算、结构体字段传播。
- constraint：范围检查、溢出检查、状态检查。
- sink：内存分配、拷贝、数组索引、指针运算、循环边界。

这个模块不需要一开始做到完美。MVP 可以只支持若干常见 sink：

- `malloc`
- `calloc`
- `realloc`
- `memcpy`
- `memmove`
- array index
- pointer arithmetic

可选实现包括：

- Joern/CPG。
- CodeQL。
- tree-sitter + 自定义轻量数据流。
- clang AST / libTooling。
- Semgrep 规则。
- 先用正则/关键词做 MVP，再逐步替换为更强的分析后端。

### 5.4 LLM 根因抽象模块

LLM 不应该直接输出“有没有漏洞”的最终结论，而应该输出结构化中间表示。

推荐输入：

- CVE 描述
- patch diff
- before/after 函数
- 程序切片结果

推荐输出：

```json
{
  "vulnerability_class": "...",
  "source": "...",
  "dangerous_dataflow": "...",
  "sink": "...",
  "missing_constraint": "...",
  "patch_added_constraint": "...",
  "library_independent_pattern": "...",
  "analysis_query_hint": "...",
  "false_positive_filters": ["..."]
}
```

关键原则：

- LLM 做抽象和解释。
- 程序分析做约束和证据。
- 不把 LLM 的自然语言判断当成唯一依据。

### 5.5 跨库检索模块

推荐两阶段检索：

**第一阶段：高召回粗筛**

- 函数名/API 关键词。
- sink 关键词。
- 代码 embedding。
- 调用图邻近关系。

输出 Top-K 候选函数。

**第二阶段：高精度重排**

- 静态分析/数据流查询。
- LLM 根据结构化根因模式打分。
- 检查是否存在 negative evidence，例如已有上界检查、使用安全 arithmetic helper。

候选结果建议包含：

```json
{
  "target_library": "lz4",
  "function": "LZ4_decompress_safe",
  "matched_pattern": "INT_TRUNC_ALLOC_001",
  "evidence": [
    "input length reaches allocation size",
    "multiplication before bounds check"
  ],
  "negative_evidence": [
    "function name contains safe but no overflow check found"
  ],
  "confidence": 0.72
}
```

---

## 6. 阶段三：评估设计

### 6.1 数据集评估

至少构建两个集合：

**Seed Set**

- 已知 CVE + patch。
- 用于抽象根因模式。

**Target Set**

- 同类库的历史版本。
- 用于检索候选。
- 可以包含已知漏洞版本，用来做回归验证。

推荐从压缩库开始：

```text
库族：compression
种子库：zlib / libarchive / brotli
目标库：zstd / lz4 / minizip / libarchive
漏洞类型：integer overflow, buffer overflow, OOB read/write
```

### 6.2 Baseline

至少和这些方法对比：

- 纯关键词检索。
- 代码克隆检测。
- 代码 embedding 相似度。
- 静态分析器告警，例如 CodeQL、clang static analyzer。
- 只用 LLM 直接判断。

VulMorph 的卖点应当是：

> 比单纯代码相似度更能跨语法迁移，比单纯 LLM 更有程序分析证据。

### 6.3 指标

推荐指标：

- Top-K 命中率：目标漏洞是否出现在前 K 个候选中。
- Precision@K：前 K 个候选中真实相关比例。
- Recall：已知目标漏洞被找回的比例。
- 人工审计成本：每个模式平均需要审多少候选函数。
- 误报类型：为什么看起来像但不是漏洞。
- 新漏洞数量：能否发现 previously unknown bug。

### 6.4 消融实验

建议做这些消融：

- 去掉程序切片，只用 LLM。
- 去掉 LLM，只用静态分析模式。
- 去掉 negative evidence 过滤。
- 去掉 embedding 粗筛。

这样可以证明每个模块是否真的有贡献。

---

## 7. 里程碑计划

### Milestone 0：仓库初始化

目标：把项目从文档变成可运行骨架。

建议目录：

```text
VulMorph/
  README.md
  Project.md
  data/
    seeds/
    targets/
    patterns/
  vulmorph/
    collectors/
    diff_analysis/
    slicing/
    retrieval/
    ranking/
    validation/
  scripts/
  experiments/
  docs/
```

### Milestone 1：手工案例

目标：完成 1 个端到端案例。

交付物：

- 1 个种子 CVE。
- 1 个根因模式 JSON。
- 2-3 个目标库候选函数。
- 1 份人工分析报告。

成功标准：

- 能清楚说明为什么候选与原漏洞根因相似。
- 能说明候选是真问题、潜在风险，或为什么不是漏洞。

### Milestone 2：小规模数据集

目标：完成 5-10 个种子 CVE。

交付物：

- `data/seeds/*.json`
- `data/patterns/*.json`
- 每个模式对应的候选检索结果。

成功标准：

- 至少 2-3 个模式可以跨库找到有意义候选。
- 总结哪些漏洞类型适合迁移，哪些不适合。

### Milestone 3：半自动检索

目标：实现候选发现流水线。

交付物：

- patch 解析脚本。
- sink/source 提取脚本。
- 静态分析查询模板。
- embedding 粗筛脚本。
- 候选排序报告。

成功标准：

- 给定一个 pattern，可以自动输出 Top-K 候选函数。
- 每个候选有 evidence 和 negative evidence。

### Milestone 4：验证与论文实验

目标：系统化评估。

交付物：

- baseline 对比结果。
- 消融实验结果。
- 若干人工确认 bug。
- 如果可能，提交上游 issue 或 CVE。

成功标准：

- 在历史漏洞回归中优于 baseline。
- 至少发现若干真实 bug 或高质量潜在漏洞。

---

## 8. 风险与调整方向

### 风险 1：跨库迁移太难

表现：

- 手工分析也找不到相似候选。
- 不同库实现差异过大。

调整：

- 缩小到“同库跨版本”或“同项目不同模块”。
- 选择功能更接近的库族。
- 聚焦更稳定的漏洞类型，例如整数溢出到内存分配。

### 风险 2：LLM 幻觉较多

表现：

- LLM 编造不存在的数据流。
- 候选解释看似合理但代码证据不足。

调整：

- 所有结论必须绑定代码位置和数据流证据。
- LLM 只输出假设，静态分析/人工验证证据。
- 增加 negative evidence 检查。

### 风险 3：静态分析噪音太大

表现：

- 静态分析查询返回大量无关候选。

调整：

- 先用 embedding 或关键词缩小范围。
- 限定 source/sink 类型。
- 用 patch 中新增约束作为过滤条件。

### 风险 4：漏洞验证成本高

表现：

- 候选像漏洞，但难以构造 PoC。

调整：

- 先做历史漏洞回归评估。
- 把“高风险候选发现”作为主要成果。
- 对少数高置信候选再投入 fuzzing。

---

## 9. 近期最建议做的事情

接下来最合适的执行顺序是：

1. 选定压缩库族作为唯一初始场景。
2. 收集 5 个带 patch 的压缩库 CVE。
3. 手工写出 5 个 `pattern.json`。
4. 为每个 pattern 在 2-3 个目标库中找 Top-10 候选。
5. 写一份 `docs/case-study-001.md`，记录第一个端到端案例。
6. 再决定是否自动化静态分析、embedding 和 LLM 模块。

这条路线的关键是先证明“迁移”这件事值得做。只要第一个案例成立，后面的系统化工作就会清晰很多。
