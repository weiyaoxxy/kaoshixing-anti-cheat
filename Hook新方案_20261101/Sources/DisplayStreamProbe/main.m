#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreVideo/CoreVideo.h>
#import <IOSurface/IOSurface.h>
#import <ImageIO/ImageIO.h>
#import <dlfcn.h>
#import <unistd.h>

// Historical public symbols remain exported on this test OS. The current SDK
// marks their public declarations unavailable. These aliases preserve ordinary
// Mach-O symbol binding, including the experimental dyld interposition route.
extern CGDisplayStreamRef ProbeCreate(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,CGDisplayStreamFrameAvailableHandler) __asm("_CGDisplayStreamCreate");
extern CGDisplayStreamRef ProbeCreateQueue(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,dispatch_queue_t,CGDisplayStreamFrameAvailableHandler) __asm("_CGDisplayStreamCreateWithDispatchQueue");
extern CGError ProbeStart(CGDisplayStreamRef) __asm("_CGDisplayStreamStart");
extern CGError ProbeStop(CGDisplayStreamRef) __asm("_CGDisplayStreamStop");
extern CFRunLoopSourceRef ProbeRunLoopSource(CGDisplayStreamRef) __asm("_CGDisplayStreamGetRunLoopSource");

static NSString *Stamp(void) { return [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]]; }
static NSString *StatusName(int status) {
    switch (status) { case 0:return @"complete"; case 1:return @"idle"; case 2:return @"blank"; case 3:return @"stopped"; default:return @"unknown"; }
}
static NSDictionary *RectDict(CGRect r) { return @{@"x":@(r.origin.x),@"y":@(r.origin.y),@"width":@(r.size.width),@"height":@(r.size.height)}; }
static NSString *DynamicKey(const char *symbol) {
    CFStringRef *p = (CFStringRef *)dlsym(RTLD_DEFAULT, symbol);
    return p && *p ? (__bridge NSString *)*p : nil;
}
static void Pump(double seconds) {
    double end = NSProcessInfo.processInfo.systemUptime + seconds;
    while (NSProcessInfo.processInfo.systemUptime < end) {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, MIN(.03,end-NSProcessInfo.processInfo.systemUptime), true);
        usleep(3000);
    }
}
static BOOL SavePNG(CGImageRef image, NSString *path) {
    CGImageDestinationRef dest = CGImageDestinationCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:path],CFSTR("public.png"),1,NULL);
    if (!dest) return NO;
    CGImageDestinationAddImage(dest,image,NULL);
    BOOL ok = CGImageDestinationFinalize(dest); CFRelease(dest); return ok;
}
static NSDictionary *PixelStats(NSData *data,size_t width,size_t height,size_t bpr) {
    const uint8_t *bytes=data.bytes; unsigned lo[4]={255,255,255,255},hi[4]={0,0,0,0};
    for(size_t y=0;y<height;y++) for(size_t x=0;x<width;x++) for(size_t c=0;c<4;c++) {
        unsigned v=bytes[y*bpr+x*4+c]; lo[c]=MIN(lo[c],v);hi[c]=MAX(hi[c],v);
    }
    return @{@"minimumBGRA":@[@(lo[0]),@(lo[1]),@(lo[2]),@(lo[3])],@"maximumBGRA":@[@(hi[0]),@(hi[1]),@(hi[2]),@(hi[3])],
             @"allTransparent":@(hi[3]==0),@"allRGBZero":@(hi[0]==0&&hi[1]==0&&hi[2]==0),@"allOpaqueBlack":@(hi[0]==0&&hi[1]==0&&hi[2]==0&&lo[3]==255)};
}

