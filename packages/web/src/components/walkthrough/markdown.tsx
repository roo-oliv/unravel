"use client";

import ReactMarkdown from "react-markdown";

import { cn } from "@/lib/utils";

interface Props {
  children: string;
  className?: string;
}

/**
 * Narration / summary / overview text rendered as Markdown.
 *
 * Storage stays as plain Markdown (see plan) so this is purely presentational.
 * We keep the component set small: paragraphs, inline code, code blocks,
 * lists, links, emphasis. No raw HTML.
 */
export function Markdown({ children, className }: Props) {
  return (
    <div className={cn("space-y-2", className)}>
      <ReactMarkdown
        skipHtml
        components={{
          p: ({ children }) => (
            <p className="leading-relaxed">{children}</p>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="underline underline-offset-2 decoration-muted-foreground/60 hover:decoration-foreground"
            >
              {children}
            </a>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => (
            <ul className="ml-5 list-disc space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="ml-5 list-decimal space-y-1">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed">{children}</li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-muted pl-3 italic text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-border" />,
          h1: ({ children }) => (
            <h3 className="text-base font-semibold">{children}</h3>
          ),
          h2: ({ children }) => (
            <h3 className="text-base font-semibold">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="text-sm font-semibold">{children}</h4>
          ),
          code: ({ className: codeClass, children, ...props }) => {
            // Block code (fenced) carries `language-xxx`. Inline code has no
            // language class — style it as a chip.
            const isBlock = (codeClass ?? "").startsWith("language-");
            if (isBlock) {
              return (
                <code className={cn(codeClass, "font-mono")} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="rounded bg-muted px-1 py-[1px] font-mono text-[0.9em] text-foreground"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-md border bg-muted/60 p-3 text-[0.85em] leading-relaxed">
              {children}
            </pre>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
