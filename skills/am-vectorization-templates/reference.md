# AM 向量化接口与模板摘要

## 1) 常用向量算子（来自参考项目）

- `vec_muli(a, b)`：乘法
- `vec_mula(a, b, c)`：乘加
- `vec_mulb(a, b, c)`：乘减
- `vm_fdivd16(a, b)`：除法
- `vm_frecd16(a)`：倒数
- `vm_sqrtd16(a)`：开方
- `vm_powd16_u10(x, y)`：幂
- `vm_fmaxd16(a, b)` / `vm_fmind16(a, b)`：最大/最小
- `vm_sind16_u10(a)`：正弦

## 2) 访存与内存接口

- `vector_load(src, buf, bytes)`：全局内存到向量缓存
- `vector_store(buf, dst, bytes)`：向量缓存回写到全局内存
- `vec_ld(0, buf)` / `vec_st(reg, 0, buf)`：缓冲与向量变量互转
- `vector_malloc(bytes)` / `vector_free(ptr)`：向量缓存分配释放

## 3) 推荐宏与流程

```c
#define SIMD_LEN 16
#define VEC_BYTES 128
```

流程：分工 -> load -> 向量算子 -> store -> 尾部标量。

## 4) 模板选择建议

- `Generic`：通用循环、不确定模式。
- `DenseMatMul`：矩阵乘热点。
- `MatVec`：矩阵向量乘。
- `Stencil`：邻域访问。
- `Elementwise`：逐元素计算。
- `Irregular`：不规则访问（通常混合标量）。

