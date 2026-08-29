import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

export function Markdown({ children }: { children: string }) {

  const components: Components = {
    // Downgrade h1/h2 semantically to avoid duplicate page headings
    h1: ({ children }) => <h2 className="markdown-h1">{children}</h2>,
    h2: ({ children }) => <h3 className="markdown-h2">{children}</h3>,

    // Style code blocks - react-markdown doesn't pass inline prop directly
    code: ({ children, className }) => {
      const isInline = !className || !className.startsWith('language-');
      return isInline ? (
        <code className="inline-code">{children}</code>
      ) : (
        <pre className="code-block">
          <code>{children}</code>
        </pre>
      );
    },

    // Disable links to prevent navigation during incident response
    a: ({ children }) => <span className="markdown-link">{children}</span>,
  };

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        disallowedElements={['script', 'iframe', 'object', 'embed']}
        unwrapDisallowed={true}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
