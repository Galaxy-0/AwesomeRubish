# RL stage 0: GPU environment

仅为工作刮水刀 vs .52、温泉峡谷、fixed60、180秒的环境准备目录。
本阶段不含训练器，不启动训练；原T1/S1入口和策略目录保持暂停/不改。

服务器私有目录为 `asuka0:~/splatoon3-native-rl-stage0/`，权限700。
`bootstrap-remote.sh`仅在用户明确授权的服务器账户内创建独立venv，安装固定
`torch==2.8.0+cu128`与`numpy==2.2.6`，并检查CUDA真实张量运算。
无需也不得在服务器运行游戏宿主。安装日志与CUDA检查输出保留在该私有目录。

```sh
scp rl/gpu/bootstrap-remote.sh asuka0:splatoon3-native-rl-stage0/
ssh asuka0 'cd ~/splatoon3-native-rl-stage0 && sh bootstrap-remote.sh > install.log 2>&1'
```

游戏参数/派生地图只能放私有data目录；不得提交到git。数值来源优先既有S1/D2–D4
只读证据，不把稀疏RomFS缺项当0，也不将S1的未签收原生保真度升级为已通过。
阶段0必须完成原生镜头测量、GPU/S1误差、完整观测吞吐20万环境帧/秒、关键机制单测、
180秒随机局和showcase回放，才可进入下一阶段。安装环境或跑通样例不代表过门。
