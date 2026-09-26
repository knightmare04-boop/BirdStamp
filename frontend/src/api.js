// Centralized API configuration for the BirdStamp frontend.
//
// The frontend always talks to the backend through relative URLs. In dev,
// the Vite server proxies '/api' and '/uploads' to the backend (see
// vite.config.js); in the packaged desktop build, pywebview serves the
// frontend from the same origin as the backend. Either way, relative URLs
// are always correct and the backend's actual port never needs to be known
// here.
export const API_BASE = '/api';

/**
 * Resolves a stamp's stored image URL into something displayable in <img>.
 *
 * - '/uploads/...' (server-hosted uploads), 'data:' and 'blob:' URLs are
 *   already usable as-is and are returned untouched.
 * - For images hosted on birdtheme.org, the site serves small thumbnails
 *   with an 's' suffix before the extension (e.g. 'foo-s.jpg'); we rewrite
 *   that to the large variant ('foo-l.jpg') for a better display image.
 * - Any other absolute URL is left completely untouched.
 */
export function resolveImageUrl(url) {
  if (!url) return '';
  if (url.startsWith('/uploads') || url.startsWith('data:') || url.startsWith('blob:')) {
    return url;
  }

  try {
    const parsed = new URL(url, typeof window !== 'undefined' ? window.location.origin : undefined);
    const host = parsed.hostname.toLowerCase();
    if (host === 'birdtheme.org' || host.endsWith('.birdtheme.org')) {
      return url.replace(/s(\.\w+)$/, 'l$1');
    }
  } catch {
    // Not a parseable absolute URL; fall through and return it untouched.
  }

  return url;
}
