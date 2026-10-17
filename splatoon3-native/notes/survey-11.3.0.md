# 粗查 | Survey: Splatoon 3 (0100C2500FC20000)

- 显示版本 | display version: 11.3.0
- 基础版 | base: `Splatoon 3 [0100C2500FC20000][v0].xci` (4.75 GB)
- 更新 | update: `[UPD][11.3.0][0100C2500FC20800][US][22.5.0].nsp` (v720896, 6.77 GB)（粗查用的这一个 | used for this survey）

## 代码模块 | Code modules

| 模块 module | 构建号 build ID | text / ro / data (MB) |
|---|---|---|
| main | `28c4287aee36f7499da60f3e68b54c70` | 78.6 / 12.2 / 5.2 |
| rtld | `263c3426d28af8d8cce29a9d2da8ff0f` | 0.0 / 0.0 / 0.0 |
| sdk | `574284b40c06cf1821a44857939083be` | 6.4 / 4.8 / 0.3 |

- main.npdm 程序号 | program ID: `0100C2500FC20000`
- SDK: 20_5_22（马力欧 | Mario: 16_2_0 / 16_2_12；D2R ≈ 12）
- SDK 组件 | SDK components: NintendoSDK_Google_APIs_For_NPLN-1_38_1, NintendoSDK_NPLN-1_38_1, NintendoSDK_NVN-20_5_22, NintendoSDK_OpenSSL_For_NPLN-0_0_0, NintendoSDK_gRPC_For_NPLN-0_0_0, NintendoSDK_libcurl-20_5_22, NintendoSDK_libz-20_5_22, NintendoSdk_BuildTarget-64, NintendoSdk_nnSdk-20_5_22, NintendoWare_Font-13_3_6, NintendoWare_G3d2-20_5_22, NintendoWare_Ui2d-13_3_6, NintendoWare_Vfx2-20_5_22, Pia-6_32_3, PiaClone-6_32_3, PiaCommon-6_32_3, PiaLan-6_32_3, PiaLocal-6_32_3, PiaNplnd-6_32_3, PiaSession-6_32_3, PiaSync-6_32_3, PiaTransport-6_32_3, Pia_ZStandard-6_32_3, QREncoder-20_1_0
- 引擎与接口标记 | engine and API markers: NVN (main, sdk); Nintendo sead (main); Nintendo agl (main); Nintendo gsys (main); Havok (main)

## RomFS: 22857 个文件 | files, 9.37 GB

| 顶层 top level | 文件 files | GB |
|---|---|---|
| Pack/Actor | 8060 | 0.04 |
| UI/Icon | 7694 | 0.43 |
| Model | 3287 | 5.20 |
| Sound/Resource | 1594 | 2.55 |
| Layout | 593 | 0.09 |
| Bake/Scene | 325 | 0.87 |
| Locker | 215 | 0.00 |
| Pack/Scene | 145 | 0.03 |
| Gyml | 141 | 0.00 |
| AnimationEvent/AsNode | 138 | 0.00 |
| Phive/ControllerSetParam | 93 | 0.00 |
| Banc/BinLayer | 91 | 0.00 |
| Component/Physics | 77 | 0.00 |
| RSDB | 74 | 0.00 |
| Phive/Shape | 58 | 0.00 |
| Phive/ShapeParam | 58 | 0.00 |
| CameraAnimation | 33 | 0.00 |
| Phive/NavMesh | 16 | 0.00 |
| Mals | 14 | 0.01 |
| NavTable | 12 | 0.00 |

| 文件头 header magic | 文件 files | GB |
|---|---|---|
| zstd | 21550 | 7.07 |
| BWAV | 714 | 2.29 |
| BNSH | 1 | 0.00 |

扩展名 | extensions: `.zs` 21550, `.bwav` 714, `.bgyml` 437, `.baev` 139, `.bin` 5, `.ainb` 5, `.bfevfl` 2, `.ntx` 2, `.bnsh` 1, `.xtx` 1, `.txt` 1

## 改写点统计 | Rewrite-site census (insn_census.py)

