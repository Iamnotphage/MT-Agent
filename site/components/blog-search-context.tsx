'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { BlogSearchModal } from './blog-search-modal'

type BlogSearchContextValue = {
  openSearch: () => void
}

const BlogSearchContext = createContext<BlogSearchContextValue | null>(null)

export function useBlogSearch() {
  const ctx = useContext(BlogSearchContext)
  return ctx
}

export function BlogSearchProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)

  const openSearch = useCallback(() => setOpen(true), [])
  const onClose = useCallback(() => setOpen(false), [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(prev => !prev)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <BlogSearchContext.Provider value={{ openSearch }}>
      {children}
      <BlogSearchModal open={open} onClose={onClose} />
    </BlogSearchContext.Provider>
  )
}
