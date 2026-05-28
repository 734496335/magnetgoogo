> ⚠️ **本方案已于 2026-05-26 暂停**
>
> **暂停原因**：在 K30S 真机实测，标准 BT DHT bootstrap 节点（router.bittorrent.com 等）在国内网络下 UDP 不可达，10s 内 dhtNodes=0，metadata 永远无法获取。详见 DEV-LOG 同日条目。
>
> **结论**：纯本地 P2P metadata 解析在国内冷启动环境下不可行。文档保留作为后续技术参考。如需推进类似功能，请考虑：
> - HTTP cache 服务兜底（itorrents.org / btcache.me）
> - 或预置 DHT 路由表（需研究持久化方案）
> - 或仅在海外发版启用

---
# 磁力元数据本地解析功能 — 架构设计

文档版本：V1.0
更新时间：2026-05-26
负责模块：magnetgoogo-app（React Native + Android Native Module）

---

## 一、需求与约束

### 1.1 用户故事

> 用户搜索资源后，对每张结果卡片，App 自动在本地通过 P2P 网络解析磁力链接，获取真实的文件列表、文件类型、创建时间等元数据，提升用户判断"这是不是我想要的资源"的能力。

### 1.2 功能边界

| 必须做 | 不做 |
|---|---|
| 本地 P2P 获取 metadata（不走自建服务器）| 不实际下载文件内容 |
| 自动解析 + 手动触发兜底 | 不做后台预热 |
| 解析失败优雅降级 | 不重试（避免 DHT 滥用）|
| 内存缓存解析结果 | 不做磁盘持久化（避免占用空间）|
| 串行队列控制资源 | 不并发解析（避免 CPU/内存峰值）|

### 1.3 关键约束

1. **零服务器依赖**：所有解析在用户手机本地完成
2. **不卡顿**：UI 主线程 0 阻塞，Native 后台异步
3. **锦上添花**：现有搜索流程完全不变，解析失败用户无感
4. **APK 体积**：增加不超过 8MB
5. **隐私**：解析过程不上传任何用户数据到服务器

---

## 二、用户体验设计

### 2.1 卡片状态机

```
┌──────────────────────────────────────────────┐
│  IDLE         初始态（搜索结果刚出来）         │
│   │                                          │
│   ↓ 进入可视区域                              │
│  PENDING      排队中（队列里等待）             │
│   │                                          │
│   ↓ 队列轮到自己                              │
│  RESOLVING    解析中（小 loading 指示器）      │
│   │                                          │
│   ├─→ SUCCESS    解析成功                    │
│   │     - 卡片信息更新                        │
│   │     - 显示"展开文件列表"按钮               │
│   │                                          │
│   └─→ FAILED     解析失败/超时                │
│         - 静默降级                            │
│         - 显示"🧲 解析磁力"手动按钮            │
└──────────────────────────────────────────────┘
```

### 2.2 卡片视觉规范

**IDLE 态（默认）**：
```
┌─────────────────────────────────────┐
│ Inception.2010.1080p.BrRip.x264     │
│ 1.85 GB · Seeds: 156                │
│ [复制磁力] [打开]                     │
└─────────────────────────────────────┘
```

**RESOLVING 态**：
```
┌─────────────────────────────────────┐
│ Inception.2010.1080p.BrRip.x264   ⠋ │  ← 极简旋转点（不抢眼）
│ 1.85 GB · Seeds: 156                │
│ [复制磁力] [打开]                     │
└─────────────────────────────────────┘
```

**SUCCESS 态**：
```
┌─────────────────────────────────────┐
│ Inception.2010.1080p.BrRip.x264     │
│ 🎬 MKV · 3 文件 · 1.85 GB · 2024-03 │  ← 增强信息行
│ [复制磁力] [打开] [▾ 文件列表]       │
└─────────────────────────────────────┘
```

