# SM 缓存策略参考（CACHEd/CACHEs/CACHEb）

## 1) 头文件与依赖

使用前需包含：

```c
#include "common/cache_strategy/cache_wrapper.h"
```

并确保链接设备端库（含 `scalar_load/scalar_store/scalar_malloc/scalar_free`）。

## 2) CACHEd（直接映射、多 set）

- `CACHEd_INIT(name, type, Ea, sets, lines)`
- `CACHEd_RD(name, addr, value)`
- `CACHEd_WT(name, addr, value)`
- `CACHEd_FLUSH(name)` / `CACHEd_INVALID(name)`

适用：随机/散列访问，降低冲突。

## 3) CACHEs（单缓冲）

- `CACHEs_INIT(name, type, Ea, sets, lines)`（`sets` 常传 0）
- `CACHEs_RD` / `CACHEs_WT`
- `CACHEs_FLUSH` / `CACHEs_INVALID`

适用：顺序访问、局部复用较好。

## 4) CACHEb（批量缓存）

- `CACHEb_INIT(name, type, Ea, sets, bytes)`（第 5 参数是字节数）
- `CACHEb_RD` / `CACHEb_WT`
- `CACHEb_FLUSH` / `CACHEb_INVALID`

适用：连续区间整块读改写。

## 5) CACHEb 最小范式

```c
size_t bytes = (size_t)len * sizeof(double);
double *A_cache = NULL;
CACHEb_INIT(A_cache, double, (size_t)A, 0, bytes);
for (int i = 0; i < len; ++i) {
    double v;
    CACHEb_RD(A_cache, &A_cache[i], v);
    // compute
    CACHEb_WT(A_cache, &A_cache[i], v);
}
CACHEb_FLUSH(A_cache);
```

