# 文档一详细大纲：Bus GPS Processing in London Live

目标：读者读完就能自己复现整条流水线。每一节写明"讲什么、给哪张图、用哪些实测数字、对应代码里哪个常量"。
最终成文英文，Quarto 单源出 PDF 和 HTML。预计 22–28 页，图 18–22 张，表 8–10 张。
标注说明：〔图〕= 需要生成的图；〔表〕= 表格；〔数〕= 要从归档数据算出来的数字；〔码〕= 代码常量，附录 B 汇总。

---

## 0. Summary（1 页，子弹点）

- 输入只有一样：DfT BODS 的 SIRI-VM 车辆定位流，每 15 秒一包，全伦敦约 7.5 MB XML、8–9 千辆车。
- 输出四样：每条线路每个方向的真实路径；每辆车沿路径的平滑位置；正在发生的绕路事件及其生命周期；每条走廊每天的班次密度（Bus Flow）。
- 没有用到任何路线形状数据：TfL 不向 BODS 发布时刻表，路径全部从车辆自己的 GPS 学出来，每晚重学。
- 绕路检测不依赖任何通知，先于或独立于 TfL 的道路事件记录（举 H32 例子）。
- 全部跑在一台小实例上；本文档第 9 节给出资源占用。
- 三条局限：单向低频线路学不出路径；绕路括号只增不减；没有到站时间所以算不出"晚点分钟数"。

## 1. Scope and reading guide（半页）

- 本文档只讲公交 GPS 这条线；地铁位置推断、后端架构分别是文档二、三。
- 读者分层：只看 Summary 和第 10 节的（运营）；看第 3–6 节的（数据/算法）；要复现的看附录 A、B 和仓库链接。
- 术语表指向附录 C。

## 2. Data source: BODS SIRI-VM（按 DfT 的 Coverage / Source / Methodology / Quality 四段写）

2.1 Coverage
- 地理范围：London bounding box（写出 bbox 坐标）；运营商：TFLO 约 94% 的车辆，其余为 Go-Ahead、Arriva 等〔数：按 operator 前缀统计一天 traces 的车辆占比〕。
- 车辆数随时间：每个 15 秒快照的车辆数，一天曲线，工作日 vs 周末〔图 2.1：用 bus-rollups 36 天的 totals 画〕。

2.2 Source
- 接口：`data.bus-data.dft.gov.uk/api/v1/datafeed/` + boundingBox；15 秒轮询〔码 POLL_INTERVAL_MS〕；30 秒超时；5 分钟没更新即视为过期〔码 STALE_AFTER_MS〕。
- 一条 VehicleActivity 里我们取哪些字段〔表 2.1：VehicleRef、OperatorRef、LineRef、DirectionRef、DestinationName、Latitude、Longitude、Bearing、RecordedAtTime，各字段含义与坑〕。
- 解析方式：字符串扫描而非 DOM，原因是 7.5 MB 的 XML 每 15 秒一次；解析出的字符串必须拷贝，否则 V8 的 slice 视图会把整份 XML 钉在内存里（指向文档三的 OOM 案例，一句话）。
- 存储格式：每条定位一行 JSONL `{k, i, x, y, t}`，k = OPERATOR:line:direction，i = OPERATOR:vehicleRef〔表 2.2〕；每天一个文件，保留 7 天、总量上限 2 GB〔码 RETENTION_DAYS、MAX_TOTAL_BYTES〕。

2.3 Methodology（如何从流变成可分析的数据）
- 去重：同一辆车 RecordedAtTime 没变就不写。
- 一天数据量：9 月 22 日 8,767,672 条定位〔数〕；每辆车每天定位数分布〔图 2.2〕。
- 定位间隔：同一辆车相邻两条定位的时间差直方图，中位数、p90〔图 2.3，数〕；这个分布决定了后面所有阈值（例如 60 秒、120 秒）。
- 延迟：RecordedAtTime 到我们收到的时间差分布〔图 2.4，数：需要用 t 与轮询时刻比较；若归档没存轮询时刻，用文档里的 10–30 秒实测值并注明来源〕。

2.4 Quality（这一节最重要，TfL 的人最关心）
- 位置噪声：城市峡谷漂移是有偏的，不是零均值；举一个固定漂移点的例子〔图 2.5：某条线一段路的所有定位点云，叠加学出来的路径〕。
- 方向标签错误：DirectionRef 有时标反，后果是把去程和回程粘成一条 journey；第 3 节和第 5 节各有一个防护规则专门对付它。
- 缺 Bearing 的比例〔数〕。
- 速度异常：由相邻定位算出的隐含速度超过 40 m/s 的比例〔数，rollup-writer 的 MAX_SPEED_MS〕。
- 每日快照缺失：轮询失败/超时的次数〔数：从 health 采样或日志估计，说明来源〕。

