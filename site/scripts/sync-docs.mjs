import fs from 'node:fs'
import path from 'node:path'

const projectRoot = process.cwd()
const docsRoot = path.resolve(projectRoot, '..', 'docs')
const contentRoot = path.resolve(projectRoot, '.generated', 'content')
const publicRoot = path.resolve(projectRoot, 'public')
const repoRoot = path.resolve(projectRoot, '..')
const repoReadmePath = path.join(repoRoot, 'README.md')
const repoUrl = 'https://github.com/Iamnotphage/MT-Agent/blob/main'

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
      line.startsWith('---') ||
      line.startsWith('***') ||
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

function collapseBadgeImageLines(content) {
  const lines = content.split(/\r?\n/)
  const output = []
  let badgeBuffer = []

  function flushBadges() {
    if (badgeBuffer.length === 0) return
    output.push(badgeBuffer.join(' '))
    badgeBuffer = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    const isStandaloneBadge =
      /^!\[[^\]]*\]\((https?:\/\/[^)]*shields\.io[^)]*)\)$/.test(trimmed)

    if (isStandaloneBadge) {
      badgeBuffer.push(trimmed)
      continue
    }

    flushBadges()
    output.push(line)
  }

  flushBadges()
  return output.join('\n')
}

function isRelativeRef(ref) {
  return (
    ref &&
    !ref.startsWith('http://') &&
    !ref.startsWith('https://') &&
    !ref.startsWith('/') &&
    !ref.startsWith('#')
  )
}

function rewriteMarkdownRefs(content, sourceFile) {
  return content.replace(/(!?)\]\(([^)#?]+)(#[^)]+)?\)/g, (full, bang, target, hash = '') => {
    if (!isRelativeRef(target)) {
      return full
    }

    const extension = path.extname(target).toLowerCase()
    const normalizedTarget = target.replaceAll('\\', '/')

    if (bang !== '!' && extension === '.md') {
      const basename = path.basename(target)
      if (basename === 'README.md') {
        return `${bang}](/${hash})`
      }

      return `${bang}](/articles/${slugify(basename)}${hash})`
    }

    if (normalizedTarget.startsWith('docs/imgs/') || normalizedTarget.startsWith('./imgs/')) {
      return `${bang}](/imgs/${path.basename(target)}${hash})`
    }

    const absoluteTarget = path.resolve(path.dirname(sourceFile), target)

    if (absoluteTarget.startsWith(path.join(docsRoot, 'imgs') + path.sep)) {
      const relativeImgPath = path.relative(path.join(docsRoot, 'imgs'), absoluteTarget).replaceAll(path.sep, '/')
      return `${bang}](/imgs/${relativeImgPath}${hash})`
    }

    const repoRelativePath = path.relative(repoRoot, absoluteTarget).replaceAll(path.sep, '/')
    return `${bang}](${repoUrl}/${repoRelativePath}${hash})`
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
  const docsReadmePath = path.join(docsRoot, 'README.md')
  const docsReadmeContent = fs.readFileSync(docsReadmePath, 'utf8')
  const readingOrder = getReadingOrder(docsReadmeContent)
  const repoReadmeRaw = fs.readFileSync(repoReadmePath, 'utf8')
  const repoReadmeDescription = extractDescription(
    repoReadmeRaw.replace(/^\s*(---|\*\*\*)\s*$/gm, ''),
  )

  fs.rmSync(contentRoot, { recursive: true, force: true })
  fs.mkdirSync(contentRoot, { recursive: true })

  const imagesDir = path.join(docsRoot, 'imgs')
  if (fs.existsSync(imagesDir)) {
    fs.cpSync(imagesDir, path.join(contentRoot, 'imgs'), { recursive: true })
    fs.cpSync(imagesDir, path.join(contentRoot, 'docs', 'imgs'), { recursive: true })
    fs.mkdirSync(path.join(publicRoot, 'imgs'), { recursive: true })
    fs.cpSync(imagesDir, path.join(publicRoot, 'imgs'), { recursive: true })
  }

  writeDocFile({
    targetPath: path.join(contentRoot, 'README.mdx'),
    title: extractTitle(repoReadmeRaw, 'README'),
    description: repoReadmeDescription,
    slug: 'readme',
    kind: 'readme',
    order: 0,
    sourcePath: 'README.md',
    toc: false,
    body: escapeMdxText(
      preservePlainTextLineBreaks(
        collapseBadgeImageLines(
          rewriteMarkdownRefs(repoReadmeRaw, repoReadmePath),
        ),
      ),
    ),
  })

  for (const fileName of fs.readdirSync(docsRoot)) {
    if (!fileName.endsWith('.md')) continue
    if (fileName === 'README.md') continue

    const sourcePath = path.join(docsRoot, fileName)
    const raw = fs.readFileSync(sourcePath, 'utf8')
    const title = extractTitle(raw, fileName.replace(/\.md$/, ''))
    const description = extractDescription(raw)
    const body = escapeMdxText(preservePlainTextLineBreaks(rewriteMarkdownRefs(raw, sourcePath)))

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
