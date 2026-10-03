import type { ReactNode } from "react";
import { isRecord, type UnknownRecord } from "../../api/parsing";
import "./zendoCards.css";

export function readContent(state: UnknownRecord): Record<string, unknown> {
  return isRecord(state.content) ? state.content : {};
}

function contentList(content: Record<string, unknown>, key: string): unknown[] {
  const items = content[key];
  return Array.isArray(items) ? items : [];
}

function isCard(item: unknown, cardId: string): item is Record<string, unknown> {
  return isRecord(item) && item.card_id === cardId;
}

function findCard(
  content: Record<string, unknown>,
  key: string,
  cardId: string,
): Record<string, unknown> | undefined {
  return contentList(content, key).find((item) => isCard(item, cardId));
}

export function classificationLabel(card: Record<string, unknown>): string {
  return card.classification === "positive" ? "подходит" : "не подходит";
}

function cardOutcome(
  cardId: string,
  content: Record<string, unknown>,
): "positive" | "negative" | null {
  for (const key of ["examples", "probe_observations"]) {
    const card = findCard(content, key, cardId);
    if (card && "classification" in card) {
      return card.classification === "positive" ? "positive" : "negative";
    }
  }
  return null;
}

function cardRole(cardId: string, content: Record<string, unknown>): string {
  if (cardId === "source" || cardId === "image") return cardId;
  if (findCard(content, "examples", cardId)) return "example";
  if (findCard(content, "targets", cardId)) return "target";
  // Вскрытая проба ведёт себя как открытая конструкция-пример.
  if (findCard(content, "probe_observations", cardId)) return "example";
  if (findCard(content, "probe_cards", cardId)) return "probe";
  return "plain";
}

function cardLabel(cardId: string, content: Record<string, unknown>): string {
  if (cardId === "source") return "Исходная фигура";
  if (cardId === "image") return "Образ";
  const example = findCard(content, "examples", cardId);
  if (example && "classification" in example) {
    return `${cardId} · ${classificationLabel(example)}`;
  }
  const targetIndex = contentList(content, "targets").findIndex((item) =>
    isCard(item, cardId),
  );
  if (targetIndex >= 0) return `${cardId} · цель ${targetIndex + 1}`;
  if (findCard(content, "probe_cards", cardId)) {
    const observed = findCard(content, "probe_observations", cardId);
    return observed && "classification" in observed
      ? `${cardId} · ${classificationLabel(observed)}`
      : `${cardId} · доступна проба`;
  }
  return cardId.replaceAll("_", " ");
}

export function ZendoCard({
  className,
  probeableClassName = "",
  cardId,
  content,
  canProbe = false,
  onProbe,
  children,
}: {
  className: string;
  probeableClassName?: string;
  cardId: string;
  content: Record<string, unknown>;
  canProbe?: boolean;
  onProbe?: (cardId: string) => void;
  children: ReactNode;
}) {
  const role = cardRole(cardId, content);
  const probe =
    role === "probe" && canProbe && onProbe ? () => onProbe(cardId) : undefined;
  return (
    <section
      className={probe ? `${className} ${probeableClassName}` : className}
      data-role={role}
      data-outcome={cardOutcome(cardId, content) ?? undefined}
      data-tour={
        role === "probe"
          ? "probe-card"
          : role === "target"
            ? "targets"
            : undefined
      }
      role={probe ? "button" : undefined}
      tabIndex={probe ? 0 : undefined}
      onClick={probe}
      onKeyDown={
        probe
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                probe();
              }
            }
          : undefined
      }
    >
      <header>
        {cardLabel(cardId, content)}
        {probe && <span aria-hidden="true"> · нажми, чтобы проверить</span>}
      </header>
      {children}
    </section>
  );
}
