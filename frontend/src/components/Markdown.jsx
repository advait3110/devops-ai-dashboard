/* Renders Gemini's Markdown answers. Code blocks get a copy button. */
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const text = String(children?.props?.children ?? "").replace(/\n$/, "");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: ignore */
    }
  };
  return (
    <div className="code-block">
      <button className="copy-btn" onClick={copy} aria-label="Copy code">
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre>{children}</pre>
    </div>
  );
}

const components = {
  pre: CodeBlock,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown components={components}>{children || ""}</ReactMarkdown>
    </div>
  );
}
