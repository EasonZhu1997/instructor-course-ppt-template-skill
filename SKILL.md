---
name: course-ppt-template
description: 为课程、教学大纲、PPT提纲、课件和讲师模板制作可编辑PPTX，按需规划并嵌入图片和视频。讲授 AIUI/aiui、AIUI Studio、Rokid AIUI、.ink 页面或 AIUI 眼镜界面时，先加载 aiui-dev 核对技术知识。普通课程也适用；只问代码或API而不需要教学材料时，使用aiui-dev，不启动PPT流程。
metadata:
  version: "1.2.0"
---

# 讲师课程 PPT 模版 Skill

把课程内容写入固定教学版式。模型负责教学组织、短文案及媒体计划，`scripts/pptx_engine.py` 负责 OOXML 页面克隆、文字替换、声明的媒体入槽与结构验证。交付普通可编辑 `.pptx`，不把整页截图当课件。图片/视频生成由宿主对应工具执行，提示词、旁白文案和分镜本身不代表媒体已生成。

## AIUI 课程自动联动

先判断本次真正要讲的课程主题。用户只要提出 AIUI、aiui、AIUI Studio、Rokid AIUI，或明确属于 AIUI 的 `.ink` / `app.json` / Page 绑定与眼镜界面教学，就进入 AIUI 路线，不要求用户再说“调用 AIUI skill”。大小写不影响判断；被否定、排除的主题或无关历史提及不算本课主题。

**在写 AIUI 课件提纲、讲稿或代码说明之前，先用宿主原生 skill 工具加载 `aiui-dev`，再读取与本课匹配的 references。** 只有“AIUI”标题或绿色配图不能代替开发知识技能。按 [AIUI 联动说明](references/aiui-routing.md) 选择项目结构、事件、组件、样式或 API 文档，不把整套文档一次全部读入。

若列表没有 `aiui-dev`，先检查依赖是否安装：`python3 SKILL_DIR/scripts/install_aiui_dependency.py` 可复用本机已有源；无本机源时按 README 的 `--with-aiui` 安装流程取得依赖。宿主没有原生 skill 工具时，可以直接读取已安装 `aiui-dev/SKILL.md` 及其相对资料，但必须确实读取，不能口头声称已加载。缺少依赖且无法取得时，要说明技术知识尚未核对，不凭记忆编造 API。

普通课程不额外加载 AIUI 文档。纯 AIUI 开发问答直接交给 `aiui-dev`；Rokid 的 CXR/Android 等其他路线不能仅因涉及眼镜就套用 AIUI 文档。保持任务范围，不因技术技能被加载就擅自创建、导入或发布 AIUI 应用。

## 开始

用户只要教学提纲或讲解要点时，完成知识核对后直接回答，不创建文件或启动 PPT 构建。只有进入实际排版/生成阶段才读取完整 profile 并运行生成与渲染命令。

1. 读取用户讲稿，保留指定课程名、对象、时长、总页数及内容边界。缺少非关键资料可用明确的教学假设，不编造产品参数、实测结果或来源。
2. 实际排版时读取本技能的 `references/profile.json`。每个 layout 的 `slots` 定义文字字段，`media_slots` 定义可填写的图片或视频框；没有媒体槽的页面不能自行叠图。`max_chars` 包括标点和换行，`max_lines` 是显式行数上限，`max_chars_per_line` 限制每一行的字符数。有 `auto` 的文字槽由脚本填写，内容 JSON 中不要传这些字段。
3. 界面或网络实操课另读 `references/practical-course-checks.md`，逐项核对课表覆盖、状态一致性和可跟随的操作步骤。
4. 使用用户显式指定的 `--template`；未指定时优先使用本技能 `assets/template.pptx`，不存在才回退到 `~/.dsh/course-ppt-template/template.pptx`。完整发布包已含模板和图片，不要求用户另外提供原课件。若两者都缺失，先检查是否安装了完整技能，再按下文从随包源稿重新提取。

## 课程组织

按实际课程需要选择页面，可重复同一页型；用户指定 N 页就是总计 N 页。九种页型：

