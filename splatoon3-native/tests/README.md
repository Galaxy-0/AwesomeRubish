# 回归测试

M1 的一键入口：

```sh
uv pip install --python .venv/bin/python -r tests/requirements.txt
bash tests/run_all.sh
```

需要当前 Apple Silicon / Metal 4 环境、`upstream/` 补丁以及已提取并改写的 `work/data/v720896/`、`work/build/patched_v720896/`、MSL 缓存和字体。测试不下载游戏数据，也不连接任天堂服务。

入口先构建宿主，执行无游戏素材的条件渲染 / 命令复制 GPU 检查和 NVN 检查，再启动真实游戏 75 秒。运行使用独立的新存档目录；每次的日志、600/1200/2400 帧截图和 `result.json` 保存在 `work/tests/m1-<timestamp>/`。

M1 同时要求：宿主持续运行到测试时限、最终帧数至少 2400、末尾采样窗口内帧数增长、无 CRASH/FATAL/看门狗及 GPU 执行错误、SIGTERM 优雅退出完成，以及三个 1920×1080 截图平均 RGB 方差 ≥25、非黑像素比例 ≥5%。任何一项失败都会返回非零。方差检查只证明输出不是全黑，不代表图形已经完全正确。

可用 `bash tests/run_all.sh --seconds 120` 延长检查。初次编译 MSL 的机器可能需要更长时间。当前 M2–M6 尚未实现；此入口只检验 M1，不能当作全部目标已完成的证明。
