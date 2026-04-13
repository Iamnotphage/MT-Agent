import { notFound } from 'next/navigation'
import { docs } from '#velite'
import { MDXContent } from '@/components/mdx-content'
import { BlogTableOfContents } from '@/components/blog-table-of-contents'
import { DocsSidebar } from '@/components/docs-sidebar'

interface DocumentationPageProps {
  params: Promise<{
    slug: string
  }>
}

const orderedDocs = [...docs]
  .filter(doc => doc.kind === 'docs-index' || doc.kind === 'article')
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

export function generateStaticParams() {
  return orderedDocs.map(doc => ({ slug: doc.slug }))
}

export default async function DocumentationPage({ params }: DocumentationPageProps) {
  const { slug } = await params
  const doc = orderedDocs.find(item => item.slug === slug)

  if (!doc) {
    notFound()
  }

  return (
    <div className="bg-white dark:bg-neutral-950">
      <div className="mx-auto max-w-[92rem] px-6 py-10">
        <div className="relative xl:grid xl:grid-cols-[16rem_minmax(0,56rem)_16rem] xl:justify-center xl:gap-x-8 2xl:grid-cols-[17rem_minmax(0,60rem)_17rem] 2xl:gap-x-10">
          <aside className="hidden xl:block">
            <DocsSidebar activeSlug={doc.slug} className="sticky top-24 pr-2" />
          </aside>

          <article className="min-w-0">
            <div className="mx-auto w-full max-w-[56rem] 2xl:max-w-[60rem] xl:max-w-none">
              <div
                data-article-body
                className="prose prose-lg prose-neutral max-w-none dark:prose-invert prose-p:leading-relaxed prose-p:text-neutral-700 dark:prose-p:text-neutral-300 prose-headings:font-bold prose-headings:tracking-tight prose-h2:mt-10 prose-h2:mb-4 prose-h3:mt-8 prose-h3:mb-3 prose-a:text-green-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-green-400 prose-li:my-1 prose-ul:my-4 prose-ol:my-4 prose-code:rounded-md prose-code:bg-neutral-100 prose-code:px-[0.4em] prose-code:py-[0.2em] prose-code:text-[0.85em] prose-code:font-normal prose-code:text-neutral-800 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-neutral-800/90 dark:prose-code:text-neutral-200 prose-pre:p-0 prose-pre:bg-transparent prose-pre:border-0 prose-table:my-6 prose-th:bg-neutral-100 dark:prose-th:bg-neutral-800 prose-blockquote:border-l-green-500 dark:prose-blockquote:border-l-green-500 prose-blockquote:bg-emerald-50 dark:prose-blockquote:bg-neutral-900/50 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-hr:my-8"
              >
                <MDXContent code={doc.content} />
              </div>
            </div>
          </article>

          <aside className="hidden xl:block">
            {doc.toc ? <BlogTableOfContents className="sticky top-24 pl-2" /> : null}
          </aside>
        </div>
      </div>
    </div>
  )
}
