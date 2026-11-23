import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_CART_TARGETS = Object.freeze({
  deliveryEstimate: "checkout.cart.deliveryEstimate",
});

export const CHECKOUT_CART_RESULTS = Object.freeze({
  deliveryEstimatePanel: "delivery_estimate_panel",
  shippingInformationDialog: "shipping_information_dialog",
});

const CART_RESULT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartDeliveryEstimateOpensShippingInformation]:
    Object.freeze({
      [CHECKOUT_CART_TARGETS.deliveryEstimate]:
        CHECKOUT_CART_RESULTS.shippingInformationDialog,
    }),
});

export function resolveCartEffects(activeSeeds = []) {
  const cartResultOverrides = {};

  for (const seedId of activeSeeds) {
    const resultOverrides = CART_RESULT_OVERRIDES_BY_SEED[seedId];
    if (resultOverrides) {
      Object.assign(cartResultOverrides, resultOverrides);
    }
  }

  if (Object.keys(cartResultOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    cartResultOverrides: Object.freeze(cartResultOverrides),
  });
}

export function getCartResultOverride(cartEffects, targetId) {
  const cartResultOverrides = cartEffects?.cartResultOverrides ?? {};
  return cartResultOverrides[targetId] ?? undefined;
}
