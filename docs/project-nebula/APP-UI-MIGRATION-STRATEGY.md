# magnetgoogo UI 迁移策略

文档版本：v0.1
更新时间：2026-04-25

## 1. 目标

本次高保真 UI 重构不把页面写成一次性网页，而是把 UI 资产拆成可迁移结构，减少后续迁 App 时的重复开发。

## 2. 当前拆分原则

前端已按 4 层拆分：

1. `tokens`
2. `presenter / model`
3. `components`
4. `page composition`

对应目录：

- `web/src/features/magnetgoogo/tokens.ts`
- `web/src/features/magnetgoogo/models.ts`
- `web/src/features/magnetgoogo/components/*`
- `web/src/app/page.tsx`

## 3. 为什么这样拆

### 3.1 token 可迁移

颜色、圆角、阴影、间距、按钮风格不应该散落在页面里。  
未来无论迁到 React Native、Flutter，还是桌面壳子，这些 token 都可以直接映射到对应平台。

### 3.2 presenter 可迁移

`MagnetResult -> ResultCardModel` 的映射逻辑不应绑死在页面组件中。  
这样未来换 UI 框架时，只需要替换展示层，不需要重写资源卡片的字段组织与显示逻辑。

### 3.3 component 可重组

`DeviceFrame`、`BrandWordmark`、`SearchField`、`GradientSearchButton`、`ResultCard`、`HomeScreen`、`ResultsScreen`
这些组件本质上就是 App 页面可复用的展示部件。

## 4. 迁移到 App 时的复用方式

### 4.1 可以直接复用的

- 设计 token 体系
- 字段 ViewModel 结构
- 页面层级与信息架构
- 文案与标签策略
- 交互动线

### 4.2 需要平台重写但不需要重设计的

- DeviceFrame
- SearchField
- GradientSearchButton
- ResultCard
- 页面布局容器

说明：

这些组件在 React Native/Flutter 中语法会重写，但视觉规则、间距规则、字段组织已经固定，不需要重新设计。

### 4.3 不建议继续耦合在 Web 的

- 直接把业务逻辑写进 JSX
- 直接在页面里散写颜色和阴影
- 让搜索接口字段和展示字段直接绑定

## 5. 下一步建议

为了进一步减少迁移成本，后续建议继续做这几件事：

- 把 `ResultCardModel` 扩展成完整的 App ViewModel
- 为收藏、历史、我的页复用同一套 `features/magnetgoogo` 组件组织方式
- 补一份 design token 对照表，明确颜色、字号、圆角、阴影、间距枚举
- 若后续确定原生技术栈，再建立一份 Web token -> Native token 映射表

## 6. 结论

这次 UI 重构的目标不是“网页像设计图”，而是“做出一套以后能迁到 App 的高保真展示系统”。  
因此后续新增页面也必须延续这一拆分方式，避免重新回到大页面耦合写法。
