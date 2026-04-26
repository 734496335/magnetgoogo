import React from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';

const PRIVACY_ZH = `
# 隐私协议与免责声明

最后更新：2026年4月26日

## 一、隐私政策

### 1. 信息收集
MagGoogo（以下简称"本应用"）**不收集**任何个人身份信息。
- 本应用不要求注册或登录
- 本应用不收集姓名、邮箱、手机号等个人信息
- 搜索历史和收藏数据仅存储在您的设备本地，不会上传至服务器

### 2. 网络请求
本应用在运行时会发起以下网络请求：
- 从配置服务器获取应用配置信息（版本检查）
- 从第三方磁力链接索引网站搜索公开信息
- 所有请求均从您的设备直接发起，不经过本应用服务器代理

### 3. 数据存储
- 搜索历史：存储在设备本地（AsyncStorage），可随时清除
- 收藏数据：存储在设备本地，可随时删除
- 源数据缓存：存储在设备安全存储中，应用卸载后自动删除

### 4. 第三方服务
本应用使用以下第三方基础设施：
- Cloudflare Workers：用于配置分发和版本检查
- GitHub：用于源数据托管
- 以上服务各自有独立的隐私政策

## 二、免责声明

### 1. 搜索工具性质
本应用是一款**磁力链接搜索聚合工具**，类似于搜索引擎：
- 本应用不存储、托管、上传或分发任何文件内容
- 所有搜索结果来自公开的第三方网站
- 磁力链接仅为指向分布式网络资源的标识符

### 2. 内容责任
- 搜索结果由第三方网站提供，本应用不对其内容的合法性、准确性或完整性承担责任
- 用户应自行判断搜索结果的合法性，并遵守所在地区的法律法规
- 如有版权方认为搜索结果侵犯其权利，请联系对应的第三方网站处理

### 3. 用户责任
- 用户应对使用本应用的行为及后果承担全部责任
- 用户不应将本应用用于任何违法目的
- 用户应遵守当地关于数字内容获取和使用的法律法规

### 4. 风险提示
- 通过磁力链接下载的文件可能包含恶意软件，请使用杀毒软件检查
- 某些内容的下载和传播在您所在的国家或地区可能违反法律
- 本应用不对因使用搜索结果而导致的任何损失承担责任

### 5. 服务变更
本应用保留随时修改、暂停或终止服务的权利，无需事先通知。

## 三、联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。
`.trim();

const PRIVACY_EN = `
# Privacy Policy & Disclaimer

Last updated: April 26, 2026

## I. Privacy Policy

### 1. Information Collection
MagGoogo (the "App") does **not collect** any personally identifiable information.
- No registration or login is required
- No personal information (name, email, phone) is collected
- Search history and favorites are stored locally on your device only

### 2. Network Requests
The App makes the following network requests during operation:
- Configuration checks from a configuration server (version checking)
- Searches on third-party magnet link index websites for public information
- All requests are made directly from your device; no server proxy is involved

### 3. Data Storage
- Search history: Stored locally (AsyncStorage), clearable at any time
- Favorites: Stored locally, deletable at any time
- Source cache: Stored in device secure storage, auto-deleted on uninstall

### 4. Third-party Services
The App uses the following third-party infrastructure:
- Cloudflare Workers: Configuration distribution and version checking
- GitHub: Source data hosting
- Each service has its own independent privacy policy

## II. Disclaimer

### 1. Search Tool Nature
This App is a **magnet link search aggregator**, similar to a search engine:
- The App does not store, host, upload, or distribute any file content
- All search results come from public third-party websites
- Magnet links are merely identifiers pointing to distributed network resources

### 2. Content Liability
- Search results are provided by third-party websites; the App assumes no responsibility for their legality, accuracy, or completeness
- Users should independently assess the legality of search results and comply with local laws
- Copyright holders who believe results infringe their rights should contact the respective third-party websites

### 3. User Responsibility
- Users bear full responsibility for their use of the App and its consequences
- Users shall not use the App for any illegal purposes
- Users must comply with local laws regarding digital content acquisition and use

### 4. Risk Warning
- Files downloaded via magnet links may contain malware; please use antivirus software
- Downloading certain content may violate laws in your country or region
- The App is not liable for any losses resulting from the use of search results

### 5. Service Changes
The App reserves the right to modify, suspend, or terminate the service at any time without prior notice.

## III. Contact

For questions or suggestions, please contact us via GitHub Issues.
`.trim();

export default function PrivacyScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { lang, t } = useLang();
  const { colors } = useTheme();
  const content = lang === 'zh' ? PRIVACY_ZH : PRIVACY_EN;

  // Simple markdown-ish renderer
  const renderContent = () => {
    return content.split('\n').map((line, i) => {
      if (line.startsWith('# ')) {
        return <Text key={i} style={styles.h1}>{line.slice(2)}</Text>;
      }
      if (line.startsWith('## ')) {
        return <Text key={i} style={styles.h2}>{line.slice(3)}</Text>;
      }
      if (line.startsWith('### ')) {
        return <Text key={i} style={styles.h3}>{line.slice(4)}</Text>;
      }
      if (line.startsWith('- ')) {
        return (
          <View key={i} style={styles.bullet}>
            <Text style={styles.bulletDot}>•</Text>
            <Text style={styles.body}>{line.slice(2).replace(/\*\*(.*?)\*\*/g, '$1')}</Text>
          </View>
        );
      }
      if (line.trim() === '') {
        return <View key={i} style={{ height: 8 }} />;
      }
      return <Text key={i} style={styles.body}>{line.replace(/\*\*(.*?)\*\*/g, '$1')}</Text>;
    });
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t.privacyTitle}</Text>
        <View style={{ width: 26 }} />
      </View>
      <ScrollView contentContainerStyle={styles.scroll}>
        {renderContent()}
      </ScrollView>
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
  scroll: { padding: 20, paddingBottom: 60 },
  h1: { fontSize: 20, fontWeight: '800', color: '#262b35', marginBottom: 16, marginTop: 8 },
  h2: { fontSize: 17, fontWeight: '700', color: '#374151', marginTop: 20, marginBottom: 8 },
  h3: { fontSize: 15, fontWeight: '600', color: '#4B5563', marginTop: 12, marginBottom: 4 },
  body: { fontSize: 14, lineHeight: 22, color: '#6B7280', marginBottom: 2 },
  bullet: { flexDirection: 'row', paddingLeft: 8, gap: 6, marginBottom: 2 },
  bulletDot: { fontSize: 14, color: '#9CA3AF', lineHeight: 22 },
});