## 3. Pipeline overview（1 页 + 1 张大图）

〔图 3.1：数据流图〕BODS 15 s → 解析 → 三个消费者并行：(a) TraceWriter 写 JSONL；(b) DiversionDetector 在线投影；(c) /api/buses 给前端。夜间：LearnerScheduler → fetch-bus-prior（每周）→ learn-bus-routes（每天，读最近 3 天 traces）→ learned/<key>.json → 前端吸附 + 卡尔曼；RollupWriter 每小时把完成的一天压成 rollup → CoverageWriter 每天合成 Bus Flow GeoJSON。
- 每个箭头旁标数据量和频率。
- 一句话说明为什么没有 cron：调度器自己看上次运行的时间戳。

## 4. Journeys: from a vehicle's stream to trips（半页，为第 5、6 节做准备）

- 同一辆车按时间排序，间隔超过 600 秒切开〔码 JOURNEY_SPLIT_GAP_S〕。
- 完整 journey 的三个门槛：≥15 条定位、≥2 km、≥480 秒〔码〕；不满足的不参与学习。
- 终点站停车的补切：在 80 米内停留 ≥300 秒也切〔码 LAYOVER_*〕，原因是 254 路一次 591 秒的停站把去程和回程粘在一起，赢了"最能解释点云"的比赛。
- 〔图 4.1：一辆车一天的 s–t 图，标出切分点〕
- 〔表 4.1：一天里 journey 数、平均长度、平均时长，按 TFLO / 非 TFLO〕〔数〕

## 5. Route shape learning（核心节之一，4–5 页）

5.1 Problem statement
- 输入：某个 key 最近 3 天所有完整 journey 的定位点；可选先验形状（只有非 TfL 运营商有）。
- 输出：一条折线 poly（25 米一个顶点）和质量指标 {journeys, meanResidualM, coverage}。
- 为什么不能直接用 OSM 路网做地图匹配：没有路线的站序，不知道该匹配哪条路；而且要处理的是"这条线实际怎么走"，包括临时改道后的常态化。

5.2 Seed
- 有先验用先验；没有就取路径长度处于中位数的那条 journey；重采样到 25 米等距〔码 SEED_SPACING_M〕，顶点上限 2,500。
- 〔图 5.1：一个 key 的点云 + 中位 journey 作为 seed〕

5.3 Corridor fit
- 每个点投影到 seed，取残差；走廊宽度 = clamp(30 m, p90(残差), 60 m)〔码 CORRIDOR_START_M、CORRIDOR_CAP_M〕；残差 >100 m 的点直接忽略〔码 MAX_CONSIDERED_RESIDUAL_M〕。
- 每个顶点收集落在走廊内、投影到它的点；点数 <4 的顶点保持 seed 位置〔码 VERTEX_MIN_SUPPORT〕；其余按残差排序，去掉最差 20%〔码 TRIM_FRACTION〕，取均值作为新顶点。
- 〔图 5.2：某一个顶点的点集、被截掉的 20%、新顶点位置的放大图〕
- 写出公式：新顶点 = mean of the (1−α) fraction nearest points, α = 0.2。

5.4 Stop anchoring and smoothing
- 有先验站点时，40 米内的顶点向站点拉 50%〔码 STOP_ANCHOR_RADIUS_M、STOP_ANCHOR_PULL〕；TfL 线路没有先验，这一步不发生，要写清楚。
- 1-2-1 平滑一遍（0.25/0.5/0.25）。

5.5 Quality gate
- 用结果重新投影（抽样最多 2 万点），meanResidual >35 m 则丢弃〔码 MAX_MEAN_RESIDUAL_M〕，原因："形状错了的路径比不吸附更糟"。
- 〔图 5.3：全部 learned key 的 meanResidualM 分布直方图；标 35 m 的门槛〕〔数：读线上 34 个/或归档里的 learned 文件〕

