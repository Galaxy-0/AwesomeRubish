# 2026-10-16 · 批量验证：29 个 zlib 函数的匹配率分布

## 结论

**用正确配置（含 `-fomit-frame-pointer`），zlib 29 个函数的平均匹配率 95.2%。**

| 区间 | 函数数 | 占比 |
|------|-------|------|
| **100%（零真差异）** | 7 | 24% |
| 99–100% | 1 | 3% |
| 90–99% | 18 | 62% |
| < 90% | 3 | 10% |

**这比之前的 6 函数 100% 更真实**——大样本暴露了分布，而不是只看到精选样本。
但它仍然支撑"匹配路线可行"的结论（详见下文").

## 关键发现：`-fomit-frame-pointer` 是必需的

这是本轮最重要的技术发现。

### 现象

配置从 `-O3 -mcpu=cortex-a57` 改成加 `-fomit-frame-pointer` 后：

| 指标 | 改之前 | 改之后 |
|------|-------|-------|
| 平均匹配率 | 82.8% | **95.2%** |
| <90% 的函数 | 11 | 3 |
| `deflate` | 6.6% | 68.0% |

### 证据

`deflate` 函数入口对比：

```text
目标 (0x1d55a0):
    stp  x30, x25, [sp, #-0x40]!    ← 只保存 x30，没有 x29
    stp  x24, x23, [sp, #0x10]
    stp  x22, x21, [sp, #0x20]
    stp  x20, x19, [sp, #0x30]

不带 -fomit-frame-pointer:
    stp  x29, x30, [sp, #-0x50]!    ← 保存了 x29
    stp  x20, x19, [sp, #0x40]
    ...
    mov  x29, sp                     ← 建立了帧指针
```

加了 `-fomit-frame-pointer` 后，`stp x30, x25, [sp, #-0x40]!` 与目标**完全一致**。

### 一个重要细节：全局 vs 库代码

这是个容易踩的坑。全 `.text` 的统计：

| 区域 | `mov x29,sp` 数量 | 比例 |
|------|------------------|------|
| **全 .text** | 97,419 | 99% |
| **zlib 区域**（0x1d4000-0x1e2000，14,336 条指令） | **0** | **0%** |

**游戏自身的代码有帧指针（99%），但 zlib 没有。**

意味着：Nintendo 编译自己的代码时用了帧指针，编译第三方库（zlib）时关掉了。
**所以 `-fomit-frame-pointer` 只对库代码正确**，不能推广到游戏自身代码。

（这也解释了为什么早期用 `subsdk0` 观察时没发现——那是 Flexlion 的模块。）

## 剩余差异的性质

对匹配率 <95% 的函数，分析差异的性质：

| 函数 | 差异数 | 其中"两边都出现"的指令 |
|------|-------|---------------------|
| `send_tree` | 20 | **20（100%）** |
| `deflate_stored` | 20 | 15 |
| `deflate_rle` | 20 | 13 |
| `deflate` | 20 | 11 |
| `deflateInit2_` | 19 | 10 |
| `fill_window` | 15 | 9 |
| `deflate_slow` | 20 | 6 |
| `deflate_huff` | 14 | 4 |
| `inflateReset2` | 5 | 3 |
| `deflateResetKeep` | 4 | **0** |
| `flush_pending` | 2 | **0** |
| `inflateInit_` | 5 | **0** |
| `inflateInit2_` | 6 | **0** |

**"两边都出现"= 指令完全相同，只是位置不同（调度差异）。**

`send_tree` 是最干净的例证——20 处差异的指令 100% 在两边都出现：

```text
目标:  stir x23 / stp x22,x21 / stp x20,x19 / ldrh ...
我们:  str x23 / ldrh ... / stp x20,x19 / ... / stp x22,x21
```

编译器把**寄存器保存指令分散插入到函数体不同位置**。语义完全等价。

### 两类差异

1. **调度差异**（多数）：指令集合相同，位置不同 → 可用后处理修正，
   或接受为"语义等价"
2. **真代码差异**（少数）：如 `deflate` 有 11/20 条对不上——
   目标在 prologue 后有 `bl` 调用，我们内联了。这可能是：
   - Nintendo 改了 zlib 的编译选项（比如 `-fno-inline` 的某个变体）
   - 或用了稍不同的 zlib 版本/补丁

## 对项目的意义

### 好消息

1. **平均 95.2%，最好的区间是 100%**——核心算法函数（`adler32`、`crc32`、
   `longest_match`、`build_tree`）都完美匹配
2. **剩余差异以调度为主**——不是"编译器生成了不同代码"，是"同样的代码换了顺序"
3. **`-fomit-frame-pointer` 的发现是决定性的**：一个 flag 让平均分从 82.8% → 95.2%

### 需要正视的

1. **不能只看精选样本**。之前报的"6/6 100%"是挑选的结果——那 6 个恰好都是
   简单函数。大样本才是真相。
2. **函数越大、越复杂，匹配越难**。`deflate`（900 条）只有 68%，
   而 `crc32_z`（212 条）100%。这个趋势符合直觉（调度空间更大）。
