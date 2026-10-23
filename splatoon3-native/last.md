# D4 展示辨识修复（2026-10-23）

仅展示层，未启动游戏。D4开启自动使用中性灰底；绿/琥珀/红结果格、白色偷袭点、未知虚框、不可达不填色。地图左下常驻图例，上方直接显示敌位/朝向/最佳①/剩槽/偷袭或暴露。大号①②③图钉可点，默认温泉#634自动选中并显示路线；敌人具有人形、箭头和180°半圆。手机2D自动纵向排图，首屏可见结论、图钉和图例。空结果明确提示换朝向；关闭D4恢复原底图和控件。

图钉标签只从原有完整查询复制；模型/原始数据/研究结论不改。所有原有payload字段逐项一致，18个冻结top1/top2保持一致，11个已有完整敌态有排序标签；未完整计算只称候选。代表#634仍124f、69.90%、零钩偷袭；完整D4状态沿用下方既有记录，不因视觉修复改变。

`showcase/index.html`已重生，5,283,490 bytes，未提交/未发布。整页JS语法、原字段不变/标签原件/冻结点审计及24,591项页面检查通过。三图默认点、无确认点提示、图层开关恢复、2D/3D俯视、亮暗及390px通过；390px内容宽390，本页无控制台错误（浏览器扩展日志另保留）。临时视口恢复，自建页关闭。未动policies、存档、宿主或对战代码；T1/S1暂停。

最终截图（均在work下，不提交）：

- `work/showcase/d4-visual-final-light-3d-top.jpg`
- `work/showcase/d4-visual-final-dark-3d-top.jpg`
- `work/showcase/d4-visual-final-light-2d.jpg`
- `work/showcase/d4-visual-final-dark-2d.jpg`
- `work/showcase/d4-visual-final-light-mobile-3d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-3d.jpg`
- `work/showcase/d4-visual-final-light-mobile-2d.jpg`
- `work/showcase/d4-visual-final-dark-mobile-2d.jpg`

审计：`work/showcase/d4-visual-data-audit-v7-20261023.json`、`d4-visual-check-v7-20261023.json`、`d4-visual-browser-final-20261023.json`，绑定最终页SHA。详情见showcase/README.md；源码提交推送后停止。

---

# D4c 限定交付 / 停止（2026-10-23）

**新216全部闭合；完整D4未闭合。** 最初被打断两刀result/steps/双方host.log原件与SHA已保全。优先查横5球左右/纵7球上下裁剪，最终物理数组身份、核心共享及接触分半仍未闭合；未把领域知识误写为已否定。四刀机制预算用完后按授权切换接触确定不相交、整波墨刃场地清晰的有限路线。

三图各3敌态×top1/top2/对照×8：216有效（217尝试，1发动前进程失败，原例按规则只重试一次成功），0对战未决，旧12/机制/资格0复用。优选144/144先杀，对照0/72；各敌态8/8、8/8、0/8。原生KO124–128f，剩槽69.074–69.815%；队列墙钟6时28分47秒、峰值3房。原驱动退出0、stop_reason=null；当前无dmhost，143项原件/保护宿主/冻结输入/模块SHA一致。

**边界**：所有27点为零钩满蓄接轻斩40f，不证明飞索切入/连钩。原生.52固定脚本直线枪口跟瞄未补下坠，不是理想防守方/玩家胜率。实际姿态可判136次，16次模型原生不一致、80次未知均保留。接触规则、极限连钩、完整D4及全局最优仍未闭合；不恢复T1/S1，不改策略/原存档/正式默认宿主，不启动下一阶段。

[交付报告](notes/d4c-delivery-20261023.md) · [216数值/逐例原件SHA](notes/d4-blade-only-native-20261022.json) · [两半机制](notes/d4-halves-20261022.md)。原件 `work/d4/restart-v4/chain-preservation-v1.json`；正式批次 `work/d4/restart-v4/blade-native216-v1/batch.json`；最终完整性 `work/d4/restart-v4/integrity-20261023-final.json`。

生成页 `showcase/index.html`，5,259,960 bytes（<10MB）；11完整限定查询/14,771起点行，并非63,328组合全量完成。支持敌位/四向/四手速正反查、3D路线/暴露/槽曲线/步骤回放、旧均匀先验附录和新原生实数表，未知不涂失败。Python/浏览器72单刀/288终结/45查询/3预算恢复通过；最终24,526项格值/trace/来源/资源审计通过。点634复核124f/69.90%/零钩偷袭，控制台无错误，390px内容宽390无横向溢出。页面未发布。

最终截图（本地自绘页面，均不提交）：

- `work/showcase/d4c-final-map-light-20261023.jpg`
- `work/showcase/d4c-final-map-dark-20261023.jpg`
- `work/showcase/d4c-final-native-light-v3-20261023.jpg`
- `work/showcase/d4c-final-native-dark-v3-20261023.jpg`
- `work/showcase/d4c-final-native-mobile-20261023.jpg`

审计 `work/showcase/d4c-final-check-v2-20261023.json`，UI摘要 `work/showcase/d4c-final-browser-20261023.json`，二者绑定最终页SHA。生成页/派生网格/截图/游戏资源不提交；源码和文档分段推送，本轮在最终提交推送后停止。
