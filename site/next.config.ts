import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'export',
  turbopack: {
    root: __dirname,
  },
  // 静态导出无服务端，需关闭 Image 默认优化（否则会报错）
  images: { unoptimized: true },
  // 若部署到 GitHub Pages 且仓库非 *.github.io，取消下一行注释并改为你的仓库名
  // basePath: '/neuromancer',
  // assetPrefix: '/neuromancer',
};

export default nextConfig;
