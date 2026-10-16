# tools/

| 路径 | 内容 | 入库? |
|------|------|------|
| `sysroot/include/` | 最小 freestanding 头文件集（编译第三方库用） | ✅ |
| `toolchain-samples/` | 已确认的编译器配置 + 可复现样本 | ✅（.o 除外） |
| `bin/` | hactool、nstool 编译产物 | ❌ 需自行编译 |
| `keys/` | 清理后的 prod.keys | ❌ **绝不入库** |

## tools/bin/ —— 怎么重建

两个工具都需要自己编译（brew 没有）：

```bash
# hactool（处理 NSP/XCI/NCA/NSO）
git clone --depth 1 https://github.com/SciresM/hactool.git
cd hactool && git submodule update --init
brew install mbedtls@2   # 或用仓库自带的 mbedtls 子模块
cp config.mk.template config.mk && make

# nstool（处理分段 BKTR patch —— hactool 做不到）
git clone --depth 1 https://github.com/jakcron/nstool.git
cd nstool && git submodule update --init && make deps && make
```

## tools/keys/prod.keys.clean 是什么

原版 `~/.switch/prod.keys` 有 **33 个畸形键**（多带尾部 `00`，34 位 hex），
hactool 解析时会直接报错退出：

```text
Key (77605ad2ee6ef83c3f72e2599dac5e5600) must be 32 hex digits!
```

这些是 `mariko_master_kek_source_05..15` 和 `master_kek_source_06..15`，
**解密游戏内容用不到**（只用于主机密钥派生）。清理版丢掉了这 33 个键。

另一个坑：**hactool 即使传了 `-k` 也会先尝试加载 `~/.switch/prod.keys`**，
所以要么修原文件，要么确保传的是干净的。
