import fs from 'node:fs';
import path from 'node:path';

export interface ReleaseAssetInfo {
  name: string;
  url: string;
  sha256?: string;
}

export interface ReleaseInfo {
  version: string;
  publishedAt: string;
  releaseUrl: string;
  macos: ReleaseAssetInfo;
  windows: ReleaseAssetInfo;
  linux: ReleaseAssetInfo;
}

const REPO = 'Skyl9/AnkiDraft';
const BASE_DOWNLOAD = `https://github.com/${REPO}/releases/latest/download`;

function readPyprojectVersion(): string {
  try {
    const pyprojectPath = path.resolve(process.cwd(), '..', 'pyproject.toml');
    const content = fs.readFileSync(pyprojectPath, 'utf-8');
    const match = content.match(/^version\s*=\s*"([^"]+)"/m);
    if (match?.[1]) {
      return match[1];
    }
  } catch {
    // Fallback if pyproject.toml is unreadable
  }
  return '1.0.5';
}

export async function getLatestRelease(): Promise<ReleaseInfo> {
  const fallbackVersion = readPyprojectVersion();
  const fallback: ReleaseInfo = {
    version: fallbackVersion,
    publishedAt: new Date().toISOString().slice(0, 10),
    releaseUrl: `https://github.com/${REPO}/releases/latest`,
    macos: {
      name: 'AnkiDraft-macos-arm64.dmg',
      url: `${BASE_DOWNLOAD}/AnkiDraft-macos-arm64.dmg`,
    },
    windows: {
      name: 'AnkiDraft-Setup-x64.exe',
      url: `${BASE_DOWNLOAD}/AnkiDraft-Setup-x64.exe`,
    },
    linux: {
      name: 'AnkiDraft-x86_64.AppImage',
      url: `${BASE_DOWNLOAD}/AnkiDraft-x86_64.AppImage`,
    },
  };

  try {
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
      headers: {
        Accept: 'application/vnd.github+json',
        'User-Agent': 'AnkiDraft-Website-Builder',
      },
    });
    if (!res.ok) {
      return fallback;
    }
    const data = (await res.json()) as {
      tag_name?: string;
      published_at?: string;
      html_url?: string;
    };
    const version = (data.tag_name || fallbackVersion).replace(/^v/i, '');
    return {
      ...fallback,
      version,
      publishedAt: (data.published_at || fallback.publishedAt).slice(0, 10),
      releaseUrl: data.html_url || fallback.releaseUrl,
    };
  } catch {
    return fallback;
  }
}