- `cover`：课程封面。`title` 显式分为 2–3 行，每行不超过 8 个汉字；讲师字段保持简短。
- `overview`：四个目标/回顾点及右侧三项提示。
- `section`：章节导语和三个学习目标。主标题最多 6 个字符，只用 1 行，避免撞上右侧目标栏。
- `concepts`：三个核心知识点及总结框，无绑定 AI 产品含义的图标。每条正文和总结框正文只用一行，总结小标题最多 4 字；需要多行讲解时另选版式或分页。
- `comparison`：双栏对照及底部三个观察点。左右标签尽量 4–6 字。左右正文最多两行，给底部说明留出空间。
- `exercise`：三道问题或三项练习。时长由课程需求决定，不编造答案。
- `closing`：一句结课总结及四个产出标签。大标题最多两行，每行不超过 12 个字符。
- `image_explainer`：左侧大图、右侧三个讲解点与下方图注。`media.visual` 必填真实 PNG/JPEG 路径，默认等比完整显示。
- `video_explainer`：左侧视频、右侧播放前/观看时/播放后讲解与图注。`media.visual` 必填本地 H.264 MP4、PNG/JPEG 封面和配图说明；构建与验证需要 `ffprobe`。

信息较多时优先精简或在允许的总页数内分页。保持原模板字号、颜色、背景、边框、位置和图像比例。不要临时缩字号、重画装饰、换字体，或用未确认数字填充课堂内容。较长英文也要计入槽位预算。

## 按大纲规划图片与视频

用户要求配图、视频或多媒体课件时，读取 [媒体槽与计划流程](references/media-slots.md)，先按每页教学目的决定是否需要媒体，再写完整文字槽和媒体大纲。`scripts/plan_course_media.py plan` 生成提示词、视频旁白文案、分镜、目标文件名和明确待填充的内容 JSON。实际生成时调用当前宿主的图片/视频工具；无对应工具则保留计划并说明媒体尚未生成，不编造文件或生成成功记录。

把已生成或已授权的本地素材放到计划指定位置，再用 `collect` 写出可构建的媒体路径。图片支持 PNG/JPEG；JPEG 完整解码需 Pillow，未安装时使用 PNG。视频需要 H.264 MP4 及比例匹配的封面。`ffmpeg` 仅在 `collect --make-posters` 提取缺失封面时使用，`ffprobe` 用于视频 build/validate。`collect` 确认文件存在不等于格式、画面或播放已验，保留 `delivery_ready: false`。

只有涉及 Rokid AIUI 单绿眼镜屏幕/HUD 的区域才读取 [AIUI 演示图说明](references/aiui-demo-visuals.md) 并应用单绿。其余课件、开发工具、手机画面和普通课程保持各自配色。优先用真实/预览截图；生成概念图或概念视频时明确标注，不当成 AIUI 应用已运行或真机录屏。

## 内容文件与生成

内容使用下面的根结构，UTF-8 JSON，不带 Markdown 围栏：

```json
{
  "title": "Rokid AIUI 入门开发",
  "slides": [
    {
      "layout": "cover",
      "slots": {
        "title": "Rokid\nAIUI入门开发",
        "presenter": "主讲：课程讲师"
      }
    }
  ]
}
```

除 auto 槽外，每页必须提供该 layout 全部 slots，不能有未知字段或空文字。媒体页另含 `media`；图片项为 `{"path":"assets/example.png","alt":"配图说明"}`，视频项还需 `"poster":"assets/poster.png"`。相对路径以内容 JSON 所在目录为基准，不能使用 URL。完整格式见媒体说明。上述示例只演示封面，实际内容按用户的总页数完整填写。

用当前宿主的文件工具保存 `content.json`，再执行（`SKILL_DIR` 表示本技能所在目录，需要替换成真实路径）：

