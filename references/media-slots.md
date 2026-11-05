# 图片、视频槽与媒体计划

1.2.0 的最终模板增加 `image_explainer`、`video_explainer`。两种页面均有左侧大媒体框、右侧三个讲解点、标题与图注，继续沿用蓝紫教学版。媒体以真实文件嵌入 PPTX，正文保持可编辑。

## 从教学大纲开始

先确定这一页让学员观察什么、看完做什么，再决定用图片、录屏或短视频。没有视觉教学目的的页面可以继续使用原有文字页型。AIUI 课程先按 SKILL.md 加载 `aiui-dev` 核对技术内容，不能只凭概念配图编造 API 或设备行为。

大纲根结构仍是 `title`、`slides`。每页提供 `layout` 和该页全部非自动 `slots`；媒体页另加 `media.visual`。文字预算与字段名称以 `references/profile.json` 为准，完整例子见 [Rokid AIUI 媒体大纲](../examples/rokid-aiui-media-outline.json)。

规划阶段的媒体字段：

| 字段 | 图片 | 视频 |
| --- | --- | --- |
| `kind` | `image`，可省略以沿用页型 | `video`，可省略以沿用页型 |
| `prompt` | 必填，准确文案、构图、教学目标 | 必填，场景、动作和画面要求 |
| `alt` | 必填，准确的图片说明 | 必填，准确的视频说明 |
| `visual_context` | `general` 或 `aiui_glasses` | 同左 |
| `format` | `png`（默认）、`jpg`、`jpeg` | `mp4`（默认） |
| `narration` | 不需要 | 必填，计划中的旁白文案 |
| `storyboard` | 不需要 | 必填，非空分镜文字数组 |
| `duration_seconds` | 不需要 | 必填，正数，最多 3600 秒 |

`visual_context: "aiui_glasses"` 只用于明确的 AIUI 单绿眼镜屏幕/HUD，规划器会附入相应单绿约束。普通课件、手机或 Studio 操作画面用 `general`。不因课程名包含 AIUI 就把整页改成绿色。

默认媒体框为 16:9，建议横向图片至少 1280×720，视频与封面使用相同比例；这是配图建议，不是设备分辨率声明。480:352 的眼镜界面可以原比例放入，`contain` 会留边，不拉伸。`fit` 来自模板 profile；不要通过改坐标、背景或字体来迁就素材。

## 生成媒体计划

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"
COURSE_MEDIA_DIR="$PWD/outputs/AIUI媒体计划"

python3 "$COURSE_SKILL_DIR/scripts/plan_course_media.py" plan \
  --outline "$COURSE_SKILL_DIR/examples/rokid-aiui-media-outline.json" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --out "$COURSE_MEDIA_DIR"
```

`--out` 必须为新目录。生成：

- `media-plan.md`：供人和宿主媒体工具使用的提示词、旁白文案、分镜与文件名。
- `media-plan.json`：同一任务的机器可读清单，含目标素材与视频封面位置。
- `content.planned.json`：已填文字、明确声明待生成媒体的草稿内容。
- `assets/`：存放实际素材的目录；创建目录不表示素材已生成。

这个脚本不调用图像、视频或语音模型。由当前宿主的相应工具实际生成素材，或使用已授权的现成文件。按任务清单保存到 `expected_file`；视频另需 `expected_poster`。不要把提示词、旁白文字、分镜或 PNG 路径当成已经生成的 MP4 或音轨。没有工具时保留计划，明确说明哪项媒体尚未生成。

## 收集实际文件

```bash
python3 "$COURSE_SKILL_DIR/scripts/plan_course_media.py" collect \
  --plan "$COURSE_MEDIA_DIR/media-plan.json"
```

默认输出计划目录内的 `content.ready.json`。也可用 `--output` 指定内容文件，用 `--force` 明确替换本次生成的旧内容文件。素材不齐时默认拒绝收集成品；`--allow-pending-media` 只用于保留未完成草稿。

`collect` 负责确认素材路径和文件存在，并把路径写入内容 JSON；素材齐备时返回 `status: assets_collected`，`delivery_ready` 保留为 `false`。这个状态不代表文件格式、画面质量或视频播放已验。即使文件名为 `content.ready.json`，仍需完成下一步引擎验证和人工复核。

已有视频缺封面时，可用：

```bash
python3 "$COURSE_SKILL_DIR/scripts/plan_course_media.py" collect \
  --plan "$COURSE_MEDIA_DIR/media-plan.json" \
  --make-posters
