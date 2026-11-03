#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#import <QuartzCore/QuartzCore.h>
#import <libproc.h>
#import <sys/stat.h>
#import <unistd.h>

// Own-window-only integration host. It never requests TCC, saves image bytes,
// reads another window's title, or interacts with any remote-control application.
static NSDictionary *Identity(void) {
    struct proc_bsdinfo info = {0};
    char path[PROC_PIDPATHINFO_MAXSIZE] = {0};
    if (proc_pidinfo(getpid(), PROC_PIDTBSDINFO, 0, &info, sizeof(info)) != sizeof(info) ||
        proc_pidpath(getpid(), path, sizeof(path)) <= 0) return nil;
    return @{@"pid": @(getpid()), @"uid": @(getuid()), @"executable": @(path),
             @"processStartSeconds": @(info.pbi_start_tvsec),
             @"processStartMicroseconds": @(info.pbi_start_tvusec),
             @"identitySource": @"hostProcPidInfoAndProcPidPath"};
}

static BOOL WriteJSON(NSDictionary *value, NSString *path) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
    BOOL ok = data && [data writeToFile:path options:NSDataWritingAtomic error:nil];
    if (ok) chmod(path.fileSystemRepresentation, 0600);
    return ok;
}

@interface InvocationProbe : NSObject <SCStreamOutput, SCStreamDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) NSTextField *label;
@property(nonatomic, strong) NSTimer *ticker;
@property(nonatomic, strong) SCStream *stream;
@property(nonatomic, strong) NSMutableDictionary *report;
@property(nonatomic, copy) NSString *reportPath;
@property(nonatomic) BOOL finishing;
@property(nonatomic) BOOL screenshotFinished;
@property(nonatomic) BOOL streamStarted;
@property(nonatomic) NSUInteger frameCount;
@property(nonatomic) NSUInteger completeFrames;
@property(nonatomic) NSUInteger tick;
@property(nonatomic) BOOL exerciseAudioRemoval;
@end

