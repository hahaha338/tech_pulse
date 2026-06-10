# 📡 TechPulse Auto-Push

简化版技术学习追踪推送工具。

第一版功能保持简单：

- 抓取外部影像技术趋势
- 抓取大手机厂商影像发展趋势
- 调用 QGenie 生成中文摘要
- 保存 Markdown 报告
- 可选推送到企业微信 / Email

---

## 1. 项目结构

```text
tech_pulse/
├── main.py
├── config.yaml
├── requirements.txt
├── fetchers/
│   └── external_fetcher.py
├── summarizer.py
├── notifier.py
├── utils/
│   ├── config.py
│   ├── logger.py
│   └── formatter.py
├── logs/
└── output/
```

---

## 2. 安装依赖

进入项目目录：

```bash
cd tech_pulse
```

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 3. 修改配置

编辑 `config.yaml`。

### 3.1 外部趋势配置

当前外部趋势分两类：

1. `tech`：通用外部影像技术趋势
2. `oem`：大手机厂商和传感器供应商影像趋势

当前来源包含三类：

1. 官方 RSS：例如 Apple / Samsung / Google Pixel
2. 官方新闻页轻量抓取：例如 Xiaomi / OPPO / vivo / Huawei / HONOR / Sony Semiconductor / Samsung Semiconductor
3. 国外手机 / 影像技术媒体 RSS：例如 Android Authority、9to5Google、9to5Mac、The Verge、DPReview、PetaPixel
4. 国内技术博客 / 数码媒体 RSS：例如 IT之家、少数派、爱范儿、雷峰网
5. Google News RSS 聚合：作为补充来源

覆盖范围包括：

```yaml
rss_sources:
  # 论文 / 学术趋势
  - name: "arXiv CV"
    category: "tech"
    url: "https://arxiv.org/rss/cs.CV"

  # 手机厂商 / 上游厂商官网
  - name: "Apple Newsroom"
    category: "oem"
    type: "rss"

  - name: "Samsung Global Newsroom"
    category: "oem"
    type: "rss"

  - name: "Google Pixel Blog"
    category: "oem"
    type: "rss"

  - name: "Xiaomi Global Newsroom"
    category: "oem"
    type: "html"

  - name: "OPPO Newsroom"
    category: "oem"
    type: "html"

  - name: "vivo News"
    category: "oem"
    type: "html"

  - name: "Huawei Consumer News"
    category: "oem"
    type: "html"

  - name: "HONOR News"
    category: "oem"
    type: "html"

  - name: "Sony Semiconductor News"
    category: "oem"
    type: "html"

  - name: "Samsung Semiconductor Newsroom"
    category: "oem"
    type: "html"

  # 国外手机 / 影像技术媒体 RSS
  - name: "Android Authority"
    category: "oem"
    type: "rss"

  - name: "9to5Google"
    category: "oem"
    type: "rss"

  - name: "9to5Mac"
    category: "oem"
    type: "rss"

  - name: "The Verge"
    category: "tech"
    type: "rss"

  - name: "DPReview"
    category: "tech"
    type: "rss"

  - name: "PetaPixel"
    category: "tech"
    type: "rss"

  # 国内技术博客 / 数码媒体 RSS
  - name: "IT之家"
    category: "oem"
    type: "rss"

  - name: "少数派"
    category: "oem"
    type: "rss"

  - name: "爱范儿"
    category: "oem"
    type: "rss"

  - name: "雷峰网"
    category: "tech"
    type: "rss"

  # 通用影像技术趋势
  - name: "Google News - Computational Photography"
    category: "tech"

  - name: "Google News - Image Sensor Tech"
    category: "tech"

  - name: "Google News - Neural ISP AI Imaging"
    category: "tech"

  # 手机厂商影像技术趋势
  - name: "Google News - OEM Imaging Tech"
    category: "oem"

  - name: "Google News - Apple Pixel Imaging"
    category: "oem"

  - name: "Google News - Samsung Xiaomi OPPO Vivo Imaging"
    category: "oem"

  - name: "Google News - Huawei HONOR Imaging China"
    category: "oem"

  - name: "Google News - OEM Imaging Tech China"
    category: "oem"

  # 传感器供应商 / 上游技术
  - name: "Google News - Mobile Sensor Vendors"
    category: "oem"
```

说明：