**SUCCESS + 展开**：
```
┌─────────────────────────────────────┐
│ Inception.2010.1080p.BrRip.x264     │
│ 🎬 MKV · 3 文件 · 1.85 GB · 2024-03 │
│ [复制磁力] [打开] [▴ 收起]           │
│ ┌─────────────────────────────────┐ │
│ │ 🎬 Inception.2010.1080p.mkv   1.82G│ │
│ │ 📄 Inception.srt              52KB│ │
│ │ 📄 Inception.nfo               3KB│ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

**FAILED 态**：
```
┌─────────────────────────────────────┐
│ Inception.2010.1080p.BrRip.x264     │
│ 1.85 GB · Seeds: 156                │
│ [复制磁力] [打开] [🧲 解析磁力]      │  ← 手动触发按钮
└─────────────────────────────────────┘
```

### 2.3 交互细则

| 场景 | 行为 |
|---|---|
| 卡片进入屏幕（首次） | 进入 PENDING → RESOLVING |
| 卡片滚出屏幕 | 不取消解析（已经在跑就让它跑完）|
| 解析中切换关键词 | 队列清空，正在跑的让它跑完（避免崩溃）|
| 用户点击"🧲 解析磁力" | FAILED → RESOLVING（再试一次）|
| 用户点击"▾ 文件列表" | 展开/收起（带 LayoutAnimation 过渡）|
| 同一 magnet 二次出现 | 直接命中缓存，无 loading |
| App 切后台 | 解析继续，新任务不入队 |
| App 切回前台 | 恢复正常入队 |



---

## 三、技术架构

### 3.1 分层结构

```
┌────────────────────────────────────────────┐
│  React Native UI 层                         │
│  ────────────────────────────                │
│  components/SearchResultCard.tsx            │  ← 卡片组件（状态机渲染）
│  app/search.tsx                             │  ← 搜索页（队列触发）
└────────────────────────────────────────────┘
              ↕ 订阅状态变化
┌────────────────────────────────────────────┐
│  JS 业务层（src/core/）                      │
│  ────────────────────────────                │
│  metadataResolver.ts                        │  ← 队列调度 + 缓存 + JS 接口
│  metadataTypes.ts                           │  ← 类型定义
└────────────────────────────────────────────┘
              ↕ ReactMethod (Promise 异步)
┌────────────────────────────────────────────┐
│  Android Native 层（Kotlin）                 │
│  ────────────────────────────                │
│  TorrentMetadataModule.kt                   │  ← Native Module 入口
│  TorrentMetadataPackage.kt                  │  ← 注册到 RN
└────────────────────────────────────────────┘
              ↕ JNI
┌────────────────────────────────────────────┐
│  jlibtorrent (.aar)                         │
│  ────────────────────────────                │
│  - SessionManager                           │
│  - DHT 路由表                                │
│  - peer 连接管理                              │
│  - ut_metadata 协议                          │
└────────────────────────────────────────────┘
              ↕ TCP/UDP
┌────────────────────────────────────────────┐
│  BitTorrent P2P 网络                        │
│  - DHT 节点（全球分布）                       │
│  - 持有资源的 peer                            │
└────────────────────────────────────────────┘
```

### 3.2 核心数据流

```
用户搜索
   ↓
搜索引擎返回 SearchResult[]（含 magnet URI）
   ↓
FlatList 渲染，可见卡片触发 enqueue(magnetUri)
   ↓
metadataResolver 队列：检查缓存 → 未命中则入队
   ↓
串行处理：调用 NativeModule.resolveMetadata(uri, 15000)
   ↓
Native 线程：jlibtorrent 通过 DHT 找 peer → ut_metadata 交换
   ↓
返回文件列表 → JS 缓存 → 通知订阅者（卡片）
   ↓
