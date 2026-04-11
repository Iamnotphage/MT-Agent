import Link from 'next/link'
import { docs } from '#velite'

const orderedArticles = [...docs]
  .filter(doc => doc.kind === 'article')
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

export default function ArticlesPage() {
  return (
    <div className="bg-white dark:bg-neutral-950">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="max-w-3xl">
          <p className="text-sm font-medium uppercase tracking-[0.24em] text-green-600 dark:text-green-400">
            Wiki Articles
          </p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100">
            Documentation index
          </h1>
          <p className="mt-4 text-base leading-7 text-neutral-600 dark:text-neutral-400">
            所有文章都直接复用仓库里的 <code>docs/</code> 内容，通过构建阶段补充 frontmatter 和路由信息。
          </p>
        </div>

        <div className="mt-10 grid gap-4">
          {orderedArticles.map(article => (
            <Link
              key={article.slug}
              href={article.permalink}
              className="group rounded-3xl border border-neutral-200 bg-neutral-50/80 px-6 py-5 transition hover:border-neutral-300 hover:bg-white hover:shadow-lg hover:shadow-neutral-950/5 dark:border-neutral-800 dark:bg-neutral-900/80 dark:hover:border-neutral-700 dark:hover:bg-neutral-900"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="mb-2 inline-flex rounded-full bg-neutral-200/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                    Step {article.order}
                  </div>
                  <h2 className="text-xl font-semibold text-neutral-900 transition group-hover:text-green-600 dark:text-neutral-100 dark:group-hover:text-green-400">
                    {article.title}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600 dark:text-neutral-400">
                    {article.description}
                  </p>
                </div>
                <div className="shrink-0 text-sm font-medium text-neutral-500 transition group-hover:text-neutral-700 dark:text-neutral-400 dark:group-hover:text-neutral-200">
                  Open
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
