import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_HEADING_TARGETS = Object.freeze({
  productsPageHeading: "checkout.products.pageHeading",
  productsPageSummary: "checkout.products.pageSummary",
  cartPageHeading: "checkout.cart.pageHeading",
  cartPageSummary: "checkout.cart.pageSummary",
  cartEmptyHeading: "checkout.cart.emptyHeading",
  productsFeaturedProductsHeading:
    "checkout.products.featuredProductsHeading",
  paymentMethodHeading: "checkout.payment.methodHeading",
});

const HEADING_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsPageHeadingPaymentDetails]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.productsPageHeading]: "Payment details",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsPageHeadingFishingTechniques]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.productsPageHeading]: "Fishing techniques",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsFeaturedHeadingOrderSummary]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.productsFeaturedProductsHeading]: "Order summary",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsFeaturedHeadingWeatherForecast]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.productsFeaturedProductsHeading]: "Weather forecast",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartPageHeadingProducts]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.cartPageHeading]: "Products",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartPageHeadingShippingAddress]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.cartPageHeading]: "Shipping address",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartEmptyHeadingCartItems]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.cartEmptyHeading]: "Cart items",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentMethodHeadingCardNumber]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.paymentMethodHeading]: "Card number",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartHeadingBlockProducts]: Object.freeze({
    [CHECKOUT_HEADING_TARGETS.cartPageHeading]: "Products",
    [CHECKOUT_HEADING_TARGETS.cartPageSummary]:
      "Browse featured products and update the cart summary.",
  }),
});

export function resolveHeadingEffects(activeSeeds = []) {
  const headingTextOverrides = {};

  for (const seedId of activeSeeds) {
    const textOverrides = HEADING_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(headingTextOverrides, textOverrides);
    }
  }

  if (Object.keys(headingTextOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    headingTextOverrides: Object.freeze(headingTextOverrides),
  });
}

export function getHeadingTextOverride(headingEffects, targetId) {
  const headingTextOverrides = headingEffects?.headingTextOverrides ?? {};
  return headingTextOverrides[targetId] ?? undefined;
}
