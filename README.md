# 澄岬光学双通道复检

澄岬光学质控室的白班校准员把台架原测和参考读值登记成不可变修订，并按指定版本签出双通道证据。夜班关站后凭固定件核对甲读值组内的乙达标率，用于决定是否补测。交班员按报告号领取当时签定的原口径和数值。

## 运行

使用 Python 3.11 标准库。在项目根目录运行。

```sh
python3 -B check_project.py
python3 -B run_demo.py
```

`check_project.py` 由运行平台提供，发现并执行 `tests` 包的全部 `test_*.py`。也可以直接用 `python3 -B -m unittest discover -s tests -t .` 执行原套件。演示从 `samples/shift.json` 读取有限台架样例，数据库只放在演示临时目录中。

## 一天的工作

1. 白班录入具名台架测次、参考读值和情景锚点，领取当前修订号。
2. 选取确切修订，登记带权三角情景和两路仿射响应，领取校准号及版本。
3. 按批次、校准号及版本发行固定件，从站库按件号领取可交接正文。
4. 关闭站库后，夜班凭预期批次、指定件号、固定件正文和本次复检口径提交请求。
5. 在同一固定件上核算甲筛选质量及该组中乙达标的联合质量。
6. 报告库存下实际父件、原口径和三项签定值，回送可领取的报告号。
7. 白班以当前修订为父版追加完整勘误，按新修订校准并签出新件。
8. 夜班凭新件走原入口签定新报告。
9. 交班员重开报告库，分别按号领取新旧报告，比较补测所用的依据。

## Python 接口

站库和报告库分别使用调用方持有的 `sqlite3.Connection`。调用者负责关闭连接，写接口各自拥有一次事务，调用前连接应处于事务外。站库先调用 `RevisionStore(db).initialize()`，再初始化 `CalibrationStore(db, revisions)` 和 `IssueCatalog(db)`。报告库调用 `ReportStore(db).initialize()`。重复初始化保留已有记录。初始化无样例写入。

- `archive.batches.BatchArchive(revisions).submit(batch, observations, scenario_inputs=())` 录入首版并返回 `RevisionRef(batch, number)`。`correct(parent, observations, scenario_inputs=())` 以当前父版追加新快照。每条原测形如 `{"name": "bench-01", "raw": ["3/10", 0], "reference": ["3/10", 0]}`，两组有理值均按甲、乙顺序。可选情景锚点形如 `{"name": "origin", "observation": "bench-01", "origin": [0, 0]}`，引用同版的测次。`archive.queries.get_revision(revisions, ref)` 和 `get_current_revision(revisions, batch)` 返回快照或 `None`。
- `calibration.response.CalibrationStore.register(ref, inputs)` 登记确切修订的模型。每个情景有 `name`、`vertices`、`weight`、`a`、`b`，以及可选 `anchor`。`vertices` 是三个二维有理点。两路响应各为 `[u 系数, v 系数, 常数]`。有锚点时，两路以归档情景的 `origin` 为局部原点，各加上所引用测次的参考值减原测值。权重总和须恰为 1，零权允许。校准 `version` 取该记录的来源修订号。`read_exact(batch, number, version)` 查确切登记，失配时返回 `None`。
- `issue.publication.issue_packet(calibrations, catalog, batch=..., calibration_id=..., version=...)` 签出指定校准的固定件。同一校准和证据重复发行取得同一件号。`IssueCatalog.get(packet_id)` 按件号领取已存固定件。`issue.packet.encode_packet(packet)` 交付 V1 JSON 文本，外层由 `version`、`source`、`evidence` 组成。来源含 `packet_id`、`batch`、`calibration_id`、`revision`。件号绑定规范化内容，证据正文供解码及核算，且只含输出空间概率信息。`decode_packet(text)` 验证结构、来源、件号和概率质量。台架原测、站内输入坐标及原响应式留站。
- `review.requests.submit_review(store, batch=..., packet_id=..., packet_text=..., window=..., threshold=...)` 签出一份报告。窗口形如 `{"low": "1/2", "high": 1, "include_low": true, "include_high": false}`。有理端点可超出量程并直接与读值比较。支持闭单点和同端点带开端的空窗口。乙等于门槛计为达标。
- `delivery.readback.receive_report(store, number)` 按确切号码读取已签快照，成功领取单独登记。未知有效号码抛出 `ReportNotFound`。`delivery.export.export_handoff(report)` 返回可 JSON 序列化的交班对象，包含号码、真实父件、原口径、状态及三个精确值。`ReportStore.read_signed(number)` 只查询快照并在缺失时返回 `None`。

## 核算与失败语义

每个正权情景在源三角形上均匀取值，两路在同一个情景点分别求值，再各自限幅至归一满量程 `[0,1]`。输出联合证据的总概率为 1，含面上、线段上和单点上的质量。筛选质量 D 来自甲落入请求窗口的事件，联合质量 N 来自同一次观测同时落入该窗口且乙达标的事件。`measured` 报告给出 D、N 和 N/D，其中条件率可为零。`no_evidence` 报告给出两个零质量，条件率为 `null`。

输入接受 `Fraction`、整数及可精确解析的有理文本。浮点近似和布尔值作为数值均拒绝。存取与交班采用约分、正分母的有理文本。归档、校准、发行及复检请求对业务输入错误抛出 `ValueError`。重复测次、过期父修订、未知确切来源、非法权重和父件不符均在相应写入前拒绝。SQLite 写入或提交错误向调用方可见，失败事务回滚。本次提交成功后返回定稿，后续勘误可继续签发新报告，之前的号码仍对应原父件及原签值。

## 确定性样例与回归

单位直角三角情景中，甲为限幅后的 2u，乙为 u。甲满量程对应 u≥1/2，乙达 3/4 对应 u≥3/4。三角形相似比给出筛选质量 `1/4`、联合质量 `1/16`、条件率 `1/4`。演示在关站后实际签发该报告。样例勘误把乙的锚点调整量改为 `−1/4`，相同口径下筛选质量仍为 `1/4`，联合及条件率均为零。重开按原号领取两份报告。

原测试覆盖确切发行绑定和恒量程边界、重复测次及过期勘误、权重与情景合法性、满量程线段、同边缘异联合、饱和点的开闭资格、父件和载荷拒绝、勘误后按号精确领取、重复初始化、真实 SQLite 延迟约束提交失败和回滚后的重试。历史精度场景按乙阈值 `1/3` 核对 `4/9` 和 `1/9` 的原样存取。
