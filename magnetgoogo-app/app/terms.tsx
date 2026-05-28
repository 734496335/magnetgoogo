import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';

const URLS = {
  primary: 'https://cn.magnetgoogo.com/terms.html',
  fallback: 'https://magnetgoogo.com/terms.html',
};

export default function TermsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { t } = useLang();
  const { colors } = useTheme();
  const [url, setUrl] = useState(URLS.primary);
  const [loading, setLoading] = useState(true);
  const [retried, setRetried] = useState(false);

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t.termsTitle}</Text>
        <View style={{ width: 26 }} />
      </View>
      {loading && (
        <ActivityIndicator style={styles.loader} size="small" color={colors.text} />
      )}
      <WebView
        source={{ uri: url }}
        style={{ flex: 1 }}
        onLoadEnd={() => setLoading(false)}
        onError={() => {
          if (!retried) {
            setRetried(true);
            setUrl(URLS.fallback);
          }
        }}
        onHttpError={() => {
          if (!retried) {
            setRetried(true);
            setUrl(URLS.fallback);
          }
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fffdfb' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#262b35' },
  loader: { position: 'absolute', top: '50%', alignSelf: 'center', zIndex: 10 },
});

/* OLD INLINE CONTENT BELOW — kept as comment for reference
const TERMS_ZH = `
# 用户协议

生效日期：2026年5月2日

欢迎使用 MagGoogo（磁力古哥，以下简称"本应用"）。使用本应用即表示您已阅读、理解并同意以下条款。如不同意，请立即停止使用。

## 一、服务描述

本应用是一款磁力链接搜索聚合工具，为用户提供跨多个公开第三方网站的磁力链接搜索服务。
- 本应用不存储、托管、上传或分发任何文件内容
- 所有搜索结果来自公开的第三方磁力链接索引网站
- 磁力链接是指向分布式网络资源的标识符，本身不包含任何文件数据

## 二、使用条件

您同意仅将本应用用于合法目的，并遵守您所在国家或地区的法律法规。您不得使用本应用：
- 搜索、获取或传播侵犯他人知识产权的内容
- 搜索、获取或传播违反法律法规的内容
- 以任何方式干扰或破坏本应用的正常运行
- 对本应用进行反编译、反汇编或逆向工程（法律允许的范围除外）

## 三、知识产权

### 1. 应用知识产权
本应用的软件代码、界面设计、图标、商标等知识产权归开发者所有，受法律保护。

### 2. 搜索结果
搜索结果中展示的内容来自第三方网站，其知识产权归各自权利人所有。本应用仅提供搜索索引功能，不对搜索结果内容主张任何权利。

## 四、版权投诉

如果您认为本应用的搜索结果涉及侵犯您的版权或其他知识产权，请通过以下方式联系我们：
- 邮箱：maggoogo@outlook.com
- 请提供：权利人身份证明、侵权内容描述、权属证明材料

我们将在收到有效通知后及时处理。由于搜索结果来自第三方网站，我们建议您同时联系内容的实际托管方。

## 五、免责声明

### 1. 搜索结果
- 搜索结果由第三方网站提供，本应用不对其合法性、准确性、完整性或可用性作任何保证
- 本应用不对搜索结果中可能存在的虚假、误导或有害信息承担责任

### 2. 下载风险
- 通过磁力链接下载的文件可能包含恶意软件、病毒或其他有害内容
- 某些内容的下载和传播在您所在地区可能违反法律
- 用户应使用杀毒软件检查下载的文件
- 本应用不对因使用搜索结果或下载文件导致的任何损失承担责任

### 3. 服务可用性
- 本应用按"现状"提供，不保证服务的连续性、及时性或安全性
- 第三方数据源可能随时变更、关闭或不可用
- 本应用不对因服务中断或数据源变更导致的损失承担责任

## 六、责任限制

在法律允许的最大范围内，本应用开发者不对任何直接、间接、附带、特殊或后果性损害承担责任，无论该损害是否可预见，也无论是基于合同、侵权或其他法律理论。

## 七、协议变更

我们保留随时修改本协议的权利。变更后继续使用本应用即视为同意修改后的条款。重大变更将通过应用内公告通知。

## 八、服务终止

我们保留随时修改、暂停或终止本应用服务的权利，无需事先通知，且无需对用户或第三方承担任何责任。

## 九、适用法律

本协议的解释和执行适用中华人民共和国法律（不含冲突法规则）。因本协议产生的争议，双方应首先协商解决；协商不成的，提交开发者所在地有管辖权的人民法院解决。

## 十、其他

- 本协议构成双方之间就本应用使用事项的完整协议
- 本协议任何条款被认定无效或不可执行，不影响其余条款的效力
- 开发者未行使或延迟行使本协议项下的任何权利，不构成对该权利的放弃

## 联系方式

邮箱：maggoogo@outlook.com
`.trim();

const TERMS_EN = `
# Terms of Service

Effective Date: May 2, 2026

Welcome to MagGoogo (the "App"). By using the App, you acknowledge that you have read, understood, and agree to the following terms. If you do not agree, please stop using the App immediately.

## 1. Service Description

The App is a magnet link search aggregation tool that provides users with search services across multiple public third-party websites.
- The App does not store, host, upload, or distribute any file content
- All search results come from public third-party magnet link index websites
- Magnet links are identifiers pointing to distributed network resources and do not contain any file data themselves

## 2. Conditions of Use

You agree to use the App only for lawful purposes and in compliance with the laws of your country or region. You shall not use the App to:
- Search for, obtain, or distribute content that infringes the intellectual property rights of others
- Search for, obtain, or distribute content that violates applicable laws
- Interfere with or disrupt the normal operation of the App
- Decompile, disassemble, or reverse-engineer the App (except as permitted by law)

## 3. Intellectual Property

### App IP
The software code, interface design, icons, and trademarks of the App are owned by the developer and are protected by law.

### Search Results
Content displayed in search results originates from third-party websites. Intellectual property rights belong to the respective rights holders. The App provides only a search index function and claims no rights over search result content.

## 4. Copyright Complaints

If you believe that search results provided by the App infringe your copyright or other intellectual property rights, please contact us:
- Email: maggoogo@outlook.com
- Please provide: proof of identity, description of the infringing content, and proof of ownership

We will process valid notices promptly. Since search results come from third-party websites, we recommend also contacting the actual content host.

## 5. Disclaimers

### Search Results
- Search results are provided by third-party websites; the App makes no guarantees regarding their legality, accuracy, completeness, or availability
- The App is not responsible for false, misleading, or harmful information in search results

### Download Risks
- Files downloaded via magnet links may contain malware, viruses, or other harmful content
- Downloading certain content may violate laws in your jurisdiction
- Users should scan downloaded files with antivirus software
- The App is not liable for any losses resulting from the use of search results or downloaded files

### Service Availability
- The App is provided "as is" without warranty of continuity, timeliness, or security
- Third-party data sources may change, close, or become unavailable at any time
- The App is not liable for losses caused by service interruption or data source changes

## 6. Limitation of Liability

To the maximum extent permitted by law, the developer shall not be liable for any direct, indirect, incidental, special, or consequential damages, whether foreseeable or not, and whether based on contract, tort, or any other legal theory.

## 7. Changes to Terms

We reserve the right to modify these Terms at any time. Continued use of the App after changes constitutes acceptance of the modified Terms. Significant changes will be communicated via in-app announcements.

## 8. Service Termination

We reserve the right to modify, suspend, or terminate the App's services at any time without prior notice and without liability to users or third parties.

## 9. Governing Law

These Terms shall be governed by and construed in accordance with the laws of the People's Republic of China (excluding conflict of law rules). Any disputes arising from these Terms shall be resolved through negotiation; failing that, they shall be submitted to the competent court at the developer's location.

## 10. Miscellaneous

- These Terms constitute the entire agreement between the parties regarding the use of the App
- If any provision is held invalid or unenforceable, the remaining provisions shall remain in effect
- The developer's failure to exercise or delay in exercising any right under these Terms shall not constitute a waiver of that right

## Contact

Email: maggoogo@outlook.com
`.trim();
*/