5.6 Coverage measurement and the repair path
- coverage = 该 key 全部定位落在结果走廊内的比例；伦敦运营商 <0.9 触发修复〔码 COVERAGE_THRESHOLD〕。
- 修复：在最多 400 条候选 journey 里找"最能解释整个点云"的一条重新做 seed；评分 = recall × precision，precision = 被 ≥3 个点支持的顶点比例〔码 SCORING_*、VERTEX_SUPPORT_MIN_FIXES〕。
- 反折返防护：候选路径有 >30% 顶点落在自己更早、且相隔 >20 段的部分 30 米内，判为去程+回程粘连，拒绝〔码 OVERLAP_*〕。
- 为什么只对伦敦运营商修：长途/乡村运营商合法地走高速变体，重 seed 反而有害。
- 〔图 5.4：一个修复前后对比的真实例子：坏 seed 的形状 vs 修复后的形状 + coverage 数字〕

5.7 Scheduling and idempotence
- 启动时若上次运行超过 20 小时就先跑一次，之后每 24 小时〔码 STALE_AFTER_MS、RUN_INTERVAL_MS〕；45 分钟超时；失败只记日志，下个周期重试。
- 每次都是全量重算，缺数据的 key 保留旧文件。
- 内存有界：按 chunk 处理，每 chunk 不超过 400 万条定位（约 100 MB）。

5.8 Results
- 〔表 5.1：学出多少个 key、跳过多少（按 skip 原因分类：journeys 不足 / degenerate-seed / bad-geometry）〕〔数：需要一次本地运行 learner 的摘要行，或线上日志〕
- 〔数：闭站杆到学习路径的中位距离 5 m，出处 disruption-geolocation 记录〕
- 〔图 5.5：三张地图截图：中心区一条线、郊区一条线、一条有终点环线的线〕

## 6. Snapping and along-route filtering（前端显示模型，3–4 页）

6.1 Two models running side by side
- 原始模型：用最近两条不同的定位算速度，沿直线外推；决定吸附的开关；没有学到路径的车只用它。
- 过滤模型：只在吸附时启用，沿路径工作。
- 为什么过滤器不能自己决定吸附与否（"自信但错的过滤器会让自己活下去"）。

6.2 Snap hysteresis
- 原始位置到路径距离 <50 m 进入吸附，>80 m 退出〔码 SNAP_ON_M、SNAP_OFF_M〕；投影先在当前段 ±30 段内找〔码 SNAP_LOCAL_WINDOW〕，避免在终点环线上跳到另一支。
- 〔图 6.1：一辆车一段时间的 d(t) 曲线 + 吸附状态的阶梯图〕

6.3 The 1-D Kalman filter along the route
- 状态：弧长 s、有符号速度 v、协方差 (pS, pV, pSV)；时间用 RecordedAtTime 不用墙钟。
- 预测：s += v·dt；Q 为连续白噪声加速度模型，q = 2 m²/s³；写出为什么是 2（300–400 米一站，20–30 秒内速度从 0 到 8–13 m/s 要"统计上不意外"；最初 0.2 导致 20–36% 的正常刹车定位被门控拒绝，全车队"冲刺-停顿"）。
- 更新：K = pS/(pS+R)；R 来自该路线的 meanResidualM × 1.25（MAD→σ），下限 8 m〔码 KF_MEAS_SIGMA_FLOOR_M〕，没有质量字段的路线用 44 m〔码 KF_DEFAULT_MEAS_SIGMA_M〕。
- 门控：创新 >3σ 拒绝〔码 KF_GATE_SIGMA〕；连续拒绝 3 次重置〔码 KF_MAX_REJECTS〕。
- 初始 σ：位置 30 m（对应学习器走廊起点）、速度 3 m/s；|v| ≤ 20 m/s。
- 〔图 6.2：一辆车 30 分钟的 s(t)：原始投影 z、滤波 s、±2σ 带、被门控拒绝的点用叉标出〕〔数：需要用归档 traces 离线重放 bus-kalman.ts 的逻辑；写一个 Node 脚本直接 import 前端的纯函数〕
- 公式块：预测和更新的 5 个方程。

6.4 Display between fixes: the asymmetric loss
- 显示目标是"尽量接近但不超前"；超前的代价是"车倒车"的观感。
- 衰减滑行：Δs = v·τ·(1−e^(−Δt/τ))，τ = 12 s，静默上限 v·τ ≈ 96 m〔码 KF_COAST_TAU_S〕。
- 只前进：落后于显示位置的修正让车停住等状态追上；超过 1.2 km 才允许跳〔码 KF_JUMP_DISTANCE_M〕。
- 追赶上限 25 m/s；渲染缓动 τ = 2.5 s〔码 EASE_TAU_S〕。
- 〔图 6.3：线性外推 vs 衰减滑行的位移-时间曲线，标出 96 m 上限〕
- 停车判定：20 分钟内移动 <60 m 显示为停放〔码 PARKED_*〕。

