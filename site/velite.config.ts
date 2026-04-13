import { defineConfig, defineCollection, s } from 'velite'
import rehypePrettyCode from 'rehype-pretty-code'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import remarkGemoji from 'remark-gemoji'
import rehypeMermaid from 'rehype-mermaid'
import { visit } from 'unist-util-visit'
import type { Root } from 'hast'
import type { Root as MdastRoot } from 'mdast'

/** 兼容单行三反引号：```foo``` -> 代码块（默认 text），避免被 mdast 解析成 inlineCode */
function remarkSingleLineFencedCode() {
  return (tree: MdastRoot, file?: { value?: unknown }) => {
    const source = typeof file?.value === 'string' ? file.value : ''
    if (!source) return

    visit(tree, 'paragraph', (node) => {
      if (node.children.length !== 1) return

      const only = node.children[0]
      if (only.type !== 'inlineCode' || !node.position) return

      const startOffset = node.position.start.offset
      const endOffset = node.position.end.offset
      if (typeof startOffset !== 'number' || typeof endOffset !== 'number') return

      const raw = source.slice(startOffset, endOffset).trim()
      if (!/^```[^`\r\n]+```$/.test(raw)) return

      node.type = 'code'
      ;(node as unknown as { lang?: string; meta?: string | null; value?: string }).lang = 'text'
      ;(node as unknown as { lang?: string; meta?: string | null; value?: string }).meta = null
      ;(node as unknown as { lang?: string; meta?: string | null; value?: string }).value = only.value
      delete (node as unknown as { children?: unknown }).children
    })
  }
}

/** 未显式声明语言的 fenced code block 默认按 text 处理 */
function remarkDefaultCodeLanguage() {
  return (tree: MdastRoot) => {
    visit(tree, 'code', (node) => {
      if (!node.lang || !node.lang.trim()) {
        node.lang = 'text'
      }
    })
  }
}

/** 两个及以上连续空行时插入可见间距：在 mdast 中插入一个会渲染为 div 的占位节点 */
function remarkDoubleBlankSpacer() {
  return (tree: MdastRoot) => {
    const children = tree.children
    if (!Array.isArray(children) || children.length < 2) return
    const next: MdastRoot['children'] = []
    for (let i = 0; i < children.length; i++) {
      next.push(children[i])
      const curr = children[i]
      const prev = children[i + 1]
      if (!prev || !curr.position || !prev.position) continue
      const gap = prev.position.start.line - curr.position.end.line
      if (gap > 2) {
        next.push({
          type: 'paragraph',
          children: [],
          data: {
            hName: 'div',
            hProperties: { className: 'prose-double-blank-spacer my-4' },
          },
        } as MdastRoot['children'][0])
      }
    }
    tree.children = next
  }
}

/** 支持 GitHub Flavored Markdown alerts，避免 remark-alerts 生成 raw/html 节点导致 MDX 构建报错 */
function remarkGitHubAlerts() {
  // 只匹配同一行内的可选标题：\s* 会吃掉 \n，导致下一行正文被误当成自定义标题（如 [!NOTE]\n一般提示）
  const markerPattern =
    /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:[ \t]+([^\r\n]+))?/i
  const defaultTitles: Record<string, string> = {
    note: 'Note',
    tip: 'Tip',
    important: 'Important',
    warning: 'Warning',
    caution: 'Caution',
  }

  return (tree: MdastRoot) => {
    visit(tree, 'blockquote', (node) => {
      const first = node.children[0]
      if (!first || first.type !== 'paragraph' || first.children.length === 0) return

      const lead = first.children[0]
      if (lead.type !== 'text') return

      const match = lead.value.match(markerPattern)
      if (!match) return

      const type = match[1].toLowerCase()
      const title = (match[2]?.trim() || defaultTitles[type] || match[1]).trim()
      const remaining = lead.value.slice(match[0].length).trimStart()

      if (remaining) {
        lead.value = remaining
      } else {
        first.children.splice(0, 1)
        if (first.children.length === 0) {
          node.children.shift()
        }
      }

      node.data = {
        hName: 'div',
        hProperties: {
          className: ['markdown-alert', `markdown-alert-${type}`],
        },
      }

      node.children.unshift({
        type: 'paragraph',
        data: {
          hName: 'p',
          hProperties: {
            className: ['markdown-alert-title'],
          },
        },
        children: [
          {
            type: 'text',
            value: '',
            data: {
              hName: 'span',
              hProperties: {
                className: ['markdown-alert-title-icon'],
                'aria-hidden': 'true',
              },
            },
          },
          {
            type: 'text',
            value: title,
            data: {
              hName: 'span',
              hProperties: {
                className: ['markdown-alert-title-text'],
              },
            },
          },
        ],
      })
    })
  }
}

/** 将 GitHub blob 图片链接转为 raw 直链，否则 <img> 会拿到 HTML 无法显示 */
function rehypeGitHubRawImages() {
  return (tree: Root) => {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'img' || typeof node.properties?.src !== 'string') return
      const src = node.properties.src
      const m = src.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\/([^/]+)\/(.+)$/)
      if (m) {
        const [, owner, repo, branch, path] = m
        node.properties.src = `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${path}`
      }
    })
  }
}

const docs = defineCollection({
  name: 'Doc',
  pattern: '**/*.mdx',
  schema: s
    .object({
      title: s.string(),
      description: s.string(),
      slug: s.string(),
      kind: s.string(),
      order: s.number(),
      sourcePath: s.string(),
      toc: s.boolean().optional().default(true),
      content: s.mdx(),
    })
    .transform(data => ({
      ...data,
      permalink: data.kind === 'readme' ? '/' : `/articles/${data.slug}`,
    })),
})

export default defineConfig({
  root: '.generated/content',
  output: {
    data: '.velite',
    assets: 'public/static',
    base: '/static/',
    name: '[name]-[hash:6].[ext]',
    clean: true,
  },
  collections: { docs },
  mdx: {
    rehypePlugins: [
      rehypeSlug,
      [
        rehypeAutolinkHeadings,
        {
          behavior: 'wrap',
          properties: {
            className: ['heading-anchor'],
            ariaLabel: 'Link to heading',
          },
        },
      ],
      rehypeGitHubRawImages,
      // Mermaid 必须在 pretty-code 之前，避免先被高亮器改写
      [rehypeMermaid, { strategy: 'inline-svg' }],
      [rehypePrettyCode, { theme: 'one-dark-pro' }],
      [
        rehypeKatex,
        {
          output: 'html',
          strict: false,
          minRuleThickness: 0.06,
        },
      ],
    ],
    remarkPlugins: [remarkGfm, remarkSingleLineFencedCode, remarkDefaultCodeLanguage, remarkGitHubAlerts, remarkMath, remarkGemoji, remarkDoubleBlankSpacer],
  },
})
