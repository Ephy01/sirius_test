import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const BLANK_PAGE = "<!doctype html><html><head></head><body></body></html>";

/**
 * Shows its children in a frame of their own. Styles written for the width of
 * the window then follow the width of the frame, so a task looks here the way
 * it does on a screen of that size.
 */
export function PreviewFrame({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [body, setBody] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!body) return;
    const inner = body.ownerDocument;
    const copyStyles = () =>
      inner.head.replaceChildren(
        ...Array.from(
          document.head.querySelectorAll('style, link[rel="stylesheet"]'),
          (node) => inner.importNode(node, true),
        ),
      );
    copyStyles();
    // The page adds style sheets as its parts load.
    const observer = new MutationObserver(copyStyles);
    observer.observe(document.head, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, [body]);

  return (
    <iframe
      className="preview-frame"
      ref={frame}
      title={title}
      srcDoc={BLANK_PAGE}
      onLoad={() => {
        const inner = frame.current?.contentDocument;
        if (!inner) return;
        inner.documentElement.lang = document.documentElement.lang;
        setBody(inner.body);
      }}
    >
      {body && createPortal(children, body)}
    </iframe>
  );
}
