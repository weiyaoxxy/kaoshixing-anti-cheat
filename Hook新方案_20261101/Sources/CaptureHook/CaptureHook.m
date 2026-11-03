#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#import <IOSurface/IOSurface.h>
#import <objc/runtime.h>
#import <mach-o/dyld.h>
#import <dlfcn.h>
#import <pthread.h>
#import <fcntl.h>
#import <unistd.h>
#import <libproc.h>
#import <stdatomic.h>
#import <errno.h>
#import <sys/file.h>
#import <sys/stat.h>

// A voluntary, per-process laboratory interposer. No target binary is patched.
static int logFD = -1;
static BOOL blocking = NO;
static NSString *configPath;
static pthread_mutex_t logMutex = PTHREAD_MUTEX_INITIALIZER;
static char filterKey, streamFilterKey, streamConfigKey, proxyKey, streamIDKey, streamCreationKey;
static NSString *sessionID, *hookInstanceID, *processExecutable;
static uint64_t processStartSeconds, processStartMicroseconds, logSequence, logWriteFailures;
static pid_t initializedPID;
static NSString *const HookVersion = @"1.4";
static _Atomic(uint64_t) identifierCounter = 0;
static NSNumber *BoolValue(BOOL value) { return value?@YES:@NO; }
static NSString *NextID(NSString *kind) {
    return [NSString stringWithFormat:@"%@-%llu",kind,(unsigned long long)(atomic_fetch_add(&identifierCounter,1)+1)];
}
static id Sanitize(id value, NSMutableArray *paths, NSString *path) {
    if (!value || value==NSNull.null) return NSNull.null;
    if ([value isKindOfClass:NSString.class]) return value;
    if ([value isKindOfClass:NSNumber.class]) {
        double n=[value doubleValue];
        if(isfinite(n))return value;
        [paths addObject:path]; return isnan(n)?@"NaN":(n<0?@"-Infinity":@"Infinity");
    }
    if ([value isKindOfClass:NSArray.class]) {
        NSMutableArray *out=[NSMutableArray array];NSUInteger i=0;
        for(id item in value){[out addObject:Sanitize(item,paths,[path stringByAppendingFormat:@"[%lu]",(unsigned long)i++])];}
        return out;
    }
    if ([value isKindOfClass:NSDictionary.class]) {
        NSMutableDictionary *out=[NSMutableDictionary dictionary];
        for(id key in value){NSString *safeKey=[key isKindOfClass:NSString.class]?key:@"<non-string-key>";out[safeKey]=Sanitize(value[key],paths,[path stringByAppendingFormat:@".%@",safeKey]);}
        return out;
    }
    [paths addObject:path]; return [@"unsupported-type:" stringByAppendingString:NSStringFromClass([value class])];
}
// Caller owns logMutex: sequence, monotonic timestamp and bytes share one order.
static void WriteLogBytes(const void *bytes,size_t count) {
    // Legacy launchers may share a path across processes. Prefer %p, but never
    // interleave JSON and newlines if they do share. Don't stall the host on a
    // contended lock: missing evidence is reported by the sequence/failure count.
    int lockResult;do{lockResult=flock(logFD,LOCK_EX|LOCK_NB);}while(lockResult<0&&errno==EINTR);
    if(lockResult<0){logWriteFailures++;return;}
    uint8_t *record=malloc(count+1);
    if(!record){logWriteFailures++;flock(logFD,LOCK_UN);return;}
    memcpy(record,bytes,count);record[count]='\n';
    const uint8_t *p=record;size_t left=count+1;
    while(left){ssize_t n=write(logFD,p,left);if(n<0&&errno==EINTR)continue;if(n<=0){logWriteFailures++;break;}p+=n;left-=n;}
    free(record);flock(logFD,LOCK_UN);
}
static void Log(NSString *event, NSDictionary *fields) {
    // A fork without exec has no fresh identity or safe inherited mutex state.
    // Such children are unsupported; never emit the parent's birth identity.
    if (logFD < 0 || getpid()!=initializedPID) return;
    pthread_mutex_lock(&logMutex);
    @autoreleasepool { @try {
        NSMutableDictionary *d = [NSMutableDictionary dictionary];
        if ([fields isKindOfClass:NSDictionary.class]) [d addEntriesFromDictionary:fields];
        [d addEntriesFromDictionary:@{@"schemaVersion":@2,@"hookVersion":HookVersion,@"event":event?:@"unknown",
            @"pid":@(getpid()),@"uid":@(getuid()),@"hostTime":@(CACurrentMediaTime()),@"mode":blocking?@"block":@"audit",
            @"sessionID":sessionID?:@"",@"hookInstanceID":hookInstanceID?:@"",@"sequence":@(++logSequence),
            @"processStartSeconds":@(processStartSeconds),@"processStartMicroseconds":@(processStartMicroseconds),
            @"executable":processExecutable?:@"unknown",@"identityAvailable":BoolValue(processStartSeconds>0&&processExecutable!=nil),
            @"priorLogWriteFailures":@(logWriteFailures)}];
        NSMutableArray *paths=[NSMutableArray array];
        NSMutableDictionary *safe=[Sanitize(d,paths,@"$") mutableCopy];
        if(paths.count)safe[@"sanitizedFields"]=paths;
        NSData *data = [NSJSONSerialization isValidJSONObject:safe]?[NSJSONSerialization dataWithJSONObject:safe options:NSJSONWritingSortedKeys error:nil]:nil;
        if (data) WriteLogBytes(data.bytes,data.length);
        else logWriteFailures++;
    } @catch(NSException *exception) {
        // Diagnostics must never raise a Foundation exception into the host.
        const char msg[]="{\"event\":\"log_serialization_exception\"}";
        WriteLogBytes(msg,sizeof(msg)-1);
    }}
    pthread_mutex_unlock(&logMutex);
}
__attribute__((visibility("default"))) void CaptureHookLogSelfTest(void) {
    Log(@"log_self_test",@{@"positive":@(INFINITY),@"negative":@(-INFINITY),@"nested":@[@{@"nan":@(NAN)}],@"finite":@1.25,@"boolean":@YES});
}
static NSDictionary *RectDict(CGRect r) { return @{@"x":@(r.origin.x),@"y":@(r.origin.y),@"width":@(r.size.width),@"height":@(r.size.height)}; }
static void ImageResult(NSString *api,NSString *callID,CGImageRef image,NSError *error) {
    size_t w=image?CGImageGetWidth(image):0,h=image?CGImageGetHeight(image):0;
    BOOL valid=image&&w>0&&h>0;
    Log(@"capture_result",@{@"api":api,@"callID":callID,@"hasImage":BoolValue(image!=NULL),@"hasSample":@NO,
        @"width":@(w),@"height":@(h),@"validImageOrSample":BoolValue(valid),@"success":BoolValue(valid&&!error),
        @"errorDomain":error.domain?:@"",@"errorCode":@(error.code)});
}
static void SampleResult(NSString *api,NSString *callID,CMSampleBufferRef sample,NSError *error) {
    CVPixelBufferRef image=sample?CMSampleBufferGetImageBuffer(sample):NULL;
    size_t w=image?CVPixelBufferGetWidth(image):0,h=image?CVPixelBufferGetHeight(image):0;
    BOOL valid=sample&&CMSampleBufferIsValid(sample)&&CMSampleBufferDataIsReady(sample)&&image&&w>0&&h>0;
    Log(@"capture_result",@{@"api":api,@"callID":callID,@"hasImage":BoolValue(image!=NULL),@"hasSample":BoolValue(sample!=NULL),
        @"width":@(w),@"height":@(h),@"validImageOrSample":BoolValue(valid),@"success":BoolValue(valid&&!error),
        @"errorDomain":error.domain?:@"",@"errorCode":@(error.code)});
}
static CGRect DictRect(NSDictionary *d) { return CGRectMake([d[@"x"] doubleValue],[d[@"y"] doubleValue],[d[@"width"] doubleValue],[d[@"height"] doubleValue]); }
static NSDictionary *Target(void) {
    if (!blocking || !configPath) return nil;
    NSData *data=[NSData dataWithContentsOfFile:configPath];
    NSDictionary *d=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
    if (![d isKindOfClass:NSDictionary.class] || (d[@"enabled"] && ![d[@"enabled"] boolValue]) || ![d[@"bounds"] isKindOfClass:NSDictionary.class]) return nil;
    CGRect r=DictRect(d[@"bounds"]);
    if (!isfinite(r.origin.x)||!isfinite(r.origin.y)||!isfinite(r.size.width)||!isfinite(r.size.height)||r.size.width<=0||r.size.height<=0) return nil;
    return d;
}
static NSDictionary *WindowScope(CGWindowID wid, CGRect rect) { return @{@"kind":@"window",@"windowID":@(wid),@"bounds":RectDict(rect)}; }
static NSDictionary *DisplayScope(CGDirectDisplayID did) { return @{@"kind":@"display",@"displayID":@(did),@"bounds":RectDict(CGDisplayBounds(did))}; }
static CGRect DesktopBounds(void) {
    CGDirectDisplayID ids[32]; uint32_t count=0; CGRect rect=CGRectNull;
    if(CGGetActiveDisplayList(32,ids,&count)!=kCGErrorSuccess)return CGRectNull;
    for(uint32_t i=0;i<count;i++)rect=CGRectUnion(rect,CGDisplayBounds(ids[i]));
    return rect;
}
// Return a top-left-origin pixel rectangle. Only unambiguous 1:1-aspect mappings
// are supported. Unsupported/cropped mappings PASS THROUGH and are reported.
static CGRect MaskRect(NSDictionary *scope, size_t w, size_t h, NSString **reason) {
    NSDictionary *target=Target();
    if(!target){*reason=@"no_enabled_valid_target";return CGRectNull;}
    if(!scope){*reason=@"unknown_capture_scope";return CGRectNull;}
    if([scope[@"cropped"] boolValue]){*reason=@"source_crop_not_supported";return CGRectNull;}
    if([scope[@"kind"] isEqual:@"window"]){
        if([scope[@"windowID"] unsignedIntValue]==[target[@"windowID"] unsignedIntValue]){*reason=@"target_window_full_frame";return CGRectMake(0,0,w,h);}
        *reason=@"different_window";return CGRectNull;
    }
    CGRect bounds=DictRect(scope[@"bounds"]), secret=DictRect(target[@"bounds"]);
    if(CGRectIsEmpty(bounds)){*reason=@"invalid_capture_bounds";return CGRectNull;}
    double sx=w/bounds.size.width,sy=h/bounds.size.height;
    if(fabs(sx-sy)>MAX(sx,sy)*.015){*reason=@"aspect_mapping_not_supported";return CGRectNull;}
    CGRect intersect=CGRectIntersection(bounds,secret);
    if(CGRectIsEmpty(intersect)||CGRectIsNull(intersect)){*reason=@"target_outside_capture";return CGRectNull;}
    *reason=@"target_rectangle";
    // Expand by two output pixels to cover rounding at the target window edge.
    CGRect r=CGRectMake(floor((intersect.origin.x-bounds.origin.x)*sx)-2,floor((intersect.origin.y-bounds.origin.y)*sy)-2,ceil(intersect.size.width*sx)+4,ceil(intersect.size.height*sy)+4);
    return CGRectIntersection(r,CGRectMake(0,0,w,h));
}
static CGImageRef RedactImage(CGImageRef image,NSDictionary *scope,NSString *api) CF_RETURNS_RETAINED {
    if(!image)return NULL;
    size_t w=CGImageGetWidth(image),h=CGImageGetHeight(image);NSString *reason;
    CGRect mask=MaskRect(scope,w,h,&reason);
    if(CGRectIsNull(mask)||CGRectIsEmpty(mask)){Log(@"redaction_passthrough",@{@"api":api,@"reason":reason?:@"unknown",@"width":@(w),@"height":@(h)});return CGImageRetain(image);}
    CGColorSpaceRef cs=CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx=CGBitmapContextCreate(NULL,w,h,8,w*4,cs,kCGImageAlphaPremultipliedLast|kCGBitmapByteOrder32Big);CGColorSpaceRelease(cs);
    if(!ctx){Log(@"redaction_failed",@{@"api":api,@"reason":@"bitmap_allocation"});return CGImageRetain(image);}
    CGContextDrawImage(ctx,CGRectMake(0,0,w,h),image);
    CGContextSetRGBFillColor(ctx,0,0,0,1);CGContextFillRect(ctx,CGRectMake(mask.origin.x,h-CGRectGetMaxY(mask),mask.size.width,mask.size.height));
    CGImageRef result=CGBitmapContextCreateImage(ctx);CGContextRelease(ctx);
    Log(@"image_redacted",@{@"api":api,@"width":@(w),@"height":@(h),@"maskPixels":RectDict(mask)});
    return result?:CGImageRetain(image);
}
static void BlackPixels(uint8_t *base,size_t bpr,CGRect rect) {
    size_t x0=(size_t)rect.origin.x,y0=(size_t)rect.origin.y,x1=(size_t)CGRectGetMaxX(rect),y1=(size_t)CGRectGetMaxY(rect);
    for(size_t y=y0;y<y1;y++)for(size_t x=x0;x<x1;x++){uint8_t *p=base+y*bpr+x*4;p[0]=p[1]=p[2]=0;p[3]=255;}
}

