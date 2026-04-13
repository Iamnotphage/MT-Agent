import Link from 'next/link'
import { docs } from '#velite'

const orderedArticles = [...docs]
  .filter(doc => doc.kind === 'docs-index' || doc.kind === 'article')
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

interface DocsSidebarProps {
  activeSlug?: string
  className?: string
}

export function DocsSidebar({ activeSlug, className }: DocsSidebarProps) {
  return (
    <div className={className}>
      <div className="mb-3 text-base font-semibold text-neutral-800 dark:text-neutral-200">
        文档
      </div>
      <nav aria-label="Documentation sidebar" className="space-y-1.5">
        {orderedArticles.map((doc) => {
          const active = doc.slug === activeSlug

          return (
            <Link
              key={doc.slug}
              href={doc.permalink}
              aria-current={active ? 'page' : undefined}
              className={`block rounded-xl px-3 py-2 text-[15px] leading-6 transition-colors ${
                active
                  ? 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-900 dark:hover:text-neutral-200'
              }`}
            >
              <span>{doc.title}</span>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