6.5 Cost
- 协方差只在收到定位时更新（全车队约 110 次/秒），每帧只做一次外推和一次缓动；渲染 ≤15 Hz。

## 7. Diversion detection（核心节之二，5–6 页）

7.1 Definitions
- 对每个 (key, vehicle)，每条定位投影到学习路径得到 (s, d)。
- 排除：journey 开头 500 m 的地面轨迹（车场出车）〔码 CLIP_M〕；600 s 间隔切 journey。
- 阈值：|d| > max(50 m, 5 × meanResidualM)〔码 THRESHOLD_FLOOR_M、THRESHOLD_RESIDUAL_MULT〕；没有质量字段按 15 m 算。
- 〔图 7.1：(s, d) 平面示意：一次真实绕路的点序列，标出离开点、外面的点、回来点〕

7.2 What counts as an excursion（写成一张判定表〔表 7.1〕）
- ≥5 条越界定位、≥60 s、≥300 m 真实地面移动（只算相邻 ≤60 s 的定位对，跨间隙的位移不算）〔码 MIN_RUN_*、REAL_MOVE_MAX_DT_S〕。
- 两侧各 ≥2 条在路定位〔码 MIN_ON_ROUTE_BRACKET_FIXES〕，且 s 向前推进（用最近 32 条在路定位的中位数判断）〔码 BEFORE_S_WINDOW〕。
- 记录 sExit、sRejoin、maxD、地面距离、中点坐标、置信度。

7.3 Guards, each with the false positive that motivated it（〔表 7.2〕规则 / 阈值 / 当时的误报）
- Wanderer：地面距离 > max(2500 m, 4 × 跳过的 s 区间) 且跳过 <500 m → 不是绕路，是终点越界或跑错线。
- Gap reset：越界期间出现 ≥180 s 的间隙就重新开始计数。
- Endpoint clamp：投影落在 s=0 或 s=max 1 m 内的比例 >20%，或在端点 200 m 范围内 → 端点钳位，不算。
- Dwell：越界期间移动的比例 <30%（速度 <2 m/s 算不动）→ 降为 LOW 置信度。
- Mislabel：抽 15 条定位重投影到反方向路径，如果更贴合 → 方向标签错，不算。
- Credibility caps：|d| >1500 m 或跳过区间 >4000 m 不可信（曾把 11–15 km 的"绕路"涂满西北伦敦）。
- 每辆车最多缓存 4 个待定 excursion、2000 条定位；30 分钟不见的车状态清除。

7.4 From excursions to events
- 站点合并：中点距离 <500 m 的 excursion 归同一事件〔码 SITE_MERGE_DIST_M〕；45 分钟窗口〔码 EVENT_WINDOW_S〕。
- 每个 route-direction 一个括号：sA = min(sExit)，sB = max(sRejoin)，只增不减；这就是为什么红带会比任何一辆车实际跳过的段更长（写清楚，这是 TfL 的人看图时第一个会问的）。
- 显示门槛：≥2 辆车〔码 DISPLAY_MIN_VEHICLES〕；严重度 road（≥2 个 route-direction）/ partial。
- 归因只用 HIGH 置信度成员。
- 画法：把学习路径从 sA 切到 sB，最多 12 段〔码 MAX_EVENT_SEGMENTS〕。

7.5 Lifecycle（〔图 7.2：状态机图〕active → recovering → dropped；active → stale → dropped）
- recovering：最后一次 excursion 之后 20 分钟无新 excursion〔码 QUIET_RECOVERY_S〕，且 ≥2 辆车各自覆盖每个括号 90% 的长度（±50 m 容差）〔码 RECOVERY_*〕；10 分钟后移除。
- stale：90 分钟无任何证据；6 小时后移除。
- 新 excursion 把 recovering 拉回 active。
- longRunning：超过 24 小时打标。
- 每次状态变化追加到 diversions/YYYY-MM-DD.jsonl；重启后从零重建，几分钟内恢复。

7.6 Matching to TfL road disruptions
- 每 10 分钟拉一次 TfL Road/all/Disruption；每段红带中点找最近事件，<250 m 挂上〔码 TFL_MATCH_DIST_M〕；弹窗显示距离。
- 〔数：过去 N 天事件里有多少比例匹配到了 TfL 记录；匹配距离分布〕〔图 7.3〕

