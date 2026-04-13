"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { AnimatePresence, motion } from "motion/react"
import { useBlogSearch } from "@/components/blog-search-context"
import {
  Navbar,
  NavBody,
  NavItems,
  MobileNav,
  NavbarButton,
  MobileNavHeader,
  MobileNavToggle,
  MobileNavMenu,
} from "@/components/ui/resizable-navbar"
import { ThemeToggle } from "@/components/ui/theme-toggle"

const primaryNavItems = [
  { name: "README", link: "/" },
  { name: "文档", link: "/documents/README" },
]

const MaskedSvgIcon = ({
  src,
  className,
  title,
}: {
  src: string
  className?: string
  title?: string
}) => (
  <span
    aria-hidden={title ? undefined : "true"}
    title={title}
    className={`bg-black dark:bg-white ${className ?? ""}`}
    style={{
      WebkitMaskImage: `url(${src})`,
      maskImage: `url(${src})`,
      WebkitMaskRepeat: "no-repeat",
      maskRepeat: "no-repeat",
      WebkitMaskPosition: "center",
      maskPosition: "center",
      WebkitMaskSize: "contain",
      maskSize: "contain",
    }}
  />
)

const contactLinks = [
  {
    name: "GitHub Repo",
    href: "https://github.com/Iamnotphage/MT-Agent",
    icon: <MaskedSvgIcon src="/icons/github.svg" className="h-4 w-4" title="GitHub" />,
  },
  {
    name: "Docs Source",
    href: "https://github.com/Iamnotphage/MT-Agent/tree/main/docs",
    icon: <MaskedSvgIcon src="/icons/source.svg" className="h-4 w-4" title="Source" />,
  },
  {
    name: "Issues",
    href: "https://github.com/Iamnotphage/MT-Agent/issues",
    icon: (
      <svg className="h-4 w-4 text-current" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
]

function WikiLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3.5 6.5C3.5 5.12 4.62 4 6 4h4.5c1.93 0 3.5 1.57 3.5 3.5V20c-.9-.83-2.04-1.25-3.42-1.25H6a2.5 2.5 0 0 0-2.5 2.5z" />
      <path d="M20.5 6.5C20.5 5.12 19.38 4 18 4h-4.5C11.57 4 10 5.57 10 7.5V20c.9-.83 2.04-1.25 3.42-1.25H18a2.5 2.5 0 0 1 2.5 2.5z" />
    </svg>
  )
}

function SearchTrigger() {
  const blogSearch = useBlogSearch()
  if (!blogSearch) return null
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        blogSearch.openSearch()
      }}
      className="relative z-10 flex shrink-0 items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 px-2.5 py-1.5 text-neutral-600 transition-colors hover:bg-neutral-100 hover:text-neutral-900 dark:border-neutral-700 dark:bg-neutral-800/80 dark:text-neutral-400 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
      aria-label="搜索文档 (⌘K)"
    >
      <span className="text-[11px] font-medium tabular-nums text-neutral-500 dark:text-neutral-400">⌘K</span>
      <svg className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    </button>
  )
}

const NavbarLogo = () => (
  <Link
    href="/"
    className="relative z-20 mr-4 flex items-center space-x-2 px-2 py-1 text-sm font-normal"
  >
    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-50">
      <WikiLogo className="h-[18px] w-[18px]" />
    </div>
    <span className="font-bold text-black dark:text-white">MT-Agent</span>
  </Link>
)

function isTabActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/"
  if (href === "/documents/README") return pathname === "/documents/README" || pathname.startsWith("/documents/")
  return pathname === href
}