3. **`deflate` 的 68% 需要单独调查**——它可能是 Nintendo 的自定义编译选项，
   也可能是我们的样本有偏差。

## 工具改进

本轮改了 `scripts/batch_verify.py`：

- **多窗口探测**：不再只用函数开头做指纹（prologue 差异会破坏开头），
  而是用多个窗口（开头/中部/靠尾）分别查找
- **局部对齐微调**：命中位置 ±6 条指令内搜索最佳对齐（避免差一条指令
  导致整体错位）

这个改进本身很重要：**第一版只找到 6 个函数，改进后找到 29 个**。

## 下一步

1. **调查 `deflate` 的 68%**——这是理解"真代码差异"性质的最佳样本
2. **测更多库**（OpenSSL 需要更完整的 sysroot，值得投入）
3. **考虑接受"调度差异"为正常**——匹配反编译项目里，非 100% 是常态，
   关键是差异可解释。objdiff 用百分比而非二值，正是这个原因。
4. **转向游戏自身代码**——这才是真正的目标。库代码只是校准工具链。

## 附：完整结果

```text
函数                      长度    真差异    匹配率
adler32_z                240       0   100.0%
crc32_z                  212       0   100.0%
deflateBound              88       0   100.0%
longest_match            150       0   100.0%
inflateEnd                36       0   100.0%
_tr_flush_bits            36       0   100.0%
_tr_align                 92       0   100.0%
build_tree               552       1    99.8%
deflateEnd                76       1    98.7%
init_block                68       1    98.5%
inflate_table            428       7    98.4%
_tr_flush_block          580      11    98.1%
_tr_stored_block          92       2    97.8%
compress_block           252       7    97.2%
inflate_fast             954      37    96.1%
deflate_fast             372      16    95.7%
inflateReset2             96       5    94.8%
deflateResetKeep          72       4    94.4%
flush_pending             36       2    94.4%
send_tree                331      20    94.0%
fill_window              248      15    94.0%
deflate_slow             428      26    93.9%
deflate_huff             200      14    93.0%
deflate_stored           416      32    92.3%
inflateInit_              64       5    92.2%
inflateInit2_             72       6    91.7%
deflateInit2_            184      19    89.7%
deflate_rle              320      42    86.9%
deflate                  900     288    68.0%
```

配置：`clang 17.0.6 --target=aarch64-none-elf -O3 -mcpu=cortex-a57 -fomit-frame-pointer`

---

## 追加实验：`deflate` 的 68% 是什么原因？（否证）

`deflate` 是最差的样本（900 条，68%）。目标是这样的：

```text
目标 (0x1d55a0):
    stp  x30, x25, [sp, #-0x40]!
    stp  x24, x23, [sp, #0x10]
    stp  x22, x21, [sp, #0x20]
    stp  x20, x19, [sp, #0x30]
    mov  w21, w1
    mov  x20, x0
    bl   0x1164940            ← 我们这里没有这个调用
```

`0x1164940` 展开是 `adrp` + `add` + `b`（跳到日志函数），形如 assert/错误上报。

### 假设 1：Nintendo 定义了 `ZLIB_DEBUG`（assert 生效）→ **否证**

zlib 的 `Assert` 宏由 `ZLIB_DEBUG` 控制：

```c
#ifdef ZLIB_DEBUG
#  define Assert(cond,msg) {if(!(cond)) z_error(msg);}
#else
#  define Assert(cond,msg)          // 空
#endif
```

用 `-DZLIB_DEBUG` 重编译全部 zlib 后重跑：

| 配置 | 平均匹配率 | 100% 函数 |
|------|-----------|----------|
| `-O3 -mcpu=cortex-a57 -fomit-frame-pointer` | **95.2%** | 7/29 |
| 加上 `-DZLIB_DEBUG` | **73.9%** | 3/15 |

**显著变差。** 假设否证——Nintendo **没有**全局开启 zlib 的 debug assert。

（这也合理：开 assert 会让所有函数膨胀，不会只有 `deflate` 一个受影响。）

### 结论

`deflate` 的差异**原因未定**。可能是：
- Nintendo 对该文件用了额外的编译选项
- 或 zlib 源码有 Nintendo 的局部修改（未公开）
- 或我们的样本在函数边界判定上有偏差

**但这不影响大局**：29 个函数里只有 1 个落在 68%，其余 28 个都在 86.9% 以上，
中位数约 95%。`deflate` 是长尾个例，值得记下来但不必现在解决。

## 本轮的方法论收获

1. **单样本会骗人**。之前"6/6 = 100%"是因为挑的 6 个恰好都简单。
   扩到 29 个才看到真实分布（24% 完美，10% 低于 90%）。

2. **否证和证实一样重要**。`-fomit-frame-pointer` 是被证实的关键 flag
   （82.8% → 95.2%）；`-DZLIB_DEBUG` 是被否证的假设（95.2% → 73.9%）。
   两个方向都跑，才知道哪个是真的。

3. **差异要分类，不能只数个数**。"20 处差异"里可能 20 处都是指令换位
   （`send_tree`），也可能有真代码差异（`deflate`）。分清楚才知道下一步该做什么。