// Historical C symbols use aliases to avoid unavailable SDK declarations.
// Calls from this interposing image bind to the original implementation.
// Do NOT resolve through dlsym(RTLD_NEXT): on this runtime it re-applies
// interposition and resolved back to the wrapper in the archived v1.0 failure.
extern CGImageRef HookSymbolWindow(CGRect,uint32_t,uint32_t,uint32_t) __asm("_CGWindowListCreateImage");
extern CGImageRef HookSymbolDisplay(uint32_t) __asm("_CGDisplayCreateImage");
static CGImageRef HookWindow(CGRect rect,uint32_t options,uint32_t wid,uint32_t imageOptions) {
    typedef CGImageRef(*Fn)(CGRect,uint32_t,uint32_t,uint32_t);Fn fn=HookSymbolWindow;
    NSString *callID=NextID(@"call");
    Log(@"capture_call",@{@"api":@"CGWindowListCreateImage",@"operation":@"snapshot_request",@"callID":callID,@"windowID":@(wid),@"options":@(options)});
    if(!fn){Log(@"original_symbol_missing",@{@"api":@"CGWindowListCreateImage"});return NULL;}
    CGImageRef image=fn(rect,options,wid,imageOptions);ImageResult(@"CGWindowListCreateImage",callID,image,nil);if(!blocking||!image)return image;
    NSDictionary *scope=nil;
    if((options&kCGWindowListOptionIncludingWindow)&&wid)scope=WindowScope(wid,CGRectZero);
    else if(wid==0&&(options==0||(options&kCGWindowListOptionOnScreenOnly))){CGRect b=(CGRectIsInfinite(rect)||CGRectIsNull(rect))?DesktopBounds():rect;scope=@{@"kind":@"desktop",@"bounds":RectDict(b)};}
    CGImageRef result=RedactImage(image,scope,@"CGWindowListCreateImage");CGImageRelease(image);return result;
}
static CGImageRef HookDisplay(uint32_t did) {
    typedef CGImageRef(*Fn)(uint32_t);Fn fn=HookSymbolDisplay;
    NSString *callID=NextID(@"call");
    Log(@"capture_call",@{@"api":@"CGDisplayCreateImage",@"operation":@"snapshot_request",@"callID":callID,@"displayID":@(did)});
    if(!fn)return NULL;CGImageRef image=fn(did);ImageResult(@"CGDisplayCreateImage",callID,image,nil);if(!blocking||!image)return image;
    CGImageRef result=RedactImage(image,DisplayScope(did),@"CGDisplayCreateImage");CGImageRelease(image);return result;
}