@interface ProbeState : NSObject
@property(nonatomic) NSMutableArray<NSMutableDictionary *> *frames;
@property(nonatomic) NSMutableArray<NSString *> *errors;
@property(nonatomic) NSString *output;
@property(nonatomic) NSUInteger completeCount;
@property(nonatomic) NSUInteger savedCount;
@property(nonatomic) BOOL stopped;
@property(nonatomic) CGImageRef lastImage;
@property(nonatomic) NSData *lastData;
@property(nonatomic) NSMutableDictionary *lastRow;
@end
@implementation ProbeState
- (instancetype)init { if((self=[super init])) { _frames=[NSMutableArray array];_errors=[NSMutableArray array]; } return self; }
- (void)dealloc { if(_lastImage) CGImageRelease(_lastImage); }
- (void)save:(CGImageRef)image data:(NSData *)data row:(NSMutableDictionary *)row reason:(NSString *)reason {
    if([row[@"saved"] boolValue] || self.savedCount>=10) return;
    NSString *name=[NSString stringWithFormat:@"frame-%04lu.png",(unsigned long)[row[@"completeIndex"] unsignedIntegerValue]];
    BOOL ok=SavePNG(image,[self.output stringByAppendingPathComponent:name]);
    row[@"saved"]=@(ok); row[@"saveReason"]=reason;
    if(ok) { row[@"file"]=name; row[@"pixelStats"]=PixelStats(data,CGImageGetWidth(image),CGImageGetHeight(image),CGImageGetBytesPerRow(image));self.savedCount++; }
    else [self.errors addObject:[@"PNG write failed: " stringByAppendingString:name]];
}
- (void)frame:(CGDisplayStreamFrameStatus)status displayTime:(uint64_t)displayTime surface:(IOSurfaceRef)surface {
    @synchronized(self) {
        NSMutableDictionary *row=[@{@"callbackIndex":@(self.frames.count+1),@"status":@((int)status),@"statusName":StatusName(status),@"displayTimeMachTicks":@(displayTime),@"callbackUptimeSeconds":@(NSProcessInfo.processInfo.systemUptime),@"surfacePresent":@(surface!=NULL),@"saved":@NO} mutableCopy];
        [self.frames addObject:row];
        if(status==3)self.stopped=YES;
        if(!surface)return;
        size_t w=IOSurfaceGetWidth(surface),h=IOSurfaceGetHeight(surface),bpr=IOSurfaceGetBytesPerRow(surface),planes=IOSurfaceGetPlaneCount(surface);
        OSType fmt=IOSurfaceGetPixelFormat(surface);
        row[@"width"]=@(w);row[@"height"]=@(h);row[@"bytesPerRow"]=@(bpr);row[@"planeCount"]=@(planes);row[@"pixelFormat"]=@(fmt);
        if(status!=0)return;
        self.completeCount++;row[@"completeIndex"]=@(self.completeCount);
        if(fmt!=kCVPixelFormatType_32BGRA||planes!=0||w==0||h==0||bpr<w*4||bpr>512*1024*1024/h) {
            row[@"decodeError"]=@"unsupported surface format or dimensions";[self.errors addObject:row[@"decodeError"]];return;
        }
        kern_return_t lock=IOSurfaceLock(surface,kIOSurfaceLockReadOnly,NULL);row[@"surfaceLockReturnCode"]=@(lock);
        if(lock!=KERN_SUCCESS) { row[@"decodeError"]=@"IOSurfaceLock failed";[self.errors addObject:row[@"decodeError"]];return; }
        const void *base=IOSurfaceGetBaseAddress(surface);
        // Copy before leaving the callback. The original IOSurface is reusable.
        NSData *data=base?[NSData dataWithBytes:base length:bpr*h]:nil;
        IOSurfaceUnlock(surface,kIOSurfaceLockReadOnly,NULL);
        if(!data) { row[@"decodeError"]=@"missing IOSurface base address";[self.errors addObject:row[@"decodeError"]];return; }
        CGDataProviderRef provider=CGDataProviderCreateWithCFData((__bridge CFDataRef)data);
        CGColorSpaceRef color=CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CGImageRef image=CGImageCreate(w,h,8,32,bpr,color,kCGBitmapByteOrder32Little|kCGImageAlphaPremultipliedFirst,provider,NULL,false,kCGRenderingIntentDefault);
        CGColorSpaceRelease(color);CGDataProviderRelease(provider);
        if(!image) { row[@"decodeError"]=@"CGImageCreate failed";[self.errors addObject:row[@"decodeError"]];return; }
        if(self.lastImage)CGImageRelease(self.lastImage);
        self.lastImage=image;self.lastData=data;self.lastRow=row;
        if(self.completeCount==1 || self.completeCount%5==0) [self save:image data:data row:row reason:self.completeCount==1?@"first-complete":@"every-fifth-complete"];
    }
}
@end

