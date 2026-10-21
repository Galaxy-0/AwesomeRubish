# inklab.trace.v1

用于 D1 3D 动态回放的展示交换格式。只包含实验产生的位置、朝向、形态、HP 和输入事件，不含游戏画面 / 模型。当前由 `derive_traces.py` 从已有记录转换，内联到生成的 `index.html`；派生 JSON 不提交。

```js
{
  schema: 'inklab.trace.v1',
  id: 'native-r1',
  label: '原生 T1 · R1 温泉峡谷',
  source_kind: 'native_observation', // 或 simulated_state
  map: 'Yunohana',                 // District00 / Yagara
  fps: 60, start_frame: 3182, end_frame: 4982, stride: 6,
  columns: ['frame','sample_frame','x','y','z','heading','form','hp','alive','ink'],
  players: [{
    id: 'alpha', role: 'player_1',
    states: [ /* 每项是按 columns 顺序的十列数组 */ ],
    events: [
      {frame: 3200, type: 'ZR_down', evidence: 'recorded_input_edge'},
      {frame: 3224, type: 'ZR_release', hold_frames: 24,
       evidence: 'recorded_input_edge'}
    ]
  }],
  selection: '展示片段的选择规则',
  position_semantics: '数据来源与未知值边界'
}
```

上例仅说明结构，事件帧为示例，不构成实际记录。

- 帧号是原记录的受控帧；一秒 60 帧。`frame` 是策略观测 / 模拟记录帧，`sample_frame` 是原生自身采样帧 / 模型状态帧。两者不得混为真实状态产生时刻。
- XYZ 为游戏世界坐标单位，Y 向上；坐标量化 0.01 单位，朝向为弧度、保留四位小数，0 朝 +Z、正角朝 +X。HP / 墨量为 0–1，保留三位小数；未知为 null。
- `form` 为 human / squid / submerged / null。原生取自身形态/潜墨反馈；模拟取录制的模型 squid 与接触条件，不当作原生真值。
- `alive` 保留 bool / null，不能由 HP 填补。缺位置行省略，不假造原地状态。播放器在相邻 6 帧采样间插值位置、按最短角插值朝向；样本间隔 >18 帧不跨越插值、不外推隐藏状态。HP / 形态保持最近过去样本。
- 当前事件支持 ZR_down / ZR_release / R_down / RS_down / B_down。输入帧是该记录中的动作边沿；ZR 松键及持有时长不证明真实出刀、满蓄、伤害或最后一击。光圈只作输入事件示意。
- 原生回放分别使用两位玩家自己的白名单观测，不从敌人不可见字段恢复位置；这是展示阶段的双端合成，未改变策略观测或沙箱。
- S1 使用已保存的 route-check trace，原报告轨迹 digest 与 ranks-final 一致；不重新运行策略，不把模拟状态与原生观测混成同一条真值轨迹。
- 当前四段均为 30 秒：R1 / R2 温泉峡谷各一段原生与同帧区间的 S1。原生以“记录中仍存活双方最近距离”附近选展示窗口，S1保留相同帧区间，未作路径拉伸 / 空间对齐。属于展示选段，不是新增排名样本或受控消融；策略会因模拟状态不同而选择不同动作，不能把两段当成同输入重演。
- 人物是自绘胶囊 / 方向锥体，始终穿透地形显示，以保留最高层简化几何下的低层真实轨迹；显示可见不代表几何通视。射程圈为水平距离参考，不模拟弹道。

未来 D2/D3 可以增加实际测得的动作阶段、挂钩事件和命中事件，但必须使用新的证据字段，不能把本格式现有输入事件重命名成机制真值。