```
/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native/work/0100C2500FC20000_survey/extract/ExeFS/main: 20594032 instructions decoded (48 undecodable words)
  x18 use                48478
  mrs tpidr_el0          804
  svc                    165
  svc numbers: #0x26 x165
/Users/galaxy/Project/GalaxyAI/AwesomeRubish/splatoon3-native/work/0100C2500FC20000_survey/extract/ExeFS/sdk: 1674686 instructions decoded (2 undecodable words)
  x18 use                15575
  mrs tpidrro_el0        124
  svc                    58
  mrs cntpct_el0         43
  msr tpidr_el0          3
  mrs tpidr_el0          2
  svc numbers: #1 x1, #2 x1, #3 x1, #4 x1, #5 x1, #6 x1, #7 x1, #8 x1, #9 x1, #0xa x1, #0xb x1, #0xc x1, #0xd x1, #0xe x1, #0xf x1, #0x10 x1, #0x11 x1, #0x12 x1, #0x13 x1, #0x14 x1, #0x15 x1, #0x16 x1, #0x17 x1, #0x18 x1, #0x19 x1, #0x1a x1, #0x1b x1, #0x1c x1, #0x1d x1, #0x1f x1, #0x21 x1, #0x22 x1, #0x23 x1, #0x25 x1, #0x26 x1, #0x27 x1, #0x28 x1, #0x29 x1, #0x2a x1, #0x2c x1, #0x2d x1, #0x2f x1, #0x32 x1, #0x33 x1, #0x34 x1, #0x35 x1, #0x36 x1, #0x40 x1, #0x41 x1, #0x43 x1, #0x44 x1, #0x45 x1, #0x4b x1, #0x50 x1, #0x51 x1, #0x52 x1, #0x70 x1, #0x72 x1
```

## 导入与宿主钩子 | Imports vs host hooks (nso_syms.py)

