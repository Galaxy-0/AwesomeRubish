# work/ —— 临时工作区（gitignore）

内容都可重建，不需保留/备份。

| 路径 | 内容 | 重建方式 |
|------|------|---------|
| `text/text.bin` | `.text` 段裸字节（82.4 MB）| 见下方 |
| `text/text.elf` | 包装成 ELF 供反汇编 | `llvm-objcopy -I binary -O elf64-littleaarch64` |
| `match/` | 早期匹配实验 | — |
| `probe/` | 早期编译探针 | — |

## 重建 text.bin

```python
import struct
d = open('binaries/11.3.0/main.uncompressed','rb').read()
fo, dst, sz, tot = struct.unpack_from('<IIII', d, 0x10)   # 第一个段 = .text
open('work/text/text.bin','wb').write(d[fo:fo+sz])
```

## 重建 text.elf

```bash
/opt/homebrew/opt/llvm/bin/llvm-objcopy -I binary -O elf64-littleaarch64 -B aarch64 \
  --rename-section .data=.text,alloc,load,readonly,code \
  work/text/text.bin work/text/text.elf
```
