import type { ReactNode } from "react";
import OutputSourceBadge, { type OutputSourceKind } from "./OutputSourceBadge";

type Props = {
  title: string;
  hint?: string;
  source?: OutputSourceKind;
  actions?: ReactNode;
  as?: "h2" | "h3";
};

export default function SectionHeading({ title, hint, source, actions, as = "h2" }: Props) {
  const HeadingTag = as;

  return (
    <div className="section-title section-heading">
      <div className="section-heading-text">
        <div className="section-heading-row">
          <HeadingTag>{title}</HeadingTag>
          {source && <OutputSourceBadge source={source} />}
        </div>
        {hint && <p className="hint">{hint}</p>}
      </div>
      {actions}
    </div>
  );
}