```
HLE hooks in host: 503 | present in new game sdk exports: 476
main imports: old game 0, new game 1210, shared 0, new-only 1210

new game main imports by area (total / not imported by old game):
  C / libc                 235 /  235
  nn::audio                185 /  185
  nn::os                   119 /  119
  other C++                 93 /   93
  nn::hid                   56 /   56
  nn::util                  49 /   49
  nn::async                 44 /   44
  nn::fs                    34 /   34
  nn::prepo                 33 /   33
  nn::socket                30 /   30
  nn::ldn                   26 /   26
  nn::image                 25 /   25
  nn::fontll                24 /   24
  nn::account               24 /   24
  nn::crypto                22 /   22
  nn::bcat                  22 /   22
  nn::oe                    22 /   22
  nn::nfp                   20 /   20
  nn::time                  19 /   19
  nn::friends               17 /   17
  nn::err                   14 /   14
  nn::nifm                   9 /    9
  nn::mem                    9 /    9
  nn::ssl                    9 /    9
  nn::codec                  8 /    8
  nn::swkbd                  8 /    8
  nn::diag                   7 /    7
  nn::ngc                    7 /    7
  nn::web                    6 /    6
  nn::album                  6 /    6
  nn::vi                     5 /    5
  nn::pia                    4 /    4
  nn::pctl                   3 /    3
  nn::lmem                   3 /    3
  nn::pl                     3 /    3
  nn::aoc                    2 /    2
  nvn                        2 /    2
  nn::nsd                    2 /    2
  nn::ro                     1 /    1
  nn::detail                 1 /    1

examples of new-only imports per area:
  C / libc: _Unwind_Resume, __cxa_allocate_exception, __cxa_begin_catch, __cxa_demangle
  nn::audio: _ZN2nn5audio11RemoveDelayEPNS0_19AudioRendererConfigEPNS0_9DelayTypeEPNS0_10SubMixTypeE, _ZN2nn5audio11RemoveDelayEPNS0_19AudioRendererConfigEPNS0_9DelayTypeEPNS0_12FinalMixTypeE, _ZN2nn5audio12GetDelayTimeEPKNS0_9DelayTypeE, _ZN2nn5audio12IsAuxEnabledEPKNS0_7AuxTypeE
  nn::os: _ZN2nn2os10ClearEventEPNS0_9EventTypeE, _ZN2nn2os10WaitThreadEPNS0_10ThreadTypeE, _ZN2nn2os11FreeTlsSlotENS0_7TlsSlotE, _ZN2nn2os11GetThreadIdEPKNS0_10ThreadTypeE
  other C++: _ZN2nv18InitializeGraphicsEPvm, _ZN2nv20SetGraphicsAllocatorEPFPvmmS0_EPFvS0_S0_EPFS0_S0_mS0_ES0_, _ZN2nv28SetGraphicsDevtoolsAllocatorEPFPvmmS0_EPFvS0_S0_EPFS0_S0_mS0_ES0_, _ZNKSt3__119__shared_weak_count13__get_deleterERKSt9type_info
  nn::hid: _ZN2nn3hid13GetNpadStatesEPNS0_16NpadFullKeyStateEiRKj, _ZN2nn3hid13GetNpadStatesEPNS0_16NpadJoyDualStateEiRKj, _ZN2nn3hid13GetNpadStatesEPNS0_16NpadJoyLeftStateEiRKj, _ZN2nn3hid13GetNpadStatesEPNS0_17NpadHandheldStateEiRKj
  nn::util: _ZN2nn4util11ReferSymbolEPKv, _ZN2nn4util12CompressZlibEPmPvmPKvmS2_m, _ZN2nn4util12GenerateUuidEv, _ZN2nn4util14DecompressZlibEPvmPKvmS1_m
  nn::async: _ZN2nn5async10Executable7ExecuteERKNS0_17CancellationTokenE, _ZN2nn5async10ExecutableC2Ev, _ZN2nn5async10ExecutableD2Ev, _ZN2nn5async11IsAwaitableEv
  nn::fs: _ZN2nn2fs10CreateFileEPKcl, _ZN2nn2fs10DeleteFileEPKc, _ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE, _ZN2nn2fs11SetFileSizeENS0_10FileHandleEl
  nn::prepo: _ZN2nn5prepo10PlayReport10SetEventIdEPKc, _ZN2nn5prepo10PlayReport20SetOptInCheckEnabledEb, _ZN2nn5prepo10PlayReport3AddEPKcPKvm, _ZN2nn5prepo10PlayReport3AddEPKcRKNS0_10Any64BitIdE
  nn::socket: _ZN2nn6socket10InitializeEPvmmi, _ZN2nn6socket10SetSockOptEiNS0_5LevelENS0_6OptionEPKvj, _ZN2nn6socket11EventFdReadEiPm, _ZN2nn6socket11GAIStrErrorENS0_7AiErrnoE
  nn::ldn: _ZN2nn3ldn10DisconnectEv, _ZN2nn3ldn10InitializeEv, _ZN2nn3ldn11OpenStationEv, _ZN2nn3ldn11ScanPrivateEPNS0_11NetworkInfoEPiiRKNS0_10ScanFilterEi
  nn::image: _ZN2nn5image10PngEncoder10InitializeEPFPvmS2_ES2_PFvS2_S2_ES2_, _ZN2nn5image10PngEncoder12SetPixelDataEPKvmNS0_11PixelFormatENS0_9DimensionEm, _ZN2nn5image10PngEncoder6EncodeEPmPvm, _ZN2nn5image10PngEncoderC1Ev
  nn::fontll: _ZN2nn6fontll18ScalableFontEngine10GetAdvanceEPsS2_PiS3_jt, _ZN2nn6fontll18ScalableFontEngine10GetKerningEPiS2_jj, _ZN2nn6fontll18ScalableFontEngine10InitializeEPvj, _ZN2nn6fontll18ScalableFontEngine11SetAutoHintEb
  nn::account: _ZN2nn7account10InitializeEv, _ZN2nn7account11GetNicknameEPNS0_8NicknameERKNS0_3UidE, _ZN2nn7account12AsyncContext14GetSystemEventEPNS_2os11SystemEventE, _ZN2nn7account12AsyncContext6CancelEv
```

## 对移植意味着什么 | What it means for a port

- SDK 20，不是马力欧的 16：NVN 对象尺寸、API 版本与服务布局按 SDK 不同（宿主已从 D2R 的 SDK 12 改成 16 的尺寸），按 docs/agents/03 逐项核对 | SDK 20, not Mario's 16: NVN object sizes, API version and service layouts differ by SDK (the host was converted from D2R's SDK 12 to SDK 16 sizes); check them one by one per docs/agents/03
- 导入 nn::ro（运行时装 NRO 模块）：宿主没有 | imports nn::ro (loads NRO modules at run time): not in the host

下一步见 docs/agents（02 粗查、03 起机）。 | Next steps: docs/agents (02 survey, 03 bring-up).
