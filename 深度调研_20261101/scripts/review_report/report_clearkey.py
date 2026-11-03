# Executed by build_report.py inside its existing Document context.
# Source evidence is synthetic, local, and preserved in the deep research folder.

page('Clear Key：有效媒体与捕获差异', 'E1 本机实测；macOS 26.6.2（25G83），SDK 26.5。API 从 macOS 26.4 可用。')
ptext('已用真正的 SAMPLE-AES 加密视频验证 allowsCaptureOfClearKeyVideo：false 时所测外部捕获隐藏视频，true 时可捕获。false 时同进程 VideoOutput 仍有明文，与官方文档描述存在差异，不能将其当作稳定的自录豁免。[R05]')
h2('有效媒体与控制条件')
ptext('复用本项目合成试题 MP4（1800×1000、约18秒），由 Bento4 mp42hls 生成 MPEG-TS HLS，采用 SAMPLE-AES、identity 密钥交付和匹配的16字节 key/IV。已成功离线解密；这不是整段 AES-128 加密。服务只绑定127.0.0.1。普通窗口与 AVPlayerLayer 未叠加 .none 或 preventsCapture；三组均播放就绪、时间推进、无解码错误。[R24–R26]')
h2('三组矩阵：秘密检出图片数 / 有效图片数')
table(['捕获路径','明文 / false','加密 / false','加密 / true'], [
    ('系统窗口截图', '1 / 1', '0 / 1', '1 / 1'),
    ('旧 CG 窗口及显示器合成', '2 / 2', '0 / 2', '2 / 2'),
    ('SCK 窗口及显示器单帧', '2 / 2', '0 / 2', '2 / 2'),
    ('SCK 窗口流，约2秒', '21 / 21', '0 / 22', '21 / 21'),
    ('SCK 显示器流，约2秒', '21 / 21', '0 / 22', '21 / 21'),
    ('同进程 VideoOutput 像素采样', '8 / 8', '8 / 8', '8 / 8'),
], [6.0, 3.8, 3.8, 3.8], 9)
h2('初始化顺序补测')
ptext('先设置 false 再挂接 VideoOutput，仍复制107次，4张落盘图全部含题目；完全不挂接 VideoOutput 时，外部也隐藏视频。两组共34张外部图全部未检出。主矩阵与补测合计205张 PNG（152流、25外部单帧、28像素采样），逐张OCR及标记区像素统计，无缺图或分析错误。')
note('边界：尚无本次 AVPlayer 路径的肉眼显示确认；VOD结果不证明实时试卷编码、交互延迟或完整MP4自录。false不是捕获进程白名单；true会同时开放外部捕获。证据：artifacts/clearkey-20261101T085500Z、clearkey-order-20261101T090226Z。')

page('Clear Key：同一媒体的截图对照', '下图均由独立系统截图命令取得；只含合成试题。不能据此确认用户物理屏幕正常显示。')
imagefile(
    ROOT / 'artifacts/clearkey-20261101T085500Z/sample-aes-false/system-window.png',
    '图7  SAMPLE-AES + false。原生标题和公开标签仍可读，视频区域黑色。裁去窗口阴影及底部输入提示；未修改图内像素。来源：本轮 ClearKey 主矩阵 / sample-aes-false / system-window.png。',
    width=6.0,
    crop=(112, 76, 1912, 1120),
)
imagefile(
    ROOT / 'artifacts/clearkey-20261101T085500Z/sample-aes-true/system-window.png',
    '图8  SAMPLE-AES + true。相同媒体及窗口布局，可读到合成题干和选项。采用上图相同裁剪。来源：本轮 ClearKey 主矩阵 / sample-aes-true / system-window.png。',
    width=6.0,
    crop=(112, 76, 1912, 1120),
)
note('false组同进程 VideoOutput 仍有明文，与文档描述不一致；完整数据见上一页，原图与源码均保留。')

page('AAC：考试会话与部署验收', 'E2 官方公开但受限的考试方案；当前未取得批准签名，也未运行真实 AAC 会话。[R13–R15]')
ptext('AutomaticAssessmentConfiguration 适用于教育测评，可限制考试期间的截屏、录屏和其他系统资源。考试应用可以申请专用 entitlement，但是否获批由 Apple 决定。它提供会话级限制，不提供按捕获进程授权的窗口白名单。[R13–R14]')
h2('版本与部署条件')
table(['能力','最低 macOS','部署含义'], [
    ('核心考试会话', '10.15.4', '须获批 entitlement、匹配 App ID 与有效 provisioning profile；ad-hoc添加布尔键不构成授权。'),
    ('辅助应用及配置更新', '12.0', '允许指定应用参与及配置网络；参加考试不等于获得录屏豁免。'),
    ('支持能力查询', '14.5', '运行时查询多参与者与配置更新支持；不是这些功能最早出现的版本。'),
    ('allowsScreenshots', '26.1', '仅指定复制到剪贴板的截图例外，默认false；不是SCK录屏许可。'),
], [4.6, 2.8, 10.0], 9)
ptext('26.1的截图例外针对通常由 Cmd-Control-Shift-3/4 复制到剪贴板的图像，结束会话前会清空剪贴板。当前参与者配置没有文档化的通用捕获授权键；不能发明 configurationInfo 键来承诺放行。在线文档中属于macOS27的新能力，不计入本机26.6.2验证。[R15]')
h2('自身录制必须分别判断')
table(['实现','现有依据与判定'], [
    ('主应用用 SCK 回采自己', '未找到AAC同进程捕获豁免承诺，未测。'),
    ('参与者辅助应用用 SCK', '参与／联网许可不等于捕获许可，未测。'),
    ('原始帧送入 AVAssetWriter', '非AAC原型已验证；与真实AAC会话的组合仍需获批后实测。'),
], [6.0, 11.4], 9)
h2('获批后的验收顺序')
ptext('先处理相机／麦克风等权限和可靠退出；收到会话已开始回调后才显示题目。分别测试三种录制路线、外部捕获、参与者运行／联网、会话中断与恢复，并解码最终录像。默认保持allowsScreenshots=false，同时验收VoiceOver、替代输入及敏感语义暴露。')
