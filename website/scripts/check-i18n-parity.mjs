#!/usr/bin/env node
/**
 * Vérifie la parité bilingue 1:1 entre website/src/content/docs/fr/ et website/src/content/docs/en/
 * ainsi que l'absence d'imports MDX/JSX incompatibles avec le lecteur hors-ligne DocReaderDialog.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const docsRoot = path.resolve(__dirname, '..', 'src', 'content', 'docs');
const frRoot = path.join(docsRoot, 'fr');
const enRoot = path.join(docsRoot, 'en');

function listMarkdownFiles(dir, base = dir) {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  let files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files = files.concat(listMarkdownFiles(full, base));
    } else if (entry.isFile() && (entry.name.endsWith('.md') || entry.name.endsWith('.mdx'))) {
      files.push(path.relative(base, full).replace(/\\/g, '/'));
    }
  }
  return files.sort();
}

const frFiles = listMarkdownFiles(frRoot);
const enFiles = listMarkdownFiles(enRoot);

let hasError = false;

if (frFiles.length === 0) {
  console.error('❌ Aucun fichier Markdown trouvé dans website/src/content/docs/fr/');
  process.exit(1);
}

for (const f of frFiles) {
  if (f.endsWith('.mdx')) {
    console.error(`❌ Fichier .mdx interdit (utiliser .md pur pour DocReaderDialog) : fr/${f}`);
    hasError = true;
  }
  if (!enFiles.includes(f)) {
    console.error(`❌ Page anglaise manquante pour : fr/${f} (attendu : en/${f})`);
    hasError = true;
  }
}

for (const f of enFiles) {
  if (f.endsWith('.mdx')) {
    console.error(`❌ Fichier .mdx interdit (utiliser .md pur pour DocReaderDialog) : en/${f}`);
    hasError = true;
  }
  if (!frFiles.includes(f)) {
    console.error(`❌ Page française manquante pour : en/${f} (attendu : fr/${f})`);
    hasError = true;
  }
}

if (hasError) {
  process.exit(1);
}

console.log(`✅ Parité bilingue FR/EN validée (${frFiles.length} pages par langue).`);
