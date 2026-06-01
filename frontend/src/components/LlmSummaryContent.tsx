import type { ReactNode } from "react";

type Props = {
  text: string;
};

export default function LlmSummaryContent({ text }: Props) {
  return <div className="llm-summary">{renderSummary(text)}</div>;
}

function renderSummary(text: string) {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let key = 0;

  const flushParagraph = () => {
    const content = paragraph.join(" ").trim();
    if (content) {
      blocks.push(
        <p key={`p-${key++}`}>{content}</p>,
      );
    }
    paragraph = [];
  };

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push(
        <ul key={`ul-${key++}`}>
          {listItems.map((item, index) => (
            <li key={`${index}-${item}`}>{item}</li>
          ))}
        </ul>,
      );
      listItems = [];
    }
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      flushList();
      flushParagraph();
      continue;
    }

    if (trimmed.startsWith("## ")) {
      flushList();
      flushParagraph();
      blocks.push(<h3 key={`h-${key++}`}>{trimmed.slice(3).trim()}</h3>);
      continue;
    }

    if (trimmed.startsWith("- ")) {
      flushParagraph();
      listItems.push(trimmed.slice(2).trim());
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }

  flushList();
  flushParagraph();

  if (blocks.length === 0) {
    return <pre>{text}</pre>;
  }

  return blocks;
}
