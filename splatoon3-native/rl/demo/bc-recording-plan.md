# 下一批示范：15局训练 + 4局留出（本轮没有录新的人类局）

建议范围为10–20局训练、3–5局留出。一个具体分配是：

|用途|easy|medium|hard|合计|
|---|---:|---:|---:|---:|
|训练|3|6|6|15|
|留出|0|2|2|4|

新留出局只用于最后评估，不再像005一样用于早停、选结构或选解码器。
按完整局分组；同一局、同一路线切出的片段不能分到训练和留出两边。
难度标签是本项目脚本参数档位，不代表已验证的人类段位强度。

每局仍为温泉峡谷、Stamper(player_0) vs .52、主武器only、180秒。交替左路/中路/右路开局，
保留完整Winners，不用游戏夹具替人摆位或直接瞄准。

希望增加的片段：

- 从静止/潜墨重新开始移动、出墨立即蓄斩、连续轻挥、满蓄后补轻挥。
- 看到敌人后横移跟枪、距离过远时先接近、失去视线后绕掩体重新看见。
- 残血或低墨后潜墨恢复，再重新进入交火；倒下后重新出发。
- 跨平台跳跃、碰到墙边后转向绕行。前半批优先坡道/跳跃可达路线；必须攀墙的片段单独标注，
  当前GPU尚无完整攀墙，墙面墨色也未闭合，不能把这些样本当成已经可迁移的地面动作。

不必故意追求高K/D。比继续重复一条碾压路线更有帮助的是覆盖不同的启动、脱离和恢复情形。
若后续要纠正模型会卡住的具体场景，应先保留模型失败回放，再让用户演示这些场景的正常操作。

## 单局命令模板

在项目根的独立终端执行。每次手动改档位和输出目录，目录必须全新；不要一次无人值守启动多局。
以下只是一条操作说明，本轮没有替用户执行：

```sh
demo_level=medium
demo_out=work/rl-demo/bc-next-train-001

.venv/bin/python -m rl.demo.capture \
  --fixture --allow-unqualified --source controller \
  --controller-profile work/rl-demo/recording-profile-r1/profile.json \
  --opponent 52 --opponent-level "$demo_level" --loadout primary_only \
  --host work/rl-demo/ink-recording-host-r1/dmhost-demo \
  --modules work/rl-demo/ink-recording-host-r1/modules \
  --render-predicate async --present-link 0 --max-catchup-frames 1 \
  --ink-every 30 --warm-from work/rl-demo/run76/warm-for-005 \
  --out "$demo_out"
```

切换难度仅把 `demo_level` 改为 `easy`、`medium` 或 `hard`。留出目录例如
`work/rl-demo/bc-next-holdout-001`，由用户指定完整局，后续训练命令不要列入这些目录。
此处不加 `--fixture-bc-checkpoint`、`--bc-ink-contract`，因此仍走普通人类手柄录制路径。

等终端出现 **DEMO_WARM_READY** 后操作，正常打到自动保存退出。X可以观察小地图；BC动作空间不包含X。
未确认的Minus/Plus/十字上继续忽略；提前停止可用Ctrl-C或输出目录里的STOP文件，
但提前结束不算完整训练局。记录自己的开局路线和异常现象，不修改原录像。

新录制仍保留原生数值/输入/图像在私有work目录。生成BC数据时使用新的版本输出目录，
过去的录像、失败样本、回放和预热原件均保留。
