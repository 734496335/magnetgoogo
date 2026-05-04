# MagGoogo 运营后台

> 本地管理面板，用于查看数据源状态、运营数据分析、版本控制、用户反馈。

## 一键启动

双击项目根目录的 `start-admin.bat`，自动启动服务并打开浏览器。

```
地址: http://localhost:3800
```

手动启动：

```bash
cd admin-server
node server.js
# 浏览器打开 http://localhost:3800
```

## 依赖

- **Node.js** ≥ 18（仅 express + cors，无需构建）
- 首次运行时 bat 脚本会自动 `npm install`

## 功能一览

| Tab | 内容 |
|-----|------|
| **概览** | 源总数/版本号/APK大小/CDN地址/一键发布（加密+推送） |
| **数据分析** | 设备数/搜索量/事件趋势/热词TOP20/源性能排行/版本&地区分布 |
| **版本控制** | 最新版本/强制更新线/公告/下载地址/源有效期 |
| **用户反馈** | 来自 App 端的反馈列表，支持删除 |
| **数据源** | 四个子标签（见下） |

### 数据源子标签

| 子Tab | 内容 |
|-------|------|
| **概览** | 6统计卡(总/Green/Yellow/Gray/独立来源/品牌数) + 能力统计 + 状态明细分布条 + Green独立来源速览 |
| **品牌** | 品牌卡片网格，按状态着色，筛选(有绿/有黄/纯灰) + 搜索，点击跳转列表 |
| **列表** | 完整规则表(9列)，支持搜索/状态筛选/列排序，品牌列可点击聚焦 |
| **导航与发布页** | 发布页(29个) + 导航站(34个) + 工具(4个)，URL可直接点击访问 |

## 数据来源

- **sources.json** — 数据源规则和健康状态（本地文件，修改后实时生效）
- **CF Gateway** — 埋点数据（通过 `api.naoshiquan.com` 代理拉取）
- **mg-data/config.json** — App 配置文件

## 文件结构

```
admin-server/
  server.js          # Express 后端（API + 静态页面服务）
  package.json       # 依赖声明
admin_templates/
  dashboard.html     # 单文件前端（Alpine.js + TailwindCSS CDN + Chart.js）
start-admin.bat      # 一键启动脚本
```

## 注意事项

- 埋点数据分析需要网络连接（CF Gateway）
- 一键发布功能需要 `encrypt_sources.py` 和 `mg-data` 仓库存在
- 本面板不含认证，仅限本地使用