function DocTabs() {
  const pathname = usePathname()

  return (
    <div className="border-b border-neutral-200/80 bg-white/88 dark:border-neutral-800/80 dark:bg-neutral-950/75">
      <div className="mx-auto max-w-7xl px-4">
        <nav
          aria-label="文档标签"
          className="scrollbar-none flex items-center gap-2 overflow-x-auto py-2"
        >
          {primaryNavItems.map((tab) => {
            const active = isTabActive(pathname, tab.link)

            return (
              <Link
                key={tab.link}
                href={tab.link}
                className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-950"
                    : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-white"
                }`}
                aria-current={active ? "page" : undefined}
              >
                {tab.name}
              </Link>
            )
          })}
        </nav>
      </div>
    </div>
  )
}

export function SiteNavbar() {
  const blogSearch = useBlogSearch()
  const pathname = usePathname()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isContactMenuOpen, setIsContactMenuOpen] = useState(false)
  const contactMenuRef = useRef<HTMLDivElement>(null)

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        contactMenuRef.current &&
        !contactMenuRef.current.contains(event.target as Node)
      ) {
        setIsContactMenuOpen(false)
      }
    }

    if (isContactMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside)
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [isContactMenuOpen])

  // ESC 关闭下拉菜单
  useEffect(() => {
    if (!isContactMenuOpen) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsContactMenuOpen(false)
        contactMenuRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [isContactMenuOpen])

  const menuVariants = {
    closed: {
      opacity: 0,
      y: 10,
      scale: 0.98,
      transition: { duration: 0.12, ease: "easeOut" },
    },
    open: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: {
        type: "spring",
        stiffness: 520,
        damping: 34,
        mass: 0.7,
        staggerChildren: 0.045,
        delayChildren: 0.02,
      },
    },
  } as const

  const itemVariants = {
    closed: { opacity: 0, x: 6 },
    open: { opacity: 1, x: 0, transition: { duration: 0.14 } },
  } as const

  return (
    <>
      <Navbar>
        <NavBody narrowMinWidth="980px">
          <NavbarLogo />
          <NavItems items={primaryNavItems} />
          <div className="relative z-10 flex shrink-0 items-center gap-4">
            <SearchTrigger />
            <ThemeToggle />
            <div className="relative" ref={contactMenuRef}>
              <NavbarButton
                variant="primary"
                as="button"
                onClick={() => setIsContactMenuOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={isContactMenuOpen}
                aria-controls="contact-menu"
                className="bg-neutral-900 text-white hover:bg-neutral-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                Links
              </NavbarButton>

              <AnimatePresence>
                {isContactMenuOpen && (
                  <motion.div
                    id="contact-menu"
                    role="menu"
                    aria-label="Contact links"
                    initial="closed"
                    animate="open"
                    exit="closed"
                    variants={menuVariants}
                    className="absolute right-0 top-full mt-2 z-50 min-w-[12rem] origin-top-right rounded-xl border border-neutral-200/70 bg-white/85 p-1 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.25)] backdrop-blur-md dark:border-neutral-700/60 dark:bg-neutral-950/70"
                  >
                    <div className="absolute -top-1 right-5 h-2 w-2 rotate-45 rounded-[2px] border border-neutral-200/70 bg-white/85 backdrop-blur-md dark:border-neutral-700/60 dark:bg-neutral-950/70" />

                    <motion.div
                      variants={{
                        open: { transition: { staggerChildren: 0.045 } },
                        closed: { transition: { staggerChildren: 0.02 } },
                      }}
                      className="flex flex-col gap-1"
                    >
                      {contactLinks.map((link, idx) => (
                        <motion.a
                          key={`contact-${idx}`}
                          role="menuitem"
                          href={link.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          variants={itemVariants}
                          whileHover={{ x: 2 }}
                          whileTap={{ scale: 0.98 }}
                          className="group flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800/70"
                          onClick={() => setIsContactMenuOpen(false)}
                        >
                          <span className="flex h-5 w-5 items-center justify-center">
                            {link.icon}
                          </span>
                          <span className="whitespace-nowrap">{link.name}</span>
                          <span className="ml-auto text-xs text-neutral-400 opacity-0 transition-opacity group-hover:opacity-100 dark:text-neutral-500">
                            ↗
                          </span>
                        </motion.a>
                      ))}
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </NavBody>

        <MobileNav>
          <MobileNavHeader>
            <NavbarLogo />
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <MobileNavToggle
                isOpen={isMobileMenuOpen}
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              />
            </div>
          </MobileNavHeader>

          <MobileNavMenu
            isOpen={isMobileMenuOpen}
            onClose={() => setIsMobileMenuOpen(false)}
          >
            {primaryNavItems.map((item, idx) => (
              <a
                key={`mobile-link-${idx}`}
                href={item.link}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`relative ${isTabActive(pathname, item.link) ? "text-neutral-900 dark:text-white" : "text-neutral-600 dark:text-neutral-300"}`}
              >
                <span className="block">{item.name}</span>
              </a>
            ))}

            <div className="flex w-full flex-col gap-2 mt-4 pt-4 border-t border-neutral-200 dark:border-neutral-700">
              <span className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 px-2">
                Project links
              </span>
              {contactLinks.map((link, idx) => (
                <a
                  key={idx}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-3 px-2 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  <span className="flex h-6 w-6 items-center justify-center">
                    {link.icon}
                  </span>
                  <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    {link.name}
                  </span>
                </a>
              ))}
              <button
                type="button"
                onClick={() => {
                  setIsMobileMenuOpen(false)
                  blogSearch?.openSearch()
                }}
                className="flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Search docs
              </button>
            </div>
          </MobileNavMenu>
        </MobileNav>
      </Navbar>

      <DocTabs />
    </>
  )
}
