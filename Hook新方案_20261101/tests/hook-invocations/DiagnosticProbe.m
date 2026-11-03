#import <Foundation/Foundation.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <libproc.h>
#import <unistd.h>

// No screen/window enumeration: replace the method in this self-owned process
// before loading CaptureHook. The wrapper must forward these synthetic objects.
@interface SyntheticShareableContent : NSObject
@property(nonatomic, strong) NSArray *displays;
@property(nonatomic, strong) NSArray *windows;
@property(nonatomic, strong) NSArray *applications;
@end
@implementation SyntheticShareableContent
@end

static SyntheticShareableContent *fixtureContent;
static NSError *fixtureError;
static NSUInteger requests, nilCompletions;
static BOOL lastExclude, lastOnScreen;
static void MockShareable(id cls, SEL sel, BOOL exclude, BOOL onScreen,
                          void(^completion)(SCShareableContent *, NSError *)) {
    requests++; lastExclude=exclude; lastOnScreen=onScreen;
    if(!completion){nilCompletions++;return;}
    completion(exclude?(SCShareableContent *)fixtureContent:nil, onScreen?nil:fixtureError);
}

static NSDictionary *Identity(void) {
    struct proc_bsdinfo info={0}; char path[PROC_PIDPATHINFO_MAXSIZE]={0};
    if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))!=sizeof(info) ||
       proc_pidpath(getpid(),path,sizeof(path))<=0) return nil;
    return @{@"pid":@(getpid()),@"uid":@(getuid()),@"processStartSeconds":@(info.pbi_start_tvsec),
             @"processStartMicroseconds":@(info.pbi_start_tvusec),@"executable":@(path)};
}

int main(int argc,const char **argv){@autoreleasepool{
    if(argc!=3)return 2;
    NSDictionary *identity=Identity();if(!identity)return 3;
    NSMutableDictionary *receipt=[identity mutableCopy];
    receipt[@"screenCapturePerformed"]=@NO;
    receipt[@"realScreenEnumerationPerformed"]=@NO;
    receipt[@"uuOperationPerformed"]=@NO;
    if(strcmp(argv[1],"shareable")==0){
        fixtureContent=[SyntheticShareableContent new];
        fixtureContent.displays=@[@"synthetic-display"];
        fixtureContent.windows=@[@"synthetic-window-1",@"synthetic-window-2"];
        fixtureContent.applications=@[@"synthetic-app-1",@"synthetic-app-2",@"synthetic-app-3"];
        fixtureError=[NSError errorWithDomain:@"SyntheticDiagnostic" code:-37 userInfo:nil];
        SEL selector=@selector(getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:);
        Method method=class_getClassMethod(SCShareableContent.class,selector);
        if(!method)return 4;
        method_setImplementation(method,(IMP)MockShareable);
        BOOL load=strcmp(argv[2],"-")!=0;
        if(load&&!dlopen(argv[2],RTLD_NOW|RTLD_LOCAL))return 5;
        BOOL installed=method_getImplementation(method)!=(IMP)MockShareable;
        if(installed!=load)return 6;
        __block BOOL objects=YES,errors=YES;__block NSUInteger callbacks=0;
        BOOL arguments=YES;
        for(int test=0;test<3;test++){
            BOOL exclude=test!=1,onScreen=test==0;
            [SCShareableContent getShareableContentExcludingDesktopWindows:exclude onScreenWindowsOnly:onScreen completionHandler:^(SCShareableContent *content,NSError *error){
                callbacks++;
                objects=objects&&(content==(exclude?(SCShareableContent *)fixtureContent:nil));
                errors=errors&&(error==(onScreen?nil:fixtureError));
            }];
            arguments=arguments&&lastExclude==exclude&&lastOnScreen==onScreen;
        }
        // Preserve the original nil-handler behavior without synthesizing a callback.
        ((void(*)(id,SEL,BOOL,BOOL,id))objc_msgSend)(SCShareableContent.class,selector,NO,YES,nil);
        arguments=arguments&&!lastExclude&&lastOnScreen;
        [receipt addEntriesFromDictionary:@{@"wrapperInstalled":installed?@YES:@NO,
            @"argumentPassThrough":arguments?@YES:@NO,@"objectIdentityPreserved":objects?@YES:@NO,
            @"errorIdentityPreserved":errors?@YES:@NO,@"nilCompletionPassedThrough":nilCompletions==1?@YES:@NO,
            @"requests":@(requests),@"callbacks":@(callbacks)}];
        if(!arguments||!objects||!errors||requests!=4||callbacks!=3||nilCompletions!=1)return 7;
    }else if(strcmp(argv[1],"display-control")==0){
        // The SDK explicitly accepts a nullable stream argument. No stream is
        // created, so these calls cannot start screen capture or deliver frames.
        CGError start=CGDisplayStreamStart(NULL),stop=CGDisplayStreamStop(NULL);
        receipt[@"startReturnCode"]=@(start);receipt[@"stopReturnCode"]=@(stop);
        if(start==kCGErrorSuccess||stop==kCGErrorSuccess)return 8;
    }else return 2;
    receipt[@"passed"]=@YES;
    NSData *data=[NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingSortedKeys error:nil];
    if(!data)return 9;
    fwrite(data.bytes,1,data.length,stdout);fputc('\n',stdout);return 0;
}}
