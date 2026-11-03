import AppKit
import CoreGraphics
import QuartzCore

// This target intentionally uses ordinary native controls. It does not create a
// protected media layer, change capture policy, or capture the desktop itself.
struct Options {
    var output: URL
    var duration: TimeInterval = 0
    var autoType = false
    var integrityProbe = false
    var legacyHookDemo = false
    var guardRunner = ExamGuardLaunchConfiguration.projectRoot.appendingPathComponent("scripts/exam-guard.py")
    var guardInventory = ExamGuardLaunchConfiguration.projectRoot.appendingPathComponent("build/RemoteProcessInventory")
    var guardPolicy = ExamGuardLaunchConfiguration.projectRoot.appendingPathComponent("Sources/RemoteProcessInventory/policy.json")
    var guardPython = URL(fileURLWithPath: "/usr/bin/python3")
    var guardWorker: URL?
    var guardVendors = ["uu", "todesk", "sunlogin"]
    var guardWorkerLease = 180
    var guardTestMode = false
    var guardTestAutoStart = false
    var guardTestWorkspaceEventAfter: TimeInterval?

    init() throws {
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        output = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Desktop/考试星防作弊/Hook新方案_20261101/artifacts")
            .appendingPathComponent("native-interactive-\(stamp)-\(UUID().uuidString.prefix(6))")
        let args = Array(CommandLine.arguments.dropFirst())
        var index = 0
        while index < args.count {
            switch args[index] {
            case "--output":
                index += 1
                guard index < args.count, !args[index].hasPrefix("--") else { throw optionError("--output requires a directory") }
                output = URL(fileURLWithPath: args[index], isDirectory: true).standardizedFileURL
            case "--duration":
                index += 1
                guard index < args.count, let value = Double(args[index]), value.isFinite, value >= 0 else {
                    throw optionError("--duration requires a finite number >= 0")
                }
                duration = value
            case "--auto-type": autoType = true
            case "--integrity-probe": integrityProbe = true
            #if LEGACY_HOOK_TESTING
            case "--legacy-hook-demo": legacyHookDemo = true
            #endif
            case "--guard-runner", "--guard-inventory", "--guard-policy", "--guard-python", "--guard-worker":
                let flag = args[index]
                index += 1
                guard index < args.count, args[index].hasPrefix("/"), !args[index].hasPrefix("--") else {
                    throw optionError("\(flag) requires an absolute path")
                }
                let value = URL(fileURLWithPath: args[index]).standardizedFileURL
                switch flag {
                case "--guard-runner": guardRunner = value
                case "--guard-inventory": guardInventory = value
                case "--guard-policy": guardPolicy = value
                case "--guard-worker": guardWorker = value
                default: guardPython = value
                }
            case "--guard-vendors":
                index += 1
                guard index < args.count else { throw optionError("--guard-vendors requires a comma-separated set") }
                let values = args[index].split(separator: ",", omittingEmptySubsequences: false).map(String.init)
                guard !values.isEmpty, Set(values).count == values.count,
                      values.allSatisfy({ ["uu", "todesk", "sunlogin"].contains($0) }) else {
                    throw optionError("--guard-vendors only supports uu,todesk,sunlogin without duplicates")
                }
                guardVendors = values
            case "--guard-worker-lease":
                index += 1
                guard index < args.count, let seconds = Int(args[index]), (10...600).contains(seconds) else {
                    throw optionError("--guard-worker-lease requires 10...600 seconds")
                }
                guardWorkerLease = seconds
            #if GUARD_TESTING
            case "--guard-test-mode": guardTestMode = true
            case "--guard-test-auto-start": guardTestAutoStart = true
            case "--guard-test-workspace-event-after":
                index += 1
                guard index < args.count, let value = Double(args[index]), value.isFinite, value > 0 else {
                    throw optionError("--guard-test-workspace-event-after requires a positive number")
                }
                guardTestWorkspaceEventAfter = value
            #endif
            case "--help":
                print("NativeExamHookDemo --output NEW_OR_EMPTY_DIRECTORY [--guard-runner ABSOLUTE --guard-inventory ABSOLUTE --guard-policy ABSOLUTE --guard-python ABSOLUTE] [--guard-worker ABSOLUTE --guard-vendors uu,todesk,sunlogin --guard-worker-lease 180] [--duration SECONDS] [--legacy-hook-demo] [--integrity-probe]")
                exit(0)
            default: throw optionError("Unknown option: \(args[index])")
            }
            index += 1
        }
        guard (!guardTestAutoStart && guardTestWorkspaceEventAfter == nil) || guardTestMode else { throw optionError("Test auto-start requires an explicit test build and --guard-test-mode") }
        guard !(legacyHookDemo && guardTestMode) else { throw optionError("Legacy and guard test modes cannot be combined") }
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: output.path, isDirectory: &isDirectory) {
            guard isDirectory.boolValue,
                  try FileManager.default.contentsOfDirectory(atPath: output.path).isEmpty else {
                throw optionError("Output directory must be new or empty; refusing to overwrite a previous run")
            }
        } else {
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        }
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: output.path)
    }
}

