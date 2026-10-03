import type { ClassicMathSubKind } from "../tasks/classicMath";

export type TaskFamilyKey =
  | "geo_zendo"
  | "token_zendo"
  | "point_zendo"
  | "grid_zendo"
  | "hidden_wiring"
  | "machine_reach"
  | "fold_punch"
  | "chess_coverage"
  | "dice_chess"
  | "geo_transform"
  | "geo_probability";

export type TaskFamilyConfig = {
  key: TaskFamilyKey;
  skin: string;
  enabled: boolean;
  weight: number;
  initialDifficulty: number;
  maxDifficulty: number;
  subKinds?: string[];
};

export const FAMILY_LABELS: Record<
  TaskFamilyKey,
  { title: string; description: string }
> = {
  geo_zendo: {
    title: "Геометрический Zendo",
    description:
      "Восстановление скрытого закона по положительным и отрицательным конфигурациям.",
  },
  token_zendo: {
    title: "Zendo: фишки",
    description:
      "Скрытое правило про последовательности числовых фишек трёх цветов.",
  },
  point_zendo: {
    title: "Zendo: точки",
    description:
      "Скрытое правило про наборы точек на решётке: прямые, симметрия, окружности.",
  },
  grid_zendo: {
    title: "Zendo: узоры",
    description:
      "Скрытое правило про узоры 5×5: симметрии, связность, чётности; пробы рисуются.",
  },
  hidden_wiring: {
    title: "Скрытая проводка",
    description:
      "Панель с лампами: кнопки срабатывают только парами, проводку нужно восстановить.",
  },
  machine_reach: {
    title: "Машины и инварианты",
    description:
      "Лампы, числовые операции, перестановки и прыгуны: достигните цели или докажите недостижимость.",
  },
  fold_punch: {
    title: "Дырокол",
    description:
      "Лист складывают и пробивают дырки; отметьте, где они окажутся после разворота.",
  },
  chess_coverage: {
    title: "Шахматное покрытие",
    description:
      "Расстановка фигур с особыми ходами: покрыть цели при ограниченных ресурсах и возрастающей стоимости.",
  },
  dice_chess: {
    title: "Dice & Chess",
    description:
      "Вероятностные события на доске и решения, зависящие от кубика фигур.",
  },
  geo_transform: {
    title: "Инварианты",
    description:
      "Преобразования фигур и графов: найти то, что сохраняется, или распознать действие.",
  },
  geo_probability: {
    title: "Комбинаторика",
    description:
      "Подсчёт конфигураций и вероятностей на сетях из точек, рёбер и областей.",
  },
};

export const CLASSIC_MATH_TASKS: Record<
  ClassicMathSubKind,
  { title: string; description: string }
> = {
  share_paradox: {
    title: "Парадокс долей",
    description:
      "Развёрнуто объяснить, почему помесячные и суммарные доли могут давать разный порядок.",
  },
  bar_seating: {
    title: "Рассадка в баре",
    description:
      "Найти первое место, максимальное число посетителей и доказать оптимальность рассадки.",
  },
};

export const CONTENT_FAMILIES: TaskFamilyConfig[] = [
  {
    key: "geo_zendo",
    skin: "graph",
    enabled: true,
    weight: 14,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "token_zendo",
    skin: "tokens",
    enabled: true,
    weight: 12,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "point_zendo",
    skin: "points",
    enabled: true,
    weight: 12,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "grid_zendo",
    skin: "grid",
    enabled: true,
    weight: 12,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "hidden_wiring",
    skin: "panel",
    enabled: true,
    weight: 14,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "machine_reach",
    skin: "machine_panel",
    enabled: true,
    weight: 12,
    initialDifficulty: 1,
    maxDifficulty: 5,
    subKinds: [
      "lamps_gf2",
      "numeric_machine",
      "perm_puzzle",
      "leaper_board",
    ],
  },
  {
    key: "fold_punch",
    skin: "sheet",
    enabled: true,
    weight: 8,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "chess_coverage",
    skin: "chess",
    enabled: true,
    weight: 8,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "geo_transform",
    skin: "graph",
    enabled: true,
    weight: 2,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
  {
    key: "geo_probability",
    skin: "graph",
    enabled: true,
    weight: 2,
    initialDifficulty: 1,
    maxDifficulty: 5,
  },
];
