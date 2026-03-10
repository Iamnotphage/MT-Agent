#include <stdint.h>
#include <compiler/m3000.h>
#include "hthread_device.h"

// SM缓存优化库
#include "common/cache_strategy/cache_wrapper.h"

// 性能采集
#include "common/compute_tool.h"
#include "common/prof_event.h"

//大模型生成的存储文件
#include "kernel_generated.h"