static CGDisplayStreamFrameAvailableHandler WrapDisplayHandler(CGDirectDisplayID did,int32_t pixelFormat,CFDictionaryRef props,NSString *streamID,CGDisplayStreamFrameAvailableHandler original) {
    if(!original)return nil;
    __block uint64_t frameCount=0,screenFrames=0;
    NSObject *counterLock=[NSObject new];NSString *outputID=NextID(@"output");
    // Crop/destination geometry is not modelled in this prototype. Reject it
    // explicitly, even if a supplied rectangle happens to equal the display.
    BOOL unsupportedProps=props&&(CFDictionaryContainsKey(props,kCGDisplayStreamSourceRect)||CFDictionaryContainsKey(props,kCGDisplayStreamDestinationRect));
    if(unsupportedProps)Log(@"display_stream_geometry",@{@"displayID":@(did),@"redactionSupported":@NO,@"reason":@"source_or_destination_rectangle_property"});
    return ^(CGDisplayStreamFrameStatus status,uint64_t displayTime,IOSurfaceRef surface,CGDisplayStreamUpdateRef update){
        size_t w=surface?IOSurfaceGetWidth(surface):0,h=surface?IOSurfaceGetHeight(surface):0;
        BOOL valid=surface&&status==kCGDisplayStreamFrameStatusFrameComplete&&w>0&&h>0;
        uint64_t callbackCount,validCount;
        @synchronized(counterLock){callbackCount=++frameCount;if(valid)screenFrames++;validCount=screenFrames;}
        BOOL logFrame=callbackCount==1||callbackCount%60==0||(valid&&(validCount==1||validCount%60==0));
        NSString *frameID=[NSString stringWithFormat:@"%@-%llu",outputID,(unsigned long long)callbackCount];
        if(logFrame)Log(@"display_stream_frame",@{@"streamID":streamID,@"outputID":outputID,@"frameID":frameID,@"validScreenFrame":BoolValue(valid),@"screenFrameCount":@(validCount),@"displayID":@(did),@"status":@(status),@"frameCount":@(callbackCount),@"width":@(w),@"height":@(h),@"pixelFormat":@(surface?IOSurfaceGetPixelFormat(surface):pixelFormat)});
        void (^forward)(IOSurfaceRef)=^(IOSurfaceRef out){original(status,displayTime,out,update);if(logFrame)Log(@"frame_forwarded",@{@"streamID":streamID,@"outputID":outputID,@"frameID":frameID,@"validScreenFrame":BoolValue(valid),@"originalCallbackReturned":@YES,@"surfaceReplaced":BoolValue(out!=surface)});};
        if(!blocking||!surface||status!=kCGDisplayStreamFrameStatusFrameComplete){forward(surface);return;}
        if(unsupportedProps){if(logFrame)Log(@"display_stream_passthrough",@{@"streamID":streamID,@"frameID":frameID,@"reason":@"source_or_destination_rectangle_property"});forward(surface);return;}
        OSType fmt=IOSurfaceGetPixelFormat(surface);NSString *reason;CGRect mask=MaskRect(DisplayScope(did),w,h,&reason);
        if(fmt!=kCVPixelFormatType_32BGRA||IOSurfaceGetPlaneCount(surface)>0||CGRectIsNull(mask)||CGRectIsEmpty(mask)){
            if(logFrame)Log(@"display_stream_passthrough",@{@"streamID":streamID,@"frameID":frameID,@"reason":fmt!=kCVPixelFormatType_32BGRA?@"pixel_format_not_BGRA":(reason?:@"unsupported"),@"pixelFormat":@(fmt)});
            forward(surface);return;
        }
        size_t bpr=w*4;
        IOSurfaceRef copy=IOSurfaceCreate((__bridge CFDictionaryRef)@{(__bridge NSString*)kIOSurfaceWidth:@(w),(__bridge NSString*)kIOSurfaceHeight:@(h),(__bridge NSString*)kIOSurfaceBytesPerElement:@4,(__bridge NSString*)kIOSurfaceBytesPerRow:@(bpr),(__bridge NSString*)kIOSurfaceAllocSize:@(bpr*h),(__bridge NSString*)kIOSurfacePixelFormat:@(fmt)});
        if(!copy){Log(@"redaction_failed",@{@"api":@"CGDisplayStream",@"reason":@"surface_allocation"});forward(surface);return;}
        kern_return_t a=IOSurfaceLock(surface,kIOSurfaceLockReadOnly,NULL),b=IOSurfaceLock(copy,0,NULL);
        if(a!=KERN_SUCCESS||b!=KERN_SUCCESS){if(a==KERN_SUCCESS)IOSurfaceUnlock(surface,kIOSurfaceLockReadOnly,NULL);if(b==KERN_SUCCESS)IOSurfaceUnlock(copy,0,NULL);CFRelease(copy);Log(@"redaction_failed",@{@"api":@"CGDisplayStream",@"reason":@"surface_lock"});forward(surface);return;}
        size_t sbpr=IOSurfaceGetBytesPerRow(surface),dbpr=IOSurfaceGetBytesPerRow(copy);uint8_t *src=IOSurfaceGetBaseAddress(surface),*dst=IOSurfaceGetBaseAddress(copy);
        for(size_t y=0;y<h;y++)memcpy(dst+y*dbpr,src+y*sbpr,w*4);
        BlackPixels(dst,dbpr,mask);IOSurfaceUnlock(surface,kIOSurfaceLockReadOnly,NULL);IOSurfaceUnlock(copy,0,NULL);
        if(logFrame)Log(@"display_stream_redacted",@{@"streamID":streamID,@"frameID":frameID,@"frameCount":@(callbackCount),@"maskPixels":RectDict(mask),@"dirtyRegionMetadataUnmodified":@YES});
        forward(copy);CFRelease(copy);
    };
}
extern CGDisplayStreamRef HookSymbolStream(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,CGDisplayStreamFrameAvailableHandler) __asm("_CGDisplayStreamCreate");
extern CGDisplayStreamRef HookSymbolStreamQueue(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,dispatch_queue_t,CGDisplayStreamFrameAvailableHandler) __asm("_CGDisplayStreamCreateWithDispatchQueue");
static CGDisplayStreamRef HookStream(CGDirectDisplayID did,size_t w,size_t h,int32_t fmt,CFDictionaryRef props,CGDisplayStreamFrameAvailableHandler handler){
    typedef CGDisplayStreamRef(*Fn)(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,CGDisplayStreamFrameAvailableHandler);Fn fn=HookSymbolStream;
    NSString *callID=NextID(@"call"),*streamID=NextID(@"stream");
    Log(@"capture_call",@{@"api":@"CGDisplayStreamCreate",@"operation":@"stream_create",@"callID":callID,@"streamID":streamID,@"displayID":@(did),@"width":@(w),@"height":@(h),@"pixelFormat":@(fmt)});
    CGDisplayStreamRef result=fn?fn(did,w,h,fmt,props,WrapDisplayHandler(did,fmt,props,streamID,handler)):NULL;
    Log(@"stream_create_result",@{@"api":@"CGDisplayStreamCreate",@"callID":callID,@"streamID":streamID,@"success":BoolValue(result!=NULL)});return result;
}
static CGDisplayStreamRef HookStreamQueue(CGDirectDisplayID did,size_t w,size_t h,int32_t fmt,CFDictionaryRef props,dispatch_queue_t queue,CGDisplayStreamFrameAvailableHandler handler){
    typedef CGDisplayStreamRef(*Fn)(CGDirectDisplayID,size_t,size_t,int32_t,CFDictionaryRef,dispatch_queue_t,CGDisplayStreamFrameAvailableHandler);Fn fn=HookSymbolStreamQueue;
    NSString *callID=NextID(@"call"),*streamID=NextID(@"stream");
    Log(@"capture_call",@{@"api":@"CGDisplayStreamCreateWithDispatchQueue",@"operation":@"stream_create",@"callID":callID,@"streamID":streamID,@"displayID":@(did),@"width":@(w),@"height":@(h),@"pixelFormat":@(fmt)});
    CGDisplayStreamRef result=fn?fn(did,w,h,fmt,props,queue,WrapDisplayHandler(did,fmt,props,streamID,handler)):NULL;
    Log(@"stream_create_result",@{@"api":@"CGDisplayStreamCreateWithDispatchQueue",@"callID":callID,@"streamID":streamID,@"success":BoolValue(result!=NULL)});return result;
}
// Lifecycle diagnostics only: do not infer a frame, or retain native stream pointers
// in an identity table whose entries could outlive the objects they describe.
extern CGError HookSymbolStreamStart(CGDisplayStreamRef) __asm("_CGDisplayStreamStart");
extern CGError HookSymbolStreamStop(CGDisplayStreamRef) __asm("_CGDisplayStreamStop");
static CGError DisplayControl(CGDisplayStreamRef stream,BOOL start){
    NSString *api=start?@"CGDisplayStreamStart":@"CGDisplayStreamStop",*callID=NextID(@"call");
    NSDictionary *fields=@{@"api":api,@"callID":callID,@"streamProvided":BoolValue(stream!=NULL)};
    Log(@"display_stream_control_call",fields);
    CGError result=start?HookSymbolStreamStart(stream):HookSymbolStreamStop(stream);
    NSMutableDictionary *completed=[fields mutableCopy];
    completed[@"returnCode"]=@(result);completed[@"success"]=BoolValue(result==kCGErrorSuccess);
    Log(@"display_stream_control_result",completed);
    return result;
}
static CGError HookStreamStart(CGDisplayStreamRef stream){return DisplayControl(stream,YES);}
static CGError HookStreamStop(CGDisplayStreamRef stream){return DisplayControl(stream,NO);}
#define INTERPOSE(new,old) __attribute__((used)) static struct { const void *replacement; const void *replacee; } interpose_##new __attribute__((section("__DATA,__interpose"))) = {(const void *)(new),(const void *)(old)};
INTERPOSE(HookWindow,HookSymbolWindow)
INTERPOSE(HookDisplay,HookSymbolDisplay)
INTERPOSE(HookStream,HookSymbolStream)
INTERPOSE(HookStreamQueue,HookSymbolStreamQueue)
INTERPOSE(HookStreamStart,HookSymbolStreamStart)
INTERPOSE(HookStreamStop,HookSymbolStreamStop)

