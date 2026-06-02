# App 签名信息

> ⚠️ 此文件包含敏感信息，请勿公开提交到公开仓库。
>
> ⛔ **绝对不要删除 keystore 文件！** 丢失 keystore = 永远无法更新 App。
> 文件路径：`magnetgoogo-app/android/app/magnetgoogo-release.keystore`
> 备份路径：`releases/magnetgoogo-release-new.keystore`

## Release Keystore（v0.1.11 起使用）

| 项目 | 值 |
|------|------|
| **文件路径** | `magnetgoogo-app/android/app/magnetgoogo-release.keystore` |
| **备份路径** | `releases/magnetgoogo-release-new.keystore` |
| **Alias** | `magnetgoogo` |
| **Store Password** | `MagGoogo2026!` |
| **Key Password** | `MagGoogo2026!` |
| **有效期** | 2026-06-01 ~ 2053-10-17（10000 天） |
| **算法** | SHA256withRSA, 2048-bit RSA |

> ⚠️ **此 keystore 与 v0.1.10 及之前版本的签名不同！**
> 之前版本（v0.1.8~v0.1.10）的 keystore 已丢失，v0.1.11 起使用此新签名。
> 旧版本用户需**卸载重装**才能升级到 v0.1.11+。

## 证书指纹（阿里云备案用）

| 项目 | 值 |
|------|------|
| **包名** | `com.magnetgoogo.app` |
| **证书 MD5 指纹** | `df1e684bf483ceffe49062d285b17c06` |
| **证书 SHA1 指纹** | `4b7b0b68ecab6c4c04d2939e861ec373596fb874` |
| **证书 SHA256 指纹** | `475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d` |

## 公钥（App 备案填写用）

```
30820122300d06092a864886f70d01010105000382010f003082010a0282010100a4db146503b86162e0d7c53694b5fadb1a4bdd948f945e49cf5d28b9f598e39ad33a110112aa08ee7797342532dd15c78320b0bb56b61d88ffb699953d7aa44a10b89dae14e9adea796283acc40496f9e1e9412fb52dfba040b858c10769cfc85b6d1b7967843d26682fbab32c01d6e5347bce93d165bec1e24788d5faa537e481cf30a9328591fb21d2005898ac6110503b4f4e9713f8e9bc1deda9e3c9794fdc3715245a4378c1f80bf5863cab4e1330e56bb57ee6798b94527d6bd4b39c34f0a71f510ad281c291af50d49d8d0696646ef038d0664772e9cb467b511428641a13aabf8f8f563c7ef23f6026ce6df335155a33f4ab9d06b6d32d73666df5b70203010001
```

## 发版流程

> ⚠️ **完整发版流程已迁移至 `RELEASE-CHECKLIST.md`**，该文档为唯一权威发版指南。

### 仅换签名（版本号不变）

用于：修复签名问题、首次切换到正式签名。用户需卸载重装。

1. 用新 keystore 构建 release APK
2. 替换所有分发渠道的 APK 文件（阿里云、蓝奏云、GitHub Release）
3. 公告说明「本次更新需卸载重装」

## 注意事项

1. **签名不可更改**：一旦用此 keystore 发布 APK，后续所有更新必须使用同一签名，否则用户无法覆盖安装。
2. **备份 keystore**：丢失 keystore = 永远无法更新 App，请多处备份。
3. **不要提交到公开 Git**：确保 `.gitignore` 包含 `*.keystore`。
4. **versionCode 只能递增**：应用商店要求每次上传的 versionCode 严格大于上一次。

## 旧版签名信息（v0.1.8 ~ v0.1.10，已废弃）

> 以下签名已不可用，keystore 文件已丢失。仅保留记录用于备案参考。

| 项目 | 值 |
|------|------|
| 证书 MD5 指纹 | `f96634881fe04c1d38ba3a9ba30b873d` |
| 证书 SHA1 指纹 | `742f9643228558c14c191f77d67ee3fda2159dc8` |
| 证书 SHA256 指纹 | `d08120ec14d789c925e946dd59f3a852b64a559b6989732aa57a9e8e46617179` |
