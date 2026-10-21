# D1 视觉打磨 — 2026-10-21

已完整按 `work/codex/d1-design.txt`（含末尾截图问题）完成一轮展示层打磨。只改模板、CSS / JS、相机、配色、文案、展示依赖白名单及说明；未改数据计算、对战代码或策略目录，未启动游戏。

## 页面

- 单文件：`/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native/showcase/index.html`
- 大小：**574,559 bytes（561.1 KiB，约0.55 MiB）**，小于15MB。
- SHA256：`2051576130e693d94410eeb12f588318c1f13af36b17ab85b2622069e4f70a7c`
- 本机预览：`http://127.0.0.1:8873/index.html`。仅本机预览，没有对外发布。
- CSS / JS / 派生数据内联；外部依赖为固定 three.js 0.160.0（cdnjs + SRI）和设计指定的 Google Fonts。字体加载失败会回退系统字体，CDN / WebGL 不可用时仍保留2D入口。
- `index.html`、派生数据和截图继续被Git忽略，供用户私下发布，不提交。

## 本轮变化

1. **战术板首屏**：移除宣传式大标题和英文眉标，直接显示“温泉峡谷 · 水刀立回”；地图切换在上、图层在左、点位与数值图例在右，手机单列。下方保留武器实测、AI对练、模拟校准和路线图，以分节和细线代替满屏阴影卡片。
2. **冷调视觉体系**：亮 / 系统暗 / 手动暗三处主题token；冷蓝中性色、单一页面强调色，A/B统一洋红 / 青绿。场景背景、地形、标记、轨迹、到达时间和图表随主题变化。字体为Barlow Condensed、IBM Plex Sans、IBM Plex Mono与中文系统回退。
3. **地图可读性**：正交相机根据现有派生轮廓自动适配，避免长条地图包围盒的空角导致缩小；默认45°斜视，窄屏重新适配方向。提供俯视 / 斜视 / 跟随与复位。地形为冷色高度阶、墙体较暗、侧面暗化和细轮廓线；战术底图半透明叠加，图例带实际范围刻度。
4. **标签避让**：默认只展开选中 / 悬停区域，其余为编号点；出生点与α/β角色标记参与同一套屏幕避让。默认温泉地图在桌面及400px手机下可见标签的包围矩形无重叠。
5. **回放**：地图内保留播放暂停、拖动时间轴、当前秒 / 帧数和0.5/1/2/4倍速。事件刻度分别表示ZR松键输入、记录中的倒下状态和潜墨切换；没有该事件的片段不补造，也不把倒下状态解释为击倒归属。人物保留队伍色胶囊体、朝向楔形和乌贼态压扁；reduced-motion下追镜不平滑过渡。
6. **图表**：占地 / 熟练度与新增的校准误差图均用主题token、真实纵轴、浅网格和端点强调；校准横轴按30/60/120/300帧的真实间隔布点，端点标签放到侧边并避让，原数值不变。

## 截图与自查

已用实际Chrome截图，逐张打开自查；图片只存放在ignored `work/showcase/`。

| 截图 | 尺寸 | 路径 |
|---|---|---|
| 桌面亮色 | 1728 × 906 | [d1-design-light.jpg](work/showcase/d1-design-light.jpg) |
| 桌面暗色 | 1728 × 906 | [d1-design-dark.jpg](work/showcase/d1-design-dark.jpg) |
| 手机亮色 | 400 × 880 | [d1-design-mobile.jpg](work/showcase/d1-design-mobile.jpg) |
| 手机暗色 | 400 × 880 | [d1-design-mobile-dark.jpg](work/showcase/d1-design-mobile-dark.jpg) |

另外目视检查了占地 / 熟练度图和校准误差图的亮暗显示。手机为Chrome视口模拟，未宣称真实手机硬件验证；临时视口覆盖已恢复。

## 验证

- `.venv/bin/python showcase/build.py` 重新生成完成；三图均复用已有离线分析。
- `.venv/bin/python showcase/check.py`：**6,439项通过**，包括资源 / 精确CDN与字体白名单、96份输入SHA、地图与伏击证据、T1聚合和四段回放原件对照。没有游戏纹理、截图、原始模型、音频或游戏资源引用。
- `node --check showcase/scene.js` 与生成HTML中各可执行内联脚本语法检查通过。
- 与打磨前快照逐值比较：**除展示源码SHA外，整个嵌入数据对象完全相同**。`build.py`、`derive_3d.py`、`derive_traces.py`的SHA均未改变。证据：`work/showcase/design-data-invariance.json`；原快照保留在 `work/showcase/design-before/`。
- Chrome交互检查：三图 × 四底图、三档相机、鼠标旋转 / 复位、双指缩放输入、2D / 3D、伏击选择、4倍速 / 帧推进、时间轴首尾跳转、跟随及深浅主题通过。400px和320px无页面横向溢出；默认桌面 / 手机标签矩形无重叠。记录：`work/showcase/design-browser-check.json`。
- 浏览器错误日志为空；经典版three.js保留一条上游弃用提示，非运行错误。

## 提交边界与停止点

提交仅包含 `showcase/template.html`、`showcase/scene.js`、`showcase/check.py`、`showcase/README.md` 和本报告。`GOAL.md`、计算脚本、对战代码和alpha / bravo策略均未改；其他作者原有工作区改动不纳入。生成页面、数据、截图及work证据不入库。

D1视觉打磨结束后停止，未推进D2或启动游戏。
