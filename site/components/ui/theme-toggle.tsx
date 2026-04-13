"use client";

import { useTheme } from "@/components/theme-provider";
import { IconSun, IconMoonStars } from "@tabler/icons-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    queueMicrotask(() => setMounted(true));
  }, []);

  // 避免 hydration mismatch
  if (!mounted) {
    return (
      <div className={`p-2 rounded-full bg-gray-100 dark:bg-neutral-800 w-9 h-9 ${className}`} />
    );
  }

  return (
    <motion.button
      onClick={toggleTheme}
      className={`relative p-2 rounded-full bg-gray-100 dark:bg-neutral-800 hover:bg-gray-200 dark:hover:bg-neutral-700 transition-colors ${className}`}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      <motion.div
        initial={false}
        animate={{
          rotate: theme === "dark" ? 180 : 0,
        }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
      >
        {theme === "dark" ? (
          <IconMoonStars className="w-5 h-5 text-cyan-50" />
        ) : (
          <IconSun className="w-5 h-5 text-amber-500" />
        )}
      </motion.div>
    </motion.button>
  );
}