卡片重新渲染（IDLE → SUCCESS）
```

---

## 四、模块详细设计

### 4.1 Native Module（TorrentMetadataModule.kt）

**职责**：封装 jlibtorrent 的 metadata 获取，提供 Promise 风格的异步接口给 JS。

**核心 API**：
```kotlin
class TorrentMetadataModule(reactContext: ReactApplicationContext)
    : ReactContextBaseJavaModule(reactContext) {

    override fun getName() = "TorrentMetadata"

    // 单例 SessionManager（避免重复创建）
    companion object {
        private var sessionManager: SessionManager? = null
        private val executor = Executors.newSingleThreadExecutor()  // 串行执行
    }

    @ReactMethod
    fun resolveMetadata(magnetUri: String, timeoutMs: Int, promise: Promise) {
        executor.submit {
            try {
                val session = ensureSession()
                val data = session.fetchMagnet(magnetUri, timeoutMs / 1000)

                if (data != null) {
                    val ti = TorrentInfo.bdecode(data)
                    val result = WritableNativeMap().apply {
                        putString("name", ti.name())
                        putDouble("totalSize", ti.totalSize().toDouble())
                        putInt("numFiles", ti.numFiles())
                        putDouble("creationDate", ti.creationDate().toDouble())
                        putString("comment", ti.comment() ?: "")

                        val filesArray = WritableNativeArray()
                        val fs = ti.files()
                        for (i in 0 until fs.numFiles()) {
                            filesArray.pushMap(WritableNativeMap().apply {
                                putString("path", fs.filePath(i))
                                putString("name", fs.fileName(i))
                                putDouble("size", fs.fileSize(i).toDouble())
                            })
                        }
                        putArray("files", filesArray)
                    }
                    promise.resolve(result)
                } else {
                    promise.reject("TIMEOUT", "Metadata fetch timed out after ${timeoutMs}ms")
                }
            } catch (e: Exception) {
                promise.reject("ERROR", e.message ?: "Unknown error", e)
            }
        }
    }

    @ReactMethod
    fun stopSession(promise: Promise) {
        sessionManager?.stop()
        sessionManager = null
        promise.resolve(true)
    }

    private fun ensureSession(): SessionManager {
        if (sessionManager == null) {
            sessionManager = SessionManager().apply {
                start(SessionParams(SettingsPack().apply {
                    setString(settings_pack.string_types.user_agent.swigValue(),
                              "MagnetGoogo/1.0")
                    setBoolean(settings_pack.bool_types.enable_dht.swigValue(), true)
                    setBoolean(settings_pack.bool_types.enable_lsd.swigValue(), true)
                    setBoolean(settings_pack.bool_types.enable_upnp.swigValue(), true)
                    setInteger(settings_pack.int_types.connections_limit.swigValue(), 50)
                    setInteger(settings_pack.int_types.dht_announce_interval.swigValue(), 60)
                }))
            }
        }
        return sessionManager!!
    }
}
```

**关键设计点**：
- 单例 SessionManager：跨多次调用复用 DHT 路由表，第二次解析比第一次快
- 单线程 executor：确保 Native 层也是串行（防止 jlibtorrent 资源竞争）
- `fetchMagnet` 是 jlibtorrent 内置 API，自动处理 DHT 查找 + ut_metadata 交换
- Promise reject 时携带错误码，JS 层可区分 TIMEOUT / ERROR

### 4.2 JS 层（metadataResolver.ts）

**职责**：队列管理、缓存、订阅模式让卡片响应状态变化。

**核心类型**：
```typescript
// metadataTypes.ts
export type ResolveStatus = 'idle' | 'pending' | 'resolving' | 'success' | 'failed';

export interface FileEntry {
  path: string;
  name: string;
  size: number;
}

export interface TorrentMetadata {
  name: string;
  totalSize: number;
  numFiles: number;
  creationDate: number;  // Unix timestamp
  comment: string;
  files: FileEntry[];
}

export interface ResolveState {
  status: ResolveStatus;
  metadata?: TorrentMetadata;
  error?: string;
  timestamp: number;
}
```

**核心逻辑**：
```typescript
// metadataResolver.ts
import { NativeModules } from 'react-native';

const { TorrentMetadata } = NativeModules;

const TIMEOUT_MS = 15000;
const CACHE_SIZE = 50;     // LRU 容量
const QUEUE_MAX = 30;      // 队列上限（防积压）

class MetadataResolver {
  private cache = new Map<string, ResolveState>();
  private queue: string[] = [];
  private running = false;
  private listeners = new Set<(hash: string) => void>();

  // ===== 公共 API =====

