// No game data: validate Metal 4 counter lifetime, units and buffer contents.
#import <Metal/Metal.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) { @autoreleasepool {
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();NSError *error=nil;
    id<MTL4CommandQueue> queue=[device newMTL4CommandQueueWithDescriptor:[MTL4CommandQueueDescriptor new] error:&error];
    id<MTL4CommandAllocator> allocator=[device newCommandAllocatorWithDescriptor:[MTL4CommandAllocatorDescriptor new] error:&error];
    const NSUInteger size=64*1024*1024;
    id<MTLBuffer> buffer=[device newBufferWithLength:size options:MTLResourceStorageModeShared];
    MTLResidencySetDescriptor *rd=[MTLResidencySetDescriptor new];rd.initialCapacity=1;
    id<MTLResidencySet> residency=[device newResidencySetWithDescriptor:rd error:&error];
    [residency addAllocation:buffer];[residency commit];[residency requestResidency];[queue addResidencySet:residency];
    MTL4CounterHeapDescriptor *hd=[MTL4CounterHeapDescriptor new];hd.type=MTL4CounterHeapTypeTimestamp;hd.count=4096;
    id<MTL4CounterHeap> heap=[device newCounterHeapWithDescriptor:hd error:&error];
    if(!queue || !allocator || !buffer || !residency || !heap){fprintf(stderr,"Metal allocation: %s\n",error.description.UTF8String);return 1;}
    id<MTL4CommandBuffer> command=[device newCommandBuffer];[command beginCommandBufferWithAllocator:allocator];
    [command writeTimestampIntoHeap:heap atIndex:0];
    id<MTL4ComputeCommandEncoder> encoder=[command computeCommandEncoder];
    [encoder fillBuffer:buffer range:NSMakeRange(0,size) value:0x5a];[encoder endEncoding];
    [command writeTimestampIntoHeap:heap atIndex:1];[command endCommandBuffer];
    dispatch_semaphore_t done=dispatch_semaphore_create(0);__block double feedback=0;__block int failed=0;
    MTL4CommitOptions *options=[MTL4CommitOptions new];
    [options addFeedbackHandler:^(id<MTL4CommitFeedback> f){failed=f.error!=nil;feedback=1000*(f.GPUEndTime-f.GPUStartTime);dispatch_semaphore_signal(done);}];
    id<MTL4CommandBuffer> commands[]={command};[queue commit:commands count:1 options:options];
    if(dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC)) || failed)return 2;
    NSData *data=[heap resolveCounterRange:NSMakeRange(0,2)];
    if(data.length!=2*sizeof(MTL4TimestampHeapEntry))return 3;
    const MTL4TimestampHeapEntry *entry=data.bytes;uint64_t frequency=[device queryTimestampFrequency];
    if(!frequency || !entry[0].timestamp || entry[1].timestamp<=entry[0].timestamp)return 4;
    double span=1000.0*(entry[1].timestamp-entry[0].timestamp)/frequency;
    if(span>feedback*2+2 || feedback<=0)return 5;
    const uint8_t *bytes=buffer.contents;for(NSUInteger n=0;n<size;n++)if(bytes[n]!=0x5a)return 6;
    printf("{\"passed\":true,\"verified_bytes\":%lu,\"frequency_hz\":%llu,\"span_ms\":%.6f,\"feedback_gpu_ms\":%.6f}\n",
        (unsigned long)size,(unsigned long long)frequency,span,feedback);
    return 0;
} }
