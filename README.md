# 📡 TechPulse Auto-Push

简化版技术学习追踪推送工具。

第一版功能保持简单：

- 抓取外部影像技术趋势
- 抓取大手机厂商影像发展趋势
- 生成中文 Markdown 摘要
- 保存 Markdown 报告
- 可选推送到 Email

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

## 4. 摘要生成（千问 AI 要点提炼）

每条新闻下方会由通义千问自动提炼与手机影像、相机传感器、计算摄影相关的中文技术要点。

### 4.1 获取 DashScope API Key

1. 登录 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com)
2. 进入 **API-KEY 管理**，点击 **创建新的 API-KEY**
3. 复制生成的 Key（格式如 `sk-xxxxxxxxxxxxxxxx`）

### 4.2 设置环境变量

**Windows PowerShell（临时，当前终端有效）：**

```powershell
$env:DASHSCOPE_API_KEY="sk-你的Key"
python main.py
```

**Windows 永久设置（推荐，一次设置永久生效）：**

1. 打开「系统设置 → 高级系统设置 → 环境变量」
2. 在「用户变量」中点击「新建」
3. 变量名：`DASHSCOPE_API_KEY`，变量值：你的 Key
4. 确定保存后重新打开终端即生效

**Linux / macOS：**

```bash
export DASHSCOPE_API_KEY="sk-你的Key"
# 或写入 ~/.bashrc / ~/.zshrc 永久生效
```

### 4.3 未设置 API Key 时的行为

不影响正常运行，只是报告中不会出现「要点」字段，其他内容照常生成。

---

## 5. 邮件推送配置

### 5.1 开启邮件推送

编辑 `config.yaml`，把 `enabled` 改为 `true`，并填写你的邮箱信息(目前支持个人邮箱)：

```yaml
notifier:
  channels:
    - type: "email"
      enabled: true
      smtp_host: "smtp.qq.com"      # 根据邮箱服务商修改
      smtp_port: 587
      username: "your_email@qq.com"
      from: "your_email@qq.com"
      to:
        - "your_email@qq.com"       # 收件人，可添加多个
```

**不要把密码/授权码写在 `config.yaml` 里**，通过环境变量传入：

```powershell
# Windows PowerShell
$env:TECHPULSE_SMTP_PASSWORD="你的授权码"
python main.py
```

```bash
# Linux / macOS
TECHPULSE_SMTP_PASSWORD="你的授权码" python main.py
```

---

### 5.2 各邮箱服务商配置

| 服务商 | smtp_host | smtp_port | 说明 |
|--------|-----------|-----------|------|
| QQ 邮箱 | `smtp.qq.com` | 587 | 需在 QQ 邮箱设置中开启 SMTP 并获取**授权码** |
| Gmail | `smtp.gmail.com` | 587 | 需开启两步验证，生成**应用专用密码** |
| Outlook / Hotmail | `smtp.office365.com` | 587 | 使用账号密码登录 |
| 163 邮箱 | `smtp.163.com` | 465 | 需在邮箱设置中开启 SMTP 并获取**授权码** |

---

### 5.3 QQ 邮箱获取授权码步骤

1. 登录 [QQ 邮箱网页版](https://mail.qq.com)
2. 进入 **设置 → 账户**
3. 找到「POP3/IMAP/SMTP 服务」，点击**开启**
4. 按提示发短信验证，获得一串授权码（如 `abcdefghijklmnop`）
5. 将授权码设置为环境变量 `TECHPULSE_SMTP_PASSWORD`

> 授权码不是 QQ 密码，每次重新生成后旧的自动失效。

---

### 5.4 不想每次手动设置环境变量

**Windows**：将密码永久写入用户环境变量（系统设置 → 高级系统设置 → 环境变量），变量名 `TECHPULSE_SMTP_PASSWORD`，这样每次运行无需重复设置。

**Linux / macOS**：写入 `~/.bashrc` 或 `~/.zshrc`：

```bash
export TECHPULSE_SMTP_PASSWORD="你的授权码"
```

---

### 5.5 关闭邮件推送

把 `config.yaml` 中 `enabled` 改回 `false` 即可，报告仍会保存到 `output/`：

```yaml
      enabled: false
```

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

## 7. 定时自动运行

### Windows 任务计划程序

先创建一个启动脚本 `run_techpulse.bat`（参考项目根目录的同名文件），在里面设置好环境变量。

然后在 PowerShell 中注册定时任务，例如每天早上 8 点运行：

```powershell
schtasks /create /tn "TechPulse" /tr "C:\your\path\tech_pulse\run_techpulse.bat" /sc daily /st 08:00 /f
```

关闭定时任务：

```powershell
# 禁用（保留任务）
schtasks /change /tn "TechPulse" /disable

# 彻底删除
schtasks /delete /tn "TechPulse" /f
```

### Linux / macOS Cron

```bash
crontab -e
```

添加（每天 09:00 执行）：

```bash
0 9 * * * cd /your/path/tech_pulse && TECHPULSE_SMTP_PASSWORD="你的授权码" python main.py >> logs/cron.log 2>&1
```

### GitHub Actions（推荐，PC 无需开机）

当前已配置 `.github/workflows/techpulse.yml`，每周一北京时间 10:00 自动运行。

**首次使用步骤：**

1. 将代码推送到 GitHub（公开或私有仓库均可）

2. 进入仓库页面 → **Settings → Secrets and variables → Actions**

3. 点击 **New repository secret**，分别添加：
   - Name：`TECHPULSE_SMTP_PASSWORD`，Secret：你的 QQ 邮箱授权码
   - Name：`DASHSCOPE_API_KEY`，Secret：你的 DashScope API Key

4. 之后每周一自动运行，无需 PC 开机

**手动触发：**

进入仓库 → **Actions → TechPulse Weekly Push → Run workflow**，可随时手动触发一次。

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

### Q1: RSS 源访问失败会怎样？

不会中断。该源会被跳过，错误会写入日志和模板报告。

### Q2: 不开 Email 可以吗？

可以。默认只生成本地 Markdown 报告。

---

## 11. 最小运行步骤

```bash
cd tech_pulse
pip install -r requirements.txt
python main.py
```

如需 AI 要点提炼，运行前先设置环境变量：

```powershell
# Windows PowerShell
$env:DASHSCOPE_API_KEY="sk-你的Key"
python main.py
```

然后查看：

```bash
ls output
cat output/techpulse_YYYY-MM-DD.md
```