  enqueue(magnetUri: string, manual = false) {
    const hash = extractInfoHash(magnetUri);
    if (!hash) return;

    const cached = this.cache.get(hash);
    if (cached?.status === 'success') return;  // 已成功无需再做
    if (cached?.status === 'resolving') return;  // 正在解析

    // 手动触发：失败后允许重试
    if (cached?.status === 'failed' && !manual) return;

    this._setState(hash, { status: 'pending', timestamp: Date.now() });

    if (this.queue.includes(magnetUri)) return;
    if (this.queue.length >= QUEUE_MAX) {
      this.queue.shift();  // 丢弃最老的
    }
    this.queue.push(magnetUri);
    this._processNext();
  }

  getState(magnetUri: string): ResolveState | null {
    const hash = extractInfoHash(magnetUri);
    return hash ? this.cache.get(hash) || null : null;
  }

  subscribe(fn: (hash: string) => void): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  clearQueue() {
    this.queue = [];  // 不影响正在跑的
  }

  // ===== 私有方法 =====

  private async _processNext() {
    if (this.running || this.queue.length === 0) return;
    this.running = true;

    const uri = this.queue.shift()!;
    const hash = extractInfoHash(uri)!;

    this._setState(hash, { status: 'resolving', timestamp: Date.now() });

    try {
      const metadata = await TorrentMetadata.resolveMetadata(uri, TIMEOUT_MS);
      this._setState(hash, {
        status: 'success',
        metadata,
        timestamp: Date.now(),
      });
    } catch (err: any) {
      this._setState(hash, {
        status: 'failed',
        error: err?.code || err?.message || 'unknown',
        timestamp: Date.now(),
      });
    } finally {
      this.running = false;
      // LRU 淘汰
      if (this.cache.size > CACHE_SIZE) {
        const oldest = this.cache.keys().next().value;
        this.cache.delete(oldest);
      }
      // 处理下一个
      setTimeout(() => this._processNext(), 50);
    }
  }

  private _setState(hash: string, state: ResolveState) {
    this.cache.set(hash, state);
    this.listeners.forEach(fn => fn(hash));
  }
}

// 单例
export const metadataResolver = new MetadataResolver();

// React Hook 封装
export function useMetadata(magnetUri: string): ResolveState | null {
  const [state, setState] = useState(() => metadataResolver.getState(magnetUri));

  useEffect(() => {
    const targetHash = extractInfoHash(magnetUri);
    if (!targetHash) return;

    return metadataResolver.subscribe((hash) => {
      if (hash === targetHash) {
        setState(metadataResolver.getState(magnetUri));
      }
    });
  }, [magnetUri]);

  return state;
}

function extractInfoHash(magnetUri: string): string | null {
  const m = magnetUri.match(/xt=urn:btih:([a-fA-F0-9]{40}|[A-Z2-7]{32})/i);
  return m ? m[1].toLowerCase() : null;
}
```



### 4.3 UI 层（SearchResultCard.tsx）

**职责**：根据 metadata 状态渲染卡片不同形态，处理用户交互。

**核心结构**：
```typescript
function SearchResultCard({ result }: { result: SearchResult }) {
  const meta = useMetadata(result.magnet);
  const [expanded, setExpanded] = useState(false);

  const status = meta?.status || 'idle';

  return (
    <View style={styles.card}>
      {/* 标题行 */}
      <View style={styles.titleRow}>
        <Text style={styles.title} numberOfLines={2}>
          {result.title}
        </Text>
        {status === 'resolving' && (
          <ActivityIndicator size="small" style={styles.spinner} />
        )}
      </View>

      {/* 信息行：成功后用 metadata，失败用原始 */}
      {status === 'success' && meta?.metadata ? (
        <Text style={styles.info}>
          {fileTypeIcon(meta.metadata)} {fileTypeLabel(meta.metadata)} ·{' '}
          {meta.metadata.numFiles} 文件 ·{' '}
          {formatSize(meta.metadata.totalSize)}
          {meta.metadata.creationDate > 0 && ` · ${formatDate(meta.metadata.creationDate)}`}
        </Text>
      ) : (
        <Text style={styles.info}>
          {result.size || '未知大小'}
          {result.seeds != null && ` · Seeds: ${result.seeds}`}
        </Text>
      )}

      {/* 操作按钮 */}
      <View style={styles.actions}>
        <Btn icon="copy" label="复制磁力" onPress={...} />
        <Btn icon="open" label="打开" onPress={...} />

        {status === 'success' && (
          <Btn
            icon={expanded ? 'chevron-up' : 'chevron-down'}
            label={expanded ? '收起' : '文件列表'}
            onPress={() => {
              LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
              setExpanded(!expanded);
            }}
          />
        )}

        {(status === 'failed' || status === 'idle') && (
          <Btn
            icon="magnet"
            label="解析磁力"
            onPress={() => metadataResolver.enqueue(result.magnet, true)}
          />
        )}
      </View>

      {/* 展开的文件列表 */}
      {expanded && status === 'success' && meta?.metadata && (
        <FileList files={meta.metadata.files} />
      )}
    </View>
  );
}
```

**FileList 组件**：
```typescript
function FileList({ files }: { files: FileEntry[] }) {
  const sorted = [...files].sort((a, b) => b.size - a.size);  // 大文件在上

  return (
    <View style={styles.fileList}>
      {sorted.map((f, i) => (
        <View key={i} style={styles.fileRow}>
          <Text style={styles.fileIcon}>{fileIconByExt(f.name)}</Text>
          <Text style={styles.fileName} numberOfLines={1}>{f.name}</Text>
          <Text style={styles.fileSize}>{formatSize(f.size)}</Text>
        </View>
      ))}
    </View>
  );
}

