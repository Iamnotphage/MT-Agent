/*
 * 典型应用：标量 DAXPY 核函数，供 process_sca 做 SM 缓存优化。
 * 使用方式：在项目根目录执行
 *   python process_sca.py -i test_sca.dev.c -o test_sca_out.dev.c
 * 生成的 kernel_sca.h 会包含 daxpy_kernel_sca_qwen，由 foo_auto_sca.dev.c 编译校验。
 */
#include <stdint.h>
#include <compiler/m3000.h>
#include "hthread_device.h"

__global__ void daxpy_kernel(int n, double alpha, double *x, double *y)
{
    int tid = get_thread_id();
    int gsz = get_group_size();
    int per = (n + gsz - 1) / gsz;
    int start = tid * per;
    int end = start + per;
    if (end > n) end = n;

    for (int i = start; i < end; i++)
        y[i] = alpha * x[i] + y[i];
}
