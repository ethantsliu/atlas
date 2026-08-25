import type { ReactNode } from "react";

type PageHeadProps = {
  icon: ReactNode;
  kicker: string;
  title: string;
  copy: string;
};

export function PageHead({ icon, kicker, title, copy }: PageHeadProps) {
  return (
    <header className="page-head">
      <div className="page-icon">{icon}</div>
      <div>
        <span>{kicker}</span>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
    </header>
  );
}
