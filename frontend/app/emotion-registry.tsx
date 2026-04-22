'use client';

import { useState } from 'react';
import { useServerInsertedHTML } from 'next/navigation';
import createCache from '@emotion/cache';
import { CacheProvider } from '@emotion/react';

/**
 * Synchronises Emotion's CSS cache between SSR and client hydration.
 *
 * Without this, MUI emits <style data-emotion="…"> on the server but the
 * client's fresh Emotion cache tries to insert a <div> in the same position,
 * causing the React hydration mismatch "server rendered HTML didn't match".
 *
 * useServerInsertedHTML flushes the collected style names into the <head>
 * during streaming so the client receives the exact same style nodes that
 * were used to produce the server HTML.
 */
export default function EmotionRegistry({ children }: { children: React.ReactNode }) {
  const [{ cache, flush }] = useState(() => {
    const c = createCache({ key: 'css' });
    const prevInsert = c.insert.bind(c);
    let inserted: string[] = [];

    c.insert = function(selector, serialized, sheet, shouldCache) {
      if (c.inserted[serialized.name] === undefined) {
        inserted.push(serialized.name);
      }
      return prevInsert(selector, serialized, sheet, shouldCache);
    };

    return {
      cache: c,
      flush: () => {
        const prev = inserted;
        inserted = [];
        return prev;
      },
    };
  });

  useServerInsertedHTML(() => {
    const names = flush();
    if (names.length === 0) return null;
    // cache.inserted values are `string | true`; true means already injected
    // globally and has no serialized CSS string to emit.
    const styles = names
      .map((n) => cache.inserted[n])
      .filter((s): s is string => typeof s === 'string')
      .join('');
    if (!styles) return null;
    return (
      <style
        key={cache.key}
        data-emotion={`${cache.key} ${names.join(' ')}`}
        dangerouslySetInnerHTML={{ __html: styles }}
      />
    );
  });

  return <CacheProvider value={cache}>{children}</CacheProvider>;
}