@implementation InvocationProbe
- (void)writeAndExit {
    self.report[@"finishedHostTime"] = @(CACurrentMediaTime());
    self.report[@"streamCallbackCount"] = @(self.frameCount);
    self.report[@"completeScreenFrames"] = @(self.completeFrames);
    [self.ticker invalidate];
    [self.window orderOut:nil];
    BOOL ok = WriteJSON(self.report, self.reportPath);
    // This executable owns only its synthetic window and stream. Exiting also
    // bounds shutdown if ScreenCaptureKit fails to return its stop completion.
    exit(ok ? 0 : 3);
}
- (void)finish:(NSString *)reason {
    if (self.finishing) return;
    self.finishing = YES;
    self.report[@"finishReason"] = reason;
    if (!self.streamStarted) { [self writeAndExit]; return; }
    [self.stream stopCaptureWithCompletionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            self.report[@"streamStopSucceeded"] = @((BOOL)!error);
            if (error) self.report[@"streamStopError"] = @{@"domain": error.domain, @"code": @(error.code)};
            NSError *removeError = nil;
            BOOL removed = [self.stream removeStreamOutput:self type:SCStreamOutputTypeScreen error:&removeError];
            self.report[@"screenOutputRemoved"] = @(removed);
            if (removeError) self.report[@"screenOutputRemovalError"] = @{@"domain": removeError.domain, @"code": @(removeError.code)};
            [self writeAndExit];
        });
    }];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        self.report[@"streamStopTimedOut"] = @YES;
        [self writeAndExit];
    });
}
- (void)maybeFinish {
    if (self.screenshotFinished && self.streamStarted && self.completeFrames >= 2) [self finish:@"callbacksObserved"];
}
- (void)startWithWindow:(SCWindow *)target {
    SCContentFilter *filter = [[SCContentFilter alloc] initWithDesktopIndependentWindow:target];
    SCStreamConfiguration *config = [SCStreamConfiguration new];
    config.width = 480; config.height = 240;
    config.pixelFormat = kCVPixelFormatType_32BGRA;
    config.minimumFrameInterval = CMTimeMake(1, 10);
    config.queueDepth = 3;
    config.showsCursor = NO;
    config.capturesAudio = NO;
    if (@available(macOS 14.2, *)) config.includeChildWindows = NO;
    self.report[@"captureScope"] = @"selfOwnedSyntheticWindowOnly";
    self.report[@"screenshotRequested"] = @YES;
    [SCScreenshotManager captureImageWithFilter:filter configuration:config completionHandler:^(CGImageRef image, NSError *error) {
        BOOL valid = !error && image && CGImageGetWidth(image) > 0 && CGImageGetHeight(image) > 0;
        size_t width = image ? CGImageGetWidth(image) : 0, height = image ? CGImageGetHeight(image) : 0;
        dispatch_async(dispatch_get_main_queue(), ^{
            self.screenshotFinished = YES;
            self.report[@"screenshotCallbackDelivered"] = @YES;
            self.report[@"screenshotSucceeded"] = @(valid);
            self.report[@"screenshotDimensions"] = @[@(width), @(height)];
            if (error) self.report[@"screenshotError"] = @{@"domain": error.domain, @"code": @(error.code)};
            [self maybeFinish];
        });
    }];
    self.stream = [[SCStream alloc] initWithFilter:filter configuration:config delegate:self];
    NSError *outputError = nil;
    BOOL attached = [self.stream addStreamOutput:self type:SCStreamOutputTypeScreen
                            sampleHandlerQueue:dispatch_queue_create("local.examcapture.invocation-probe.frames", DISPATCH_QUEUE_SERIAL)
                                         error:&outputError];
    self.report[@"streamOutputAttached"] = @(attached);
    if (!attached) {
        if (outputError) self.report[@"streamOutputError"] = @{@"domain": outputError.domain, @"code": @(outputError.code)};
        return; // Bounded overall timer still allows the screenshot callback to finish.
    }
    if (self.exerciseAudioRemoval) {
        // Register/remove an audio output without ever enabling audio capture.
        // The same object stays registered as the screen output throughout.
        NSError *audioError = nil;
        BOOL audioAttached = [self.stream addStreamOutput:self type:SCStreamOutputTypeAudio
            sampleHandlerQueue:dispatch_queue_create("local.examcapture.invocation-probe.unused-audio", DISPATCH_QUEUE_SERIAL)
            error:&audioError];
        self.report[@"audioOutputAttached"] = @(audioAttached);
        if (audioError) self.report[@"audioOutputError"] = @{@"domain": audioError.domain, @"code": @(audioError.code)};
        if (audioAttached) {
            audioError = nil;
            BOOL removed = [self.stream removeStreamOutput:self type:SCStreamOutputTypeAudio error:&audioError];
            self.report[@"audioOutputRemovedBeforeStart"] = @(removed);
            if (audioError) self.report[@"audioOutputRemovalError"] = @{@"domain": audioError.domain, @"code": @(audioError.code)};
        }
    }
    self.report[@"streamStartRequested"] = @YES;
    [self.stream startCaptureWithCompletionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            self.streamStarted = !error;
            self.report[@"streamStartSucceeded"] = @((BOOL)!error);
            if (error) self.report[@"streamStartError"] = @{@"domain": error.domain, @"code": @(error.code)};
            [self maybeFinish];
        });
    }];
}
- (void)begin {
    // Preflight is a query only. No CGRequestScreenCaptureAccess call exists.
    BOOL permission = CGPreflightScreenCaptureAccess();
    self.report[@"screenCapturePreflightGranted"] = @(permission);
    if (!permission) {
        self.report[@"captureSkipped"] = @YES;
        [self finish:@"screenCapturePermissionNotPreauthorized"];
        return;
    }
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(80, 80, 480, 240)
        styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"CaptureHook invocation test — synthetic window";
    self.window.releasedWhenClosed = NO;
    self.window.backgroundColor = NSColor.whiteColor;
    self.label = [NSTextField labelWithString:@"SYNTHETIC TEST ONLY\nOriginal callback probe: 0"];
    self.label.frame = NSMakeRect(20, 70, 440, 100);
    self.label.font = [NSFont monospacedSystemFontOfSize:23 weight:NSFontWeightRegular];
    self.label.textColor = NSColor.blackColor;
    [self.window.contentView addSubview:self.label];
    [self.window orderFrontRegardless];
    self.report[@"ownWindowID"] = @(self.window.windowNumber);
    self.ticker = [NSTimer scheduledTimerWithTimeInterval:0.1 repeats:YES block:^(NSTimer *timer) {
        self.tick++;
        self.label.stringValue = [NSString stringWithFormat:@"SYNTHETIC TEST ONLY\nOriginal callback probe: %lu", (unsigned long)self.tick];
    }];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 350 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        [SCShareableContent getShareableContentExcludingDesktopWindows:YES onScreenWindowsOnly:YES
            completionHandler:^(SCShareableContent *content, NSError *error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (self.finishing) return;
                SCWindow *own = nil;
                // Inspect only numeric identities; never access any window title.
                for (SCWindow *candidate in content.windows) {
                    if (candidate.windowID == self.window.windowNumber && candidate.owningApplication.processID == getpid()) { own = candidate; break; }
                }
                if (!own) {
                    self.report[@"shareableOwnWindowFound"] = @NO;
                    if (error) self.report[@"shareableContentError"] = @{@"domain": error.domain, @"code": @(error.code)};
                    [self finish:@"ownWindowUnavailable"];
                    return;
                }
                self.report[@"shareableOwnWindowFound"] = @YES;
                [self startWithWindow:own];
            });
        }];
    });
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self finish:@"captureDeadlineReached"]; });
}
- (void)stream:(SCStream *)stream didOutputSampleBuffer:(CMSampleBufferRef)sample ofType:(SCStreamOutputType)type {
    if (type != SCStreamOutputTypeScreen) return;
    NSArray *attachments = (__bridge NSArray *)CMSampleBufferGetSampleAttachmentsArray(sample, false);
    NSNumber *status = attachments.count ? attachments.firstObject[SCStreamFrameInfoStatus] : nil;
    CVPixelBufferRef image = CMSampleBufferGetImageBuffer(sample);
    size_t width = image ? CVPixelBufferGetWidth(image) : 0, height = image ? CVPixelBufferGetHeight(image) : 0;
    BOOL valid = status && status.integerValue == SCFrameStatusComplete && CMSampleBufferIsValid(sample) &&
        CMSampleBufferDataIsReady(sample) && image && width > 0 && height > 0;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.finishing) return;
        self.frameCount++;
        if (valid) {
            self.completeFrames++;
            self.report[@"lastCompleteFrameDimensions"] = @[@(width), @(height)];
            self.report[@"completeFrameStatus"] = @(SCFrameStatusComplete);
        }
        [self maybeFinish];
    });
}
- (void)stream:(SCStream *)stream didStopWithError:(NSError *)error {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.report[@"streamDelegateError"] = @{@"domain": error.domain, @"code": @(error.code)};
        [self finish:@"streamStoppedWithError"];
    });
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 4 || (strcmp(argv[1], "load-only") && strcmp(argv[1], "capture") && strcmp(argv[1], "capture-remove-audio"))) return 2;
        NSDictionary *identity = Identity();
        if (!identity) return 3;
        NSMutableDictionary *ready = [identity mutableCopy];
        ready[@"readyHostTime"] = @(CACurrentMediaTime());
        if (!WriteJSON(ready, @(argv[2]))) return 3;
        InvocationProbe *probe = [InvocationProbe new];
        probe.reportPath = @(argv[3]);
        probe.exerciseAudioRemoval = !strcmp(argv[1], "capture-remove-audio");
        probe.report = [identity mutableCopy];
        [probe.report addEntriesFromDictionary:@{@"mode": @(argv[1]), @"imagesSaved": @NO,
            @"permissionRequestAttempted": @NO, @"captureSkipped": @NO,
            @"screenshotRequested": @NO, @"screenshotSucceeded": @NO,
            @"screenshotCallbackDelivered": @NO, @"streamStartRequested": @NO,
            @"streamStartSucceeded": @NO, @"audioCaptureEnabled": @NO,
            @"audioRemovalRegression": @(probe.exerciseAudioRemoval), @"scope": @"ownSyntheticWindowOnly"}];
        if (!strcmp(argv[1], "load-only")) {
            probe.report[@"captureSkipped"] = @YES;
            [probe finish:@"loadOnlyNoCaptureAPICalls"];
            return 0;
        }
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        dispatch_async(dispatch_get_main_queue(), ^{ [probe begin]; });
        [NSApp run];
    }
    return 0;
}
