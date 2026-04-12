'use client'

import * as runtime from 'react/jsx-runtime'
import { ComponentProps, useCallback, useEffect, useMemo, useState } from 'react'
import { Children, isValidElement } from 'react'
import { cn } from '@/lib/utils'

// 复制到剪贴板：优先 Clipboard API，非安全上下文（如局域网 http）下回退到 execCommand
async function copyToClipboard(text: string): Promise<boolean> {
  if (typeof navigator === 'undefined') return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 非安全上下文（如 http://192.168.x.x）下 clipboard 会抛错，走 fallback
  }
  // Fallback：临时 textarea + execCommand
  try {
    const el = document.createElement('textarea')
    el.value = text
    el.setAttribute('readonly', '')
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    el.style.top = '0'
    document.body.appendChild(el)
    el.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(el)
    return ok
  } catch {
    return false
  }
}

// Copy button: 清理 timeout、复制失败处理、无障碍
function CopyButton({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle')

  const handleCopy = useCallback(async () => {
    if (!text) return
    const ok = await copyToClipboard(text)
    setStatus(ok ? 'copied' : 'error')
  }, [text])

  useEffect(() => {
    if (status === 'idle') return
    const t = setTimeout(() => setStatus('idle'), 2000)
    return () => clearTimeout(t)
  }, [status])

  const label =
    status === 'copied'
      ? 'Copied!'
      : status === 'error'
        ? 'Copy failed'
        : 'Copy code'

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200 focus:outline-none focus:ring-2 focus:ring-neutral-500 focus:ring-offset-2 focus:ring-offset-neutral-900"
      title={label}
      aria-label={label}
      aria-live="polite"
    >
      {status === 'copied' ? (
        <>
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>Copied!</span>
        </>
      ) : status === 'error' ? (
        <>
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Failed</span>
        </>
      ) : (
        <>
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <span>Copy</span>
        </>
      )}
    </button>
  )
}

// 从 React 子节点中抽取纯文本（用于复制）
function extractText(children: React.ReactNode): string {
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map(extractText).join('')
  if (children != null && typeof children === 'object' && 'props' in children) {
    const el = children as React.ReactElement<{ children?: React.ReactNode }>
    return extractText(el.props.children)
  }
  return ''
}

// 从 pre 或其子 code 节点上读取 data-language（兼容 rehype-pretty-code）
function getCodeLanguage(preProps: Record<string, unknown>, children: React.ReactNode): string | undefined {
  const onPre = preProps['data-language']
  if (onPre && typeof onPre === 'string') return onPre
  const arr = Children.toArray(children)
  const first = arr[0]
  if (isValidElement(first) && first.props && typeof first.props === 'object' && 'data-language' in first.props) {
    const lang = (first.props as Record<string, unknown>)['data-language']
    return typeof lang === 'string' ? lang : undefined
  }
  return undefined
}

// 代码块：语言标签 + 复制按钮，与 rehype-pretty-code 兼容
function Pre({ children, ...props }: ComponentProps<'pre'>) {
  const language = getCodeLanguage(props as Record<string, unknown>, children)
  const codeText = useMemo(() => extractText(children), [children])

  return (
    <div className="group relative my-6 overflow-hidden rounded-xl border border-neutral-200 bg-neutral-950 dark:border-neutral-700">
      <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900 px-4 py-2">
        <span className="text-xs font-medium text-neutral-400">
          {language || 'code'}
        </span>
        <CopyButton text={codeText} />
      </div>
      <pre {...props} className="overflow-x-auto p-4 text-sm">
        {children}
      </pre>
    </div>
  )
}

// Custom figure wrapper for rehype-pretty-code
function Figure({ children, ...props }: ComponentProps<'figure'>) {
  if ('data-rehype-pretty-code-figure' in props) {
    return <>{children}</>
  }
  return <figure {...props}>{children}</figure>
}

// Custom heading components
function H1({ children, ...props }: ComponentProps<'h1'>) {
  return (
    <h1
      {...props}
      className="mt-10 mb-5 text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100"
    >
      {children}
    </h1>
  )
}

function H2({ children, ...props }: ComponentProps<'h2'>) {
  return (
    <h2
      {...props}
      className="mt-12 mb-4 text-2xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100"
    >
      {children}
    </h2>
  )
}

function H3({ children, ...props }: ComponentProps<'h3'>) {
  return (
    <h3
      {...props}
      className="mt-8 mb-3 text-xl font-semibold tracking-tight text-neutral-800 dark:text-neutral-200"
    >
      {children}
    </h3>
  )
}

function H4({ children, ...props }: ComponentProps<'h4'>) {
  return (
    <h4
      {...props}
      className="mt-6 mb-2 text-lg font-semibold text-neutral-700 dark:text-neutral-300"
    >
      {children}
    </h4>
  )
}

// Inline code（code block 内的 code 由 data-language 区分，不做内联样式）
const inlineCodeClass =
  'rounded-sm border border-neutral-300/90 bg-neutral-100 px-1 py-px font-mono text-[0.9em] text-neutral-800 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200 break-all'

function Code({
  children,
  className,
  ...props
}: ComponentProps<'code'> & { 'data-language'?: string }) {
  if (props['data-language']) {
    return <code {...props} className={className}>{children}</code>
  }
  return (
    <code {...props} className={cn(inlineCodeClass, className)}>
      {children}
    </code>
  )
}