7.7 Case studies（三个，各一页，都有真实数据）
- Camberwell New Road，9 月 22 日 13:53 碰撞封路：36/185/P5 的 excursion 时间线、红→黄→绿的时刻、JamCam 截图〔图 7.4〕。
- H32，9 月 22 日：没有 TfL 记录；一辆车（LTZ1657）在红带起点拐出的 (s, d) 序列〔图 7.5〕。
- Victoria Street：11/24/26/148 一条带；说明"换 24 路没用"是怎么从数据里看出来的〔图 7.6〕。

7.8 Validation
- 原型阶段：审计门槛 8/10 确认、0 个车场伪影（写清楚这是人工审计，样本量多少）。
- 线上：过去 N 天的事件数、按 severity、按是否匹配 TfL、按生命周期结局统计〔表 7.3〕〔数：从 ~/bus-archive/diversions/*.jsonl 算〕。
- 明确没有的东西：没有 ground truth 的召回率；这正是向 TfL 要绕路记录的理由。

## 8. Bus Flow: corridor journey density（1.5 页）

- 输入：learned 路径 + 最近 7 个完整天的 rollup（每条线每天 journey 数）。
- 走廊合并：每条线按 25 m 重采样，落在已画走廊 18 m 内且方向相容的段把自己的班次加上去，不重画〔码 COVERAGE_*〕。
- 桶是绝对值（0/10/30/75/150/300 班/天），不是分位数，保证颜色含义跨天稳定。
- 每天重建一次；重建是进程最大的内存峰值，所以不多建。
- 〔图 8.1：Bus Flow 全城截图〕〔表 8.1：桶分布〕

## 9. Operational footprint（1 页，指向文档三）

- 每 15 秒 7.5 MB 下载 ≈ 43 GB/天入口流量；解析耗时〔数〕。
- 内存中的车辆表、路径索引、事件存储的条目数（/health 暴露：vehicleStates、routeIndexes、shapeGates、events）〔图 9.1：用 health 采样画这些计数的时间序列〕。
- 学习器运行时长与内存峰值〔数：日志〕。

## 10. Limitations and what data would help（1 页，对应给 TfL 的请求）

- 学不出路径的 key：班次 <5 的线、夜班线、单向短线；数量〔数〕。
- 括号只增不减：红带是并集，不是某辆车的实际跳过段；改进方向是 p10/p90。
- 没有到站/时刻表数据：能看到"慢"，算不出"晚点几分钟"。
- 方向标签错误是最大的噪声源。
- 3 天窗口：改道常态化超过 3 天会被学成新路径，绕路检测随之失效——这是设计取舍，写明。
- 想要的数据：TfL 内部绕路/封路记录（标注检测器）、到站时间（延误量化）、一个月以上的历史 SIRI-VM（回放与调参）。

## 11. Reproducibility

- 仓库、各脚本路径、运行命令、环境变量；本文档所有图的生成脚本放在 docs/reports/figures/ 下。
- 输入数据的获取方式（BODS API key 免费申请）。

## Appendix A. Data schemas
- SIRI-VM 取用字段、trace JSONL、learned JSON、rollup JSON、diversions transition JSONL、/api/buses wire 格式。

## Appendix B. Parameter table
- 全部〔码〕常量：名称、值、单位、所在文件、一句话理由。约 60 行。

## Appendix C. Glossary
- key、journey、fix、excursion、bracket、corridor、coverage、residual、s/d 等。

---

## 需要先做的数据工作（写正文前）

1. 从 ~/bus-archive 的 36 天 traces 和 rollups 算：车辆数曲线、定位间隔分布、每车每天定位数、隐含速度分布、缺 Bearing 比例、journey 统计。
2. 从 learned 文件算 meanResidualM 分布（线上现有 34 个样本在 scratchpad，最好拉全量 ~1,800 个）。
3. 从 diversions/*.jsonl 算事件统计与 TfL 匹配率。
4. 写一个 Node 脚本离线重放前端 bus-kalman 纯函数，得到图 6.1–6.3。
5. 三个案例的轨迹切片已在 scratchpad（Victoria、H32、Camberwell 部分需要从 traces 再切）。

## 你需要拍板的

- 篇幅接受 22–28 页吗（比之前说的 15–20 长）。
- 第 7.8 节要不要写"没有召回率"这句话（我建议写，它是要数据的理由）。
- 案例里车牌号要不要保留（LTZ1657 这种）。
