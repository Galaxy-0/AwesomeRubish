# D1 水刀 3D 攻略展示工具 — 2026-10-21

已按最新方向完成 D1 展示原型；不启动游戏进程，不推进 D2。产品方向和 D1→D4 路线已写入 `GOAL.md` 新阶段“D：水刀攻略”。

## 页面与打开方式

- 最终单文件：`/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native/showcase/index.html`
- 大小：**562,643 bytes（549.5 KiB / 约0.54 MiB）**，小于15MB。
- SHA256：`f36de1133b419d4d749267d4f99e87ec99d4fcd9e390a2af6a1511d4f1eeba78`
- 本机预览：`http://127.0.0.1:8873/index.html`（仅loopback预览服务；没有对外发布）。也可按 `showcase/README.md` 在空闲端口重开服务。
- 页面CSS / JS / 派生数据内联，唯一外部依赖为 cdnjs 固定 three.js 0.160.0，带SRI。首次加载3D需能访问该CDN；没有WebGL / CDN时保留2D入口。
- `index.html` 与 `showcase/data/derived.json` **均已加入.gitignore，不提交**；由用户私下发布。

## 内容概要

1. **三图 3D 地图**：温泉峡谷 / District00 / Yagara，由碰撞导航粗格和竖直碰撞面的墙体体素重建。支持拖动旋转、滚轮 / 双指缩放、平移、重置和地面点选；保留2D切换。按高度、静态通行/潜墨、到达差或几何视域着色。
2. **可开关图层**：墙体、出生点、出生到各区域的时间与最短路线、GeometricVision潜在视域、19/22单位射程、条件伏击候选。三图分别为1684/1913/2226个地面粗格、475/606/611个墙体体素、16/16/15个条件候选；候选可点击或从侧栏选择，展示对手假定接近侧和观察位。
3. **动态回放**：定义 `inklab.trace.v1`（`showcase/trace-format.md`）。已有原生T1 R1/R2温泉各一段，加对应S1各一段，共四段30秒、2,408条六帧抽样状态。支持地图内/下方时间轴、暂停播放、重来、0.5/1/2倍速、Alpha/Bravo跟随、朝向/形态/HP、路径与ZR松键输入标注。两段同帧区间不代表同输入重演。
4. **保留原有板块**：工作刮水刀35/70伤害、19/22约射程、21/26帧蓄力、快速炸弹、触手喷射的实测边界；T1 R0–R9胜负/平均占地/HUD倒下/每版战术一句/熟练度与源码身份；独立A5 high-ground对rush 61:9，与T1 R0 47:3分开；S1前后误差、Yagara方向一致和R1反例；L1–L5路线图及D1→D4方向。
5. 明示“非官方研究项目，数据来自本地实验”。无游戏纹理、截图、原始模型、音频或原始资源文件。

## 验证与边界

- `.venv/bin/python showcase/check.py` 通过，含唯一CDN/SRI、资源引用、96份输入SHA、网格/墙体量化、路线端点与时间、全部候选的遮挡/距离/潜在潜墨条件，以及回放位置/HP/原生采样帧对照原件。报告：`work/showcase/check.json`。
- 重复构建输出SHA一致；Python编译与内联JavaScript / scene.js语法检查通过。
- 实际Chrome验证：桌面、390px和320px无横向溢出；三图×四底图、2D/3D切换、伏击选择、鼠标旋转/滚轮、合成双指缩放、时间轴鼠标及键盘跳转、帧数推进/暂停、跟随、深浅色均通过；运行错误日志为空。固定经典版three.js有一条上游弃用提示，非渲染错误。未宣称真实手机硬件测试。
- 页面派生JSON已实际下载，逐值等于内联payload；验证记录：`work/showcase/download-check-3d.json`。
- 预览证据只在ignored work：`work/showcase/d1-3d-desktop.jpg`、`work/showcase/d1-3d-mobile.jpg`。旧2D页/模板保留在 `work/showcase/d1-2d-{index,template}.html`；没有删除原件。
- 3D为有损展示几何，最高层网格会丢失叠层/细壁/动态对象。人物穿透地形显示以保留低层轨迹，显示可见不代表通视；射程圈不作弹道命中判定。时间为AP0实测速度下静态路线下界，不含发射、加速、跳跃执行或战斗。
- 伏击仅满足指定静态场景，实际己墨、出墨命中和对手换路安全性未验证；**不是飞索挂点**。飞索钩索攀附/连招与 .52 / 精英枪 / 热泡对位留到D2/D3，不编造结论。S1保真度仍未签收。
- 浏览器实际验证走127.0.0.1 HTTP；file://自动打开受浏览器工具协议策略限制，未绕过。单文件无旁文件依赖另经静态审计确认。

## 源码与提交范围

生成：`showcase/build.py`；3D派生：`derive_3d.py`；回放转换：`derive_traces.py`；场景/播放器源码：`scene.js`；页面模板：`template.html`；核对：`check.py`；使用与格式说明：`README.md`、`trace-format.md`。

提交仅限上述源码、`.gitignore`、`GOAL.md`与本报告。生成index / 派生data、截图、work数据和所有游戏资源不入库；对战代码与alpha/bravo作者已有改动未修改或纳入提交。D1结束后停止，D2等用户指示。
