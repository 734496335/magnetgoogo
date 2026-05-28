# App 签名信息

> ⚠️ 此文件包含敏感信息，请勿公开提交到公开仓库。

## Release Keystore

| 项目 | 值 |
|------|------|
| **文件路径** | `magnetgoogo-app/android/app/magnetgoogo-release.keystore` |
| **Alias** | `magnetgoogo` |
| **Store Password** | `MagGoogo2026!` |
| **Key Password** | `MagGoogo2026!` |
| **有效期** | 2026-05-04 ~ 2053-09-19（10000天） |
| **算法** | SHA256withRSA, 2048-bit RSA |

## App 备案所需信息

| 项目 | 值 |
|------|------|
| **包名** | `com.magnetgoogo.app` |
| **证书 MD5 指纹** | `f96634881fe04c1d38ba3a9ba30b873d` |
| **证书 SHA1 指纹** | `74:2F:96:43:22:85:58:C1:4C:19:1F:77:D6:7E:E3:FD:A2:15:9D:C8` |
| **证书 SHA256 指纹** | `D0:81:20:EC:14:D7:89:C9:25:E9:46:DD:59:F3:A8:52:B6:4A:55:9B:69:89:73:2A:A5:7A:9E:8E:46:61:71:79` |
| **公钥（十六进制）** | 见下方 |

## 公钥（App 备案填写用）

```
3082010a0282010100c649b171007d6ff49a2c2aea54a9f00cc0e4ee4da9e3c7dc018e22228f90037b40b41942645d5da832885329cc18310f2b50965d67d8e9d9c27d24c21ab476f442430f873739570a0be8fb7c9e0bc919f2fed0958fc2bb386fe9096c5092e30f3abc3a9e96c49720fc1c255903901ff40087f9bb58c2afbfd1e6399d15629372676bac5a7c6ab18465cee2cbc87a5c10bc2980af820811e3bef5c2f0ef71d9a76c6532d87a0896928f0a59e0a24b35922d27fbcd96a916a7b4731c3f7733cb5c52518be558078858e2436eff97022e58d9cdf0b39dfc5a44c50f50f99213994c95466c400e51e0844839033b58a20c57fae448016453fe379e0e6a307f9b37cf0203010001
```

## 发版流程

> ⚠️ **完整发版流程已迁移至 `RELEASE-CHECKLIST.md`**，该文档为唯一权威发版指南。
>
> 包含：版本号位置索引、构建命令、分发渠道、下载链接架构（稳定链接 vs 易变链接）、
> 官网更新脚本、App 内更新机制、事故记录等。

### 仅换签名（版本号不变）

用于：修复签名问题、首次切换到正式签名。用户需卸载重装。

1. 用新 keystore 构建 release APK
2. 替换所有分发渠道的 APK 文件（阿里云、蓝奏云、GitHub Release）
3. 公告说明「本次更新需卸载重装」

## 注意事项

1. **签名不可更改**：一旦用此 keystore 发布 APK，后续所有更新必须使用同一签名，否则用户无法覆盖安装。
2. **备份 keystore**：丢失 keystore = 永远无法更新 App，请多处备份。
3. **不要提交到公开 Git**：确保 `.gitignore` 包含 `*.keystore`。
4. **之前版本（v0.1.8 及更早）** 使用的是 debug.keystore，切换到新签名后旧版本用户需要卸载重装。
5. **versionCode 只能递增**：应用商店要求每次上传的 versionCode 严格大于上一次。
