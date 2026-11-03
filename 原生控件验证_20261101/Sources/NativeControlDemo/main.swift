import AppKit
import AVFoundation
import CoreMedia
import CoreVideo
import QuartzCore

let args = CommandLine.arguments
func arg(_ key: String, _ fallback: String) -> String { guard let i=args.firstIndex(of:key), i+1<args.count else{return fallback};return args[i+1] }
let mode=arg("--mode","raster-protected")
let output=URL(fileURLWithPath:arg("--output",FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Desktop/考试星防作弊/原生控件验证_20261101/artifacts/interactive").path),isDirectory:true)
let fps=Int(arg("--fps","20")) ?? 20
let duration=Double(arg("--duration","0")) ?? 0
let scenario=arg("--scenario","none")
guard ["direct","raster-baseline","raster-protected","mixed"].contains(mode), (1...60).contains(fps),duration>=0 else {exit(64)}
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
func cleanJSON(_ x:Any)->Any { if let d=x as? [String:Any]{return d.mapValues{cleanJSON($0)}};if let a=x as? [Any]{return a.map{cleanJSON($0)}};if let n=x as? Double,!n.isFinite{return String(describing:n)};return x }
func saveJSON(_ x:[String:Any],_ name:String){if let d=try? JSONSerialization.data(withJSONObject:cleanJSON(x),options:[.prettyPrinted,.sortedKeys]){try? d.write(to:output.appendingPathComponent(name),options:.atomic)}}
func rangeJSON(_ r:NSRange)->[String:Any]{["location":r.location==NSNotFound ? -1:r.location,"length":r.length]}

final class Recorder {
 let writer:AVAssetWriter;let input:AVAssetWriterInput;let adaptor:AVAssetWriterInputPixelBufferAdaptor
 var first:Double?;var accepted=0;var dropped=0
 init(_ url:URL,_ width:Int,_ height:Int)throws{
  writer=try AVAssetWriter(outputURL:url,fileType:.mp4)
  input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:width,AVVideoHeightKey:height,AVVideoCompressionPropertiesKey:[AVVideoAverageBitRateKey:8_000_000,AVVideoMaxKeyFrameIntervalKey:fps]])
  input.expectsMediaDataInRealTime=true
  adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,kCVPixelBufferWidthKey as String:width,kCVPixelBufferHeightKey as String:height,kCVPixelBufferIOSurfacePropertiesKey as String:[:]])
  writer.add(input);guard writer.startWriting() else{throw writer.error ?? NSError(domain:"Writer",code:1)};writer.startSession(atSourceTime:.zero)
 }
 func append(_ p:CVPixelBuffer,_ t:Double){if first==nil{first=t};guard input.isReadyForMoreMediaData else{dropped+=1;return};if adaptor.append(p,withPresentationTime:CMTime(seconds:t-first!,preferredTimescale:60000)){accepted+=1}else{dropped+=1}}
 func finish(_ done:@escaping()->Void){input.markAsFinished();writer.finishWriting{DispatchQueue.main.async{done()}}}
}
final class Canvas:NSView{
 override var isFlipped:Bool{true}
 override func draw(_ rect:NSRect){NSColor(calibratedRed:0.96,green:0.97,blue:0.99,alpha:1).setFill();bounds.fill()}
}
final class ProxyView:NSView,NSTextInputClient{
 weak var owner:AppDelegate?
 override var isFlipped:Bool{true}
 override var acceptsFirstResponder:Bool{true}
 override func mouseDown(with event:NSEvent){owner?.proxyMouse(event,kind:"mouseDown")}
 override func mouseDragged(with event:NSEvent){owner?.proxyMouse(event,kind:"mouseDragged")}
 override func mouseUp(with event:NSEvent){owner?.log("proxy-mouseUp",origin:"NSEvent",extra:["eventNumber":event.eventNumber])}
 override func scrollWheel(with event:NSEvent){owner?.proxyScroll(event)}
 override func keyDown(with event:NSEvent){
  owner?.log("proxy-keyDown",origin:"NSEvent",extra:["keyCode":event.keyCode,"shift":event.modifierFlags.contains(.shift)])
  if event.keyCode==48,!(owner?.editor()?.hasMarkedText() ?? false){owner?.cycleFocus(backward:event.modifierFlags.contains(.shift),origin:"NSEvent-Tab");return}
  if let o=owner,["checkbox","button"].contains(o.lastFocus){
   if event.keyCode==49 || (event.keyCode==36 && o.lastFocus=="button") || (event.keyCode==76 && o.lastFocus=="button"){o.activateFocused(origin:"NSEvent-key");return}
  }
  interpretKeyEvents([event]);owner?.render()
 }
 override func performKeyEquivalent(with event:NSEvent)->Bool{
  guard event.modifierFlags.contains(.command),let key=event.charactersIgnoringModifiers?.lowercased(),let o=owner else{return super.performKeyEquivalent(with:event)}
  switch key {case "a":o.editor()?.selectAll(nil);case "c":o.editor()?.copy(nil);case "v":o.editor()?.paste(nil);case "x":o.editor()?.cut(nil);case "z":if event.modifierFlags.contains(.shift){o.editor()?.undoManager?.redo()}else{o.editor()?.undoManager?.undo()};default:return super.performKeyEquivalent(with:event)}
  o.synchronize();o.log("proxy-command-\(key)",origin:"NSEvent");o.render();return true
 }
 override func selectAll(_ sender:Any?){owner?.editor()?.selectAll(sender);finishMenuAction("selectAll")}
 @objc func cut(_ sender:Any?){owner?.editor()?.cut(sender);finishMenuAction("cut")}
 @objc func copy(_ sender:Any?){owner?.editor()?.copy(sender);finishMenuAction("copy")}
 @objc func paste(_ sender:Any?){owner?.editor()?.paste(sender);finishMenuAction("paste")}
 @objc func undo(_ sender:Any?){owner?.editor()?.undoManager?.undo();finishMenuAction("undo")}
 @objc func redo(_ sender:Any?){owner?.editor()?.undoManager?.redo();finishMenuAction("redo")}
 func finishMenuAction(_ action:String){owner?.synchronize();owner?.log("edit-menu-\(action)",origin:"responder-chain");owner?.render()}
 func insertText(_ string:Any,replacementRange:NSRange){owner?.editor()?.insertText(string,replacementRange:replacementRange);owner?.synchronize();owner?.log("insertText",origin:"NSTextInputClient",extra:["text":(string as? NSAttributedString)?.string ?? (string as? String ?? "")]);owner?.render()}
 func setMarkedText(_ string:Any,selectedRange:NSRange,replacementRange:NSRange){owner?.editor()?.setMarkedText(string,selectedRange:selectedRange,replacementRange:replacementRange);owner?.synchronize();owner?.log("setMarkedText",origin:"NSTextInputClient",extra:["text":(string as? NSAttributedString)?.string ?? (string as? String ?? "")]);owner?.render()}
 func unmarkText(){owner?.editor()?.unmarkText();owner?.synchronize();owner?.log("unmarkText",origin:"NSTextInputClient");owner?.render()}
 func selectedRange()->NSRange{owner?.editor()?.selectedRange() ?? NSRange(location:NSNotFound,length:0)}
 func markedRange()->NSRange{owner?.editor()?.markedRange() ?? NSRange(location:NSNotFound,length:0)}
 func hasMarkedText()->Bool{owner?.editor()?.hasMarkedText() ?? false}
 func validAttributesForMarkedText()->[NSAttributedString.Key]{owner?.editor()?.validAttributesForMarkedText() ?? []}
 func attributedSubstring(forProposedRange range:NSRange,actualRange:NSRangePointer?)->NSAttributedString?{owner?.editor()?.attributedSubstring(forProposedRange:range,actualRange:actualRange)}
 func characterIndex(for point:NSPoint)->Int{guard let o=owner,let e=o.editor(),let w=window else{return 0};let win=w.convertPoint(fromScreen:point);let local=convert(win,from:nil);let ep=e.convert(local,from:o.canvas);return e.characterIndexForInsertion(at:ep)}
 func firstRect(forCharacterRange range:NSRange,actualRange:NSRangePointer?)->NSRect{
  guard let o=owner,let e=o.editor(),let w=window else{return .zero}
  var source=e.firstRect(forCharacterRange:range,actualRange:actualRange)
  if let sw=e.window {source=sw.convertFromScreen(source);source=o.canvas.convert(source,from:nil)}
  let local=convert(source,to:nil);return w.convertToScreen(local)
 }
 override func doCommand(by selector:Selector){
  let name=NSStringFromSelector(selector)
  if ["insertTab:","insertTabIgnoringFieldEditor:"].contains(name){owner?.cycleFocus(backward:false,origin:"NSTextInputClient-command");return}
  if ["insertBacktab:","insertBacktabIgnoringFieldEditor:"].contains(name){owner?.cycleFocus(backward:true,origin:"NSTextInputClient-command");return}
  owner?.editor()?.doCommand(by:selector);owner?.synchronize();owner?.log("doCommand",origin:"NSTextInputClient",extra:["selector":name]);owner?.render()
 }
}
final class AppDelegate:NSObject,NSApplicationDelegate,NSWindowDelegate,NSTextFieldDelegate,NSTextViewDelegate{
 var window:NSWindow!;var sourceWindow:NSWindow!;let canvas=Canvas(frame:NSRect(x:0,y:0,width:900,height:500));var proxy:ProxyView!
 let video=AVSampleBufferDisplayLayer();let field=NSTextField(frame:NSRect(x:24,y:108,width:840,height:38));let checkbox=NSButton(checkboxWithTitle:"真实 NSButton 选择：NATIVE-CHECK-3P8R",target:nil,action:nil)
 let button=NSButton(title:"真实按钮：计数 +1",target:nil,action:nil);let scroll=NSScrollView(frame:NSRect(x:24,y:235,width:840,height:210));let textView=NSTextView(frame:NSRect(x:0,y:0,width:820,height:1000))
 var counter=0;var countLabel:NSTextField!;var eventLog:[[String:Any]]=[];var timer:Timer?;var pollTimer:Timer?;var pool:CVPixelBufferPool?;var format:CMVideoFormatDescription?;var lastFrame:CVPixelBuffer?;var recorder:Recorder?;var recordingURL:URL?;var submitted=0;var rendered=0;var frameErrors:[String]=[];var renderTimes:[Double]=[];var lastCommand="";var finishing=false;var mouseAnchor=0;var lastFocus="field";var scale:CGFloat=2;var lastBitmap:NSBitmapImageRep?;var lastCacheSize="";var sourceEverOrderedFront=false;var sourceExposureTest=false;var lastNativeBitmap:NSBitmapImageRep?;var proxyCaretRect:NSRect?;var proxyCaretDrawn=false;var proxyFocusOutlineDrawn=false;var nativeFocusAccepted=false;var localEventMonitor:Any?
 func label(_ s:String,_ rect:NSRect,_ size:CGFloat=18)->NSTextField{let v=NSTextField(labelWithString:s);v.frame=rect;v.font = .systemFont(ofSize:size);v.textColor = .black;canvas.addSubview(v);return v}
 func applicationDidFinishLaunching(_ n:Notification){
  NSApp.setActivationPolicy(.regular)
  let menu=NSMenu();let item=NSMenuItem();menu.addItem(item);let appMenu=NSMenu();appMenu.addItem(withTitle:"退出 Native Demo",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q");item.submenu=appMenu
  let editItem=NSMenuItem(title:"编辑",action:nil,keyEquivalent:"");let editMenu=NSMenu(title:"编辑");editMenu.autoenablesItems=true
  let undoItem=editMenu.addItem(withTitle:"撤销",action:#selector(ProxyView.undo(_:)),keyEquivalent:"z");undoItem.target=nil
  let redoItem=editMenu.addItem(withTitle:"重做",action:#selector(ProxyView.redo(_:)),keyEquivalent:"z");redoItem.keyEquivalentModifierMask=[.command,.shift];redoItem.target=nil
  editMenu.addItem(.separator())
  for (title,action,key) in [("剪切","cut:","x"),("复制","copy:","c"),("粘贴","paste:","v"),("全选","selectAll:","a")] {
   let entry=editMenu.addItem(withTitle:title,action:Selector(action),keyEquivalent:key);entry.target=nil
  }
  editItem.submenu=editMenu;menu.addItem(editItem);NSApp.mainMenu=menu
  localEventMonitor=NSEvent.addLocalMonitorForEvents(matching:[.keyDown,.leftMouseDown,.rightMouseDown,.otherMouseDown,.flagsChanged]){[weak self] event in
   guard let self else{return event}
   var details:[String:Any]=["typeRaw":event.type.rawValue,"windowID":event.windowNumber,"flagsRaw":event.modifierFlags.rawValue,"eventTimestamp":event.timestamp,"appActive":NSApp.isActive,"appHidden":NSApp.isHidden,"visibleWindowVisible":self.window?.isVisible ?? false,"visibleWindowMiniaturized":self.window?.isMiniaturized ?? false,"visibleWindowKey":self.window?.isKeyWindow ?? false,"visibleFirstResponder":self.window?.firstResponder.map{String(describing:type(of:$0))} ?? "none"]
   if event.type == .keyDown || event.type == .flagsChanged{details["keyCode"]=event.keyCode}
   if event.type == .keyDown{details["isRepeat"]=event.isARepeat}
   if [.leftMouseDown,.rightMouseDown,.otherMouseDown].contains(event.type){details["clickCount"]=event.clickCount;details["locationInWindow"]=[event.locationInWindow.x,event.locationInWindow.y]}
   if let cg=event.cgEvent{details["eventSourcePID"]=cg.getIntegerValueField(.eventSourceUnixProcessID)}
   self.log("local-NSEvent",origin:"app-local-monitor",extra:details)
   return event
  }
  _=label("原生控件离屏验证 · EXAM-SECRET-7K9Q",NSRect(x:24,y:20,width:850,height:35),25)
  _=label("真实可编辑 NSTextField · NATIVE-EDIT-6T2W",NSRect(x:24,y:72,width:850,height:28),20)
  field.font = .systemFont(ofSize:22);field.stringValue="NATIVE-INPUT-START-5B7K";field.isEditable=true;field.isSelectable=true;field.isBezeled=true;field.drawsBackground=true;field.delegate=self;canvas.addSubview(field)
  checkbox.frame=NSRect(x:24,y:165,width:530,height:32);checkbox.target=self;checkbox.action=#selector(toggle);canvas.addSubview(checkbox)
  button.frame=NSRect(x:560,y:160,width:230,height:40);button.target=self;button.action=#selector(increment);canvas.addSubview(button)
  countLabel=label("点击计数：0",NSRect(x:24,y:202,width:840,height:27),17)
  scroll.hasVerticalScroller=true;scroll.borderType = .bezelBorder;scroll.autohidesScrollers=false;textView.isEditable=true;textView.isSelectable=true;textView.font = .systemFont(ofSize:19);textView.textColor = .black;textView.backgroundColor = .white;textView.isRichText=false;textView.string=(0..<35).map{"原生滚动内容 ROW-\(String(format:"%02d",$0)) SCROLL-SECRET-9J4V"}.joined(separator:"\n");textView.delegate=self;scroll.documentView=textView;canvas.addSubview(scroll)
  _=label("输入、选区与焦点需独立验证；系统候选窗不自动受视频保护",NSRect(x:24,y:460,width:850,height:26),16)
  window=NSWindow(contentRect:NSRect(x:0,y:0,width:900,height:590),styleMask:[.titled,.closable,.miniaturizable],backing:.buffered,defer:false);window.title="NativeControlDemo — \(mode)";window.delegate=self;window.isReleasedWhenClosed=false;window.sharingType = .readOnly
  let root=NSView(frame:NSRect(x:0,y:0,width:900,height:590));root.wantsLayer=true;root.layer?.backgroundColor=NSColor(calibratedRed:0.08,green:0.2,blue:0.35,alpha:1).cgColor;window.contentView=root
  let title=NSTextField(labelWithString:"PUBLIC-CONTROL-4M2P  原生控件验证  \(mode)");title.frame=NSRect(x:20,y:550,width:870,height:25);title.textColor = .white;title.font = .boldSystemFont(ofSize:18);root.addSubview(title)
  let record=NSButton(title:"开始自身录制",target:self,action:#selector(startRecording));record.frame=NSRect(x:20,y:510,width:170,height:30);root.addSubview(record)
  let note=NSTextField(labelWithString:"题目/输入区为真实 AppKit 控件的绘制结果");note.frame=NSRect(x:210,y:515,width:660,height:23);note.textColor = .white;root.addSubview(note)
  if mode=="direct" {canvas.frame.origin = .zero;root.addSubview(canvas)} else {
   sourceWindow=NSWindow(contentRect:NSRect(x:-10000,y:-10000,width:900,height:500),styleMask:.borderless,backing:.buffered,defer:false);sourceWindow.isReleasedWhenClosed=false;sourceWindow.sharingType = .readOnly;sourceWindow.contentView=canvas
   proxy=ProxyView(frame:NSRect(x:0,y:0,width:900,height:500));proxy.owner=self;proxy.wantsLayer=true;proxy.layer?.backgroundColor=NSColor.black.cgColor;root.addSubview(proxy)
   video.frame=proxy.bounds;video.videoGravity = .resize;video.preventsCapture=["raster-protected","mixed"].contains(mode);proxy.layer?.addSublayer(video)
   if mode=="mixed" {let leak=NSTextField(labelWithString:"NATIVE-LEAK-8R3T 普通覆盖控件");leak.frame=NSRect(x:350,y:55,width:480,height:30);leak.drawsBackground=true;leak.backgroundColor = .yellow;leak.textColor = .black;leak.font = .boldSystemFont(ofSize:20);root.addSubview(leak)}
  }
  window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);scale=window.backingScaleFactor
  let w=Int(900*scale),h=Int(500*scale);let attributes:[String:Any]=[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,kCVPixelBufferWidthKey as String:w,kCVPixelBufferHeightKey as String:h,kCVPixelBufferIOSurfacePropertiesKey as String:[:],kCVPixelBufferCGImageCompatibilityKey as String:true,kCVPixelBufferCGBitmapContextCompatibilityKey as String:true]
  CVPixelBufferPoolCreate(kCFAllocatorDefault,[kCVPixelBufferPoolMinimumBufferCountKey as String:4] as CFDictionary,attributes as CFDictionary,&pool)
  canvas.layoutSubtreeIfNeeded();render();focusField(selectAll:false)
  if mode != "direct"{window.makeFirstResponder(proxy)}
  if args.contains("--record"){startRecording()}
  log("ready",origin:"setup")
  timer=Timer.scheduledTimer(withTimeInterval:1/Double(fps),repeats:true){[weak self] _ in self?.render()}
  pollTimer=Timer.scheduledTimer(withTimeInterval:0.15,repeats:true){[weak self] _ in self?.pollCommand()}
  Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.persist()}
  if duration>0{Timer.scheduledTimer(withTimeInterval:duration,repeats:false){[weak self] _ in self?.finish()}}
  if scenario=="native-actions" {
   let steps:[(Double,[String:Any])]=[(2,["action":"setText","text":"NATIVE-PHASE-01-ALPHA"]),(4,["action":"select","location":0,"length":6]),(6,["action":"insert","text":"EDITED"]),(8,["action":"delete"]),(10,["action":"toggle"]),(12,["action":"button"]),(14,["action":"scroll","y":220]),(16,["action":"setMarkedText","text":"中文组合","selectedLocation":4,"selectedLength":0]),(18,["action":"unmarkText"])]
   for (delay,command) in steps {Timer.scheduledTimer(withTimeInterval:delay,repeats:false){[weak self] _ in self?.command(command,origin:"programmatic-scenario")}}
  }
 }
 func editor()->NSTextView?{
  if mode=="direct"{return window?.firstResponder as? NSTextView}
  switch lastFocus{case "textView":return textView;case "field":return field.currentEditor() as? NSTextView;default:return nil}
 }
 func focusedControlName()->String{
  guard mode=="direct",let responder=window?.firstResponder else{return lastFocus}
  if responder===textView{return "textView"};if responder===checkbox{return "checkbox"};if responder===button{return "button"}
  if let e=field.currentEditor(),responder===e{return "field"}
  return lastFocus
 }
 func focusField(selectAll:Bool){
  lastFocus="field";field.selectText(nil)
  if !selectAll,let e=editor(){e.setSelectedRange(NSRange(location:(e.string as NSString).length,length:0))}
  nativeFocusAccepted=field.currentEditor() != nil
  if mode != "direct"{window.makeFirstResponder(proxy)}
 }
 func focusControl(_ target:String,origin:String){
  guard ["field","checkbox","button","textView"].contains(target)else{return}
  synchronize()
  if target=="field"{focusField(selectAll:false)}else{
   lastFocus=target
   let responder:NSResponder = target=="checkbox" ? checkbox:(target=="button" ? button:textView)
   nativeFocusAccepted=(mode=="direct" ? window:sourceWindow)?.makeFirstResponder(responder) ?? false
   if mode != "direct"{window.makeFirstResponder(proxy)}
  }
  log("focus-change",origin:origin,extra:["focus":lastFocus,"nativeFocusAccepted":nativeFocusAccepted]);render()
 }
 func cycleFocus(backward:Bool,origin:String){let order=["field","checkbox","button","textView"];let idx=order.firstIndex(of:lastFocus) ?? 0;focusControl(order[(idx+(backward ? order.count-1:1))%order.count],origin:origin)}
 func activateFocused(origin:String){if lastFocus=="checkbox"{checkbox.performClick(nil)}else if lastFocus=="button"{button.performClick(nil)};log("focus-activate",origin:origin,extra:["focus":lastFocus]);render()}
 func nativeCaretInCanvas()->NSRect?{
  guard let ed=editor(),let sw=ed.window else{return nil}
  let range=ed.selectedRange();guard range.location != NSNotFound,range.length==0 else{return nil}
  var actual=NSRange(location:0,length:0)
  let screen=ed.firstRect(forCharacterRange:NSRange(location:range.location,length:0),actualRange:&actual)
  guard screen.origin.x.isFinite,screen.origin.y.isFinite,screen.width.isFinite,screen.height.isFinite,screen.height>0 else{return nil}
  var local=canvas.convert(sw.convertFromScreen(screen),from:nil);local.size.width=1.25
  let allowed=lastFocus=="field" ? field.frame:scroll.frame
  guard local.intersects(allowed),local.intersects(canvas.bounds)else{return nil}
  local=local.intersection(allowed).intersection(canvas.bounds)
  return local.isEmpty ? nil:local
 }
 func synchronize(){if let e=field.currentEditor() as? NSTextView,field.stringValue != e.string{field.stringValue=e.string}}
 @objc func toggle(){log("checkbox",origin:"NSButton.action");render()}
 @objc func increment(){counter+=1;countLabel.stringValue="点击计数：\(counter)";log("button",origin:"NSButton.action");render()}
 func controlTextDidChange(_ n:Notification){synchronize();log("controlTextDidChange",origin:"AppKit.delegate");render()}
 func textDidChange(_ n:Notification){log("textDidChange",origin:"AppKit.delegate");render()}
 func proxyMouse(_ e:NSEvent,kind:String){
  let p=proxy.convert(e.locationInWindow,from:nil);log("proxy-\(kind)",origin:"NSEvent",extra:["point":[p.x,p.y],"clickCount":e.clickCount])
  if field.frame.contains(p){
   if kind=="mouseDown"{focusControl("field",origin:"NSEvent-mouse")}
   if let ed=editor(){selectAtPoint(p,editor:ed,event:e,kind:kind)}
  }else if kind=="mouseDown"&&checkbox.frame.contains(p){focusControl("checkbox",origin:"NSEvent-mouse");checkbox.performClick(nil)}
  else if kind=="mouseDown"&&button.frame.contains(p){focusControl("button",origin:"NSEvent-mouse");button.performClick(nil)}
  else if scroll.frame.contains(p){if kind=="mouseDown"{focusControl("textView",origin:"NSEvent-mouse")};selectAtPoint(p,editor:textView,event:e,kind:kind)}
  render()
 }
 func selectAtPoint(_ p:NSPoint,editor ed:NSTextView,event e:NSEvent,kind:String){
  let ep=ed.convert(p,from:canvas);let idx=min((ed.string as NSString).length,max(0,ed.characterIndexForInsertion(at:ep)))
  if kind=="mouseDown"{mouseAnchor=idx;ed.setSelectedRange(NSRange(location:idx,length:0));if e.clickCount>=3{ed.selectParagraph(nil);mouseAnchor=ed.selectedRange().location}else if e.clickCount==2{ed.selectWord(nil);mouseAnchor=ed.selectedRange().location}}
  else{ed.setSelectedRange(NSRange(location:min(mouseAnchor,idx),length:abs(idx-mouseAnchor)))}
  log("native-selection",origin:"NSEvent-forwarded",extra:["clickCount":e.clickCount,"selection":rangeJSON(ed.selectedRange())])
 }
 func proxyScroll(_ e:NSEvent){let old=scroll.contentView.bounds.origin;let maxY=max(0,textView.bounds.height-scroll.contentView.bounds.height);let y=min(maxY,max(0,old.y-e.scrollingDeltaY));scroll.contentView.scroll(to:NSPoint(x:0,y:y));scroll.reflectScrolledClipView(scroll.contentView);log("scrollWheel",origin:"NSEvent",extra:["deltaY":e.scrollingDeltaY]);render()}
 func render(){
  guard !finishing,let pool else{return};let start=CACurrentMediaTime();synchronize();canvas.layoutSubtreeIfNeeded()
  guard let rep=canvas.bitmapImageRepForCachingDisplay(in:canvas.bounds) else{frameErrors.append("no bitmap rep");return};canvas.cacheDisplay(in:canvas.bounds,to:rep);lastNativeBitmap=rep;lastBitmap=rep;lastCacheSize="\(rep.pixelsWide)x\(rep.pixelsHigh)"
  guard let image=rep.cgImage else{frameErrors.append("no bitmap cgImage");return}
  var p:CVPixelBuffer?;guard CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault,pool,&p)==kCVReturnSuccess,let buffer=p else{frameErrors.append("pixel buffer failed");return}
  CVPixelBufferLockBaseAddress(buffer,[])
  let w=CVPixelBufferGetWidth(buffer),h=CVPixelBufferGetHeight(buffer)
  if let cg=CGContext(data:CVPixelBufferGetBaseAddress(buffer),width:w,height:h,bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(buffer),space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGBitmapInfo.byteOrder32Little.rawValue|CGImageAlphaInfo.premultipliedFirst.rawValue){
   cg.setFillColor(NSColor.white.cgColor);cg.fill(CGRect(x:0,y:0,width:w,height:h));cg.draw(image,in:CGRect(x:0,y:0,width:w,height:h))
   proxyCaretRect=nil;proxyCaretDrawn=false;proxyFocusOutlineDrawn=false
   if mode != "direct",window.isKeyWindow {
    if ["checkbox","button"].contains(lastFocus){
     let r=(lastFocus=="checkbox" ? checkbox.frame:button.frame).insetBy(dx:-2,dy:-2)
     cg.setStrokeColor(NSColor.systemBlue.cgColor);cg.setLineWidth(1.5*scale)
     cg.stroke(CGRect(x:r.minX*scale,y:(500-r.maxY)*scale,width:r.width*scale,height:r.height*scale));proxyFocusOutlineDrawn=true
    }
    if !args.contains("--no-proxy-caret"),let r=nativeCaretInCanvas(){
     proxyCaretRect=r
     if Int(start*2)%2==0 {cg.setFillColor(NSColor.black.cgColor);cg.fill(CGRect(x:r.minX*scale,y:(500-r.maxY)*scale,width:max(1,r.width*scale),height:r.height*scale));proxyCaretDrawn=true}
    }
   }
   if let renderedImage=cg.makeImage(){lastBitmap=NSBitmapImageRep(cgImage:renderedImage)}
  }
  else{frameErrors.append("context failed")}
  CVPixelBufferUnlockBaseAddress(buffer,[]);lastFrame=buffer;rendered+=1
  if rendered==1{saveFrame("source-reference.png")}
  if mode != "direct" {
   if format==nil{CMVideoFormatDescriptionCreateForImageBuffer(allocator:kCFAllocatorDefault,imageBuffer:buffer,formatDescriptionOut:&format)}
   if let format{var timing=CMSampleTimingInfo(duration:.invalid,presentationTimeStamp:CMTime(seconds:start,preferredTimescale:60000),decodeTimeStamp:.invalid);var sample:CMSampleBuffer?;CMSampleBufferCreateReadyWithImageBuffer(allocator:kCFAllocatorDefault,imageBuffer:buffer,formatDescription:format,sampleTiming:&timing,sampleBufferOut:&sample);if let sample{if #available(macOS 14.0,*){if video.sampleBufferRenderer.isReadyForMoreMediaData{video.sampleBufferRenderer.enqueue(sample);submitted+=1}}else{if video.isReadyForMoreMediaData{video.enqueue(sample);submitted+=1}}}}
  }
  recorder?.append(buffer,start);renderTimes.append((CACurrentMediaTime()-start)*1000)
 }
 func saveFrame(_ filename:String){guard let rep=lastBitmap,let data=rep.representation(using:.png,properties:[:])else{return};try? data.write(to:output.appendingPathComponent(filename),options:.atomic)}
 @objc func startRecording(){guard recorder==nil,let p=lastFrame else{return};let u=output.appendingPathComponent("self-recording-\(UUID().uuidString.prefix(8)).mp4");do{recorder=try Recorder(u,CVPixelBufferGetWidth(p),CVPixelBufferGetHeight(p));recordingURL=u;log("record-start",origin:"action")}catch{saveJSON(["error":error.localizedDescription],"recording-error.json")}}
 func stats()->[String:Any]{let ed=editor();var d:[String:Any]=["mode":mode,"pid":ProcessInfo.processInfo.processIdentifier,"windowID":window?.windowNumber ?? -1,"sourceWindowID":sourceWindow?.windowNumber ?? -1,"sourceWindowVisible":sourceWindow?.isVisible ?? false,"sourceWindowEverOrderedFront":sourceEverOrderedFront,"sourceExposureTest":sourceExposureTest,"windowVisible":window?.isVisible ?? false,"windowFrameAppKit":NSStringFromRect(window?.frame ?? .zero),"sourceWindowFrame":NSStringFromRect(sourceWindow?.frame ?? .zero),"canvasSize":[900,500],"pixelWidth":Int(900*scale),"pixelHeight":Int(500*scale),"backingScale":scale,"bitmapCacheSize":lastCacheSize,"preventsCapture":video.preventsCapture,"sharingType":window?.sharingType.rawValue ?? -1,"sourceSharingType":sourceWindow?.sharingType.rawValue ?? -1,"currentText":field.stringValue,"editorText":ed?.string ?? "","selectionRange":rangeJSON(ed?.selectedRange() ?? NSRange(location:NSNotFound,length:0)),"markedRange":rangeJSON(ed?.markedRange() ?? NSRange(location:NSNotFound,length:0)),"hasMarkedText":ed?.hasMarkedText() ?? false,"sourceFirstResponder":sourceWindow?.firstResponder.map{String(describing:type(of:$0))} ?? "none","visibleFirstResponder":window?.firstResponder.map{String(describing:type(of:$0))} ?? "none","fieldEditorAttached":field.currentEditor() != nil,"focus":focusedControlName(),"checkbox":checkbox.state.rawValue,"buttonCount":counter,"scrollY":scroll.contentView.bounds.origin.y,"renderedFrames":rendered,"submittedFrames":submitted,"frameErrors":frameErrors,"targetFPS":fps,"recordingPath":recordingURL?.path ?? "","timestamp":ISO8601DateFormatter().string(from:Date()),"eventCount":eventLog.count,"nativeClasses":["field":String(describing:type(of:field)),"checkbox":String(describing:type(of:checkbox)),"scroll":String(describing:type(of:scroll)),"textView":String(describing:type(of:textView))],"humanPhysicalDisplayVerified":false,"IMEPhysicalTestVerified":false,"nativeFocusAccepted":nativeFocusAccepted,"proxyCaretImplementation":"optional proxy overlay from native NSTextView.firstRect; not native insertion-point painting","proxyCaretEnabled":mode != "direct" && !args.contains("--no-proxy-caret"),"proxyCaretDrawn":proxyCaretDrawn,"proxyCaretRectCanvas":proxyCaretRect.map{NSStringFromRect($0)} ?? "unavailable","proxyFocusOutlineDrawn":proxyFocusOutlineDrawn,"proxyFocusIndicatorImplementation":"proxy outline for checkbox/button keyboard focus","implementationVersion":"native-controls-v0.3","appActive":NSApp.isActive,"appHidden":NSApp.isHidden,"windowMiniaturized":window?.isMiniaturized ?? false,"windowKey":window?.isKeyWindow ?? false]
  if let screen=window?.screen{d["screenFrame"]=NSStringFromRect(screen.frame)}
  if let w=window {
   let anchor:NSView = mode == "direct" ? canvas:proxy
   let mainMaxY=NSScreen.screens.first?.frame.maxY ?? 0
   let rects:[String:NSRect]=["field":field.frame,"checkbox":checkbox.frame,"button":button.frame,"scroll":scroll.frame]
   d["controlGeometry"]=rects.mapValues { rect -> [String:Any] in
    let point=NSPoint(x:rect.midX,y:rect.midY)
    let screenPoint=w.convertPoint(toScreen:anchor.convert(point,to:nil))
    return ["canvasRect":NSStringFromRect(rect),"canvasCenter":[point.x,point.y],"quartzGlobalCenter":[screenPoint.x,mainMaxY-screenPoint.y]]
   }
  }
  if #available(macOS 14.4,*){d["isReadyForDisplay"]=mode=="direct" ? rendered>2:video.isReadyForDisplay}
  if #available(macOS 14.0,*){d["rendererStatus"]=video.sampleBufferRenderer.status.rawValue;d["rendererError"]=video.sampleBufferRenderer.error?.localizedDescription ?? ""}
  if !renderTimes.isEmpty{let s=renderTimes.sorted();d["renderMeanMS"]=s.reduce(0,+)/Double(s.count);d["renderP95MS"]=s[min(s.count-1,Int(Double(s.count)*0.95))]}
  if let r=recorder{d["writerStatus"]=r.writer.status.rawValue;d["writerError"]=r.writer.error?.localizedDescription ?? "";d["recordedFrames"]=r.accepted;d["recordingDroppedFrames"]=r.dropped}
  return d
 }
 func persist(){saveJSON(stats(),"demo-state.json")}
 func log(_ name:String,origin:String,extra:[String:Any]=[:]){var d:[String:Any]=["event":name,"origin":origin,"hostTimeSeconds":CACurrentMediaTime(),"text":field.stringValue,"selection":rangeJSON(editor()?.selectedRange() ?? NSRange(location:NSNotFound,length:0)),"checkbox":checkbox.state.rawValue,"buttonCount":counter,"scrollY":scroll.contentView.bounds.origin.y];d.merge(extra){_,n in n};eventLog.append(d);saveJSON(["events":eventLog],"events.json")}
 func command(_ cmd:[String:Any],origin:String){let action=cmd["action"] as? String ?? "";log("before-\(action)",origin:origin,extra:["command":cmd]);switch action{
  case "focus":focusControl(cmd["control"] as? String ?? "field",origin:origin)
  case "focusNext":cycleFocus(backward:false,origin:origin)
  case "focusPrevious":cycleFocus(backward:true,origin:origin)
  case "activateFocused":activateFocused(origin:origin)
  case "setText":focusField(selectAll:true);editor()?.insertText(cmd["text"] as? String ?? "",replacementRange:NSRange(location:NSNotFound,length:0))
  case "select":focusField(selectAll:false);let len=(editor()?.string as NSString?)?.length ?? 0;let loc=max(0,min(len,cmd["location"] as? Int ?? 0));editor()?.setSelectedRange(NSRange(location:loc,length:max(0,min(len-loc,cmd["length"] as? Int ?? 0))))
  case "insert":if editor()==nil{focusField(selectAll:false)};editor()?.insertText(cmd["text"] as? String ?? "",replacementRange:NSRange(location:NSNotFound,length:0))
  case "delete":editor()?.deleteBackward(nil)
  case "toggle":checkbox.performClick(nil)
  case "button":button.performClick(nil)
  case "scroll":let y=max(0,min(textView.bounds.height-scroll.contentView.bounds.height,cmd["y"] as? Double ?? 0));scroll.contentView.scroll(to:NSPoint(x:0,y:y));scroll.reflectScrolledClipView(scroll.contentView)
  case "setMarkedText":if editor()==nil{focusField(selectAll:false)};let text=cmd["text"] as? String ?? "";editor()?.setMarkedText(text,selectedRange:NSRange(location:cmd["selectedLocation"] as? Int ?? (text as NSString).length,length:cmd["selectedLength"] as? Int ?? 0),replacementRange:NSRange(location:NSNotFound,length:0))
  case "unmarkText":editor()?.unmarkText()
  case "saveFrame","captureSource":render();saveFrame((cmd["filename"] as? String ?? "command-source.png").replacingOccurrences(of:"/",with:"_"))
  case "showSource":if let sw=sourceWindow{sourceExposureTest=true;sourceEverOrderedFront=true;sw.setFrameOrigin(NSPoint(x:100,y:100));sw.orderFront(nil)}
  case "hideSource":sourceWindow?.orderOut(nil)
  case "saveNativeFrame":if let rep=lastNativeBitmap,let data=rep.representation(using:.png,properties:[:]){try? data.write(to:output.appendingPathComponent((cmd["filename"] as? String ?? "native-only.png").replacingOccurrences(of:"/",with:"_")),options:.atomic)}
  case "minimize":window.miniaturize(nil)
  case "restore":window.deminiaturize(nil);window.makeKeyAndOrderFront(nil)
  case "hide":window.orderOut(nil)
  case "show":window.makeKeyAndOrderFront(nil)
  case "finish":finish();return
  default:break
  };synchronize();render();log("after-\(action)",origin:origin);persist()
 }
 func pollCommand(){let u=output.appendingPathComponent("control-command.json");guard let data=try? Data(contentsOf:u),let cmd=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],let id=cmd["id"] as? String,id != lastCommand else{return};lastCommand=id;command(cmd,origin:"file-command-programmatic");saveJSON(["id":id,"action":cmd["action"] ?? "","state":stats()],"control-ack.json")}
 func finish(){guard !finishing else{return};render();saveFrame("final-source.png");finishing=true;timer?.invalidate();pollTimer?.invalidate();log("finish",origin:"lifecycle");if let r=recorder{r.finish{self.persist();NSApp.terminate(nil)}}else{persist();NSApp.terminate(nil)}}
 func logWindowLifecycle(_ name:String,_ notification:Notification){
  guard let changed=notification.object as? NSWindow else{return}
  log(name,origin:"NSWindowDelegate",extra:["changedWindowID":changed.windowNumber,"isVisible":changed.isVisible,"isMiniaturized":changed.isMiniaturized,"isKeyWindow":changed.isKeyWindow,"appActive":NSApp.isActive,"appHidden":NSApp.isHidden]);persist()
 }
 func windowDidMiniaturize(_ notification:Notification){logWindowLifecycle("window-did-miniaturize",notification)}
 func windowDidDeminiaturize(_ notification:Notification){logWindowLifecycle("window-did-deminiaturize",notification)}
 func windowDidBecomeKey(_ notification:Notification){logWindowLifecycle("window-did-become-key",notification)}
 func windowDidResignKey(_ notification:Notification){logWindowLifecycle("window-did-resign-key",notification)}
 func applicationDidHide(_ notification:Notification){log("application-did-hide",origin:"NSApplicationDelegate",extra:["appHidden":NSApp.isHidden]);persist()}
 func applicationDidUnhide(_ notification:Notification){log("application-did-unhide",origin:"NSApplicationDelegate",extra:["appHidden":NSApp.isHidden]);persist()}
 func applicationDidBecomeActive(_ notification:Notification){log("application-did-become-active",origin:"NSApplicationDelegate");persist()}
 func applicationDidResignActive(_ notification:Notification){log("application-did-resign-active",origin:"NSApplicationDelegate");persist()}
 func windowShouldClose(_ sender:NSWindow)->Bool{finish();return false}
 func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply{if !finishing{finish();return .terminateCancel};return .terminateNow}
}
let app=NSApplication.shared
let delegate=AppDelegate()
app.delegate=delegate
app.run()
