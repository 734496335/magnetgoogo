# v0.2.2 蓝奏云密码提示热修复

## 原因

用户反馈 v0.2.2 的 v0.2.3 更新说明虽然引导使用“备用链接 1”打开蓝奏云，但没有展示下载密码，用户进入蓝奏云后无法直接完成下载。

## 热修复内容

更新通知现明确显示：

1. 0.2.2 用户不要点击“立即更新”。
2. 点击下方“备用链接 1”，通过蓝奏云下载并安装 0.2.3。
3. **蓝奏云下载密码：8888。**
4. 保留原三条版本更新说明。

英文、西班牙语、俄语、葡萄牙语、日语、韩语、法语、德语和阿拉伯语通知也同步增加密码 8888。

## 发布结果

- mg-data 提交：`9edb4b7`
- Cloudflare Pages 部署：`https://e16f72da.magnetgoogo-site.pages.dev`
- 阿里云配置已同步，服务器解析确认第三行为“蓝奏云下载密码：8888。”
- jsDelivr `@main` 与不可变提交 `9edb4b7` 已刷新。
- 下载版本、APK、主地址和镜像顺序均未改变。

## 公网验证

以下端点均返回 `0.2.3` 且公告包含 `8888`：

- `magnetgoogo.com/config.json`
- GitHub Raw main
- `api.naoshiquan.com/config.json`
- Workers Dev Gateway
- jsDelivr `@main`
- jsDelivr `@9edb4b7`

`cn.magnetgoogo.com` 文件已正确同步，但当前外部 Windows 客户端仍出现已知 TLS 握手异常；它不参与主下载，其他权威端点已全部生效。

## K30S 真机复核

- K30S 保留数据降级安装正式 `0.2.2 / versionCode 6`：PASS。
- 更新弹窗完整显示：`蓝奏云下载密码：8888。`
- 同时显示“不点击立即更新”和“点击备用链接 1”的迁移说明。
- 点击“备用链接 1”实际打开：`https://wwbdy.lanzn.com/iDcyE3zn4rcf`。
- 验证结束后已恢复正式 `0.2.3 / versionCode 7`。
- 启动后 Fatal、ANR、缓存提交异常：0。

## 结论

`HOTFIX=LIVE / K30S_PASS`

正式 0.2.2 用户重新打开 App 后，更新弹窗会明确看到“蓝奏云下载密码：8888”。
