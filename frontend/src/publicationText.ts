import type { Doc } from './types';

/** Internal paragraph headings never enter reader-facing text. */
export function publicationText(doc: Doc, includeCaptions = false): string {
  return [doc.title, doc.lead,
    ...doc.paragraphs.flatMap(p => includeCaptions ? [p.text, p.caption] : [p.text]),
    doc.cta, doc.tags.join(' ')].filter(Boolean).join('\n\n');
}
