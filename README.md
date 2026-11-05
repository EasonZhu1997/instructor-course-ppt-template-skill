# 讲师课程 PPT 模版 Skill

**Instructor Course PPT Template Skill**

版本 **1.2.0**：九种教学页型，支持按大纲规划图片/视频并填入受控媒体槽。

下载的 GitHub 版本已包含媒体槽、规划与收集脚本，以及可重建的图文视频示例。更新本机旧版后即可使用。

让 DSH 根据课程讲稿生成可编辑的 PPTX，并沿用 Lesson 教学版的蓝紫版式。

模型负责组织教学内容、文案及媒体计划，脚本负责复用原页面、填入文字和本地媒体、检查模板一致性。适合已有课程表、讲稿或教学大纲，希望制作统一风格课件的场景。

**日常使用看本页；AI 助手执行时读取 [SKILL.md](SKILL.md)。**

技能已内置九种可编辑版式、所需背景图片和可重新提取模板的 Lesson02 源文件。首次使用无需自行寻找原课件。

[下载完整技能 ZIP](https://github.com/EasonZhu1997/instructor-course-ppt-template-skill/releases/latest/download/course-ppt-template.zip) · [下载原始讲师模板](https://github.com/EasonZhu1997/instructor-course-ppt-template-skill/releases/download/v1.0.0/lecturer-original-template.pptx) · [查看发布说明](https://github.com/EasonZhu1997/instructor-course-ppt-template-skill/releases/latest)

![通用教学版式与图片视频槽预览](assets/preview.png)

## 先看使用流程

```mermaid
flowchart LR
    A[课程简报] --> B[DSH 编写教学内容]
    B --> C[检查文字槽位与字数]
    B --> M[按需规划图片与视频]
    M --> N[宿主工具生成或使用已有素材]
    T[技能内置模板] --> D[脚本生成可编辑 PPTX]
    C --> D
    N --> D
    D --> E[结构验证]
    E --> F[渲染并查看全部页面]
    F --> G[修改文案并交付]
```

输出的文字可以继续编辑，背景和装饰沿用源模板。它不会自动实现课件中讲授的应用、原型或服务器。

## AIUI 演示图什么时候用绿色

技能面向各类讲师课程，默认使用通用课件配色。讲授 **Rokid AIUI 单绿眼镜界面** 时，可以辅助准备或生成黑底绿字的界面示意图，绿色只出现在眼镜画面区域；Studio 工具截图、手机界面和其他课程不自动变绿。

优先采用实际截图或预览截图。宿主有图片生成工具时，可生成明确标注的教学概念图；没有绘图工具时，提供可复制提示词并说明尚未成图。`deepseek-flash` 的文字生成能力本身不等于图片生成能力。

`image_explainer` 和 `video_explainer` 提供明确媒体框，分别接受图片和带封面的视频，不覆盖原有文字或装饰。媒体计划、提示词、旁白文案和分镜需要由宿主工具实际生成素材后才能入稿。详见 [媒体槽与计划流程](references/media-slots.md) 及 [AIUI 演示图说明与 Hello AIUI 提示词](references/aiui-demo-visuals.md)。

## 三步开始使用

1. 下载上方技能 ZIP 并解压，得到 `course-ppt-template/` 文件夹。
2. 运行安装命令，复制完整技能到 DSH 用户技能目录：

   ```bash
   python3 course-ppt-template/scripts/install_skill.py --with-aiui
   ```

3. 打开已登录的 DSH，选择可用的 `deepseek-flash`，按下方示例给出课程要求。

安装时目标目录若已存在，脚本会拒绝合并。更新已有技能时加 `--replace`，脚本会先将旧目录保存在技能搜索根之外的 `skill-backups/` 中再安装，避免备份被重复发现；也可用 `--dest` 指定项目目录。模型调用需要你自己的 DSH 登录和可用额度，技能包不包含账号或密钥。

也可以通过 Git 下载并安装：

```bash
git clone https://github.com/EasonZhu1997/instructor-course-ppt-template-skill.git
python3 instructor-course-ppt-template-skill/scripts/install_skill.py --with-aiui
```

## AIUI 自动触发与知识联动

AIUI 课程会同时使用两个技能：`course-ppt-template` 负责教学与版式，`aiui-dev` 负责真实开发契约。安装时的 `--with-aiui` 会复用本机现有的 AIUI 技能；找不到时从上游固定版本取得（需要 Git 和网络）。上游内容不被重新打包或套用本仓库许可。只做普通课程时可以省略这个选项。

已经装过旧版的用户可以运行：

```bash
python3 course-ppt-template/scripts/install_skill.py --replace --with-aiui
```

之后可自然提问，无需每次点名技能，例如：

```text
为《Rokid aiui 入门开发》拟3页课件提纲，讲页面结构和问候文字更新。
```

AIUI、aiui、AIUI Studio 和明确的 `.ink` 页面教学会进入技术联动：先加载 `aiui-dev`，再按任务读取 framework、事件、组件、样式或 API 文档。只问 AIUI 开发代码而不需要教学材料时，直接使用开发技能；普通课程和明确排除 AIUI 的请求不应额外加载它。AIUI 知识联动不等于把课件改绿，眼镜画面配色仍按下一节的目标边界处理。

本次八条自然请求实测：AIUI 教学知识联动 4/4，普通或排除 AIUI 的请求无误触发 3/3，纯开发问题只用 AIUI 技能 1/1。完整功能矩阵为 6/8，另两条普通提纲直接回答、没有加载课件技能；不宣称所有请求都必定触发。详见 [实测记录](references/aiui-routing-validation.md)。

依赖状态可检查：

```bash
python3 "$HOME/.dsh/skills/course-ppt-template/scripts/install_aiui_dependency.py"
```

有效依赖会显示 `AIUI ready` 并直接复用。执行器的 `run.json` 新增 `native_loaded_skills`，记录成功的原生技能加载；敏感度验收还要结合实际文档读取，不能只凭最终回答里一句“已使用”。需要从特定目录安装时用 `--source`，没有本机源时可用 `--download` 取得固定上游版本。已有有效 `aiui-dev` 不会默认被替换；确需替换时才加 `--replace`。

DSH 的默认技能监视器通常会在下一次请求刷新目录。旧对话若已经加载过旧正文，可发送 `/course-ppt-template`、`/aiui-dev` 重新加载，或新建对话测试；此后无需每次手动点名。

## 已安装后怎样调用

默认安装目录为 `~/.dsh/skills/course-ppt-template/`。模板随技能保存在 `assets/template.pptx`，不需要额外创建用户缓存。

### 方法一：在 DSH 对话中调用

选择当前账号可用的 `deepseek-flash`，然后提供课程资料和要求。例如：

```text
请使用 course-ppt-template 技能，为《Rokid AIUI 入门开发》制作10页中文PPT。

对象：第一次接触 AIUI 的开发者。
课时：60分钟。
主讲：课程讲师。
内容：AIUI Studio、项目与页面结构、最小应用、数据绑定、交互和预览调试。
交付：可编辑PPTX。

使用技能内置模板，保持课程版式。
若需要配图或视频，先按大纲生成媒体计划，再调用当前宿主的相应工具生成素材并入槽。
若画面是AIUI眼镜端界面，只在该屏幕区域用单绿；普通课件保持模板配色。
请读取完整SKILL.md，生成后执行结构验证，渲染并检查全部页面。
发现溢出时精简文案，不缩小字号。
```

课程资料里有课程名、学习对象、主要内容、课时、总页数、学员交付和不包含的内容，通常更容易得到合适的结果。指定的总页数包含封面和结尾。

### 方法二：用 CLI 生成

先把课程要求保存为 UTF-8 的 `.md` 或 `.txt` 简报。下面直接使用技能自带的通用示例：

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"

python3 "$COURSE_SKILL_DIR/scripts/run_dsh.py" \
  --brief "$COURSE_SKILL_DIR/examples/rokid-aiui-intro-brief.md" \
  --output "$PWD/outputs/Rokid AIUI 入门开发.pptx" \
  --model deepseek-flash
```

`--brief` 读取文本简报，不能直接把 DOCX 当作 UTF-8 文本传入。课程表是 Word 文件时，先让助手读取相关课程，再整理成文本简报。

脚本使用 DSH 已有的本机账号登录，会访问模型服务并使用该账号的额度。它会生成课程内容、调用模板引擎，并独立执行结构验证；画面是否合格仍要查看渲染结果。已有输出文件会被拒绝覆盖，请换一个文件名。

| 参数 | 用途 |
| --- | --- |
| `--brief` | 必填，UTF-8 课程简报路径 |
| `--output` | 必填，新建的 `.pptx` 路径 |
| `--model` | 精确模型名称，默认 `deepseek-flash` |
| `--template` | 指定另一份兼容的模板缓存 |
| `--dsh-cli` | 自动查找失败时，指定 DSH 可执行文件 |
| `--timeout` | 本次 DSH 运行时限，默认 1200 秒 |
| `--dry-run` | 只准备本地调用文件，不调用模型，也不生成 PPT |

CLI 会在输出目录内的 `.work/dsh-…/` 保存内容 JSON、提示词、日志和运行记录。日志可能包含课程内容，分享技能时不要一起上传。

## 从大纲到图片、视频课件

媒体流程把文字计划和实际文件分开。下面使用随包的《Rokid AIUI 入门开发》媒体大纲：

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"
COURSE_MEDIA_DIR="$PWD/outputs/AIUI媒体计划"

python3 "$COURSE_SKILL_DIR/scripts/plan_course_media.py" plan \
  --outline "$COURSE_SKILL_DIR/examples/rokid-aiui-media-outline.json" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --out "$COURSE_MEDIA_DIR"
```

计划目录必须是新目录。它包含 `media-plan.md`、`media-plan.json`、`content.planned.json` 和素材目录。图片提示词、视频旁白文案和分镜都在计划中；该命令不调用图片、视频或语音模型。

让当前宿主的图片/视频工具按任务生成素材，或使用你有权使用的已有素材，放到计划列出的文件位置。视频需为 H.264 MP4，并提供比例匹配的 PNG/JPEG 封面。随后收集素材并生成课件：

```bash
python3 "$COURSE_SKILL_DIR/scripts/plan_course_media.py" collect \
  --plan "$COURSE_MEDIA_DIR/media-plan.json"

python3 "$COURSE_SKILL_DIR/scripts/pptx_engine.py" build \
  --template "$COURSE_SKILL_DIR/assets/template.pptx" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --content "$COURSE_MEDIA_DIR/content.ready.json" \
  --output "$PWD/outputs/AIUI图文视频课件.pptx"
```

`collect` 只确认本地文件齐备，返回 `assets_collected`，保留 `delivery_ready: false`；格式、比例与文件哈希由引擎再检查。PNG 可用标准库检查，JPEG 完整解码需 Pillow，未安装时使用 PNG。视频 build/validate 需要 `ffprobe`，自动查找失败时加 `--ffprobe /实际路径/ffprobe`。已有视频缺封面时，可以给 `collect` 加 `--make-posters`，这一步另需 `ffmpeg`，可用 `--ffmpeg` 指定路径。

媒体未生成时，可以对 `content.planned.json` 使用 `build --allow-pending-media` 查看草稿，独立 `validate` 也必须加同一开关。规划器会让可见图注以“待补图片/待补视频”开头，引擎也检查此前缀；此时 `delivery_ready` 为 `false`，不能当作媒体课件已完成。最终课件先补齐素材，再按下文做结构、画面与目标软件播放检查。完整格式和命令见 [媒体槽说明](references/media-slots.md)。

## 示例：Rokid AIUI 入门开发

随包示例以第一次接触 AIUI 的开发者为对象，覆盖 AIUI Studio、项目与页面结构、最小页面、数据绑定、交互、预览调试及课堂验收。

- [查看或下载 10 页示例 PPT](examples/rokid-aiui-intro.pptx)
- [课程简报](examples/rokid-aiui-intro-brief.md)
- [可重建课件的内容 JSON](examples/rokid-aiui-intro-content.json)
- [AIUI 眼镜演示图提示词](references/aiui-demo-visuals.md#示例提示词rokid-aiui-入门开发)
- [图片与视频媒体大纲](examples/rokid-aiui-media-outline.json)
- [媒体入槽内容 JSON](examples/rokid-aiui-media-content.json)
- [图片与视频课件示例](examples/rokid-aiui-media-demo.pptx)

示例展示的是教学课件，未把代码讲解或预览检查写成已通过设备验收。需要配图时按上面的 AIUI 专用规则处理。

媒体示例使用 `examples/media/hello-aiui.html` 制作的 HTML 概念状态画面及对应 PNG、MP4，演示“Hello AIUI”到更新问候的状态变化。它是独立课程概念素材，不能称为 AIUI 运行结果或真机录屏。MP4 没有旁白音轨，大纲中的旁白文案和分镜仍是制作计划。目标软件实际播放情况以验证记录为准。

## 环境与模板选择

离线回归检查：`python3 course-ppt-template/scripts/test_media_slots.py`。随包素材和源稿可完成 11 项检查；视频检查需 `ffprobe`，缺少时会明确跳过。它不调用模型、不使用账号，也不代替画面和播放复核。

已验证环境为 macOS、Python 3.9.6；原课件生成验证使用 DSH CLI `0.2.1-rc.5`，本次 AIUI 自动触发验证使用本机当前的 `0.2.2-rc.1`。文本/PNG 引擎、媒体规划、安装脚本和 DSH 执行器使用 Python 标准库；JPEG 完整解码需 Pillow，没有时用 PNG。视频 build/validate 另需 `ffprobe`，`collect --make-posters` 另需 `ffmpeg`。画面渲染另需 LibreOffice 和 Poppler，Pillow 也可生成联系图。其他系统、模型入口和 DSH 版本需重新验证。

执行器按下面的顺序选择模板：

1. 显式传入的 `--template`。
2. 当前技能目录内的 `assets/template.pptx`。
3. 兼容旧版安装的 `~/.dsh/course-ppt-template/template.pptx`。

内置模板与 [profile.json](references/profile.json) 配套。要查看默认调用会使用哪些文件，可在生成命令末尾加 `--dry-run`；它会写入本地准备文件，不调用模型、不生成 PPT。

DSH 路径会依次尝试显式的 `--dsh-cli`、PATH 中的 `dsh` 和 macOS 应用内置路径。自动查找失败时指定：

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"

python3 "$COURSE_SKILL_DIR/scripts/run_dsh.py" \
  --brief "$COURSE_SKILL_DIR/examples/rokid-aiui-intro-brief.md" \
  --output "$PWD/outputs/新课程.pptx" \
  --dsh-cli "/你的DSH路径/dsh" \
  --model deepseek-flash
```

当前执行器固定使用 `deepseek-account` provider。`--model` 只切换这个账号支持的模型，不会切换到自定义 provider，也不会静默替换被拒绝的模型。其他支持文件读取、命令执行与图像查看的 AI 助手，可以按 `SKILL.md` 调用模板引擎；相应宿主尚未逐一验证。

## 原模板与图片在哪里

| 资源 | 位置与用途 |
| --- | --- |
| 可直接生成课件的九页型模板 | [assets/template.pptx](assets/template.pptx)，包含通用填写提示和明确待填充的媒体框 |
| 模板实际用到的背景和图标 | [assets/images/](assets/images/)，PPTX 内也已包含同一份资源 |
| Lesson02 原始源稿 | [assets/sources/lesson02-source.pptx](assets/sources/lesson02-source.pptx)，用于重新提取匹配的页面 |
| 原始讲师 PPT 模板 | [v1.0 原始附件](https://github.com/EasonZhu1997/instructor-course-ppt-template-skill/releases/download/v1.0.0/lecturer-original-template.pptx)，约 272 MiB，原文件完整保留 |
| 资源校验与来源记录 | [assets/manifest.json](assets/manifest.json) |

大号原始讲师模板保存在 v1.0 Release（后续版本继续引用同一原件），日常生成无需下载它。内置模板已经包含所需图片，不依赖本机其他项目目录。素材的权利边界见 [ASSET_NOTICES.md](ASSET_NOTICES.md)。

### 需要重新提取模板时

通常无需执行此步骤。最终 profile 含派生媒体页，不能直接对它运行 `bootstrap`。需要恢复模板时，使用基础七页 profile 提取源页，再由准备脚本建立两个媒体页：

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"

python3 "$COURSE_SKILL_DIR/scripts/prepare_media_template.py" \
  --source "$COURSE_SKILL_DIR/assets/sources/lesson02-source.pptx" \
  --profile "$COURSE_SKILL_DIR/references/base-profile.json" \
  --output "$PWD/outputs/NEW.pptx" \
  --profile-output "$PWD/outputs/NEW-profile.json"
```

生成的 `NEW.pptx` 与 `NEW-profile.json` 是配套文件，之后一同传给引擎 build/validate 的 `--template`、`--profile`。源课件不会被覆盖。也可用 `--template` 输入已有基础七页模板。其他版本的源稿可能因页面或文字框 ID 不同而无法套用基础 profile，需要重新检查。

## 可以使用哪些页面

同一页型可以重复使用，九种页型不等于每份课件只能有九页。

| 页型 | 适合内容 | 已收紧的排版限制 |
| --- | --- | --- |
| `cover` | 封面、讲师 | 标题最多 3 行，每行最多 8 个字符 |
| `overview` | 四项目标、回顾和侧栏提示 | 每个文字框单独设预算 |
| `section` | 章节导语、三个学习目标 | 主标题单行，最多 6 个字符 |
| `concepts` | 三个知识点及总结 | 三条正文、总结正文均为单行；总结小标题最多 4 字 |
| `comparison` | 双栏示范与三个观察点 | 左右正文最多 2 行，分别每行最多 20、24 个字符 |
| `exercise` | 三道题或三项操作任务 | 左侧标题每行最多 6 个字符 |
| `closing` | 结课总结、四个产出标签 | 大标题最多 2 行，每行最多 12 个字符 |
| `image_explainer` | 大图、三个讲解点与图注 | `visual` 槽必填 PNG/JPEG，默认 16:9 框内等比完整显示 |
| `video_explainer` | 视频、播放前后观察任务与图注 | `visual` 槽必填 H.264 MP4 和匹配封面，需实际播放复核 |

完整限制以 [profile.json](references/profile.json) 为准。字符预算包括标点、英文和空格，不能仅凭“看起来不长”判断是否能放下。信息较多时先精简、调整页型或在允许的总页数内分页。

## 不调用模型，直接生成通用模板

技能附带使用填写提示的内容文件，可直接生成模板供手工编辑；媒体槽未填时仍属于待补素材的模板：

```bash
COURSE_SKILL_DIR="$HOME/.dsh/skills/course-ppt-template"

python3 "$COURSE_SKILL_DIR/scripts/pptx_engine.py" build \
  --template "$COURSE_SKILL_DIR/assets/template.pptx" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --content "$COURSE_SKILL_DIR/examples/template-content.json" \
  --output "$PWD/outputs/通用教学模板.pptx"
```

若想编辑内容 JSON，可参考 [AIUI 入门开发示例](examples/rokid-aiui-intro-content.json) 和 [SKILL.md 的内容格式](SKILL.md#内容文件与生成)。所有非自动槽位必须填写，不能增加未知字段或保留空文字。

## 怎样检查课件

### 检查结构

`build` 成功时会执行结构检查，也可以单独再验证已有输出。`--content` 必须指向生成这份课件时使用的内容 JSON：

```bash
python3 "$COURSE_SKILL_DIR/scripts/pptx_engine.py" validate \
  --pptx "$PWD/outputs/通用教学模板.pptx" \
  --template "$COURSE_SKILL_DIR/assets/template.pptx" \
  --profile "$COURSE_SKILL_DIR/references/profile.json" \
  --content "$COURSE_SKILL_DIR/examples/template-content.json"
```

它核对文字内容、页序、内部关系、文字样式、页面几何、背景、媒体和共享母版/布局/主题。**通过结构验证不等于画面和教学内容都正确。**

媒体课件还会检查素材格式、哈希、框内等比显示和视频封面。报告中的 `structural_ready`、`assets_complete` 记录机器检查与素材齐备情况，`delivery_ready` 仍保留为 `false`，等待画面及播放复核。完成复核后另行说明观察结果，无需人为修改 JSON 完成标记。视频需要在 build 与独立 validate 时都能找到 `ffprobe`。

### 渲染并查看画面

```bash
python3 "$COURSE_SKILL_DIR/scripts/render_review.py" \
  "$PWD/outputs/通用教学模板.pptx" \
  --out "$PWD/outputs/通用教学模板预览"
```

预览目录会生成 PDF、逐页 PNG 和 `review.json`；安装 Pillow 时还会生成联系图。需要复查部分页面时可加 `--pages 2,5-7`，最终交付仍应查看全部页面。

检查中文是否完整、文字是否越框或压住备注、标题是否合理换行、页码是否正确，以及内容是否覆盖课程表。界面和通讯实操课另看 [实操课程复核清单](references/practical-course-checks.md)。

渲染器可能用本机字体替代缺失字体，PPTX 本身保留参考字体。在 WPS/PowerPoint 中打开后，还应核对目标软件的显示效果。

PDF/PNG 只显示视频封面。含视频的课件还需在目标 WPS/PowerPoint 中实际播放，检查起止、画面、字幕与声音；未完成播放检查时明确记录“已嵌入，播放待验”。

## 常见问题

| 遇到的情况 | 处理方法 |
| --- | --- |
| 提到 AIUI 但没有知识联动 | 检查 DSH 是否能发现 `aiui-dev`，执行 `--with-aiui` 安装；旧对话重新加载一次技能，不能只检查标题是否出现 AIUI |
| 提示没有模板 | 检查是否下载、解压并安装了完整技能包，`assets/template.pptx` 应存在；不要只复制 SKILL.md |
| 模板与 profile 不兼容 | 重新安装同一发布版本的完整文件，或用随包源稿重新提取，不混用不同版本 |
| 提示缺少、未知或空槽位 | 按 profile 补齐该页全部非自动字段，删除多余字段 |
| 字数、行数超限 | 缩短对应文案或调整分页，不修改限制来硬塞 |
| 提示输出已存在 | 新建文件名；`run_dsh.py` 没有 `--force`，仅引擎的导入/生成命令支持明确替换生成物 |
| 找不到 DSH | 用 `--dsh-cli` 指定可执行文件；可先用 `--dry-run` 检查本地准备 |
| 模型名被拒绝 | 使用当前账号实际支持的名称；本次验证名称为 `deepseek-flash` |
| `flash1017` 能否直接使用 | 2026-11-05 实测该名称及 `deepseek-flash1017` 被当前账号拒绝，不能假定与 `deepseek-flash` 等同 |
| 中文缺字或显示为方框 | 检查渲染字体，必要时传 `--font-file`；不要将缺字预览当成完成 |
| 找不到 LibreOffice/Poppler | 安装相应工具，或用 `--soffice`、`--pdftoppm` 指定路径 |
| 结构检查通过，画面仍有问题 | 查看全部渲染页并修改文案；结构检查无法证明没有裁切或教学逻辑错误 |
| 只有媒体提示词，没有图片或视频 | 按 `media-plan.md` 调用宿主媒体工具；计划文件不会自动生成素材 |
| 提示媒体仍待生成 | 补齐计划指定的图片、MP4 与封面；`--allow-pending-media` 只允许查看未完成草稿 |
| 视频构建提示缺少 ffprobe | 安装工具或在 build/validate 加 `--ffprobe`；仅提取封面才需 ffmpeg |
| MP4 已在包中但不能确认播放 | 在目标软件实际播放；不能用文件存在或静态封面代替验收 |

## 已验证范围与文件导航

2026-11-05 已使用 DSH `deepseek-flash` 测试多门通用课程及界面/通讯实操课，发布示例统一采用《Rokid AIUI 入门开发》。真实模型生成后经过内容审校和全页画面检查；这些记录不代表所有新课程都能免审交付。详见 [验证记录](references/validation.md)。

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | AI 助手执行说明 |
| [install_skill.py](scripts/install_skill.py) | 安装完整技能，更新前保留备份 |
| [profile.json](references/profile.json) | 九类页面、文字/媒体槽位和预算 |
| [base-profile.json](references/base-profile.json) | 原 Lesson02 七类基础页面，供模板重建 |
| [设计说明](references/design-notes.md) | 模板来源、参考差异、已知原稿问题 |
| [实操复核清单](references/practical-course-checks.md) | 界面流转、通讯概念和课堂步骤检查 |
| [AIUI 联动说明](references/aiui-routing.md) | 自然触发、依赖安装、按需读取知识与误触发边界 |
| [AIUI 触发实测](references/aiui-routing-validation.md) | 升级前缺依赖、升级后正反例与完整矩阵结果 |
| [AIUI 自然提问测试](references/aiui-routing-tests.json) | 不强制技能名的正反例测试 |
| [install_aiui_dependency.py](scripts/install_aiui_dependency.py) | 从本机或固定上游安装真实 AIUI 开发技能 |
| [AIUI 演示图说明](references/aiui-demo-visuals.md) | 仅眼镜端画面使用单绿、截图与生成边界及提示词 |
| [媒体槽与计划流程](references/media-slots.md) | 图片/视频大纲、宿主生成、素材入槽与草稿状态 |
| [验证记录](references/validation.md) | 本次实际验证范围及限制 |
| [run_dsh.py](scripts/run_dsh.py) | 调用本机 DSH 生成课件 |
| [pptx_engine.py](scripts/pptx_engine.py) | 导入模板、填充内容、验证结构 |
| [plan_course_media.py](scripts/plan_course_media.py) | 由大纲列媒体任务，收集本地素材路径 |
| [prepare_media_template.py](scripts/prepare_media_template.py) | 从基础七页建立九页型媒体模板与配套 profile |
| [render_review.py](scripts/render_review.py) | 导出 PDF/PNG 供画面复核 |

仓库随包提供经本次授权分享的课件模板、所需图片及指定源稿；原始讲师模板另附于 Releases。代码采用 [MIT License](LICENSE)，AIUI 上游依赖、课件、品牌图形与第三方素材保留各自权利，详见 [素材说明](ASSET_NOTICES.md)。不包含登录凭据、字体安装包或用户后续课程及运行日志。
