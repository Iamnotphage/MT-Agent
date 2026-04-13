import { notFound } from 'next/navigation'
import Link from 'next/link'
import { docs } from '#velite'
import { MDXContent } from '@/components/mdx-content'
import { BlogTableOfContents } from '@/components/blog-table-of-contents'

interface ArticlePageProps {
  params: Promise<{
    slug: string
  }>
}

const orderedArticles = [...docs]
  .filter(doc => doc.kind === 'article')
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

export function generateStaticParams() {
  return orderedArticles.map(article => ({ slug: article.slug }))
}

export default async function ArticlePage({ params }: ArticlePageProps) {
  const { slug } = await params
  const article = orderedArticles.find(doc => doc.slug === slug)

  if (!article) {
    notFound()
  }

  const relatedArticles = orderedArticles
    .filter(doc => doc.slug !== article.slug)
    .slice(0, 6)

  return (
    <div className="bg-white dark:bg-neutral-950">
      <div className="border-b border-neutral-200 bg-white/80 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/70">
        <div className="mx-auto max-w-[92rem] px-6 py-6">
          <div className="mx-auto w-full max-w-[56rem] 2xl:max-w-[60rem]">
            <Link
              href="/articles"
              className="mb-6 inline-flex items-center gap-2 text-sm text-neutral-600 transition-colors hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Back to articles
            </Link>

            <div className="mb-4 flex flex-wrap gap-2">
              <span className="rounded-full bg-neutral-200 px-3 py-1 text-xs font-medium text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300">
                Step {article.order}
              </span>
              <span className="rounded-full bg-neutral-200 px-3 py-1 text-xs font-medium text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300">
                {article.sourcePath}
              </span>
            </div>

            <h1 className="mb-3 text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100 lg:text-4xl">
              {article.title}
            </h1>

            <p className="text-base leading-7 text-neutral-600 dark:text-neutral-400">
              {article.description}
            </p>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[92rem] px-6 py-10">
        <div className="relative xl:grid xl:grid-cols-[16rem_minmax(0,56rem)_16rem] xl:justify-center xl:gap-x-8 2xl:grid-cols-[17rem_minmax(0,60rem)_17rem] 2xl:gap-x-10">
          <aside className="hidden xl:block">
            <div className="sticky top-24 pr-2">
              <div className="mb-3 text-base font-semibold text-neutral-800 dark:text-neutral-200">
                Continue reading
              </div>
              <div className="space-y-2 border-l border-neutral-200 pl-4 dark:border-neutral-800">
                {relatedArticles.map(doc => (
                  <Link
                    key={doc.slug}
                    href={doc.permalink}
                    className="block py-1 text-[15px] leading-6 text-neutral-600 transition-colors hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-200"
                  >
                    {doc.title}
                  </Link>
                ))}
              </div>
            </div>
          </aside>

          <article className="min-w-0">
            <div className="mx-auto w-full max-w-[56rem] 2xl:max-w-[60rem] xl:max-w-none">
              <div
                data-article-body
                className="prose prose-lg prose-neutral max-w-none dark:prose-invert prose-p:leading-relaxed prose-p:text-neutral-700 dark:prose-p:text-neutral-300 prose-headings:font-bold prose-headings:tracking-tight prose-h2:mt-10 prose-h2:mb-4 prose-h3:mt-8 prose-h3:mb-3 prose-a:text-green-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-green-400 prose-li:my-1 prose-ul:my-4 prose-ol:my-4 prose-code:rounded-md prose-code:bg-neutral-100 prose-code:px-[0.4em] prose-code:py-[0.2em] prose-code:text-[0.85em] prose-code:font-normal prose-code:text-neutral-800 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-neutral-800/90 dark:prose-code:text-neutral-200 prose-pre:p-0 prose-pre:bg-transparent prose-pre:border-0 prose-table:my-6 prose-th:bg-neutral-100 dark:prose-th:bg-neutral-800 prose-blockquote:border-l-green-500 dark:prose-blockquote:border-l-green-500 prose-blockquote:bg-emerald-50 dark:prose-blockquote:bg-neutral-900/50 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-hr:my-8"
              >
                <MDXContent code={article.content} />
              </div>
            </div>
          </article>

          <aside className="hidden xl:block">
            {article.toc ? <BlogTableOfContents className="sticky top-24 pl-2" /> : null}
          </aside>
        </div>
      </div>
    </div>
  )
}
