import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import { zendoBehaviour } from "./shared/zendo";
import { readContent, ZendoCard } from "./shared/zendoCards";
import "./tokenZendo.css";

export type TokenCard = {
  num: number;
  color: "R" | "G" | "B";
};

export type TokenZendoPublicState = {
  kind: "token_zendo";
  family: "token_zendo";
  variant: string;
  prompt: string;
  cards: Record<string, TokenCard[]>;
  content: Record<string, unknown>;
  responseHint: string;
};

function parseTokenZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): TokenZendoPublicState {
  const variant = readString(state, "variant");
  const cards: Record<string, TokenCard[]> = {};
  if (isRecord(state.cards)) {
    for (const [cardId, tokens] of Object.entries(state.cards)) {
      if (!Array.isArray(tokens)) continue;
      const parsedTokens = tokens.flatMap((item): TokenCard[] => {
        if (!isRecord(item)) return [];
        const num = readNumber(item, "num");
        const color = readString(item, "color");
        if (
          num === undefined ||
          !Number.isInteger(num) ||
          (color !== "R" && color !== "G" && color !== "B")
        ) {
          return [];
        }
        return [{ num, color }];
      });
      if (parsedTokens.length === tokens.length) {
        cards[cardId] = parsedTokens;
      }
    }
  }
  if (!variant || Object.keys(cards).length === 0) {
    throw invalidResponse(
      "Сервер вернул некорректные карточки token_zendo.",
      state,
    );
  }

  return {
    kind: "token_zendo",
    family: "token_zendo",
    variant,
    ...base,
    cards,
    content: readContent(state),
  };
}

const TOKEN_COLOR_STYLES: Record<TokenCard["color"], { fill: string; label: string }> = {
  R: { fill: "#e5857b", label: "красная" },
  G: { fill: "#4f9d79", label: "зелёная" },
  B: { fill: "#4bbecf", label: "синяя" },
};

function TokenShelfScene({
  cards,
  content,
  canProbe,
  onProbe,
}: {
  cards: Record<string, TokenCard[]>;
  content: Record<string, unknown>;
  canProbe: boolean;
  onProbe: (cardId: string) => void;
}) {
  return (
    <figure className="token-shelf" aria-label="Полки с фишками">
      <div className="token-shelf__cards">
        {Object.entries(cards).map(([cardId, tokens]) => (
          <ZendoCard
            className="token-card"
            probeableClassName="token-card--probeable"
            cardId={cardId}
            content={content}
            canProbe={canProbe}
            onProbe={onProbe}
            key={cardId}
          >
            <ol
              className="token-card__shelf"
              aria-label={`Карточка ${cardId}`}
            >
              {tokens.map((token, index) => (
                <li
                  className={`token-chip token-chip--${token.color.toLowerCase()}`}
                  style={{ background: TOKEN_COLOR_STYLES[token.color].fill }}
                  aria-label={`Фишка ${index + 1}: ${token.num}, ${
                    TOKEN_COLOR_STYLES[token.color].label
                  }`}
                  key={index}
                >
                  {token.num}
                </li>
              ))}
            </ol>
          </ZendoCard>
        ))}
      </div>
    </figure>
  );
}

export const tokenZendo: TaskKind<TokenZendoPublicState> = {
  parse: parseTokenZendoState,
  renderScene: ({ state, canAct, onCommand }) => (
    <TokenShelfScene
      cards={state.cards}
      content={state.content}
      canProbe={canAct}
      onProbe={(cardId) => onCommand(`/test ${cardId}`)}
    />
  ),
  ...zendoBehaviour("цвет и число каждой фишки видны на полке"),
};
