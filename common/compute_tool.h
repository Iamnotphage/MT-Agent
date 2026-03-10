#include <stdint.h>
#include <compiler/m3000.h>
static inline int min(int a, int b) { return a > b ? b : a; }
static inline int max(int a, int b) { return a > b ? a : b; }

static inline double sum_f64(lvector double op) {
    double ret = 0.0, tmp1;
    mov_to_svr_v16df(op);
    tmp1 = mov_from_svr0_df(); ret = ret + tmp1; 
    tmp1 = mov_from_svr1_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr2_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr3_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr4_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr5_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr6_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr7_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr8_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr9_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr10_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr11_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr12_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr13_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr14_df(); ret = ret + tmp1;
    tmp1 = mov_from_svr15_df(); ret = ret + tmp1;
    return ret;
}
static inline lvector double set_vector_f64(double * list) {
    mov_to_svr0_df(list[0]);  
    mov_to_svr1_df(list[1]);  
    mov_to_svr2_df(list[2]);  
    mov_to_svr3_df(list[3]);  
    mov_to_svr4_df(list[4]);  
    mov_to_svr5_df(list[5]);  
    mov_to_svr6_df(list[6]);  
    mov_to_svr7_df(list[7]);  
    mov_to_svr8_df(list[8]);  
    mov_to_svr9_df(list[9]);  
    mov_to_svr10_df(list[10]);  
    mov_to_svr11_df(list[11]);  
    mov_to_svr12_df(list[12]);  
    mov_to_svr13_df(list[13]);  
    mov_to_svr14_df(list[14]);  
    mov_to_svr15_df(list[15]);  
    return mov_from_svr_v16df();
}