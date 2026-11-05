# 模板与素材说明

本仓库为“讲师课程 PPT 模版 Skill”技能的独立分发版本。2026-11-05，仓库所有者明确要求随技能公开分享生成课件所需的图片与原模板，使完整技能包无需另外准备源稿即可使用。

## 代码与素材分别说明

- 本仓库原创技能说明、Python 辅助脚本和通用示例内容采用根目录的 MIT License。
- PPTX、背景图片、图标、Rokid 等品牌图形及源课件中的第三方内容保留原权利，MIT License 不把这些内容变成原创代码或授予商标权。
- 分享本次技能包的授权，不代表任何后续使用者上传的课程、学生信息、日志和账号也可公开。

## 随包资源

| 文件 | 来源与处理 |
| --- | --- |
| `assets/template.pptx` | 根据所提供的 Lesson02 指定页提取并填入通用提示，保留基础七页可编辑文字框和原设计，增加两页明确的媒体框，清理旧课隐藏描述与文档属性 |
| `assets/images/image1.png` | 内置模板使用的原始品牌背景，从 PPTX 媒体部件直接提取，未重画 |
| `assets/images/image17.svg` | 内置练习页使用的原图标，从 PPTX 媒体部件直接提取，未重画 |
| `assets/sources/lesson02-source.pptx` | 所提供的 `Lesson02_进阶商业化落地实践流程.pptx` 原文件副本，用于恢复指定页面；未修改原文件内容 |
| `examples/media/hello-aiui.html`、两张 PNG 与 `hello-aiui-demo.mp4` | 本仓库的 HTML 教学概念界面，经浏览器渲染并以 FFmpeg 编码为 6 秒无声 H.264 视频；非 AIUI 运行结果或真机录屏，示例代码与原创内容按 MIT 许可 |
| Release 附件 `lecturer-original-template.pptx` | 所提供的 `讲师PPT模版.pptx` 完整原稿，使用英文下载文件名，保持原字节；文件较大，不放入 Git 历史 |

资源的 SHA-256 与媒体部件对应关系见 `assets/manifest.json`。本仓库不附带字体安装包、DSH 登录信息或模型密钥。

普通使用无需修改模板内部 XML。要换成自己的品牌设计，应先使用有权使用的源稿，再重新建立页面槽位与文字预算并验证画面。


## AIUI 开发技能依赖

AIUI 课程联动使用外部 `aiui-dev`，来源为 [jsar-project/AIUI](https://github.com/jsar-project/AIUI/tree/07db37b3f3ea44cc4efe669cd3456b0221195189/skills/aiui-dev)。本仓库只附安装与路由代码，不附带或重新许可上游技能全文。安装时复用使用者本机已有副本，或从固定上游提交稀疏取得，并记录简洁来源。当前未假定该上游具有本仓库的 MIT 许可。