function fileIconByExt(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase();
  if (['mkv', 'mp4', 'avi', 'mov', 'flv', 'wmv'].includes(ext!)) return '🎬';
  if (['mp3', 'flac', 'wav', 'aac', 'm4a'].includes(ext!)) return '🎵';
  if (['srt', 'ass', 'ssa', 'sub', 'vtt'].includes(ext!)) return '💬';
  if (['jpg', 'png', 'gif', 'webp', 'bmp'].includes(ext!)) return '🖼️';
  if (['pdf', 'epub', 'mobi', 'txt', 'doc', 'docx'].includes(ext!)) return '📄';
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext!)) return '📦';
  if (['exe', 'apk', 'msi', 'dmg'].includes(ext!)) return '⚠️';  // 警告
  if (['nfo'].includes(ext!)) return '📋';
  return '📁';
}

function fileTypeLabel(meta: TorrentMetadata): string {
  // 主类型：找最大的文件
  const largest = [...meta.files].sort((a, b) => b.size - a.size)[0];
  if (!largest) return '未知';
  return largest.name.split('.').pop()?.toUpperCase() || '未知';
}
```

### 4.4 search.tsx 集成

**职责**：搜索完成后批量入队 + FlatList 可见性触发。

```typescript
// search.tsx 关键改动
import { metadataResolver } from '../src/core/metadataResolver';
import { useEffect, useRef } from 'react';