// Emphasis (italic)
function Em({ children, ...props }: ComponentProps<'em'>) {
  return (
    <em {...props} className="italic text-neutral-700 dark:text-neutral-300">
      {children}
    </em>
  )
}

// Strong (bold)
function Strong({ children, ...props }: ComponentProps<'strong'>) {
  return (
    <strong {...props} className="font-bold text-neutral-900 dark:text-white">
      {children}
    </strong>
  )
}

// Custom table components
function Table({ children, ...props }: ComponentProps<'table'>) {
  return (
    <div className="my-6 overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-700">
      <table {...props} className="w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  )
}

function Thead({ children, ...props }: ComponentProps<'thead'>) {
  return (
    <thead {...props} className="bg-neutral-100 dark:bg-neutral-800">
      {children}
    </thead>
  )
}

function Th({ children, ...props }: ComponentProps<'th'>) {
  return (
    <th
      {...props}
      className="border-b border-neutral-200 px-4 py-3 text-left font-semibold text-neutral-900 dark:border-neutral-700 dark:text-neutral-100"
    >
      {children}
    </th>
  )
}

function Td({ children, ...props }: ComponentProps<'td'>) {
  return (
    <td
      {...props}
      className="border-b border-neutral-200 px-4 py-3 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
    >
      {children}
    </td>
  )
}

function Tr({ children, ...props }: ComponentProps<'tr'>) {
  return (
    <tr {...props} className="transition-colors hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
      {children}
    </tr>
  )
}

// Blockquote
function Blockquote({ children, ...props }: ComponentProps<'blockquote'>) {
  return (
    <blockquote
      {...props}
      className="my-6 rounded-r-xl border-l-4 border-green-500 bg-emerald-50/50 py-3 pl-4 pr-4 italic text-neutral-700 dark:border-green-500 dark:bg-green-950/20 dark:text-neutral-300"
    >
      {children}
    </blockquote>
  )
}

// Horizontal rule
function Hr(props: ComponentProps<'hr'>) {
  return (
    <hr
      {...props}
      className="my-8 border-0 h-px bg-gradient-to-r from-transparent via-neutral-300 to-transparent dark:via-neutral-700"
    />
  )
}

// Link
function Anchor({ children, ...props }: ComponentProps<'a'>) {
  return (
    <a
      {...props}
      className="font-medium no-underline transition-all hover:underline focus-visible:underline decoration-1 underline-offset-2 text-[#16A34A] hover:text-[#15803D] active:text-[#14532D] visited:text-[#166534] dark:text-[#4ADE80] dark:hover:text-[#22C55E] dark:active:text-[#16A34A] dark:visited:text-[#16A34A]"
    >
      {children}
    </a>
  )
}

// Unordered list
function Ul({ children, ...props }: ComponentProps<'ul'>) {
  return (
    <ul
      {...props}
      className="my-4 ml-6 list-disc space-y-2 text-neutral-700 dark:text-neutral-300 marker:text-green-500 dark:marker:text-green-400"
    >
      {children}
    </ul>
  )
}

// Ordered list
function Ol({ children, ...props }: ComponentProps<'ol'>) {
  return (
    <ol
      {...props}
      className="my-4 ml-6 list-decimal space-y-2 text-neutral-700 dark:text-neutral-300 marker:text-green-500 marker:font-medium dark:marker:text-green-400"
    >
      {children}
    </ol>
  )
}

// List item
function Li({ children, ...props }: ComponentProps<'li'>) {
  return (
    <li {...props} className="pl-1">
      {children}
    </li>
  )
}

function isBadgeImage(src: string, alt?: string) {
  return src.includes('shields.io') || /badge/i.test(alt ?? '')
}

function Img({ className, alt, src, ...props }: ComponentProps<'img'>) {
  const resolvedSrc = typeof src === 'string' ? src : ''
  const badge = resolvedSrc ? isBadgeImage(resolvedSrc, alt) : false
  const resolvedClassName = badge
    ? 'my-0 inline-block h-auto max-w-full align-middle rounded-none shadow-none'
    : 'my-6 block h-auto max-w-full rounded-lg'

  return (
    // eslint-disable-next-line @next/next/no-img-element -- markdown images should keep intrinsic GitHub-like sizing
    <img
      {...props}
      src={src}
      alt={alt ?? ''}
      className={cn(resolvedClassName, className)}
    />
  )
}

// MDX components mapping
const components = {
  pre: Pre,
  figure: Figure,
  img: Img,
  h1: H1,
  h2: H2,
  h3: H3,
  h4: H4,
  code: Code,
  em: Em,
  strong: Strong,
  table: Table,
  thead: Thead,
  th: Th,
  td: Td,
  tr: Tr,
  blockquote: Blockquote,
  hr: Hr,
  a: Anchor,
  ul: Ul,
  ol: Ol,
  li: Li,
}

function getMDXComponent(code: string) {
  const fn = new Function(code)
  return fn({ ...runtime }).default
}

interface MDXContentProps {
  code: string
}

export function MDXContent({ code }: MDXContentProps) {
  // MDX 运行时从 code 编译出组件，必须在 render 中解析；用 useMemo 稳定引用
  /* eslint-disable react-hooks/static-components -- MDX compiles code to component at runtime */
  const Component = useMemo(() => getMDXComponent(code), [code])
  return <Component components={components} />
  /* eslint-enable react-hooks/static-components */
}
