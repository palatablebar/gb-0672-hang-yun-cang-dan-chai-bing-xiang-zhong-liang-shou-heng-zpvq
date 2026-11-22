# 航运舱单拆并箱与重量守恒

给货代单证员使用。主提单与分提单拆并形成有向无环关系，件数和净毛重逐层守恒。

七个业务模块：舱单采信、包装映射、拆并编组、危险品检查、净毛重核验、报关对账、版本封存；外加通知签收工作台，处理拆并方案连续修订的整批重发。

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

访问 http://localhost:18241 。启动直接载入现场脏批。切换干净样例和旧编码样例可对照核验。干净批42个节点、6个主单，件数240、净重2400kg、毛重2640kg；现场脏批包含父级缺失、依赖环、危险品不相容及1kg毛重差异，封存状态为待处理。

各模块页面对应 `/<模块英文名>`，各模块执行入口为 `POST /api/<模块英文名>`，不传参即可独立演示。完整运行 `POST /api/runs` 支持 `dataset`（dirty/clean/legacy）、`csv_text` 与 `overrides` 参数。批次历史 `GET /api/runs`，详情 `GET /api/runs/{run_id}`。

同输入与规则版本生成相同批号，只保留一条批次。复核入口 `POST /api/runs/{run_id}/review` 提交当前 `revision`，陈旧提交409。归档包只有一个下载入口 `GET /api/export/{run_id}`，含证据和运行摘要。原始隔离在页面同屏显示。

SQLite使用命名卷，容器重启后保留历史。要重建演示可在Compose中改用新的卷名称，保留旧卷。

源码在 `app/`，样例在 `sample_data/`，测试在 `tests/`；定义见 `docs/DATA-DICTIONARY.md`，模块和边界测试对应关系见 `docs/DEPTH.md`。输入上限2MB，属于离线复核工具。

采信页支持上传或粘贴CSV。完整源字节与参数随批次持久化，跨页通过run_id读取同一结果。`POST /api/runs/{run_id}/rerun` 读取该批不可变输入快照重新计算，规则未变时批号不变。切换另一示例则创建或复用另一批次。

## 通知签收

页面 `/notice`，按 `batch_id`（默认 batch-20261117）组织通知。签收单逐张主单写清本次变化、适用版本、接收方、当前依据、旧通知替代关系、签收状态与能否申报，并给出整批统一签收或受影响主单先行签收的裁决。

- `POST /api/notice/{batch_id}/publish` 发布通知，可带 `run_id`、`scenario`（v2_weight/v3_relation/v4_fail/v4_weight）或 `simulate_fail`；同载荷重发判定为 RESEND，不新增第二套签收。
- `POST /api/notice/{batch_id}/publish-demo` 一键铺出 V1首发→重量修订→关系修订→发布失败→重试恢复→同版重发的演示链。
- `POST /api/notice/delivery/{notice_no}/retry` 同一通知重试，失败通知重试成功恢复为已发布，未送达记录保留。
- `POST /api/notice/{batch_id}/signoff` 单张主单签收（`root_id`）或按 `mode` 批量签收；旧依据被替代后原签收标记失效，须按当前依据重签。
- `GET /api/notice/{batch_id}` 取签收单、版本链与送达轨迹。

新修订一旦改变拆并关系或件净毛重，旧通知对受影响主单失效；发布失败恢复旧版并保留未送达记录。通知与签收落在同一 SQLite 的 notices/deliveries/signoffs 三张表。
