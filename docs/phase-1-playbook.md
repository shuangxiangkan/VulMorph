# 第一阶段操作手册

第一阶段的目标是证明：**跨库漏洞根因迁移是否值得自动化**。

不要一开始就做完整系统。先完成一个高质量的手工案例。

## 第 1 步：拉取候选库

推荐第一个库族选择压缩库：

- 用 zlib 作为种子库。
- 用 lz4 或 zstd 作为第一个目标库。

建议本地目录结构：

```text
data/targets/
  zlib/
  lz4/
  zstd/
```

## 第 2 步：寻找 zlib 的安全修复

进入 zlib 仓库后，先用安全相关关键词检查历史：

```sh
git log --oneline --all --grep='CVE'
git log --oneline --all --grep='overflow'
git log --oneline --all --grep='bounds'
git log --oneline --all --grep='invalid'
git log --oneline --all --grep='crash'
git log --oneline --all --grep='inflate'
```

同时交叉检查这些外部来源：

- NVD
- OSV
- GitHub Security Advisories
- zlib release notes
- Linux 发行版安全追踪页面

不要只依赖 `git log --grep='CVE'`。很多安全修复 commit 不会直接写 CVE 编号，可能只写 `overflow`、`bounds`、`invalid memory access` 或 `crash`。

## 第 3 步：选择一个种子漏洞

优先选择满足这些条件的修复：

- patch 较小。
- 只影响一两个核心函数。
- 缺失检查很明确。
- 能清楚拆成 source、transform、sink。
- CWE 明确，例如 CWE-190、CWE-787、CWE-125。

第一个案例不要选大重构，也不要选跨很多文件的修复。第一阶段要验证的是思路，不是挑战最复杂的漏洞。

## 第 4 步：填写种子记录

复制模板：

```sh
cp data/seeds/seed-template.json data/seeds/zlib-cve-xxxx-yyyy.json
```

然后填写：

- 修复 commit。
- 受影响文件和函数。
- patch 摘要。
- 根因假设。
- source、transform、sink。
- patch 新增的约束。

填写时重点不是“这个 CVE 名字是什么”，而是要把漏洞修复背后的数据流和缺失检查讲清楚。

## 第 5 步：写第一个根因模式

复制模板：

```sh
cp data/patterns/pattern-template.json data/patterns/int-overflow-alloc-001.json
```

这个模式应该比 zlib 更通用。除非只是作为搜索提示，否则不要把 `inflate` 这类具体函数名写进根因定义里。

一个好的模式应该能表达：

```text
外部可控长度 / 文件字段
  -> 整数运算、类型转换、位移或长度换算
  -> 缺少范围检查或溢出检查
  -> 内存分配、拷贝、数组索引或指针运算
```

## 第 6 步：搜索目标库

先手工搜索 lz4 或 zstd。

重点查这些位置：

- 分配 API：`malloc`、`calloc`、`realloc`
- 拷贝 API：`memcpy`、`memmove`
- 长度计算：`+`、`*`、`<<`
- 整数类型转换
- 长度字段
- 解压入口函数

对每个候选位置都记录两类证据：

- 正向证据：为什么它像这个根因模式。
- 反向证据：为什么它可能其实是安全的。

反向证据很重要。比如已经有上界检查、使用了安全的 checked arithmetic helper、目标库设计上保证输入范围等。

## 第 7 步：写案例研究

复制模板：

```sh
cp docs/case-study-template.md docs/case-study-001.md
```

一个合格的案例研究应该回答：

- 原始漏洞的根因是什么？
- 抽象后的库无关模式是什么？
- 目标库里哪些函数看起来相似？
- 哪些候选被排除了，为什么？
- 这个模式是否值得后续自动化？

第一阶段的成功标准不是一定要发现新 CVE，而是要判断这条迁移路线是否真的有信号。如果一个手工案例都讲不通，就应该先调整研究问题；如果讲得通，再去做 Joern、LLM 和 embedding 自动化。