export default function SearchScreen() {
  // ... 现有逻辑

  // 搜索完成时清空旧队列（避免老结果继续解析）
  useEffect(() => {
    if (results.length === 0) return;

    metadataResolver.clearQueue();

    // 仅对前 5 个自动入队（其他靠 viewability 触发）
    results.slice(0, 5).forEach(r => {
      if (r.magnet) metadataResolver.enqueue(r.magnet);
    });
  }, [searchId]);  // 每次新搜索时触发

  // FlatList viewability：可见的卡片自动入队
  const onViewableItemsChanged = useRef(({ viewableItems }) => {
    viewableItems.forEach((vi) => {
      const result = vi.item;
      if (result?.magnet) metadataResolver.enqueue(result.magnet);
    });
  }).current;

  const viewabilityConfig = useRef({
    itemVisiblePercentThreshold: 50,  // 卡片可见超过 50% 才触发
    minimumViewTime: 300,              // 至少可见 300ms（避免快速滚动触发）
  }).current;

  return (
    <FlatList
      data={results}
      renderItem={({ item }) => <SearchResultCard result={item} />}
      onViewableItemsChanged={onViewableItemsChanged}
      viewabilityConfig={viewabilityConfig}
      // ...
    />
  );
}
```

---

## 五、性能策略

### 5.1 不卡顿的关键设计

| 设计点 | 实现 | 效果 |
|---|---|---|
| Native 异步 | Kotlin `Executors.newSingleThreadExecutor()` | JS 线程零阻塞 |
| 串行队列 | JS 层 `running` 标志位 | 同时只 1 个 metadata 在跑 |
| 单例 Session | jlibtorrent SessionManager 跨调用复用 | 第二次解析快 50% |
| 可见性触发 | FlatList `onViewableItemsChanged` | 只解析用户看得到的 |
| LRU 缓存 | Map + 50 条上限 | 避免内存膨胀 |
| 队列上限 | QUEUE_MAX=30 | 防止积压 |
| 短超时 | 15s | 失败快速降级 |
| 不重试 | 失败即标记 FAILED | 避免 DHT 滥用 |

### 5.2 资源消耗预估

| 维度 | 预估 |
|---|---|
| APK 体积增加 | jlibtorrent.aar：~5MB（双架构 arm64+armv7） |
| 内存占用 | SessionManager idle ~15MB / 活跃解析 ~30MB |
| CPU（解析中）| 单核 5-15%（DHT 查询为主，CPU 不密集）|
| CPU（idle）| < 1% |
| 流量（每次解析）| 50-200KB（DHT 路由 + metadata 包）|
| 电池 | 可忽略（短任务，无持续后台） |

### 5.3 异常场景处理

| 场景 | 处理 |
|---|---|
| jlibtorrent crash | Native 层 try-catch，promise.reject，App 不崩溃 |
| Session 内存泄漏 | App 切后台 5min 后自动 stopSession |
| DHT 节点不可达（极端网络）| 15s 超时 → 标记 FAILED → 显示手动按钮 |
| 同一 hash 在两个搜索都出现 | 缓存命中，直接显示 |
| 用户快速切换关键词 | clearQueue() 清空待办，正在跑的让它跑完 |
| info hash 格式异常 | extractInfoHash 返回 null，不入队 |
| 系统内存不足 | LRU 提前淘汰，最坏情况降级为 idle |



---

## 六、开发计划

### Day 1：Native 层验证（4-6h）

**目标**：jlibtorrent 集成 + 单个 hash 解析跑通

任务：
- [ ] `android/app/build.gradle` 加 jlibtorrent 依赖
- [ ] 创建 `TorrentMetadataModule.kt` 骨架
- [ ] 创建 `TorrentMetadataPackage.kt` 注册到 `MainApplication.kt`
- [ ] 写一个 dev 测试：用已知 hash 调用 `resolveMetadata`，看 logcat 输出
- [ ] 验证耗时在 5-15s 范围内，APK 增量在 5MB 内

**验收**：在 K30S 上调用，能拿到 Inception 的文件列表（可在 console.log 看）

### Day 2：JS 层 + 队列调度（4-6h）

**目标**：metadataResolver 单例 + useMetadata hook 跑通

任务：
- [ ] `src/core/metadataTypes.ts` 类型定义
- [ ] `src/core/metadataResolver.ts` 队列 + 缓存 + 订阅
- [ ] `extractInfoHash` 工具函数 + 单测
- [ ] 在 search.tsx 临时加一个测试入口验证

**验收**：搜索后用 React DevTools 看 metadataResolver 状态变化

### Day 3：UI 集成 + 卡片状态机（4-6h）

**目标**：用户能看到完整体验

任务：
- [ ] 提取 `SearchResultCard.tsx` 组件
- [ ] 接入 useMetadata hook
- [ ] 状态机渲染（IDLE/RESOLVING/SUCCESS/FAILED）
- [ ] FileList 子组件 + 文件类型图标
- [ ] LayoutAnimation 展开/收起
- [ ] 手动"解析磁力"按钮

**验收**：K30S 实测，搜索 "inception"，至少 3 张卡片显示文件列表

### Day 4：FlatList 集成 + 性能调优（2-4h）

**目标**：滚动流畅，无卡顿

任务：
- [ ] FlatList `onViewableItemsChanged` 触发入队
- [ ] 切换搜索时 `clearQueue()`
- [ ] App 切后台时 `stopSession()`（避免后台耗电）
- [ ] 测试：连续搜 5 次，滑动列表，无掉帧
- [ ] 看 `adb shell dumpsys meminfo` 内存稳定

**验收**：CPU profiler 看 JS 线程无尖刺，FPS 稳定 60

### Day 5：边界 + 容错 + 发版（2-4h）

任务：
- [ ] 异常场景测试（断网/超时/恶意 hash）
- [ ] 国际化（"解析磁力"/"文件列表" 多语言）
- [ ] DEV-LOG.md 更新
- [ ] 打 debug APK 实测
- [ ] release APK 构建

---

## 七、修改/新增文件清单

```
新增（Android Native）：
+ magnetgoogo-app/android/app/src/main/java/com/magnetgoogo/
    + TorrentMetadataModule.kt        (~150 行)
    + TorrentMetadataPackage.kt       (~30 行)

