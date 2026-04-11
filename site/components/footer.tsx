"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

const MaskedSvgIcon = ({
  src,
  className,
  title,
}: {
  src: string;
  className?: string;
  title?: string;
}) => (
  <span
    aria-hidden={title ? undefined : "true"}
    title={title}
    className={cn("bg-black dark:bg-white", className)}
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
);

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
  );
}

const navLinks = [
  { label: "README", href: "/" },
  { label: "Articles", href: "/articles" },
  { label: "Architecture", href: "/articles/architecture" },
  { label: "ReAct Loop", href: "/articles/reactloop" },
];

const socialLinks = [
  { label: "GitHub", href: "https://github.com/Iamnotphage/MT-Agent", icon: "/icons/github.svg" },
  { label: "Source", href: "https://github.com/Iamnotphage/MT-Agent/tree/main/docs", icon: "/icons/source.svg" },
];

export function FooterLinks() {
  return (
    <footer className="border-t border-neutral-200 bg-neutral-50/80 dark:border-neutral-800 dark:bg-neutral-900/80">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-3">
            <Link href="/" className="inline-flex items-center gap-3">
              <span className="inline-flex h-5 w-5 items-center justify-center text-neutral-900 dark:text-neutral-100">
                <WikiLogo className="h-5 w-5" />
              </span>
              <span className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                MT-Agent
              </span>
            </Link>
            <p className="max-w-xs text-xs text-neutral-500 dark:text-neutral-400">
                Project wiki for the LangGraph coding agent CLI. <br/>
                Built with Next.js and Velite.
            </p>
          </div>

          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                Navigation
              </h3>
              <ul className="space-y-2">
                {navLinks.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "text-sm text-neutral-600 transition-colors hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                Interlinked
              </h3>
              <ul className="flex flex-wrap gap-3">
                {socialLinks.map((item) => (
                  <li key={item.href}>
                    <a
                      href={item.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center rounded-md p-2 text-neutral-500 transition-colors hover:bg-neutral-200 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
                      aria-label={item.label}
                    >
                      <MaskedSvgIcon src={item.icon} className="h-5 w-5" title={item.label} />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-8 flex flex-col items-center justify-between gap-2 border-t border-neutral-200 pt-8 dark:border-neutral-800 sm:flex-row">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            © 2026 MT-Agent
          </p>
          <span className="inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400">
            All rights reserved
            <a
              href="https://github.com/Iamnotphage/MT-Agent"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-neutral-500 transition-colors hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
              aria-label="Source"
            >
              <MaskedSvgIcon
                src="/icons/source.svg"
                className="h-[1em] w-[1em]"
                title="Source"
              />
            </a>
          </span>
        </div>
      </div>
    </footer>
  );
}
