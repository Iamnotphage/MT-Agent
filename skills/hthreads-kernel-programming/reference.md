# Hthreads 编程接口参考

## 1) 线程与分工

常用接口：

- `int tid = get_thread_id();`
- `int gsz = get_group_size();`

基础分工模板：

```c
int per = (n + gsz - 1) / gsz;
int start = tid * per;
int end = (start + per < n) ? start + per : n;
for (int i = start; i < end; ++i) {
    // work
}
```

## 2) 推荐核函数骨架

```c
__global__ void kernel_name(/* args */) {
    int tid = get_thread_id();
    int gsz = get_group_size();
    // 1) 任务划分
    // 2) 数据搬运/计算
    // 3) 边界处理
}
```

## 3) 设备端注意事项

- 严格检查数组边界。
- 保持可复现性：避免依赖未初始化数据。
- 复杂优化前先保证标量版本正确。

