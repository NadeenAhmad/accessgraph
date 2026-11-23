import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_PAGE_TITLE_TARGETS = Object.freeze({
  products: "checkout.page.products",
  cart: "checkout.page.cart",
  address: "checkout.page.address",
  payment: "checkout.page.payment",
  review: "checkout.page.review",
});

const PAGE_TITLE_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsPageTitlePayment]: Object.freeze({
    [CHECKOUT_PAGE_TITLE_TARGETS.products]: "Payment",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsPageTitleWeatherForecast]: Object.freeze({
    [CHECKOUT_PAGE_TITLE_TARGETS.products]: "Weather Forecast",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentPageTitleShippingAddress]: Object.freeze({
    [CHECKOUT_PAGE_TITLE_TARGETS.payment]: "Shipping address",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressPageTitleBillingAddress]: Object.freeze({
    [CHECKOUT_PAGE_TITLE_TARGETS.address]: "Billing address",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentPageTitleReview]: Object.freeze({
    [CHECKOUT_PAGE_TITLE_TARGETS.payment]: "Review",
  }),
});

const PAGE_TITLE_CARRYOVER_TRANSITIONS_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartPageTitleRetainedOnAddress]: Object.freeze([
    Object.freeze({
      fromTarget: CHECKOUT_PAGE_TITLE_TARGETS.cart,
      toTarget: CHECKOUT_PAGE_TITLE_TARGETS.address,
    }),
  ]),
});

export function resolvePageTitleEffects(activeSeeds = []) {
  const pageTitleTextOverrides = {};
  const pageTitleCarryoverTransitions = [];

  for (const seedId of activeSeeds) {
    const textOverrides = PAGE_TITLE_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(pageTitleTextOverrides, textOverrides);
    }

    const carryoverTransitions = PAGE_TITLE_CARRYOVER_TRANSITIONS_BY_SEED[seedId];
    if (carryoverTransitions) {
      pageTitleCarryoverTransitions.push(...carryoverTransitions);
    }
  }

  const resolvedEffects = {};
  if (Object.keys(pageTitleTextOverrides).length > 0) {
    resolvedEffects.pageTitleTextOverrides = Object.freeze(pageTitleTextOverrides);
  }
  if (pageTitleCarryoverTransitions.length > 0) {
    resolvedEffects.pageTitleCarryoverTransitions = Object.freeze(
      pageTitleCarryoverTransitions,
    );
  }

  if (Object.keys(resolvedEffects).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze(resolvedEffects);
}

export function getPageTitleTextOverride(pageTitleEffects, routeId) {
  const targetId = CHECKOUT_PAGE_TITLE_TARGETS[routeId];
  if (!targetId) {
    return undefined;
  }

  const pageTitleTextOverrides = pageTitleEffects?.pageTitleTextOverrides ?? {};
  return pageTitleTextOverrides[targetId] ?? undefined;
}

export function shouldCarryPageTitleAcrossTransition(
  pageTitleEffects,
  fromRouteId,
  toRouteId,
) {
  const fromTarget = CHECKOUT_PAGE_TITLE_TARGETS[fromRouteId];
  const toTarget = CHECKOUT_PAGE_TITLE_TARGETS[toRouteId];
  if (!fromTarget || !toTarget) {
    return false;
  }

  const transitions = pageTitleEffects?.pageTitleCarryoverTransitions ?? [];
  return transitions.some(
    (transition) =>
      transition.fromTarget === fromTarget && transition.toTarget === toTarget,
  );
}