func optionError(_ message: String) -> NSError {
    NSError(domain: "NativeExamHookDemo.Options", code: 64,
            userInfo: [NSLocalizedDescriptionKey: message])
}

@objc(NativeExamAppDelegate)
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
                         NSTextFieldDelegate, NSTextViewDelegate {
    let options: Options
    let launchedAt = Date()
    let launchHostTime = CACurrentMediaTime()
    var examWindow: NSWindow!
    var publicWindow: NSWindow!
    var preparationWindow: NSWindow!
    var guardTitle: NSTextField!
    var guardMessage: NSTextField!
    var guardDetails: NSTextField!
    var inspectButton: NSButton!
    var authorizeButton: NSButton!
    var startButton: NSButton!
    var endButton: NSButton!
    var leaveUnconfirmedButton: NSButton!
    var recoveryWaitTimedOut = false
    var permitExitWithUnconfirmedRecovery = false
    var guardClient: ExamGuardClient?
    var terminationPending = false
    var terminationTimeout: Timer?
    var guardTestStarted = false
    var workspaceObservers: [NSObjectProtocol] = []
    var wasShowingQuestions = false
    var answerField: NSTextField!
    var answerView: NSTextView!
    var questionPicker: NSPopUpButton!
    var optionButtons: [NSButton] = []
    var resultLabel: NSTextField!
    var publicCounter: NSTextField!
    var publicColor: NSView!
    var integrityLabel: NSTextField!
    var uuHookLabel: NSTextField!
    let integrityMonitor: RuntimeIntegrityMonitor
    let uuHookMonitor: UUHookMonitor
    var integrityStatus: [String: Any] = ["status": "checking", "requiresReview": false]
    var uuHookStatus: [String: Any] = ["status": "checking"]
    var timer: Timer?
    var securityTimer: Timer?
    var selectedOption = 0
    var ticks = 0
    var textEditNotifications = 0
    var buttonActions = 0
    var automaticUpdates = 0
    var submittedCount = 0
    var finishing = false
    var lastEvent = "launch"

    init(options: Options) {
        self.options = options
        integrityMonitor = RuntimeIntegrityMonitor(output: options.output)
        uuHookMonitor = UUHookMonitor(output: options.output.appendingPathComponent("uu-hook-status.json"))
    }

    func label(_ text: String, frame: NSRect, size: CGFloat = 16, bold: Bool = false) -> NSTextField {
        let view = NSTextField(labelWithString: text)
        view.frame = frame
        view.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        view.lineBreakMode = .byWordWrapping
        view.maximumNumberOfLines = 0
        return view
    }

    func buildMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "退出原生考试 Demo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let editItem = NSMenuItem(title: "编辑", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "编辑")
        editMenu.addItem(withTitle: "撤销", action: NSSelectorFromString("undo:"), keyEquivalent: "z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        menu.addItem(editItem)
        NSApp.mainMenu = menu
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMenu()
        buildPublicWindow()
        if options.legacyHookDemo {
            buildExamWindow()
            examWindow.title = "历史 Hook 实验 — 未启用考试门禁"
            placeExamAndPublicWindows()
            publicWindow.orderFront(nil)
            examWindow.makeKeyAndOrderFront(nil)
            examWindow.makeFirstResponder(answerField)
            lastEvent = "legacy-windows-ready-no-exam-gate"
        } else {
            buildPreparationWindow()
            publicWindow.orderFront(nil)
            preparationWindow.makeKeyAndOrderFront(nil)
            let configuration = ExamGuardLaunchConfiguration(
                python: options.guardPython, runner: options.guardRunner,
                inventory: options.guardInventory, policy: options.guardPolicy,
                worker: options.guardWorker, vendors: options.guardVendors, workerLease: options.guardWorkerLease,
                sessionDirectory: options.output.appendingPathComponent("guard-session", isDirectory: true),
                sessionID: UUID().uuidString, testMode: options.guardTestMode)
            let client = ExamGuardClient(configuration: configuration)
            guardClient = client
            client.onChange = { [weak self] in self?.guardChanged() }
            lastEvent = "preparing-no-question-controls"
            persist()
            client.launch()
            for name in [NSWorkspace.willSleepNotification, NSWorkspace.didWakeNotification,
                         NSWorkspace.sessionDidResignActiveNotification] {
                workspaceObservers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                    guard let self, !self.finishing else { return }
                    self.guardClient?.localPause("设备休眠、唤醒或用户会话切换，考试已暂停，请重新确认环境")
                    _ = self.guardClient?.send("pause", reason: "ui_workspace_lifecycle_changed")
                })
            }
            #if GUARD_TESTING
            if options.guardTestMode, let after = options.guardTestWorkspaceEventAfter {
                let testTimer = Timer(timeInterval: after, repeats: false) { _ in
                    // Posts only in this process; never sleeps the actual Mac.
                    NSWorkspace.shared.notificationCenter.post(name: NSWorkspace.willSleepNotification, object: nil)
                }
                RunLoop.main.add(testTimer, forMode: .common)
            }
            #endif
        }
        NSApp.activate(ignoringOtherApps: true)
        persist()
        refreshSecurity()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.tick() }
        let securityTimer = Timer(timeInterval: 5, repeats: true) { [weak self] _ in self?.refreshSecurity() }
        RunLoop.main.add(securityTimer, forMode: .common)
        self.securityTimer = securityTimer
        if options.duration > 0 {
            let durationTimer = Timer(timeInterval: options.duration, repeats: false) { _ in NSApp.terminate(nil) }
            RunLoop.main.add(durationTimer, forMode: .common)
        }
    }

    func placeExamAndPublicWindows() {
        guard let screen = NSScreen.screens.first, let examWindow, let publicWindow else { return }
        let visible = screen.visibleFrame
        examWindow.setFrameOrigin(NSPoint(x: visible.minX + 24, y: visible.maxY - examWindow.frame.height - 24))
        let rightX = visible.minX + 24 + examWindow.frame.width + 16
        let publicX = rightX + publicWindow.frame.width <= visible.maxX
            ? rightX : max(visible.minX + 24, visible.maxX - publicWindow.frame.width - 16)
        let publicY = rightX + publicWindow.frame.width <= visible.maxX
            ? visible.maxY - publicWindow.frame.height - 24 : visible.minY + 12
        publicWindow.setFrameOrigin(NSPoint(x: publicX, y: publicY))
    }

    func buildPreparationWindow() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 760, height: 440))
        preparationWindow = NSWindow(contentRect: content.frame,
            styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        preparationWindow.title = options.guardTestMode ? "考试准备 — 仅模拟测试" : "考试准备 — 本机开发验证"
        preparationWindow.isReleasedWhenClosed = false
        preparationWindow.delegate = self
        preparationWindow.contentView = content
        preparationWindow.center()
        guardTitle = label("考试前检查", frame: NSRect(x: 24, y: 375, width: 710, height: 38), size: 27, bold: true)
        guardMessage = label("正在启动检测服务；试题尚未加载。", frame: NSRect(x: 24, y: 258, width: 710, height: 98), size: 18)
        guardDetails = label(options.guardTestMode ? "模拟测试：此模式不能证明真实远控已被关闭。" :
            "本机开发验证。考试前需检查并关闭禁止的远控组件，结束后恢复本次临时改变。", frame: NSRect(x: 24, y: 165, width: 710, height: 76), size: 14)
        for view in [guardTitle!, guardMessage!, guardDetails!] { content.addSubview(view) }
        func addButton(_ title: String, _ action: Selector, _ x: CGFloat, _ width: CGFloat) -> NSButton {
            let button = NSButton(title: title, target: self, action: action)
            button.bezelStyle = .rounded
            button.frame = NSRect(x: x, y: 95, width: width, height: 36)
            content.addSubview(button)
            return button
        }
        inspectButton = addButton("开始检查 / 重新检查", #selector(inspectGuard(_:)), 20, 180)
        authorizeButton = addButton("申请管理员服务", #selector(authorizeGuard(_:)), 207, 175)
        startButton = addButton("开始考试", #selector(startGuard(_:)), 390, 145)
        endButton = addButton("结束并恢复", #selector(endGuard(_:)), 548, 185)
        startButton.isEnabled = false
        leaveUnconfirmedButton = NSButton(title: "退出界面（恢复未确认）", target: self, action: #selector(leaveUnconfirmed(_:)))
        leaveUnconfirmedButton.bezelStyle = .rounded
        leaveUnconfirmedButton.frame = NSRect(x: 490, y: 56, width: 240, height: 30)
        leaveUnconfirmedButton.isHidden = true
        content.addSubview(leaveUnconfirmedButton)
        content.addSubview(label("检查未通过、检测中断或恢复未确认时，将保持准备或暂停状态。",
            frame: NSRect(x: 24, y: 8, width: 710, height: 44), size: 14))
    }

    @objc func inspectGuard(_ sender: Any?) { _ = guardClient?.send("inspect") }
    @objc func authorizeGuard(_ sender: Any?) { _ = guardClient?.send("requestAuthorization") }
    @objc func startGuard(_ sender: Any?) {
        guard let client = guardClient, integrityStatus["requiresReview"] as? Bool != true else { return }
        _ = client.send(client.canResume ? "resume" : "start")
    }
    @objc func endGuard(_ sender: Any?) {
        hideQuestions()
        _ = guardClient?.send("end")
    }

    @objc func leaveUnconfirmed(_ sender: Any?) {
        let alert = NSAlert()
        alert.messageText = "退出界面，但保留恢复未确认状态？"
        alert.informativeText = "当前无法确认远控已恢复。退出界面不会强制结束恢复服务，也不会把本轮标记为恢复成功；请依据恢复记录继续处理。"
        alert.addButton(withTitle: "保留界面")
        alert.addButton(withTitle: "退出界面")
        alert.beginSheetModal(for: preparationWindow) { [weak self] result in
            guard result == .alertSecondButtonReturn, let self else { return }
            self.permitExitWithUnconfirmedRecovery = true
            self.persist()
            NSApp.terminate(nil)
        }
    }

    func hideQuestions() {
        guard !options.legacyHookDemo else { return }
        answerField?.isEditable = false
        answerView?.isEditable = false
        examWindow?.endEditing(for: nil)
        examWindow?.makeFirstResponder(nil)
        // Also dismiss app-owned sheets/popup windows so a secondary question
        // window cannot outlive the main window's pause. This cannot retract
        // pixels already delivered to a remote viewer or an OS IME overlay.
        for window in NSApp.windows where window !== preparationWindow && window !== publicWindow {
            window.orderOut(nil)
        }
        examWindow?.contentView?.isHidden = true
        wasShowingQuestions = false
    }

    func guardChanged() {
        guard !options.legacyHookDemo, let client = guardClient else { return }
        let status = client.gate.status
        let integrityPass = integrityStatus["requiresReview"] as? Bool != true
        let canShow = client.questionsAllowed && !terminationPending && integrityPass
        if canShow {
            if examWindow == nil { buildExamWindow(); placeExamAndPublicWindows() }
            answerField.isEditable = true
            answerView.isEditable = true
            examWindow.contentView?.isHidden = false
            if !wasShowingQuestions {
                examWindow.makeKeyAndOrderFront(nil)
                examWindow.makeFirstResponder(answerField)
            }
            wasShowingQuestions = true
            preparationWindow.orderOut(nil)
        } else {
            hideQuestions()
            preparationWindow.orderFront(nil)
        }
        let state = status?.state ?? "preparing"
        let titles = ["preparing": "考试前检查", "ready": "检查通过，等待开考", "exam": "考试进行中",
                      "paused": "考试已暂停", "restoring": "正在结束并恢复", "recoveryPending": "恢复结果待确认", "finished": "本轮已结束"]
        guardTitle.stringValue = client.gate.faultReason == nil ? (titles[state] ?? "考试前检查") : "检测未就绪 / 考试暂停"
        if state == "exam" && !canShow && client.gate.faultReason == nil { guardTitle.stringValue = "考试已暂停，等待确认" }
        guardMessage.stringValue = client.gate.faultReason ?? status?.message ?? "等待检测服务；试题尚未加载。"
        guardTitle.textColor = canShow || client.canStart ? .labelColor : .systemOrange
        startButton.title = client.canResume ? "继续考试" : "开始考试"
        startButton.isEnabled = !terminationPending && integrityPass && (client.canStart || client.canResume)
        inspectButton.isEnabled = client.isRunning && !client.gate.ending && !terminationPending
        authorizeButton.isEnabled = inspectButton.isEnabled
        endButton.isEnabled = client.isRunning && state != "finished"
        leaveUnconfirmedButton.isHidden = state == "finished" || !(recoveryWaitTimedOut || state == "recoveryPending" || (!client.isRunning && !clientHasNeverReported()))
        if recoveryWaitTimedOut && state != "finished" {
            guardTitle.stringValue = "恢复尚未确认"
            guardMessage.stringValue = "已保留恢复服务。可再次点击结束并恢复，或明确选择退出界面并保留未确认记录。"
        }
        let prefix = options.guardTestMode ? "仅模拟测试；不能作为真实阻断证据。" : "本机开发验证；尚非正式部署版本。"
        let reasons = status?.detail["reasons"] as? [String] ?? []
        let names = ["uu": "UU 远程", "todesk": "ToDesk", "sunlogin": "向日葵"]
        let scope = "本轮检查：" + client.configuration.vendors.map { names[$0] ?? $0 }.joined(separator: "、")
        guardDetails.stringValue = prefix + "\n" + scope + (reasons.isEmpty ? "" : "\n" + reasons.prefix(2).joined(separator: "；"))
        lastEvent = canShow ? "guard-exam-permitted" : "guard-questions-withheld"
        persist()
        if terminationPending && state == "finished" {
            terminationTimeout?.invalidate()
            terminationPending = false
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        #if GUARD_TESTING
        if options.guardTestMode && options.guardTestAutoStart && client.canStart && !guardTestStarted {
            guardTestStarted = true
            DispatchQueue.main.async { [weak self] in self?.startGuard(nil) }
        }
        #endif
    }

    func buildExamWindow() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 850, height: 690))
        examWindow = NSWindow(contentRect: content.frame,
                              styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        examWindow.title = options.legacyHookDemo ? "NativeExamHookDemo — 原生考试窗口" : "考试管控验证 — 合成试题"
        examWindow.isReleasedWhenClosed = false
        examWindow.sharingType = .readOnly
        examWindow.delegate = self
        examWindow.contentView = content

        let title = label(options.legacyHookDemo ? "NATIVE-EXAM-SECRET-HOOK9" : "SYNTHETIC-GUARD-EXAM", frame: NSRect(x: 22, y: 640, width: 806, height: 32), size: 25, bold: true)
        title.textColor = .systemRed
        content.addSubview(title)
        content.addSubview(label(options.legacyHookDemo ? "原生 AppKit 控件 · 当前窗口没有设置媒体层捕获保护" : "合成测试题 · 检查通过后显示，发现异常时暂停", frame: NSRect(x: 22, y: 605, width: 806, height: 27)))
        content.addSubview(label(options.legacyHookDemo ? "第 1 题：下面哪一项说明当前试验的保护来源？" : "第 1 题：本轮验证的考试管控行为是什么？", frame: NSRect(x: 22, y: 562, width: 806, height: 30), size: 20, bold: true))
        let answers = options.legacyHookDemo
            ? ["A  由外部捕获进程中的 hook 处理画面", "B  输入框自身开启了视频图层保护", "C  已经禁止所有系统截图方式", "D  已经证明全部远程软件无法捕获"]
            : ["A  检查禁止组件，发现异常后暂停并处置", "B  仅凭软件名字判断是否安全", "C  把发送终止信号等同于清理完成", "D  检测服务失联后继续显示试题"]
        for (index, text) in answers.enumerated() {
            let button = NSButton(radioButtonWithTitle: text, target: self, action: #selector(changeChoice(_:)))
            button.tag = index
            button.frame = NSRect(x: 28, y: 520 - index * 34, width: 795, height: 28)
            button.font = .systemFont(ofSize: 17)
            button.state = index == 0 ? .on : .off
            optionButtons.append(button)
            content.addSubview(button)
        }
        content.addSubview(label("短答（真实 NSTextField，可选择、复制与输入）：", frame: NSRect(x: 22, y: 380, width: 800, height: 25)))
        answerField = NSTextField(frame: NSRect(x: 22, y: 340, width: 806, height: 32))
        answerField.stringValue = options.legacyHookDemo ? "NATIVE-ANSWER-HOOK9" : "此处只输入合成测试答案"
        answerField.font = .systemFont(ofSize: 19)
        answerField.placeholderString = "仅输入合成测试文字"
        answerField.isEditable = true
        answerField.isSelectable = true
        answerField.delegate = self
        content.addSubview(answerField)

        content.addSubview(label("长答（真实 NSTextView / NSScrollView）：", frame: NSRect(x: 22, y: 305, width: 800, height: 25)))
        let scroll = NSScrollView(frame: NSRect(x: 22, y: 135, width: 806, height: 162))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        answerView = NSTextView(frame: NSRect(x: 0, y: 0, width: scroll.contentSize.width, height: scroll.contentSize.height))
        answerView.isEditable = true
        answerView.isSelectable = true
        answerView.isRichText = false
        answerView.allowsUndo = true
        answerView.font = .systemFont(ofSize: 17)
        answerView.minSize = NSSize(width: 0, height: scroll.contentSize.height)
        answerView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        answerView.isVerticallyResizable = true
        answerView.isHorizontallyResizable = false
        answerView.autoresizingMask = [.width]
        answerView.textContainer?.containerSize = NSSize(width: scroll.contentSize.width, height: CGFloat.greatestFiniteMagnitude)
        answerView.textContainer?.widthTracksTextView = true
        answerView.textContainerInset = NSSize(width: 8, height: 8)
        answerView.string = "NATIVE-LONG-ANSWER-HOOK9\n这是真实的原生文本编辑区。\n可输入、选中文本、滚动并使用中文输入法；这些操作是否被远端捕获仍需实测。\n\n" + (1...12).map { "合成测试材料第 \($0) 行：只在本地保存此试验的输入内容。" }.joined(separator: "\n")
        if !options.legacyHookDemo {
            answerView.string = "合成考试材料：用于验证准入、暂停、恢复及远端画面变化。\n请只输入测试文字，不输入真实考试答案或个人信息。"
        }
        answerView.delegate = self
        scroll.documentView = answerView
        content.addSubview(scroll)

        questionPicker = NSPopUpButton(frame: NSRect(x: 22, y: 88, width: 200, height: 30))
        questionPicker.addItems(withTitles: ["第 1 题", "第 2 题", "第 3 题"])
        questionPicker.target = self
        questionPicker.action = #selector(changeQuestion(_:))
        content.addSubview(questionPicker)
        let submit = NSButton(title: "提交本地答案", target: self, action: #selector(submitAnswer(_:)))
        submit.bezelStyle = .rounded
        submit.frame = NSRect(x: 240, y: 88, width: 170, height: 30)
        content.addSubview(submit)
        resultLabel = label(options.legacyHookDemo ? "尚未提交 · 窗口共享类型 readOnly" : "尚未提交 · 本机合成测试", frame: NSRect(x: 22, y: 22, width: 806, height: 54), size: 15)
        resultLabel.textColor = .secondaryLabelColor
        content.addSubview(resultLabel)
    }

    func buildPublicWindow() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 530, height: 300))
        publicWindow = NSWindow(contentRect: content.frame,
                                styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        publicWindow.title = "PUBLIC-CONTROL-HOOK — 捕获正常性对照"
        publicWindow.isReleasedWhenClosed = false
        publicWindow.sharingType = .readOnly
        publicWindow.delegate = self
        publicWindow.contentView = content
        content.addSubview(label("PUBLIC-CONTROL-HOOK", frame: NSRect(x: 18, y: 158, width: 494, height: 32), size: 26, bold: true))
        content.addSubview(label("此窗口应持续可见，用于排除全屏黑图或断流。", frame: NSRect(x: 18, y: 122, width: 494, height: 26), size: 16))
        publicCounter = label("LIVE-TICK-0000", frame: NSRect(x: 18, y: 68, width: 390, height: 34), size: 25, bold: true)
        publicCounter.font = .monospacedSystemFont(ofSize: 25, weight: .bold)
        content.addSubview(publicCounter)
        publicColor = NSView(frame: NSRect(x: 435, y: 68, width: 60, height: 34))
        publicColor.wantsLayer = true
        publicColor.layer?.backgroundColor = NSColor.systemGreen.cgColor
        content.addSubview(publicColor)
        content.addSubview(label("主窗口关闭时结束；本对照窗口不属于遮蔽目标。", frame: NSRect(x: 18, y: 20, width: 494, height: 27), size: 14))
        for view in content.subviews { view.frame.origin.y += 90 }
        integrityLabel = label("客户端完整性：检查中", frame: NSRect(x: 18, y: 48, width: 494, height: 42), size: 14)
        uuHookLabel = label("UU Hook：检查中", frame: NSRect(x: 18, y: 6, width: 494, height: 42), size: 14)
        content.addSubview(integrityLabel)
        content.addSubview(uuHookLabel)
    }

    @objc func changeChoice(_ sender: NSButton) {
        selectedOption = sender.tag
        for (i, button) in optionButtons.enumerated() { button.state = i == selectedOption ? .on : .off }
        buttonActions += 1
        lastEvent = "native-radio-action"
        persist()
    }
    @objc func changeQuestion(_ sender: NSPopUpButton) {
        buttonActions += 1
        lastEvent = "native-popup-action"
        persist()
    }
    @objc func submitAnswer(_ sender: NSButton) {
        submittedCount += 1
        buttonActions += 1
        resultLabel.stringValue = "本地提交 \(submittedCount) 次 · 选项 \(["A", "B", "C", "D"][selectedOption]) · 输入 \(answerField.stringValue.count) 字符"
        lastEvent = "native-submit-action"
        persist()
    }
    func controlTextDidChange(_ obj: Notification) {
        textEditNotifications += 1
        lastEvent = "native-textfield-did-change"
        persist()
    }
    func textDidChange(_ notification: Notification) {
        textEditNotifications += 1
        lastEvent = "native-textview-did-change"
        persist()
    }

    @objc dynamic func tick() {
        ticks += 1
        publicCounter.stringValue = String(format: "LIVE-TICK-%04d", ticks)
        publicColor.layer?.backgroundColor = (ticks % 2 == 0 ? NSColor.systemGreen : NSColor.systemOrange).cgColor
        if options.autoType && answerField != nil && (options.legacyHookDemo || guardClient?.questionsAllowed == true) && ticks % 2 == 0 {
            automaticUpdates += 1
            answerField.stringValue = String(format: "NATIVE-ANSWER-HOOK9 AUTO-%04d", automaticUpdates)
            lastEvent = "programmatic-text-update-not-keyboard-input"
        }
        persist()
    }

    func refreshSecurity() {
        integrityMonitor.refresh { [weak self] status in
            guard let self, !self.finishing else { return }
            self.integrityStatus = status
            let review = status["requiresReview"] as? Bool == true
            self.integrityLabel.stringValue = review ? "客户端完整性：发现异常，已标记待复核" :
                status["status"] as? String == "incomplete" ? "客户端完整性：暂未发现异常，部分检查无法确认" : "客户端完整性：本轮未发现异常"
            self.integrityLabel.textColor = review ? .systemRed : .secondaryLabelColor
            if review && !self.options.legacyHookDemo {
                self.guardClient?.localPause("客户端完整性出现异常，考试已暂停")
                _ = self.guardClient?.send("pause", reason: "ui_integrity_review_required")
            }
            self.persist()
        }
        guard options.legacyHookDemo else {
            uuHookLabel.stringValue = "远控管控：以考试准备页和守护状态为准"
            return
        }
        uuHookMonitor.refresh { [weak self] status in
            guard let self, !self.finishing else { return }
            self.uuHookStatus = status
            // The monitor supplies a summary describing coverage, not protection.
            self.uuHookLabel.stringValue = "UU Hook：\(status["summary"] as? String ?? status["status"] as? String ?? "无法确认")"
            if status["reportWriteSucceeded"] as? Bool == false || status["historyWriteSucceeded"] as? Bool == false {
                self.uuHookLabel.stringValue = "UU Hook：检测记录写入失败，请查看输出权限"
                self.uuHookLabel.textColor = .systemOrange
            } else { self.uuHookLabel.textColor = .secondaryLabelColor }
            self.persist()
        }
    }

    func windowInfo(_ window: NSWindow, marker: String) -> [String: Any] {
        var result: [String: Any] = ["windowID": window.windowNumber,
                                   "ownerPID": ProcessInfo.processInfo.processIdentifier,
                                   "title": window.title, "marker": marker,
                                   "visible": window.isVisible, "miniaturized": window.isMiniaturized,
                                   "sharingType": window.sharingType.rawValue]
        let info = CGWindowListCopyWindowInfo(.optionIncludingWindow, CGWindowID(window.windowNumber)) as? [[String: Any]]
        if let raw = info?.first?[kCGWindowBounds as String] as? [String: Any],
           let rect = CGRect(dictionaryRepresentation: raw as CFDictionary),
           !rect.isInfinite, !rect.isNull {
            result["bounds"] = ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height]
            result["boundsSource"] = "CGWindowListCopyWindowInfo"
        } else { result["boundsError"] = "window bounds unavailable; do not treat this as a protected result" }
        return result
    }

    func writeJSON(_ data: [String: Any], name: String) {
        do {
            let bytes = try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys])
            try bytes.write(to: options.output.appendingPathComponent(name), options: .atomic)
        } catch { fputs("State write failed: \(error.localizedDescription)\n", stderr) }
    }

    @objc dynamic func persist() {
        if !options.legacyHookDemo {
            guard publicWindow != nil else { return }
            let client = guardClient
            var state: [String: Any] = ["schemaVersion": 2, "appName": "NativeExamGuardDemo",
                "pid": ProcessInfo.processInfo.processIdentifier, "timestamp": ISO8601DateFormatter().string(from: Date()),
                "nativeUI": true, "captureProtectionEnabled": false, "legacyHookMode": false,
                "testOnlyMode": options.guardTestMode, "productionReady": false,
                "questionControlsCreated": answerField != nil,
                "questionsVisible": examWindow?.isVisible == true && examWindow?.contentView?.isHidden == false,
                "examGateActuallyEnforced": true, "guardSessionID": client?.configuration.sessionID ?? "",
                "guardState": client?.gate.status?.state ?? "unavailable",
                "guardFault": client?.gate.faultReason ?? "", "guardSequence": client?.gate.lastSequence ?? 0,
                "guardFresh": client?.gate.fresh(at: client?.now ?? 0) ?? false,
                "questionsAllowed": client?.questionsAllowed ?? false,
                "terminationPending": terminationPending, "recoveryWaitTimedOut": recoveryWaitTimedOut,
                "exitWithRecoveryUnconfirmed": permitExitWithUnconfirmedRecovery,
                "lastEvent": lastEvent,
                "publicLiveTick": ticks, "buttonActions": buttonActions, "submittedCount": submittedCount,
                "answerContentPersisted": false, "finishing": finishing]
            if let status = client?.gate.status { state["guardStatus"] = status.detail }
            state["control"] = windowInfo(publicWindow, marker: "PUBLIC-CONTROL-HOOK")
            if let preparationWindow { state["preparation"] = windowInfo(preparationWindow, marker: "EXAM-PREPARATION") }
            if let examWindow { state["exam"] = windowInfo(examWindow, marker: "SYNTHETIC-GUARD-EXAM") }
            writeJSON(state, name: "state.json")
            writeJSON(["schemaVersion": 1, "enabled": false, "scope": "guard_mode_no_capture_hook"], name: "hook-config.json")
            return
        }
        guard examWindow != nil, publicWindow != nil, answerField != nil, answerView != nil else { return }
        let exam = windowInfo(examWindow, marker: "NATIVE-EXAM-SECRET-HOOK9")
        let control = windowInfo(publicWindow, marker: "PUBLIC-CONTROL-HOOK")
        let now = ISO8601DateFormatter().string(from: Date())
        var state: [String: Any] = [
            "schemaVersion": 1, "appName": "NativeExamHookDemo", "bundleID": "local.examcapture.hook.native",
            "pid": ProcessInfo.processInfo.processIdentifier, "ownerPID": ProcessInfo.processInfo.processIdentifier,
            "nativeUI": true, "captureProtectionEnabled": false,
            "timestamp": now, "hostTimeSeconds": CACurrentMediaTime(),
            "secondsSinceLaunch": CACurrentMediaTime() - launchHostTime,
            "exam": exam, "control": control, "lastEvent": lastEvent,
            "shortAnswer": answerField.stringValue, "longAnswer": answerView.string,
            "selectedOption": selectedOption, "selectedOptionLabel": ["A", "B", "C", "D"][selectedOption],
            "selectedQuestionIndex": questionPicker.indexOfSelectedItem,
            "publicLiveTick": ticks, "textEditNotifications": textEditNotifications,
            "buttonActions": buttonActions, "submittedCount": submittedCount,
            "autoTypeEnabled": options.autoType, "automaticTextUpdates": automaticUpdates,
            "automaticUpdateMeaning": "programmatic control value changes; not evidence of physical input or IME behavior",
            "finishing": finishing, "os": ProcessInfo.processInfo.operatingSystemVersionString
        ]
        state["integrity"] = integrityStatus
        state["uuHook"] = uuHookStatus
        // Convenient aliases let a single-window capture runner reuse the same protocol.
        state["windowID"] = exam["windowID"]
        state["bounds"] = exam["bounds"]
        writeJSON(state, name: "state.json")
        var config: [String: Any] = ["schemaVersion": 1,
                                    "enabled": !finishing && examWindow.isVisible && !examWindow.isMiniaturized,
                                    "windowID": examWindow.windowNumber,
                                    "ownerPID": ProcessInfo.processInfo.processIdentifier,
                                    "windowTitle": examWindow.title,
                                    "timestamp": now, "scope": "single_exam_window"]
        if let bounds = exam["bounds"] { config["bounds"] = bounds }
        else { config["enabled"] = false; config["error"] = "No valid CG target bounds" }
        writeJSON(config, name: "hook-config.json")
    }

    func windowDidMove(_ notification: Notification) { lastEvent = "window-moved"; persist() }
    func windowDidResize(_ notification: Notification) { lastEvent = "window-resized"; persist() }
    func windowDidMiniaturize(_ notification: Notification) { lastEvent = "window-minimized"; persist() }
    func windowDidDeminiaturize(_ notification: Notification) { lastEvent = "window-restored"; persist() }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if sender === examWindow || sender === preparationWindow { NSApp.terminate(nil); return false }
        lastEvent = "public-control-window-closed"
        return true
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if options.legacyHookDemo || permitExitWithUnconfirmedRecovery || guardClient?.gate.status?.state == "finished" { return .terminateNow }
        if terminationPending { return .terminateCancel }
        hideQuestions()
        guard let client = guardClient, client.isRunning else {
            // No service means no confirmation. Keep the preparation page so
            // the operator sees the unresolved recovery state rather than a
            // false "finished" result. A fresh untouched session may quit.
            if clientHasNeverReported() { return .terminateNow }
            guardMessage.stringValue = "检测服务已断开，恢复结果未确认。请检查恢复记录后再结束本机验证。"
            preparationWindow.makeKeyAndOrderFront(nil)
            leaveUnconfirmedButton.isHidden = false
            persist()
            return .terminateCancel
        }
        terminationPending = true
        recoveryWaitTimedOut = false
        _ = client.send("end")
        let timeout = Timer(timeInterval: 15, repeats: false) { [weak self] _ in
            guard let self, self.terminationPending else { return }
            self.terminationPending = false
            self.recoveryWaitTimedOut = true
            self.leaveUnconfirmedButton.isHidden = false
            self.guardMessage.stringValue = "恢复尚未确认，已保留窗口与恢复服务。可再次点击结束并恢复；不会强杀恢复进程。"
            self.lastEvent = "termination-recovery-timeout"
            self.persist()
            NSApp.reply(toApplicationShouldTerminate: false)
        }
        RunLoop.main.add(timeout, forMode: .common)
        terminationTimeout = timeout
        return .terminateLater
    }

    func clientHasNeverReported() -> Bool {
        guardClient?.gate.lastSequence == 0 && guardClient?.submittedCommandCount == 0
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !options.legacyHookDemo { guardChanged(); return false }
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        finishing = true
        lastEvent = "application-terminating"
        timer?.invalidate()
        securityTimer?.invalidate()
        terminationTimeout?.invalidate()
        guardClient?.closeTransport()
        for observer in workspaceObservers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
        workspaceObservers.removeAll()
        persist()
    }
}

do {
    let options = try Options()
    if options.integrityProbe {
        // Headless self-check: never starts, modifies, or injects into UU.
        let integrity = RuntimeIntegrityMonitor(output: options.output)
        let uu = UUHookMonitor(output: options.output.appendingPathComponent("uu-hook-status.json"))
        let duration = options.duration > 0 ? options.duration : 12
        let deadline = ProcessInfo.processInfo.systemUptime + duration
        var latestIntegrity: [String: Any] = ["status": "checking"]
        var latestUU: [String: Any] = ["status": "checking"]
        func refresh() {
            integrity.refresh { latestIntegrity = $0 }
            uu.refresh { latestUU = $0 }
        }
        refresh()
        let probeTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in refresh() }
        while ProcessInfo.processInfo.systemUptime < deadline {
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.1))
        }
        probeTimer.invalidate()
        let report = ["integrity": latestIntegrity, "uuHook": latestUU]
        if let data = try? JSONSerialization.data(withJSONObject: report, options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) { print(text) }
        exit(0)
    }
    let app = NSApplication.shared
    let delegate = AppDelegate(options: options)
    app.delegate = delegate
    app.run()
} catch {
    fputs("\(error.localizedDescription)\n", stderr)
    exit(64)
}