static IMP origShareableContent;
static void ShareableContent(id cls,SEL sel,BOOL excludeDesktop,BOOL onScreenOnly,
                             void(^completion)(SCShareableContent*,NSError*)){
    NSString *api=@"SCShareableContent.getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:";
    NSString *callID=NextID(@"call");
    Log(@"shareable_content_request",@{@"api":api,@"callID":callID});
    if(!completion){((void(*)(id,SEL,BOOL,BOOL,id))origShareableContent)(cls,sel,excludeDesktop,onScreenOnly,nil);return;}
    ((void(*)(id,SEL,BOOL,BOOL,id))origShareableContent)(cls,sel,excludeDesktop,onScreenOnly,^(SCShareableContent *content,NSError *error){
        // Counts only. Never enumerate or serialize window/application objects.
        Log(@"shareable_content_result",@{@"api":api,@"callID":callID,
            @"success":BoolValue(content!=nil&&!error),@"errorDomain":error.domain?:@"",@"errorCode":@(error.code),
            @"displayCount":@(content.displays.count),@"windowCount":@(content.windows.count),
            @"applicationCount":@(content.applications.count)});
        completion(content,error);
    });
}

// Record filter scopes from their public initializers, without private ivars.
static IMP origWindowFilter,origDisplayEx,origDisplayIn,origAppsIn,origAppsEx;
static id WindowFilter(id self,SEL sel,SCWindow *window){id obj=((id(*)(id,SEL,id))origWindowFilter)(self,sel,window);if(obj)objc_setAssociatedObject(obj,&filterKey,WindowScope(window.windowID,window.frame),OBJC_ASSOCIATION_RETAIN_NONATOMIC);return obj;}
static id DisplayEx(id self,SEL sel,SCDisplay *display,id windows){id obj=((id(*)(id,SEL,id,id))origDisplayEx)(self,sel,display,windows);if(obj)objc_setAssociatedObject(obj,&filterKey,DisplayScope(display.displayID),OBJC_ASSOCIATION_RETAIN_NONATOMIC);return obj;}
static id DisplayIn(id self,SEL sel,SCDisplay *display,id windows){id obj=((id(*)(id,SEL,id,id))origDisplayIn)(self,sel,display,windows);if(obj)objc_setAssociatedObject(obj,&filterKey,DisplayScope(display.displayID),OBJC_ASSOCIATION_RETAIN_NONATOMIC);return obj;}
static id AppsIn(id self,SEL sel,SCDisplay *display,id apps,id windows){id obj=((id(*)(id,SEL,id,id,id))origAppsIn)(self,sel,display,apps,windows);if(obj)objc_setAssociatedObject(obj,&filterKey,DisplayScope(display.displayID),OBJC_ASSOCIATION_RETAIN_NONATOMIC);return obj;}
static id AppsEx(id self,SEL sel,SCDisplay *display,id apps,id windows){id obj=((id(*)(id,SEL,id,id,id))origAppsEx)(self,sel,display,apps,windows);if(obj)objc_setAssociatedObject(obj,&filterKey,DisplayScope(display.displayID),OBJC_ASSOCIATION_RETAIN_NONATOMIC);return obj;}
static NSDictionary *Scope(SCContentFilter *filter,SCStreamConfiguration *config){
    NSMutableDictionary *scope=[objc_getAssociatedObject(filter,&filterKey) mutableCopy];
    if(!scope&&[filter respondsToSelector:@selector(includedWindows)]){
        if([filter style]==SCShareableContentStyleWindow){NSArray *wins=[filter includedWindows];if(wins.count==1){SCWindow *w=wins[0];scope=[WindowScope(w.windowID,w.frame) mutableCopy];}}
        else{NSArray *displays=[filter includedDisplays];if(displays.count==1){SCDisplay *d=displays[0];scope=[DisplayScope(d.displayID) mutableCopy];}}
    }
    if(config&&!CGRectIsEmpty(config.sourceRect))scope[@"cropped"]=@YES;
    return scope;
}
static IMP origShot,origRectShot,origSampleShot;
static void Shot(id cls,SEL sel,id filter,SCStreamConfiguration *config,void(^completion)(CGImageRef,NSError*)){
    NSString *callID=NextID(@"call");NSDictionary *scope=Scope(filter,config);Log(@"capture_call",@{@"api":@"SCScreenshotManager.captureImage",@"operation":@"snapshot_request",@"callID":callID,@"scope":scope?:@{}});
    ((void(*)(id,SEL,id,id,id))origShot)(cls,sel,filter,config,^(CGImageRef image,NSError *error){
        ImageResult(@"SCScreenshotManager.captureImage",callID,image,error);
        if(!completion)return;if(!blocking||!image){completion(image,error);return;}
        CGImageRef masked=RedactImage(image,scope,@"SCScreenshotManager.captureImage");completion(masked,error);if(masked)CGImageRelease(masked);
    });
}
static void RectShot(id cls,SEL sel,CGRect rect,void(^completion)(CGImageRef,NSError*)){
    NSString *callID=NextID(@"call");NSDictionary *scope=@{@"kind":@"rectangle",@"bounds":RectDict(rect)};Log(@"capture_call",@{@"api":@"SCScreenshotManager.captureImageInRect",@"operation":@"snapshot_request",@"callID":callID,@"scope":scope});
    ((void(*)(id,SEL,CGRect,id))origRectShot)(cls,sel,rect,^(CGImageRef image,NSError *error){
        ImageResult(@"SCScreenshotManager.captureImageInRect",callID,image,error);
        if(!completion)return;if(!blocking||!image){completion(image,error);return;}
        CGImageRef masked=RedactImage(image,scope,@"SCScreenshotManager.captureImageInRect");completion(masked,error);if(masked)CGImageRelease(masked);
    });
}
// Copy original timing, format and propagated attachments; never mutate shared input.
static CMSampleBufferRef RedactSample(CMSampleBufferRef original,NSDictionary *scope,NSString **reason) CF_RETURNS_RETAINED {
    CVPixelBufferRef input=CMSampleBufferGetImageBuffer(original);if(!input){*reason=@"no_image_buffer";return (CMSampleBufferRef)CFRetain(original);}
    size_t w=CVPixelBufferGetWidth(input),h=CVPixelBufferGetHeight(input);OSType fmt=CVPixelBufferGetPixelFormatType(input);
    if(fmt!=kCVPixelFormatType_32BGRA||CVPixelBufferIsPlanar(input)){*reason=@"pixel_format_not_BGRA";return (CMSampleBufferRef)CFRetain(original);}
    CGRect mask=MaskRect(scope,w,h,reason);if(CGRectIsEmpty(mask)||CGRectIsNull(mask))return (CMSampleBufferRef)CFRetain(original);
    CVPixelBufferRef output=NULL;
    if(CVPixelBufferCreate(kCFAllocatorDefault,w,h,fmt,(__bridge CFDictionaryRef)@{(id)kCVPixelBufferIOSurfacePropertiesKey:@{}},&output)!=kCVReturnSuccess){*reason=@"allocation_failed";return (CMSampleBufferRef)CFRetain(original);}
    CVReturn a=CVPixelBufferLockBaseAddress(input,kCVPixelBufferLock_ReadOnly),b=CVPixelBufferLockBaseAddress(output,0);
    if(a||b){if(!a)CVPixelBufferUnlockBaseAddress(input,kCVPixelBufferLock_ReadOnly);if(!b)CVPixelBufferUnlockBaseAddress(output,0);CFRelease(output);*reason=@"pixel_lock_failed";return (CMSampleBufferRef)CFRetain(original);}
    uint8_t *src=CVPixelBufferGetBaseAddress(input),*dst=CVPixelBufferGetBaseAddress(output);size_t sb=CVPixelBufferGetBytesPerRow(input),db=CVPixelBufferGetBytesPerRow(output);
    for(size_t y=0;y<h;y++)memcpy(dst+y*db,src+y*sb,w*4);BlackPixels(dst,db,mask);
    CVPixelBufferUnlockBaseAddress(input,kCVPixelBufferLock_ReadOnly);CVPixelBufferUnlockBaseAddress(output,0);
    CVBufferPropagateAttachments(input,output);
    CMVideoFormatDescriptionRef format=NULL;CMVideoFormatDescriptionCreateForImageBuffer(kCFAllocatorDefault,output,&format);
    CMSampleTimingInfo timing={CMSampleBufferGetDuration(original),CMSampleBufferGetPresentationTimeStamp(original),CMSampleBufferGetDecodeTimeStamp(original)};CMSampleBufferRef result=NULL;
    if(format)CMSampleBufferCreateReadyWithImageBuffer(kCFAllocatorDefault,output,format,&timing,&result);
    if(format)CFRelease(format);CFRelease(output);
    if(!result){*reason=@"sample_creation_failed";return (CMSampleBufferRef)CFRetain(original);}
    CFDictionaryRef attach=CMCopyDictionaryOfAttachments(kCFAllocatorDefault,original,kCMAttachmentMode_ShouldPropagate);if(attach){CMSetAttachments(result,attach,kCMAttachmentMode_ShouldPropagate);CFRelease(attach);}
    CFArrayRef from=CMSampleBufferGetSampleAttachmentsArray(original,false),to=CMSampleBufferGetSampleAttachmentsArray(result,true);
    if(from&&to&&CFArrayGetCount(from)&&CFArrayGetCount(to)){NSDictionary *d=(__bridge NSDictionary*)CFArrayGetValueAtIndex(from,0);NSMutableDictionary *dest=(__bridge NSMutableDictionary*)CFArrayGetValueAtIndex(to,0);[dest addEntriesFromDictionary:d];}
    *reason=@"redacted";return result;
}
static void SampleShot(id cls,SEL sel,id filter,SCStreamConfiguration *config,void(^completion)(CMSampleBufferRef,NSError*)){
    NSString *callID=NextID(@"call");NSDictionary *scope=Scope(filter,config);Log(@"capture_call",@{@"api":@"SCScreenshotManager.captureSampleBuffer",@"operation":@"snapshot_request",@"callID":callID,@"scope":scope?:@{}});
    ((void(*)(id,SEL,id,id,id))origSampleShot)(cls,sel,filter,config,^(CMSampleBufferRef sample,NSError *error){SampleResult(@"SCScreenshotManager.captureSampleBuffer",callID,sample,error);if(!completion)return;if(!blocking||!sample){completion(sample,error);return;}NSString *reason;CMSampleBufferRef out=RedactSample(sample,scope,&reason);Log(@"sample_result",@{@"api":@"SCScreenshotManager.captureSampleBuffer",@"callID":callID,@"result":reason?:@"unknown"});completion(out,error);CFRelease(out);});
}
@interface HookOutputProxy : NSObject<SCStreamOutput>
@property(nonatomic,strong) id<SCStreamOutput> original;
@property(nonatomic,weak) SCStream *stream;
@property(nonatomic) uint64_t frames;
@property(nonatomic) uint64_t screenFrames;
@property(nonatomic,strong) NSString *outputID;
@end
@implementation HookOutputProxy
- (void)stream:(SCStream*)stream didOutputSampleBuffer:(CMSampleBufferRef)sample ofType:(SCStreamOutputType)type {
    CVPixelBufferRef image=sample?CMSampleBufferGetImageBuffer(sample):NULL;
    NSInteger status=-1;CFArrayRef attachments=sample?CMSampleBufferGetSampleAttachmentsArray(sample,false):NULL;
    if(attachments&&CFArrayGetCount(attachments)>0){
        CFTypeRef first=CFArrayGetValueAtIndex(attachments,0);
        if(first&&CFGetTypeID(first)==CFDictionaryGetTypeID()){
            id value=[(__bridge NSDictionary*)first objectForKey:SCStreamFrameInfoStatus];
            if([value isKindOfClass:NSNumber.class])status=[value integerValue];
        }
    }
    size_t w=image?CVPixelBufferGetWidth(image):0,h=image?CVPixelBufferGetHeight(image):0;
    BOOL valid=type==SCStreamOutputTypeScreen&&sample&&CMSampleBufferIsValid(sample)&&CMSampleBufferDataIsReady(sample)&&image&&w>0&&h>0&&status==SCFrameStatusComplete;
    uint64_t callbackCount,validCount;
    @synchronized(self){callbackCount=++self->_frames;if(valid)self->_screenFrames++;validCount=self->_screenFrames;}
    BOOL logFrame=callbackCount==1||callbackCount%60==0||(valid&&(validCount==1||validCount%60==0));
    NSString *streamID=objc_getAssociatedObject(stream,&streamIDKey)?:@"untracked",*frameID=[NSString stringWithFormat:@"%@-%llu",self.outputID,(unsigned long long)callbackCount];
    if(logFrame)Log(@"sck_stream_frame",@{@"streamID":streamID,@"outputID":self.outputID,@"frameID":frameID,@"validScreenFrame":BoolValue(valid),@"screenFrameCount":@(validCount),@"frameStatus":@(status),@"sampleValid":BoolValue(sample&&CMSampleBufferIsValid(sample)),@"dataReady":BoolValue(sample&&CMSampleBufferDataIsReady(sample)),@"frameCount":@(callbackCount),@"type":@(type),@"width":@(w),@"height":@(h),@"pixelFormat":@(image?CVPixelBufferGetPixelFormatType(image):0)});
    CMSampleBufferRef out=sample;
    if(blocking&&sample&&type==SCStreamOutputTypeScreen){NSString *reason;out=RedactSample(sample,Scope(objc_getAssociatedObject(stream,&streamFilterKey),objc_getAssociatedObject(stream,&streamConfigKey)),&reason);if(logFrame)Log(@"sck_stream_result",@{@"streamID":streamID,@"frameID":frameID,@"frameCount":@(callbackCount),@"result":reason?:@"unknown"});}
    [self.original stream:stream didOutputSampleBuffer:out ofType:type];
    if(logFrame)Log(@"frame_forwarded",@{@"streamID":streamID,@"outputID":self.outputID,@"frameID":frameID,@"validScreenFrame":BoolValue(valid),@"originalCallbackReturned":@YES,@"sampleReplaced":BoolValue(out!=sample)});
    if(out!=sample)CFRelease(out);else if(blocking&&sample&&type==SCStreamOutputTypeScreen)CFRelease(out);
}
@end
static IMP origStreamInit,origStreamAdd,origStreamRemove,origStreamStart,origStreamStop,origStreamFilterUpdate,origStreamConfigUpdate;
static NSMutableDictionary *StreamFields(id stream,NSString *api,NSString *operation,NSString *callID){
    return [@{@"api":api,@"operation":operation,@"callID":callID,@"streamID":objc_getAssociatedObject(stream,&streamIDKey)?:@"untracked",@"creationCallID":objc_getAssociatedObject(stream,&streamCreationKey)?:@"untracked"} mutableCopy];
}
static id StreamInit(id self,SEL sel,id filter,id config,id delegate){
    NSString *callID=NextID(@"call"),*streamID=NextID(@"stream");
    Log(@"capture_call",@{@"api":@"SCStream.init",@"operation":@"stream_create",@"callID":callID,@"streamID":streamID,@"scope":Scope(filter,config)?:@{}});
    id obj=((id(*)(id,SEL,id,id,id))origStreamInit)(self,sel,filter,config,delegate);
    if(obj){objc_setAssociatedObject(obj,&streamFilterKey,filter,OBJC_ASSOCIATION_RETAIN_NONATOMIC);objc_setAssociatedObject(obj,&streamConfigKey,[config copy],OBJC_ASSOCIATION_RETAIN_NONATOMIC);objc_setAssociatedObject(obj,&streamIDKey,streamID,OBJC_ASSOCIATION_RETAIN_NONATOMIC);objc_setAssociatedObject(obj,&streamCreationKey,callID,OBJC_ASSOCIATION_RETAIN_NONATOMIC);}
    Log(@"stream_create_result",@{@"api":@"SCStream.init",@"callID":callID,@"streamID":streamID,@"success":BoolValue(obj!=nil)});return obj;
}
static BOOL StreamAdd(id self,SEL sel,id output,SCStreamOutputType type,dispatch_queue_t queue,NSError **error){
    NSString *callID=NextID(@"call"),*outputID=NextID(@"output");
    HookOutputProxy *proxy=nil;id receiver=output;
    if(type==SCStreamOutputTypeScreen){
        @synchronized(self){proxy=[objc_getAssociatedObject(self,&proxyKey) objectForKey:[NSValue valueWithNonretainedObject:output]];}
        // Preserve SDK duplicate-registration semantics for an existing output.
        if(proxy)outputID=proxy.outputID;
        else{proxy=[HookOutputProxy new];proxy.original=output;proxy.stream=self;proxy.outputID=outputID;}
        receiver=proxy;
    }
    NSMutableDictionary *fields=StreamFields(self,@"SCStream.addStreamOutput",@"stream_setup",callID);fields[@"type"]=@(type);fields[@"outputID"]=outputID;Log(@"capture_call",fields);
    BOOL ok=((BOOL(*)(id,SEL,id,SCStreamOutputType,dispatch_queue_t,NSError**))origStreamAdd)(self,sel,receiver,type,queue,error);
    if(ok&&proxy){@synchronized(self){NSMutableDictionary *map=objc_getAssociatedObject(self,&proxyKey);if(!map){map=[NSMutableDictionary dictionary];objc_setAssociatedObject(self,&proxyKey,map,OBJC_ASSOCIATION_RETAIN_NONATOMIC);}map[[NSValue valueWithNonretainedObject:output]]=proxy;}}
    fields[@"success"]=BoolValue(ok);Log(@"stream_setup_result",fields);
    return ok;
}
static BOOL StreamRemove(id self,SEL sel,id output,SCStreamOutputType type,NSError **error){id replacement=output;@synchronized(self){NSMutableDictionary *map=objc_getAssociatedObject(self,&proxyKey);if(type==SCStreamOutputTypeScreen)replacement=map[[NSValue valueWithNonretainedObject:output]]?:output;}
    BOOL ok=((BOOL(*)(id,SEL,id,SCStreamOutputType,NSError**))origStreamRemove)(self,sel,replacement,type,error);if(ok&&type==SCStreamOutputTypeScreen){@synchronized(self){[objc_getAssociatedObject(self,&proxyKey) removeObjectForKey:[NSValue valueWithNonretainedObject:output]];}}return ok;}
