# 乙门槛反查交班

白班按 README.md 的原流程发行双通道固定件。关站后，夜班选择其中一件和一个甲读值窗，签出满足乙通过率底线的最高门槛。次班领回报告后可以关库，再用手头的报告核对拟用设点。

## 业务口径

甲、乙沿用 V1 同一次抽样的限幅读值。记 `D` 为甲落入指定窗口的质量。对 `D > 0`，乙在门槛 `t` 上的通过率是甲落入该窗且乙大于或等于 `t` 的联合质量除以 `D`。在闭量程 `[0,1]` 内，签出通过率大于或等于目标的最高 `t`。点质量在等于门槛时计入，达标平台取最右端。`D = 0` 时，无论目标为何都签 `no_evidence` 和 `None` 门槛。`D > 0` 时签 `measured`，其中零目标的门槛为 1。

## Python 入口

- `review.requests.submit_threshold_review(store, *, batch, packet_id, packet_text, window, minimum_rate)` 接收初始化后的 `ReportStore`，按 V1 规则核对指定件并解析甲窗。`minimum_rate` 采用 V1 有理输入格式，范围为 `[0,1]`。成功返回已签反查报告。
- `delivery.readback.receive_threshold_review(store, number)` 按 V1 有效编号规则领取已签反查报告。编号按该领取入口解释。未知的有效反查号抛出 `ReportNotFound`。
- `delivery.readback.threshold_allows(report, setting)` 接收领回的反查报告及 `[0,1]` 内的 V1 格式有理设点，只凭报告判断设点是否不高于所签门槛。返回 `True` 或 `False`，等于门槛返回 `True`。`no_evidence` 时对合法设点返回 `None`。报告库和站库都可关闭后调用该入口。

签发和领取的报告均可读出 `.number` 和 `.draft`。报告正文提供 `draft.parent`（实际 `PacketRef`）、`draft.window`（原 `ReviewWindow`）、`draft.minimum_rate` 和 `draft.selected`（`Fraction`）、`draft.status` 和 `draft.threshold`。有理门槛返回 `Fraction`，无证据返回 `None`。无理门槛保存足以唯一确定其二次实根的精确数据，具体表示由实现决定。签发与领取所呈现的口径和门槛值一致。

非法请求、非法设点、坏件或指定父件失配抛出 `ValueError`。签发和领取各自拥有事务，沿用 V1 的连接约定。签发提交后返回报告，领取登记提交后返回领回值。数据库错误向调用方传播，本次写入全部回滚并可重试。对既有报告库调用 `ReportStore.initialize()` 后可使用新入口，原报告和其领取行为照旧。源站追加勘误或报告库重开后，旧反查号仍领回原父件、原口径和原签值。

## 可重跑样例

`python3 -B threshold_examples.py` 通过原入口发件、关站并核对这些件的有理正查结果。脚本的 `example_packets()` 返回以样例名索引的 `(PacketRef, 正文)`，可用于反查核验。除 `window-cut` 外，以下样例都使用闭单点甲窗 `[1,1]`。

| 样例 | 最低通过率 | 应签门槛或状态 | 可核对结果 |
| --- | --- | --- | --- |
| `continuous` | `1/2` | `1−√(1/2)` | 领取后设点 `73/250` 获准，`3/10` 被拒。 |
| `saturated` | `1/8` | `1` | 满量程的实际通过率为 `1/4`。 |
| `plateau` | `1/2` | `3/4` | `1/2` 和 `3/4` 上的通过率均为 `1/2`，设点 `3/4` 获准。 |
| `two-roots` | `1/2` | `1/2−√(1/2)/4` | 设点 `2/5` 被拒。 |
| `window-cut` | `1/20` | `5/8` | 甲窗为 `[1/4,1/2)`，筛选质量为 `5/16`。 |

把 `continuous` 的甲窗改为 `[0,1)` 并给零目标，应签 `no_evidence`，核对合法设点返回 `None`。原闭窗给零目标签 1。

## 运行交付

沿用 `.pointwise-runtime.json` 的版本 1 和 `cli` 类型。`setup` 保持为命令参数数组的列表，`verify` 与 `demo` 各为一条命令的参数数组。让核验入口运行完整原回归并核对反查业务结果，失败返回非零退出码。让演示入口展示固定件断源签发、重开领取及依据领回值核对设点。原回归及 `run_demo.py` 保持可运行。