新增（JS 层）：
+ magnetgoogo-app/src/core/metadataTypes.ts          (~30 行)
+ magnetgoogo-app/src/core/metadataResolver.ts       (~150 行)
+ magnetgoogo-app/src/components/SearchResultCard.tsx (~200 行)
+ magnetgoogo-app/src/components/FileList.tsx        (~80 行)

修改：
~ magnetgoogo-app/android/app/build.gradle           (加依赖)
~ magnetgoogo-app/android/app/src/main/java/.../MainApplication.kt  (注册 Package)
~ magnetgoogo-app/app/search.tsx                     (集成队列触发)
~ magnetgoogo-app/src/core/i18n.ts                   (新增文案)
~ docs/project-nebula/DEV-LOG.md                     (记录)
```

---

## 八、验收标准

### 功能验收

- [ ] 搜索"inception"，前 5 张卡片自动显示 loading 然后变成成功态
- [ ] 成功的卡片显示：主文件类型 / 文件数 / 总大小 / 创建时间
- [ ] 点击"文件列表"展开，显示按大小降序的文件清单
- [ ] 文件按类型显示图标（视频/字幕/文档等）
- [ ] 解析失败的卡片显示"🧲 解析磁力"按钮
- [ ] 点击手动按钮重新触发解析
- [ ] 同一 hash 二次出现命中缓存，无 loading

### 性能验收

- [ ] 搜索响应时间不变（基线对比）
- [ ] 列表滚动 FPS ≥ 55
- [ ] CPU profiler JS 线程无 > 50ms 的长任务
- [ ] 内存峰值 ≤ 150MB
- [ ] APK 体积增加 ≤ 8MB

### 容错验收

- [ ] 飞行模式下解析全部失败，UI 不卡死
- [ ] 解析中切换关键词，UI 立即响应
- [ ] App 切后台再切回，状态正确恢复
- [ ] 连续搜索 10 次，无内存泄漏（meminfo）

---

## 九、风险与未决

| 风险 | 影响 | 应对 |
|---|---|---|
| jlibtorrent 版本不兼容 RN 0.74 | 高 | 先用 1.2.x 稳定版，必要时 fork |
| 国内 DHT 实际成功率低于预期 | 中 | 手动按钮兜底，长期可加 cache API fallback |
| Hermes 引擎与 jlibtorrent JNI 冲突 | 低 | RN 标准 Native Module 流程，已有先例 |
| 多线程导致 SessionManager 状态混乱 | 中 | Native 层用单线程 executor 串行 |
| 用户网络很慢导致大量 timeout | 低 | 15s 超时已较激进，再短会误伤 |

---

## 十、上线策略

- **阶段 1**：debug 版本内部测试（K30S + 1-2 台真机）
- **阶段 2**：发 v0.1.11 灰度（仅官网下载渠道，10% 覆盖）
- **阶段 3**：全量发版（所有下载渠道）
- **回滚机制**：feature flag 在 `complianceConfig.ts` 加 `METADATA_RESOLVE_ENABLED`，远程 `config.json` 可关闭

---

> **文档状态**：架构设计完成，可进入 Day 1 开发。
> **配套文档**：`DEV-LOG.md`（开发日志），`CODE-STANDARDS.md`（代码规范）
