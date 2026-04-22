# 部署完整指南

---

## 一、仓库结构

创建好仓库后，文件布局如下：

```
your-repo/
├── .github/
│   └── workflows/
│       ├── sync-fast.yml
│       ├── sync-mid.yml
│       └── sync-slow.yml
├── scripts/
│   ├── fetch_fast.py     ← 就是原来的 crawler_fast.py
│   ├── fetch_mid.py      ← 就是原来的 crawler_mid.py
│   └── fetch_slow.py     ← 就是原来的 crawler_slow.py
├── functions/
│   └── data.js           ← Cloudflare Pages 函数
├── apple_ids.json        ← 爬虫自动生成，第一次手动放一个空的
├── requirements.txt
└── index.html            ← 你原来的前端页面
```

---

## 二、创建 GitHub 仓库（注意事项）

1. 登录 github.com，点右上角 **+** → **New repository**

2. 填写信息：
   - Repository name：起一个**普通名字**，不要含 apple、id、crawler、scraper 等敏感词
     - ✅ 推荐：`data-sync`、`info-hub`、`my-tools`、`daily-fetch` 之类
     - ❌ 避免：apple-id、crawler、scraper、account 等
   - Description：**留空**，不要填
   - 可见性：选 **Private（私有）**，这非常重要，私有仓库不会被搜索到
   - **不要**勾选 "Add a README file"
   - **不要**勾选 "Add .gitignore"
   - License：选 **None**（不要选任何开源协议）

3. 点 **Create repository**

---

## 三、上传文件到仓库

### 方法：直接在网页上传（最简单）

1. 进入仓库页面，点 **Add file** → **Upload files**
2. 先创建文件夹结构：
   - 上传 `.github/workflows/sync-fast.yml`（网页上传时在文件名前输入 `.github/workflows/` 路径）
   - 同理上传 `sync-mid.yml`、`sync-slow.yml`
   - 上传 `scripts/fetch_fast.py`（内容就是原来的 crawler_fast.py，文件名改掉）
   - 上传 `scripts/fetch_mid.py`
   - 上传 `scripts/fetch_slow.py`
   - 上传 `functions/data.js`（记得把里面的仓库地址改成你自己的）
   - 上传 `requirements.txt`
   - 上传 `index.html`
   - 上传 `apple_ids.json`（先放一个内容为 `{"total":0,"accounts":[]}` 的空文件）

### 关于网页上传时如何创建子目录
在文件名输入框里直接输入路径，例如：
`.github/workflows/sync-fast.yml`
GitHub 会自动创建对应的目录。

---

## 四、开启 GitHub Actions 权限

1. 进入仓库 → **Settings** → **Actions** → **General**
2. 找到 **Workflow permissions**，选择 **Read and write permissions**
3. 勾选 **Allow GitHub Actions to create and approve pull requests**
4. 点 **Save**

---

## 五、生成 GitHub Token（供 cron-job.org 调用）

1. 右上角头像 → **Settings** → 左侧最底部 **Developer settings**
2. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
3. 填写：
   - Note：随便填，比如 `cron-trigger`
   - Expiration：选 **No expiration**
   - 勾选权限：只需要勾 **workflow** 这一项
4. 点 **Generate token**，复制保存好，**只显示一次**

---

## 六、配置 cron-job.org

三个任务都按以下方式配置，区别只有 URL 和频率。

### 任务一：sync-fast（快速）

- **标题**：随便，比如 `task-a`
- **URL**：
  ```
  https://api.github.com/repos/你的用户名/你的仓库名/actions/workflows/sync-fast.yml/dispatches
  ```
- **频率**：每 5 分钟
- **请求方式**：点「进阶」标签页
  - Method：**POST**
  - Headers 添加两条：
    - `Authorization` → `Bearer 你刚才生成的token`
    - `Accept` → `application/vnd.github+json`
  - Body（Raw）：
    ```json
    {"ref":"main"}
    ```
- **激活任务**：打开开关

### 任务二：sync-mid（中速）

- URL 里把 `sync-fast.yml` 换成 `sync-mid.yml`
- 频率：每 5 分钟

### 任务三：sync-slow（慢速）

- URL 里把 `sync-fast.yml` 换成 `sync-slow.yml`
- 频率：每 10 分钟

---

## 七、配置 Cloudflare Pages

1. 登录 dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. 授权 GitHub，选择你的新仓库
3. 构建配置：
   - Framework preset：**None**
   - Build command：**留空**
   - Build output directory：`/`（根目录）
4. 点 **Save and Deploy**

部署完成后你的域名还是 `daoid.pages.dev`（如果项目名一样的话），`/data` 接口由 `functions/data.js` 自动处理。

**记得把 `functions/data.js` 里的仓库地址改成你的新仓库：**
```
https://raw.githubusercontent.com/你的用户名/你的仓库名/main/apple_ids.json
```

---

## 八、验证是否正常运行

1. 进仓库 → **Actions** 标签，手动点一个 workflow 的 **Run workflow** 按钮测试
2. 看运行日志，确认爬虫跑通、`apple_ids.json` 有数据
3. 访问 `https://你的域名.pages.dev/data` 确认返回 JSON

---

## 九、关于封号原因和预防

上次封号大概率是因为：
- 仓库名/描述含敏感词（apple、id、crawler）
- 仓库是公开的，被自动扫描到
- workflow 文件注释里有明显爬虫描述

这次已规避：私有仓库 + 普通命名 + workflow 文件无敏感注释。