int main(int argc,const char *argv[]) { @autoreleasepool {
    NSString *api=@"queue",*output=nil;double duration=2;
    for(int i=1;i<argc;i++) {
        NSString *a=@(argv[i]);
        if([a isEqual:@"--help"]) { puts("DisplayStreamProbe --api queue|runloop --output NEW_DIRECTORY [--duration 2]\nHistorical CGDisplayStream symbols; full main display; 10fps BGRA. Saves <=10 sampled PNG frames. Does not request TCC permission.");return 0; }
        if(i+1>=argc) { fprintf(stderr,"missing option value\n");return 64; }
        NSString *v=@(argv[++i]);
        if([a isEqual:@"--api"])api=v; else if([a isEqual:@"--output"])output=v; else if([a isEqual:@"--duration"]) { char *end=NULL;duration=strtod(v.UTF8String,&end);if(!end||*end)duration=NAN; } else { fprintf(stderr,"unknown option\n");return 64; }
    }
    if(!output || ![@[@"queue",@"runloop"] containsObject:api]||!isfinite(duration)||duration<.5||duration>30) { fprintf(stderr,"invalid arguments; use --help\n");return 64; }
    output=[output stringByStandardizingPath];NSFileManager *fm=NSFileManager.defaultManager;BOOL dir=NO;
    if([fm fileExistsAtPath:output isDirectory:&dir] && (!dir||[[fm contentsOfDirectoryAtPath:output error:nil] count]>0)) { fprintf(stderr,"refusing nonempty output directory\n");return 73; }
    NSError *err=nil;if(![fm createDirectoryAtPath:output withIntermediateDirectories:YES attributes:nil error:&err]) { fprintf(stderr,"cannot create output: %s\n",err.localizedDescription.UTF8String);return 73; }
    ProbeState *state=[ProbeState new];state.output=output;
    CGDirectDisplayID display=CGMainDisplayID();CGRect bounds=CGDisplayBounds(display);
    CGDisplayModeRef mode=CGDisplayCopyDisplayMode(display);
    size_t width=mode?CGDisplayModeGetPixelWidth(mode):CGDisplayPixelsWide(display),height=mode?CGDisplayModeGetPixelHeight(mode):CGDisplayPixelsHigh(display);if(mode)CGDisplayModeRelease(mode);
    BOOL permission=CGPreflightScreenCaptureAccess();
    NSString *createSymbol=[api isEqual:@"queue"]?@"CGDisplayStreamCreateWithDispatchQueue":@"CGDisplayStreamCreate";
    NSMutableDictionary *symbols=[NSMutableDictionary dictionary];
    for(NSString *symbol in @[createSymbol,@"CGDisplayStreamStart",@"CGDisplayStreamStop",@"CGDisplayStreamGetRunLoopSource"])symbols[symbol]=@(dlsym(RTLD_DEFAULT,symbol.UTF8String)!=NULL);
    NSMutableDictionary *report=[@{@"schemaVersion":@1,@"probe":@"DisplayStreamProbe",@"api":api,@"createSymbol":createSymbol,@"symbolBinding":@"ordinary linked historical public symbol via __asm alias; dlsym used only for availability and property keys",@"pid":@(getpid()),@"startedAtUTC":Stamp(),@"os":NSProcessInfo.processInfo.operatingSystemVersionString,@"screenCapturePermissionPreflight":@(permission),@"displayID":@(display),@"displayBoundsPoints":RectDict(bounds),@"outputWidth":@(width),@"outputHeight":@(height),@"requestedPixelFormat":@(kCVPixelFormatType_32BGRA),@"requestedFPS":@10,@"requestedDurationSeconds":@(duration),@"showsCursor":@NO,@"sourceRectSpecified":@NO,@"destinationRectSpecified":@NO,@"symbolsAvailable":symbols,@"createCalled":@NO,@"createReturnedNull":@YES,@"startCalled":@NO,@"stopCalled":@NO,@"samplePolicy":@"first complete, every fifth complete, last complete; at most 10 PNGs",@"outcome":@"inconclusive"} mutableCopy];
    NSString *minKey=DynamicKey("kCGDisplayStreamMinimumFrameTime"),*cursorKey=DynamicKey("kCGDisplayStreamShowCursor"),*depthKey=DynamicKey("kCGDisplayStreamQueueDepth");
    BOOL symbolsOK=YES;for(NSNumber *value in symbols.allValues)if(!value.boolValue)symbolsOK=NO;
    CGDisplayStreamRef stream=NULL;CFRunLoopSourceRef source=NULL;
    dispatch_queue_t queue=dispatch_queue_create("local.examcapture.displaystream.probe",DISPATCH_QUEUE_SERIAL);
    double startedUptime=NSProcessInfo.processInfo.systemUptime;
    if(!permission)[state.errors addObject:@"screen capture permission preflight false; capture not attempted"];
    else if(!symbolsOK||!minKey||!cursorKey||!depthKey)[state.errors addObject:@"required historical symbol unavailable"];
    else {
        NSDictionary *props=@{minKey:@.1,cursorKey:@NO,depthKey:@3};
        CGDisplayStreamFrameAvailableHandler handler=^(CGDisplayStreamFrameStatus status,uint64_t timestamp,IOSurfaceRef surface,CGDisplayStreamUpdateRef update){ @autoreleasepool { [state frame:status displayTime:timestamp surface:surface]; } };
        report[@"createCalled"]=@YES;
        stream=[api isEqual:@"queue"]?ProbeCreateQueue(display,width,height,kCVPixelFormatType_32BGRA,(__bridge CFDictionaryRef)props,queue,handler):ProbeCreate(display,width,height,kCVPixelFormatType_32BGRA,(__bridge CFDictionaryRef)props,handler);
        report[@"createReturnedNull"]=@(stream==NULL);
        if(!stream)[state.errors addObject:@"CGDisplayStream create returned NULL; no protection conclusion"];
        else {
            if([api isEqual:@"runloop"]) { source=ProbeRunLoopSource(stream);report[@"runLoopSourcePresent"]=@(source!=NULL);if(source)CFRunLoopAddSource(CFRunLoopGetMain(),source,kCFRunLoopCommonModes);else [state.errors addObject:@"missing runloop source"]; }
            report[@"startCalled"]=@YES;CGError start=ProbeStart(stream);report[@"startReturnCode"]=@(start);
            if(start==kCGErrorSuccess) { report[@"captureStartedUptimeSeconds"]=@(NSProcessInfo.processInfo.systemUptime);Pump(duration); }
            else [state.errors addObject:[NSString stringWithFormat:@"CGDisplayStreamStart returned %d",start]];
            report[@"stopCalled"]=@YES;CGError stop=ProbeStop(stream);report[@"stopReturnCode"]=@(stop);
            if(stop!=kCGErrorSuccess)[state.errors addObject:[NSString stringWithFormat:@"CGDisplayStreamStop returned %d",stop]];
            double stopDeadline=NSProcessInfo.processInfo.systemUptime+1;
            while(NSProcessInfo.processInfo.systemUptime<stopDeadline) { BOOL stopped;@synchronized(state){ stopped=state.stopped; }if(stopped)break;Pump(.02); }
            if([api isEqual:@"queue"])dispatch_sync(queue,^{});
        }
    }
    @synchronized(state) {
        if(state.lastImage)[state save:state.lastImage data:state.lastData row:state.lastRow reason:@"last-complete"];
        if(stream&&!state.stopped)[state.errors addObject:@"stopped callback not observed; stream intentionally left for process teardown"];
        if(state.savedCount==0)[state.errors addObject:@"no decoded PNG frames; cannot judge capture protection"];
        NSMutableDictionary *counts=[NSMutableDictionary dictionary];for(NSDictionary *row in state.frames){ NSString *key=row[@"statusName"];counts[key]=@([counts[key] integerValue]+1); }
        report[@"finishedAtUTC"]=Stamp();report[@"elapsedSeconds"]=@(NSProcessInfo.processInfo.systemUptime-startedUptime);report[@"frameStatusCounts"]=counts;report[@"callbackCount"]=@(state.frames.count);report[@"completeFrameCount"]=@(state.completeCount);report[@"savedPNGCount"]=@(state.savedCount);report[@"stopCallbackObserved"]=@(state.stopped);report[@"frames"]=state.frames;report[@"errors"]=state.errors;
        if(state.errors.count==0 && state.completeCount>0)report[@"outcome"]=@"capture-completed; image analysis required";
        if(source)CFRunLoopRemoveSource(CFRunLoopGetMain(),source,kCFRunLoopCommonModes);
        if(stream&&state.stopped)CFRelease(stream);
        NSData *json=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted|NSJSONWritingSortedKeys error:&err];
        if(!json||![json writeToFile:[output stringByAppendingPathComponent:@"report.json"] options:NSDataWritingAtomic error:&err]) { fprintf(stderr,"report write failed: %s\n",err.localizedDescription.UTF8String);return 74; }
        printf("api=%s pid=%d callbacks=%lu complete=%lu saved=%lu errors=%lu\n",api.UTF8String,getpid(),(unsigned long)state.frames.count,(unsigned long)state.completeCount,(unsigned long)state.savedCount,(unsigned long)state.errors.count);
        return state.errors.count?2:0;
    }
} }
