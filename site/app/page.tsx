import { docs } from '#velite'
import { BlogTableOfContents } from '@/components/blog-table-of-contents'
import { MDXContent } from '@/components/mdx-content'

export default function HomePage() {
  const readme = docs.find(doc => doc.kind === 'readme')

  if (!readme) {
    return null
  }

  return (
    <div className="bg-white dark:bg-neutral-950">
      <div className="mx-auto max-w-[92rem] px-6 py-12 sm:py-16">
        <div className="relative xl:grid xl:grid-cols-[minmax(0,56rem)_16rem] xl:justify-center xl:gap-x-8 2xl:grid-cols-[minmax(0,60rem)_17rem] 2xl:gap-x-10">
          <article className="min-w-0">
            <div className="mx-auto w-full max-w-[56rem] 2xl:max-w-[60rem] xl:max-w-none">
              <div
                data-article-body
                className="prose prose-lg prose-neutral max-w-none dark:prose-invert prose-p:leading-relaxed prose-p:text-neutral-700 dark:prose-p:text-neutral-300 prose-headings:font-bold prose-headings:tracking-tight prose-a:text-green-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-green-400 prose-li:my-1 prose-ul:my-4 prose-ol:my-4 prose-code:rounded-sm prose-code:bg-neutral-100 prose-code:px-1 prose-code:py-px prose-code:text-[0.9em] prose-code:text-green-700 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-neutral-800 dark:prose-code:text-green-400 prose-pre:p-0 prose-pre:bg-transparent prose-pre:border-0 prose-table:my-6 prose-th:bg-neutral-100 dark:prose-th:bg-neutral-800 prose-blockquote:border-l-green-500 dark:prose-blockquote:border-l-green-500 prose-blockquote:bg-emerald-50 dark:prose-blockquote:bg-neutral-900/50 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-hr:my-8"
              >
                <MDXContent code={readme.content} />
              </div>
            </div>
          </article>

          <aside className="hidden xl:block">
            <BlogTableOfContents className="sticky top-24 pl-2" />
          </aside>
        </div>
      </div>
    </div>
  )
}