```

只有 `--make-posters` 另需 `ffmpeg`；自动查找失败可加 `--ffmpeg /实际路径/ffmpeg`。该步骤从已有视频提取首帧，不生成视频或旁白，也不覆盖已有封面。

## 引擎接受的素材格式

规划字段不会直接进入正式媒体项。取得素材后，图片内容项是：

```json
"media": {
  "visual": {
    "path": "assets/slide-03-visual.png",
    "alt": "Hello AIUI 初始状态的教学概念示意"
  }
}
```

视频内容项是：

```json
"media": {
  "visual": {
    "path": "assets/slide-04-visual.mp4",
    "poster": "assets/slide-04-visual-poster.png",
    "alt": "从初始问候到更新问候的概念状态演示"
  }
}
```

以上是页对象中的字段片段，其他文字槽仍需完整填写。`alt` 是素材说明，不能代替页面上可见的 `caption` 图注。相对路径以内容 JSON 所在目录为基准，也可用本地绝对路径；不接受网络 URL。图片必须是实际 PNG/JPEG，不能只改扩展名。PNG 会检查解压后的图像数据；JPEG 需 Pillow 完整解码，未安装时请用 PNG。

视频必须为 H.264 MP4，封面是 PNG/JPEG，封面与视频的宽高比差异不得超过 2%。视频不应带待纠正的旋转元数据或非方形像素。引擎构建和独立验证都需要 `ffprobe` 确认编码，PATH 找不到时给两条命令都加 `--ffprobe /实际路径/ffprobe`。

## 构建与独立验证

```bash
python3 "$COURSE_SKILL_DIR/scripts/pptx_engine.py" build \
  --template "$COURSE_SKILL_DIR/assets/template.pptx" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --content "$COURSE_MEDIA_DIR/content.ready.json" \
  --output "$PWD/outputs/AIUI图文视频课件.pptx"

python3 "$COURSE_SKILL_DIR/scripts/pptx_engine.py" validate \
  --pptx "$PWD/outputs/AIUI图文视频课件.pptx" \
  --template "$COURSE_SKILL_DIR/assets/template.pptx" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --content "$COURSE_MEDIA_DIR/content.ready.json"
```

引擎只修改声明的媒体框，按 profile 等比显示素材，并检查文件哈希、媒体关系与模板约束。图片/视频槽必需文件缺失时，不允许按成品构建。报告用 `structural_ready`、`assets_complete` 区分结构检查与素材齐备，`delivery_ready` 始终保留为 `false`，不代替内容、视觉或播放验收。完成后在交付说明中记录实际复核结果，无需人为改 JSON 标记。

## 只看未完成草稿

如果需要在素材生成前查看排版，使用 `content.planned.json`，给 build 与 validate 都加 `--allow-pending-media`。待生成项必须明确包含：

```json
{"status":"planned","prompt":"待执行的媒体生成提示词","alt":"待生成的概念素材说明"}
```

此时输出 `status: pending_media`、`delivery_ready: false`。对应可见 `caption` 必须以“待补图片”或“待补视频”开头，规划器会添加此前缀，引擎也会检查。不能只在 JSON 标待补，页面却让人误认已有成品。正式交付前取得真实文件，重新 collect、build、validate，去掉草稿开关，并核对图注与实际素材相符。

## 画面与播放复核

用 `render_review.py` 查看全部页面，核对媒体与标题、图注、三条讲解是否对应，检查裁切、比例、中文和演示状态。PDF/PNG 只能看到视频封面，无法证明播放成功。

本机 LibreOffice 无法处理原生视频对象时，可显式选择静态封面预览；默认渲染流程保持不变，不会静默转成这个模式：

```bash
python3 "$COURSE_SKILL_DIR/scripts/render_review.py" \
  "$PWD/outputs/AIUI图文视频课件.pptx" \
  --out "$PWD/outputs/AIUI静态封面预览" \
  --video-posters
```

`--video-posters` 识别原生视频及其嵌入封面，只在另建的 QA 副本中将视频对象变为封面静态图，并移除相关播放动作和受影响页的动画时间线。原 PPTX 不写入，报告记录源文件 SHA-256 与 `source_unchanged`；stdout 和 `review.json` 都明确标示封面预览及播放未验。缺少可用封面时拒绝转换。生成的 QA 副本只供静态检查，不能代替正式视频课件。

含视频的 PPTX 还需在目标 WPS/PowerPoint 中实际播放，检查开始、结束、画面、字幕和预期声音。没有旁白音轨就明确写“无旁白”，不能凭旁白计划声明已有讲解音频。尚未播放时记录“已嵌入，播放待验”；不要把包内存在 MP4 或点击时间线当成实际播放证据。

配套 [媒体示例 PPTX](../examples/rokid-aiui-media-demo.pptx) 使用 HTML 概念状态素材；它与 AIUI 应用运行、真机录屏和眼镜光学可读性是不同结果。示例来源及其无旁白音轨的范围见 [AIUI 演示图说明](aiui-demo-visuals.md#配套媒体示例)。
