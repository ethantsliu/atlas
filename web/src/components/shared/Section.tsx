import type { ReactNode } from "react";

type ModalSectionProps = {
  title: string;
  children: ReactNode;
};

export function ModalSection({ title, children }: ModalSectionProps) {
  return (
    <section className="modal-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
