# 公开熟练度参考策略

只做可见目标的常速度预判、持续跟踪和满蓄释放，不作地图战术。
`step_frames=1`，使用公共 `stamper` 控制器；剩余蓄力时间与观测年龄
都会进入提前量。它是基准的可读参考，不代表最优手法。

从项目目录运行 `tests/benchmark_a6.py --policy arena/proficiency-reference`
并指定 `--scenario stationary|lateral|approach --out PATH`。
完整说明见 [技能库与基准](../lib_a6/README.md)。
