import Link from 'next/link'
import { docs } from '#velite'
import { MDXContent } from '@/components/mdx-content'

const orderedArticles = [...docs]
  .filter(doc => doc.kind === 'article')
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

export default function HomePage() {
  const readme = docs.find(doc => doc.kind === 'readme')

  if (!readme) {
    return null
  }

  return (
    <div className="bg-white dark:bg-neutral-950">
      <section className="border-b border-neutral-200 bg-[radial-gradient(circle_at_top,rgba(34,197,94,0.16),transparent_42%),linear-gradient(to_bottom,rgba(250,250,250,0.96),rgba(255,255,255,1))] dark:border-neutral-800 dark:bg-[radial-gradient(circle_at_top,rgba(34,197,94,0.12),transparent_38%),linear-gradient(to_bottom,rgba(10,10,10,0.96),rgba(10,10,10,1))]">
        <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <div className="max-w-4xl">
            <p className="mb-4 text-sm font-medium uppercase tracking-[0.28em] text-green-600 dark:text-green-400">
              LangGraph Coding Agent CLI
            </p>
            <h1 className="max-w-4xl text-5xl font-bold tracking-tight text-neutral-950 dark:text-neutral-50 sm:text-6xl">
              {readme.title}
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-neutral-600 dark:text-neutral-400">
              {readme.description}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/articles"
                className="rounded-full bg-neutral-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-neutral-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                Browse Articles
              </Link>
              <a
                href="https://github.com/Iamnotphage/MT-Agent"
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full border border-neutral-300 px-5 py-2.5 text-sm font-semibold text-neutral-700 transition hover:border-neutral-400 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:border-neutral-600 dark:hover:bg-neutral-900"
              >
                View Repository
              </a>
            </div>
          </div>

          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {orderedArticles.slice(0, 3).map(article => (
              <Link
                key={article.slug}
                href={article.permalink}
                className="rounded-3xl border border-neutral-200 bg-white/80 p-5 transition hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-lg hover:shadow-neutral-950/5 dark:border-neutral-800 dark:bg-neutral-900/70 dark:hover:border-neutral-700 dark:hover:shadow-black/10"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-neutral-500 dark:text-neutral-400">
                  0{article.order}
                </p>
                <h2 className="mt-3 text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                  {article.title}
                </h2>
                <p className="mt-2 line-clamp-3 text-sm leading-6 text-neutral-600 dark:text-neutral-400">
                  {article.description}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-neutral-500 dark:text-neutral-400">
              README
            </p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100">
              Project overview
            </h2>
          </div>
          <Link
            href="/articles"
            className="text-sm font-medium text-green-600 transition hover:text-green-700 dark:text-green-400 dark:hover:text-green-300"
          >
            View all articles
          </Link>
        </div>

        <div
          data-article-body
          className="prose prose-lg prose-neutral max-w-none dark:prose-invert prose-p:leading-relaxed prose-p:text-neutral-700 dark:prose-p:text-neutral-300 prose-headings:font-bold prose-headings:tracking-tight prose-a:text-green-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-green-400 prose-li:my-1 prose-ul:my-4 prose-ol:my-4 prose-code:rounded-sm prose-code:bg-neutral-100 prose-code:px-1 prose-code:py-px prose-code:text-[0.9em] prose-code:text-green-700 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-neutral-800 dark:prose-code:text-green-400 prose-pre:p-0 prose-pre:bg-transparent prose-pre:border-0 prose-table:my-6 prose-th:bg-neutral-100 dark:prose-th:bg-neutral-800 prose-blockquote:border-l-green-500 dark:prose-blockquote:border-l-green-500 prose-blockquote:bg-emerald-50 dark:prose-blockquote:bg-neutral-900/50 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-hr:my-8"
        >
          <MDXContent code={readme.content} />
        </div>
      </section>
    </div>
  )
}