```bash
python3 SKILL_DIR/scripts/pptx_engine.py build --template TEMPLATE.pptx --profile SKILL_DIR/references/profile.json --content content.json --output 课程.pptx
python3 SKILL_DIR/scripts/pptx_engine.py validate --pptx 课程.pptx --template TEMPLATE.pptx --profile SKILL_DIR/references/profile.json --content content.json
```

遇到文字预算错误，改短对应槽位再生成。不得修改校验规则绕过错误。脚本默认不覆盖已存在的文件；确认属于本次生成物时可用 `--force`。

媒体未生成时，仅为检查草稿版面才可给 build 和 validate 都加 `--allow-pending-media`，并填写显式 `status: planned`、`prompt`、`alt`。对应可见 `caption` 必须以“待补图片”或“待补视频”开头，规划器会添加此前缀；不能只在 JSON 里标待补、页面却冒充成品。此时输出 `delivery_ready: false`，不能报告完成媒体课件。正式交付不使用该开关，先补齐真实素材。

## 随包模板与重新提取

完整发布包内置九页型 `assets/template.pptx`、`assets/images/` 与 `assets/sources/lesson02-source.pptx`。常规生成直接使用内置模板，不需要先导入。`references/base-profile.json` 对应 Lesson02 的七个原始页面；最终 `references/profile.json` 另含两个派生媒体页，不能直接对最终 profile 执行 bootstrap。原始讲师材料包另见仓库 Releases。

需要重新提取时：

```bash
python3 SKILL_DIR/scripts/prepare_media_template.py --source SKILL_DIR/assets/sources/lesson02-source.pptx --profile SKILL_DIR/references/base-profile.json --output NEW.pptx --profile-output NEW-profile.json
```

脚本先从匹配源稿提取基础七页，再建立媒体页基准；也可用 `--template` 传入已有基础七页模板。生成的 NEW.pptx 必须与 NEW-profile.json 配对用于 build/validate，不混用旧 profile。资源来源与 SHA-256 见 `assets/manifest.json`，素材权利边界见 `ASSET_NOTICES.md`。参考差异见 `references/design-notes.md`。

## DSH 调用

运行 `python3 SKILL_DIR/scripts/install_skill.py` 安装完整技能至 `~/.dsh/skills/course-ppt-template/`，或用 `--dest` 指定项目目录。更新时 `--replace` 会先备份已有目录。安装完成后在 DSH 中要求使用此技能。也可运行 `scripts/run_dsh.py --help`，以现有 DSH 本机账号执行一次非交互任务，显式选择模型，保留本次输出和调用记录。

本机验证模型为 `deepseek-flash`。`flash1017` 与 `deepseek-flash1017` 曾被当前账号 API 返回 400；不宣称它们等同于 `deepseek-flash`，不静默切换失败的模型。用户指定其他入口时沿用其已配置 provider，不复制密钥到技能。

## 验收与交付

- 结构验证通过后，用 `scripts/render_review.py 课程.pptx --out 预览目录` 导出 PDF/PNG。它调用本机 LibreOffice 和 Poppler，缺少工具时如实说明；也可用 WPS/PowerPoint 打开检查。
- 查看全部页面，核对中文显示、标题换行、边界、页码、课程内容、版式一致性和可编辑文字。若中文缺字，先排查渲染环境的字体，不把缺字截图当成功。
- 检查每个页型至少一页。结构检查不能替代画面检查，未渲染只能报告“结构已验，画面待验”。
- 对每个媒体框核对原文件、比例、裁切、说明、图注与课堂叙述。视频嵌入与 H.264 检查通过后，仍需在目标 WPS/PowerPoint 中实际播放，检查开始、结束、声音及字幕；PDF/PNG 只能检查静态封面。旁白文本不能当成已有音轨。
- 机器报告的 `structural_ready`、`assets_complete` 不等同于交付完成；`delivery_ready` 保留为 `false`。完成画面和播放复核后在交付说明中记录实际观察，不要求人为修改报告中的完成标记。
- 返回 PPTX 的真实路径。发布包按本次授权随附模板、图片和指定源稿；用户后续的课程内容、运行日志、账号凭据仍留本机。不要因本技能可分享就自动公开新用户的材料。
