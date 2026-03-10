__global__ void gemm_kernel(int ni, int nj, int nk, double alpha, double beta, double *a, double *b,
                            double *c)
{
    int thread_id = get_thread_id();
    int group_size = get_group_size();

    int total_elements = ni * nj;
    int elements_per_thread = total_elements / group_size;
    int remainder = total_elements % group_size;

    int start = thread_id * elements_per_thread + (thread_id < remainder ? thread_id : remainder);
    int end = start + elements_per_thread + (thread_id < remainder ? 1 : 0);

    for (int idx = start; idx < end; ++idx) {
        c[idx] *= beta;
    }

    for (int k = 0; k < nk; ++k) {
        for (int idx = start; idx < end; ++idx) {
            int i = idx / nj;
            int j = idx % nj;
            c[idx] += alpha * a[i * nk + k] * b[k * nj + j];
        }
    }
}




