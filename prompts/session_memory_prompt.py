"""Session memory prompt templates."""

DEFAULT_SESSION_MEMORY_TEMPLATE = """# Session Title
_A short and distinctive 5-10 word descriptive title for the session. Super info dense, no filler_

# Current State
_What is actively being worked on right now? Pending tasks not yet completed. Immediate next steps._

# Task specification
_What did the user ask to build? Any design decisions or other explanatory context_

# Files and Functions
_What are the important files? In short, what do they contain and why are they relevant?_

# Workflow
_What commands are usually run and in what order? How to interpret their output if not obvious?_

# Errors & Corrections
_Errors encountered and how they were fixed. What did the user correct? What approaches failed and should not be tried again?_

# Codebase and System Documentation
_What are the important system components? How do they work/fit together?_

# Learnings
_What has worked well? What has not? What to avoid? Do not duplicate items from other sections_

# Key results
_If the user asked a specific output such as an answer to a question, a table, or other document, repeat the exact result here_

# Worklog
_Step by step, what was attempted, done? Very terse summary for each step_
"""

SESSION_MEMORY_UPDATE_SYSTEM_PROMPT = """CRITICAL: Respond with Markdown only. Do not call tools.

You are updating a long-lived session memory file for a coding agent.
Preserve the exact section headings from the existing template.
Rewrite the content under those headings so the file is a compact, accurate, technically useful working memory.
Keep facts concrete. Prefer file paths, function names, failures, fixes, pending work, and user corrections.
Do not add new top-level headings.
"""

SESSION_MEMORY_UPDATE_USER_PROMPT = """Update the session memory Markdown using the current memory file and the recent conversation history.

Requirements:
- Keep every existing top-level heading.
- Replace placeholder text with concrete content whenever possible.
- Keep the file concise but complete enough to resume work later.
- Focus on current state, files touched, commands run, failures, fixes, and pending tasks.
- If a section has no useful information yet, keep a short placeholder sentence.

Current session memory file:
<current_memory>
{current_memory}
</current_memory>

Recent conversation history:
<conversation>
{conversation}
</conversation>
"""