static void StreamStart(id self,SEL sel,void(^completion)(NSError*)){NSString *callID=NextID(@"call");NSMutableDictionary *fields=StreamFields(self,@"SCStream.startCapture",@"stream_start",callID);Log(@"capture_call",fields);((void(*)(id,SEL,id))origStreamStart)(self,sel,^(NSError *error){NSMutableDictionary *result=[fields mutableCopy];result[@"success"]=BoolValue(!error);result[@"errorDomain"]=error.domain?:@"";result[@"errorCode"]=@(error.code);Log(@"capture_start_result",result);if(completion)completion(error);});}
static void StreamStop(id self,SEL sel,void(^completion)(NSError*)){Log(@"capture_call",StreamFields(self,@"SCStream.stopCapture",@"stream_stop",NextID(@"call")));((void(*)(id,SEL,id))origStreamStop)(self,sel,completion);}
static void StreamFilterUpdate(id self,SEL sel,id filter,void(^completion)(NSError*)){Log(@"capture_call",StreamFields(self,@"SCStream.updateContentFilter",@"stream_update",NextID(@"call")));((void(*)(id,SEL,id,id))origStreamFilterUpdate)(self,sel,filter,^(NSError *e){if(!e)objc_setAssociatedObject(self,&streamFilterKey,filter,OBJC_ASSOCIATION_RETAIN_NONATOMIC);if(completion)completion(e);});}
static void StreamConfigUpdate(id self,SEL sel,id config,void(^completion)(NSError*)){Log(@"capture_call",StreamFields(self,@"SCStream.updateConfiguration",@"stream_update",NextID(@"call")));((void(*)(id,SEL,id,id))origStreamConfigUpdate)(self,sel,config,^(NSError *e){if(!e)objc_setAssociatedObject(self,&streamConfigKey,[config copy],OBJC_ASSOCIATION_RETAIN_NONATOMIC);if(completion)completion(e);});}
static void Replace(Class cls,const char *name,IMP replacement,IMP *original){Method m=class_getInstanceMethod(cls,sel_registerName(name));if(!m){Log(@"hook_unavailable",@{@"selector":@(name)});return;}*original=method_getImplementation(m);method_setImplementation(m,replacement);Log(@"hook_installed",@{@"class":NSStringFromClass(cls),@"selector":@(name)});}
__attribute__((constructor)) static void InitializeHook(void){@autoreleasepool{
    initializedPID=getpid();
    const char *lp=getenv("HOOK_DEMO_LOG"),*mode=getenv("HOOK_DEMO_MODE"),*cp=getenv("HOOK_DEMO_CONFIG"),*sid=getenv("HOOK_DEMO_SESSION_ID");
    sessionID=sid?@(sid):@"";hookInstanceID=NSUUID.UUID.UUIDString;
    char executable[PROC_PIDPATHINFO_MAXSIZE]={0};if(proc_pidpath(getpid(),executable,sizeof(executable))>0)processExecutable=@(executable);
    struct proc_bsdinfo info={0};if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))==sizeof(info)){processStartSeconds=info.pbi_start_tvsec;processStartMicroseconds=info.pbi_start_tvusec;}
    if(lp){NSString *path=[@(lp) stringByReplacingOccurrencesOfString:@"%p" withString:[NSString stringWithFormat:@"%d",getpid()]];logFD=open(path.fileSystemRepresentation,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600);struct stat st;if(logFD>=0&&(fstat(logFD,&st)!=0||!S_ISREG(st.st_mode))){close(logFD);logFD=-1;}}blocking=mode&&strcmp(mode,"block")==0;if(cp)configPath=@(cp);
    Dl_info library={0};dladdr((const void*)InitializeHook,&library);
    Log(@"image_loaded",@{@"libraryPath":library.dli_fname?@(library.dli_fname):@"unknown",@"configConfigured":BoolValue(configPath!=nil),@"version":HookVersion});
    Replace(object_getClass(NSClassFromString(@"SCShareableContent")),
            "getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:",
            (IMP)ShareableContent,&origShareableContent);
    Class filter=NSClassFromString(@"SCContentFilter");
    Replace(filter,"initWithDesktopIndependentWindow:",(IMP)WindowFilter,&origWindowFilter);
    Replace(filter,"initWithDisplay:excludingWindows:",(IMP)DisplayEx,&origDisplayEx);
    Replace(filter,"initWithDisplay:includingWindows:",(IMP)DisplayIn,&origDisplayIn);
    Replace(filter,"initWithDisplay:includingApplications:exceptingWindows:",(IMP)AppsIn,&origAppsIn);
    Replace(filter,"initWithDisplay:excludingApplications:exceptingWindows:",(IMP)AppsEx,&origAppsEx);
    Class shot=object_getClass(NSClassFromString(@"SCScreenshotManager"));
    Replace(shot,"captureImageWithFilter:configuration:completionHandler:",(IMP)Shot,&origShot);
    Replace(shot,"captureImageInRect:completionHandler:",(IMP)RectShot,&origRectShot);
    Replace(shot,"captureSampleBufferWithFilter:configuration:completionHandler:",(IMP)SampleShot,&origSampleShot);
    Class stream=NSClassFromString(@"SCStream");
    Replace(stream,"initWithFilter:configuration:delegate:",(IMP)StreamInit,&origStreamInit);
    Replace(stream,"addStreamOutput:type:sampleHandlerQueue:error:",(IMP)StreamAdd,&origStreamAdd);
    Replace(stream,"removeStreamOutput:type:error:",(IMP)StreamRemove,&origStreamRemove);
    Replace(stream,"startCaptureWithCompletionHandler:",(IMP)StreamStart,&origStreamStart);
    Replace(stream,"stopCaptureWithCompletionHandler:",(IMP)StreamStop,&origStreamStop);
    Replace(stream,"updateContentFilter:completionHandler:",(IMP)StreamFilterUpdate,&origStreamFilterUpdate);
    Replace(stream,"updateConfiguration:completionHandler:",(IMP)StreamConfigUpdate,&origStreamConfigUpdate);
}}
