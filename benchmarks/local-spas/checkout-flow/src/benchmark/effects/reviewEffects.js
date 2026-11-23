import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_REVIEW_TABLE_TARGETS = Object.freeze({
  deskLampQuantityCell: "checkout.review.orderItems.deskLamp.quantityCell",
  deskLampLineTotalCell: "checkout.review.orderItems.deskLamp.lineTotalCell",
  notebookSetLineTotalCell: "checkout.review.orderItems.notebookSet.lineTotalCell",
});

const TABLE_HEADER_ASSOCIATION_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.reviewDeskLampLineTotalQuantityHeader]: Object.freeze({
    [CHECKOUT_REVIEW_TABLE_TARGETS.deskLampLineTotalCell]: Object.freeze([
      "review-item-header-prod-desk-lamp",
      "review-quantity-header",
    ]),
  }),
  [CHECKOUT_BENCHMARK_SEEDS.reviewDeskLampQuantityLineTotalHeader]: Object.freeze({
    [CHECKOUT_REVIEW_TABLE_TARGETS.deskLampQuantityCell]: Object.freeze([
      "review-item-header-prod-desk-lamp",
      "review-line-total-header",
    ]),
  }),
  [CHECKOUT_BENCHMARK_SEEDS.reviewDeskLampLineTotalNotebookSetRowHeader]: Object.freeze({
    [CHECKOUT_REVIEW_TABLE_TARGETS.deskLampLineTotalCell]: Object.freeze([
      "review-item-header-prod-notebook-set",
      "review-line-total-header",
    ]),
  }),
  [CHECKOUT_BENCHMARK_SEEDS.reviewLineTotalRowHeaderAssociationsSwapped]: Object.freeze({
    [CHECKOUT_REVIEW_TABLE_TARGETS.deskLampLineTotalCell]: Object.freeze([
      "review-item-header-prod-notebook-set",
      "review-line-total-header",
    ]),
    [CHECKOUT_REVIEW_TABLE_TARGETS.notebookSetLineTotalCell]: Object.freeze([
      "review-item-header-prod-desk-lamp",
      "review-line-total-header",
    ]),
  }),
});

export function resolveReviewEffects(activeSeeds = []) {
  const tableHeaderAssociationOverrides = {};

  for (const seedId of activeSeeds) {
    const associationOverrides =
      TABLE_HEADER_ASSOCIATION_OVERRIDES_BY_SEED[seedId];
    if (associationOverrides) {
      Object.assign(tableHeaderAssociationOverrides, associationOverrides);
    }
  }

  if (Object.keys(tableHeaderAssociationOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    tableHeaderAssociationOverrides: Object.freeze(
      tableHeaderAssociationOverrides,
    ),
  });
}

export function getReviewTableHeaderAssociationOverride(reviewEffects, targetId) {
  const tableHeaderAssociationOverrides =
    reviewEffects?.tableHeaderAssociationOverrides ?? {};
  return tableHeaderAssociationOverrides[targetId] ?? undefined;
}
