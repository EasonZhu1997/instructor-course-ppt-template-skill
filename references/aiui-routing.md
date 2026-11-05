# AIUI 课程如何联动开发技能

`course-ppt-template` 管教学组织与课件版式，`aiui-dev` 管 AIUI 技术契约。出现 AIUI 教学主题时，两者需要一起使用。只调整 PPT 标题或把画面变绿不等于使用了 AIUI 开发技能。

## 触发边界

| 本次请求 | 应用路线 |
| --- | --- |
| AIUI、aiui、AIUI Studio、Rokid AIUI 的课程、PPT、课件或教学提纲 | 先加载本技能，再加载 `aiui-dev`，按下表读取对应知识 |
| `.ink`、`app.json`、Page、绑定、Widget 等明确 AIUI 概念的教学 | 同上，即使用户没有拼出大写 AIUI |
| 单独询问 AIUI 代码、调试或 API，没有教学材料需求 | 使用 `aiui-dev`，不启动课件生成 |
| 普通课程，或明确“这次不讲 AIUI” | 沿用通用课件路线，不因历史提及触发 AIUI |
| 只提到 Rokid/眼镜，没有确定开发路线 | 依据资料区分 AIUI 与 CXR/Android 等路线，不假定所有眼镜开发都是 AIUI |

## 真正读取知识

使用原生 `skill` 工具加载 `aiui-dev`。下列路径均相对于它自己的技能目录，不是当前课件技能目录：

| 课程涉及内容 | 随后读取 |
| --- | --- |
| Studio 入门、项目、路由、`.ink` 四区块、Page、绑定与状态 | `references/framework.md`；需要最小示例时读 `assets/minimal-page.ink` |
| 生命周期、确认/返回、焦点、按键、模板事件 | `references/events.md` |
| 内置组件及其属性/事件 | `references/components.md`，再按需读取对应组件文档 |
| 页面布局、WXSS、主题或字体 | `references/wxss.md` |
| 明确为单绿眼镜的界面视觉 | `references/design/monochrome-green.md`，再读本课件技能的 `aiui-demo-visuals.md` |
| 网络、相机、语音、AI、设备等运行时 API | `references/apis/index.md`，再读其中对应域的文档 |

只读与任务有关的资料。例如入门课至少先核对 framework；眼镜 UI 课按需核对组件、WXSS 和单绿设计；网络课要从 API 索引定位 web 域，不能直接把浏览器 fetch 或小程序 API 当成 AIUI API。

## 依赖位置与取得方式

DSH 默认不会读取 Codex 的技能目录。安装脚本可以把本机已有的 `aiui-dev` 安装到 `~/.dsh/skills/aiui-dev/`；也可从上游固定版本取得。普通课件功能仍可独立使用。

当前引用来源为 [jsar-project/AIUI 的 aiui-dev](https://github.com/jsar-project/AIUI/tree/07db37b3f3ea44cc4efe669cd3456b0221195189/skills/aiui-dev)。上游技能内容没有被重新打包进本仓库或套用本仓库 MIT；安装时从使用者已有本机副本或上游取得，保留来源。不要将本机备份路径、凭据或运行日志带入公开包。

DSH 新增可搜索技能后，下一次请求通常会刷新目录。已在旧对话加载过旧正文时，可显式发送 `/course-ppt-template` 和 `/aiui-dev` 重新加载；这只是旧会话刷新办法，新任务不应靠用户每次手动点名。

## 如何验收“敏感度”

测试使用独立 DSH 会话和自然请求，不在提示词中指定技能名。记录原生 skill 调用、成功结果，以及实际读取的知识文档。模型说“我已使用 AIUI 技能”不是证据。

课件请求应看到本技能和 `aiui-dev`；技术内容要有匹配文档读取。普通课程及否定例不应误加载 AIUI；纯开发例不应误生成 PPT。测试脚本和结果只证明列出的案例，不保证任意措辞百分之百触发。