- `category: tech` 用于外部影像技术趋势
- `category: oem` 用于大手机厂商影像发展趋势
- `lookback_days: 7` 表示只保留最近 7 天内容
- `type: rss` 表示直接读取 RSS / Atom feed
- `type: html` 表示轻量解析官网新闻页里的链接标题，不做深度爬虫、不执行 JS；如果官网链接没有明确日期，会被跳过，避免旧新闻误入
- Google News RSS 会聚合 Huawei Central、Gizchina、GSMArena、Notebookcheck、Engadget、Geeky Gadgets 等被收录科技媒体
- OEM 趋势会过滤榜单、导购、评测、横评、DxOMark、价格、促销和明显旧年份内容
- OEM 趋势重点关注厂商近期的影像技术，例如传感器、长焦、潜望、HDR、ISP、AI 影像、计算摄影、夜景、人像算法等
- 传感器供应商方向会关注 Sony LYTIA、Samsung ISOCELL、OmniVision、LOFIC、stacked sensor 等上游技术
- `query` 会自动转换成 Google News RSS URL

---

## 4. 配置 QGenie

第一版默认启用 QGenie：

```yaml
qgenie:
  enabled: true
  endpoint: "https://qgenie-api.qualcomm.com/v1/chat/completions"
  model: "qgenie-default"
  timeout_seconds: 60
  api_key_env: "QGENIE_API_KEY"
```

设置环境变量：

```bash
export QGENIE_API_KEY="your_qgenie_api_key"
```

如果 QGenie 调用失败，程序会自动退回模板化 Markdown 报告，不会中断整个任务。

如果你想临时关闭 QGenie：

```yaml
qgenie:
  enabled: false
```

---

## 5. 推送配置

默认不启用推送，只保存报告到 `output/`。

### 5.1 企业微信

设置环境变量：

```bash
export WECOM_WEBHOOK_URL="your_wecom_webhook_url"
```

然后把 `config.yaml` 中企业微信渠道打开：

```yaml
notifier:
  channels:
    - type: "wecom"
      enabled: true
      webhook_url_env: "WECOM_WEBHOOK_URL"
```

---

### 5.2 Email

把 Email 渠道打开：

```yaml
notifier:
  channels:
    - type: "email"
      enabled: true
      smtp_host: "smtp.qualcomm.com"
      smtp_port: 587
      from: "shiliang@qti.qualcomm.com"
      to:
        - "shiliang@qti.qualcomm.com"
```

当前实现使用 SMTP TLS，不带用户名密码。  
如果你的 SMTP 需要登录认证，需要后续再补 `smtp.login()`。

---

## 6. 手动运行

在 `tech_pulse` 目录下执行：

```bash
python main.py
```

运行后会生成：

```text
output/techpulse_YYYY-MM-DD.md
logs/techpulse.log
```

---

## 7. Cron 自动运行

每 2 天 09:00 执行一次：

```bash
crontab -e
```

添加：

```bash
0 9 */2 * * cd /home/shiliang/tech_pulse && python main.py >> logs/cron.log 2>&1
```

如果你的项目路径不同，请替换 `/home/shiliang/tech_pulse`。

---

## 8. 输出内容

报告结构：

```markdown
# 📡 TechPulse 技术追踪 | YYYY-MM-DD

## 1. 外部影像技术趋势

## 2. 大手机厂商影像发展趋势
```

其中“大手机厂商影像发展趋势”会关注：

- Apple / iPhone
- Samsung / Galaxy
- Xiaomi
- OPPO
- vivo
- Huawei
- HONOR
- Google Pixel
- Sony LYTIA

---

## 9. 当前版本刻意不做的事情

为了保持第一版简单，当前不做：

- 不做内部 CamX / CHI-CDK 抓取
- 不做 Gerrit 抓取
- 不做数据库
- 不做 Web UI
- 不做网页深度爬虫
- 不做 embedding
- 不做复杂去重
- 不做 SharePoint 上传
- 不做 Teams 推送

---

## 10. 常见问题

### Q1: 没有设置 QGENIE_API_KEY 会怎样？

不会中断。程序会使用模板报告。

### Q2: RSS 源访问失败会怎样？

不会中断。该源会被跳过，错误会写入日志和模板报告。

### Q3: 不开企业微信和 Email 可以吗？

可以。默认只生成本地 Markdown 报告。

---

## 11. 最小运行步骤

```bash
cd tech_pulse
pip install -r requirements.txt
export QGENIE_API_KEY="your_qgenie_api_key"
python main.py
```

然后查看：

```bash
ls output
cat output/techpulse_YYYY-MM-DD.md
```
