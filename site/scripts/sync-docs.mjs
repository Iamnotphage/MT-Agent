import fs from 'node:fs'
import path from 'node:path'

const projectRoot = process.cwd()
const docsRoot = path.resolve(projectRoot, '..', 'docs')
const contentRoot = path.resolve(projectRoot, '.generated', 'content')
const repoRoot = path.resolve(projectRoot, '..')
const repoUrl = 'https://github.com/Iamnotphage/MT-AutoOptimize/blob/main'

function slugify(input) {
  return input
    .replace(/\.[^.]+$/, '')
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function yamlString(value) {
  return JSON.stringify(String(value ?? ''))
}

function extractTitle(content, fallback) {
  const match = content.match(/^#\s+(.+)$/m)
  return match?.[1]?.trim() || fallback
}

function extractDescription(content) {
  const lines = content.split(/\r?\n/)
  let inCode = false
  const paragraph = []

  for (const rawLine of lines) {
    const line = rawLine.trim()

    if (line.startsWith('```')) {
      inCode = !inCode
      continue
    }
    if (inCode) continue
    if (!line) {
      if (paragraph.length > 0) break
      continue
    }
    if (
      line.startsWith('#') ||
      line.startsWith('>') ||
      line.startsWith('|') ||
      line.startsWith('![') ||
      line.startsWith('```') ||
      /^[-*]\s/.test(line) ||
      /^\d+\.\s/.test(line)
    ) {
      if (paragraph.length > 0) break
      continue
    }

    paragraph.push(line)
  }

  return paragraph.join(' ').trim() || 'Project documentation.'
}

function escapeMdxText(content) {
  const lines = content.split(/\r?\n/)
  let inFence = false

  return lines
    .map(line => {
      const trimmed = line.trim()
      if (trimmed.startsWith('```')) {
        inFence = !inFence
        return line
      }
      if (inFence) return line

      let result = ''
      let inInlineCode = false
      for (const char of line) {
        if (char === '`') {
          inInlineCode = !inInlineCode
          result += char
          continue
        }
        if (!inInlineCode && char === '{') {
          result += '&#123;'
          continue
        }
        if (!inInlineCode && char === '}') {
          result += '&#125;'
          continue
        }
        result += char
      }
      return result
    })
    .join('\n')
}

function isPlainTextLine(line) {
  const trimmed = line.trim()
  if (!trimmed) return false
  if (
    trimmed.startsWith('#') ||
    trimmed.startsWith('>') ||
    trimmed.startsWith('|') ||
    trimmed.startsWith('```') ||
    trimmed.startsWith('---') ||
    trimmed.startsWith(':::') ||
    trimmed.startsWith('<')
  ) {
    return false
  }
  if (/^[-*+]\s/.test(trimmed)) return false
  if (/^\d+[.)]\s/.test(trimmed)) return false
  return true
}

function preservePlainTextLineBreaks(content) {
  const lines = content.split(/\r?\n/)
  let inFence = false

  for (let i = 0; i < lines.length - 1; i += 1) {
    const current = lines[i]
    const next = lines[i + 1]
    const trimmed = current.trim()

    if (trimmed.startsWith('```')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    if (!isPlainTextLine(current) || !isPlainTextLine(next)) continue
    if (/\s{2,}$/.test(current)) continue

    lines[i] = `${current}  `
  }

  return lines.join('\n')
}

function rewriteMarkdownLinks(content, sourceFile) {
  return content.replace(/(?<!!)\]\((\.{1,2}\/[^)#?]+)(#[^)]+)?\)/g, (_, relativePath, hash = '') => {
    const extension = path.extname(relativePath).toLowerCase()

    if (extension === '.md') {
      const basename = path.basename(relativePath)
      if (basename === 'README.md') {
        return `](/${hash})`
      }

      return `](/articles/${slugify(basename)}${hash})`
    }

    const absoluteTarget = path.resolve(path.dirname(sourceFile), relativePath)
    const repoRelativePath = path.relative(repoRoot, absoluteTarget).replaceAll(path.sep, '/')
    return `](${repoUrl}/${repoRelativePath}${hash})`
  })
}

function getReadingOrder(readmeContent) {
  const order = new Map()
  const regex = /\]\(\.\/([^)]+\.md)\)/g
  let match
  let index = 1
  while ((match = regex.exec(readmeContent)) !== null) {
    const basename = path.basename(match[1])
    if (!order.has(basename)) {
      order.set(basename, index)
      index += 1
    }
  }
  return order
}

function writeDocFile({ targetPath, title, description, slug, kind, order, sourcePath, toc, body }) {
  const frontmatter = [
    '---',
    `title: ${yamlString(title)}`,
    `description: ${yamlString(description)}`,
    `slug: ${yamlString(slug)}`,
    `kind: ${yamlString(kind)}`,
    `order: ${order}`,
    `sourcePath: ${yamlString(sourcePath)}`,
    `toc: ${toc ? 'true' : 'false'}`,
    '---',
    '',
  ].join('\n')

  fs.mkdirSync(path.dirname(targetPath), { recursive: true })
  fs.writeFileSync(targetPath, `${frontmatter}\n${body.trim()}\n`)
}

function main() {
  const readmePath = path.join(docsRoot, 'README.md')
  const readmeContent = fs.readFileSync(readmePath, 'utf8')
  const readingOrder = getReadingOrder(readmeContent)

  fs.rmSync(contentRoot, { recursive: true, force: true })
  fs.mkdirSync(contentRoot, { recursive: true })

  const imagesDir = path.join(docsRoot, 'imgs')
  if (fs.existsSync(imagesDir)) {
    fs.cpSync(imagesDir, path.join(contentRoot, 'imgs'), { recursive: true })
    fs.cpSync(imagesDir, path.join(contentRoot, 'docs', 'imgs'), { recursive: true })
  }

  for (const fileName of fs.readdirSync(docsRoot)) {
    if (!fileName.endsWith('.md')) continue

    const sourcePath = path.join(docsRoot, fileName)
    const raw = fs.readFileSync(sourcePath, 'utf8')
    const title = extractTitle(raw, fileName.replace(/\.md$/, ''))
    const description = extractDescription(raw)
    const body = escapeMdxText(preservePlainTextLineBreaks(rewriteMarkdownLinks(raw, sourcePath)))

    if (fileName === 'README.md') {
      writeDocFile({
        targetPath: path.join(contentRoot, 'README.mdx'),
        title,
        description,
        slug: 'readme',
        kind: 'readme',
        order: 0,
        sourcePath: 'docs/README.md',
        toc: false,
        body,
      })
      continue
    }

    const slug = slugify(fileName)
    writeDocFile({
      targetPath: path.join(contentRoot, 'docs', `${slug}.mdx`),
      title,
      description,
      slug,
      kind: 'article',
      order: readingOrder.get(fileName) ?? 999,
      sourcePath: `docs/${fileName}`,
      toc: true,
      body,
    })
  }
}

main()
