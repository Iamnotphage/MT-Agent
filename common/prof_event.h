#ifndef PROF_EVENT_H
#define PROF_EVENT_H

#include <stdint.h>
#include <compiler/m3000.h>

// 性能事件数量，硬编码为26，可以按需修改
/*
    主机端传参使用，在主机端代码中声明，并传给核函数。这样数据可以在cpu端进行操作。
    uint64_t *before_hot_data = (uint64_t *)hthread_malloc(clusterId, 26 * sizeof(uint64_t), HT_MEM_RW); 
    uint64_t *after_hot_data = (uint64_t *)hthread_malloc(clusterId, 26 * sizeof(uint64_t), HT_MEM_RW); 

    设备端使用，就直接在核函数开头声明数组
    uint64_t before_hot_data[26];
    uint64_t after_hot_data[26];

    目前西交这个服务器上的性能计数是单线程，不支持多线程。系统库可以设置调整的，需要咨询天津超算老师。
*/
#define PROF_EVENT_NUM 26

// 性能事件初始化
static inline void prof_event_start_all(void)
{
    for (int eid = 0; eid < PROF_EVENT_NUM; eid++)
    {
        prof_start(eid);
    }
}

// 读取性能事件数据到数组
static inline void prof_event_read_all(uint64_t *data)
{
    for (int eid = 0; eid < PROF_EVENT_NUM; eid++)
    {
        data[eid] = prof_read(eid);
    }
}

// 性能事件结束，读取结束数据（同样覆盖输入数组）
static inline void prof_event_end_all(uint64_t *data)
{
    for (int eid = 0; eid < PROF_EVENT_NUM; eid++)
    {
        data[eid] = prof_end(eid);
    }
}

// 性能事件输出，我这里还是放到主机端输出，因为这样可以加入更多的程序信息，像程序名、线程数、核心名、输入规模等；还可以直接存到excel表里，生成出来可以直接python分析
static inline void prof_event_print_all(uint64_t * before_data,uint64_t *after_data)
{
    // 用这个接口输出
    // hthread_printf("TMPID:%d\n",thread_id);
}

#endif // PROF_EVENT_H