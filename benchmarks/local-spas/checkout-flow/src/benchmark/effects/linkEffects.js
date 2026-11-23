import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_LINK_TARGETS = Object.freeze({
  navigationProducts: "checkout.navigation.products",
  navigationCart: "checkout.navigation.cart",
  supportShippingInformation: "checkout.support.shippingInformation",
  supportReturns: "checkout.support.returns",
});

const LINK_DESTINATION_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsNavLinkDestinationCart]: Object.freeze({
    [CHECKOUT_LINK_TARGETS.navigationProducts]: "/cart",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.supportShippingInformationDestinationReturns]:
    Object.freeze({
      [CHECKOUT_LINK_TARGETS.supportShippingInformation]:
        "/returns-and-refunds.html",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.supportShippingInformationDestinationResource]:
    Object.freeze({
      [CHECKOUT_LINK_TARGETS.supportShippingInformation]: "/resource.html",
    }),
});

const LINK_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartNavLinkTextWeatherForecast]: Object.freeze({
    [CHECKOUT_LINK_TARGETS.navigationCart]: "Weather forecast",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartNavLinkTextShippingAddress]: Object.freeze({
    [CHECKOUT_LINK_TARGETS.navigationCart]: "Shipping address",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.supportReturnsLinkTextShippingInformation]:
    Object.freeze({
      [CHECKOUT_LINK_TARGETS.supportReturns]: "Shipping information",
    }),
});

const LINK_ACCESSIBLE_NAME_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartNavLinkAccessibleNameWeatherForecast]:
    Object.freeze({
      [CHECKOUT_LINK_TARGETS.navigationCart]: "Weather forecast",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.cartNavLinkAccessibleNameShippingAddress]:
    Object.freeze({
      [CHECKOUT_LINK_TARGETS.navigationCart]: "Shipping address",
    }),
});

export function resolveLinkEffects(activeSeeds = []) {
  const linkAccessibleNameOverrides = {};
  const linkDestinationOverrides = {};
  const linkTextOverrides = {};

  for (const seedId of activeSeeds) {
    const accessibleNameOverrides =
      LINK_ACCESSIBLE_NAME_OVERRIDES_BY_SEED[seedId];
    if (accessibleNameOverrides) {
      Object.assign(linkAccessibleNameOverrides, accessibleNameOverrides);
    }

    const destinationOverrides = LINK_DESTINATION_OVERRIDES_BY_SEED[seedId];
    if (destinationOverrides) {
      Object.assign(linkDestinationOverrides, destinationOverrides);
    }

    const overrides = LINK_TEXT_OVERRIDES_BY_SEED[seedId];
    if (overrides) {
      Object.assign(linkTextOverrides, overrides);
    }
  }

  if (
    Object.keys(linkAccessibleNameOverrides).length === 0 &&
    Object.keys(linkDestinationOverrides).length === 0 &&
    Object.keys(linkTextOverrides).length === 0
  ) {
    return Object.freeze({});
  }

  const effects = {};

  if (Object.keys(linkAccessibleNameOverrides).length > 0) {
    effects.linkAccessibleNameOverrides = Object.freeze(
      linkAccessibleNameOverrides,
    );
  }

  if (Object.keys(linkDestinationOverrides).length > 0) {
    effects.linkDestinationOverrides = Object.freeze(linkDestinationOverrides);
  }

  if (Object.keys(linkTextOverrides).length > 0) {
    effects.linkTextOverrides = Object.freeze(linkTextOverrides);
  }

  return Object.freeze(effects);
}

export function getLinkAccessibleNameOverride(linkEffects, targetId) {
  const linkAccessibleNameOverrides =
    linkEffects?.linkAccessibleNameOverrides ?? {};
  return linkAccessibleNameOverrides[targetId] ?? undefined;
}

export function getLinkDestinationOverride(linkEffects, targetId) {
  const linkDestinationOverrides = linkEffects?.linkDestinationOverrides ?? {};
  return linkDestinationOverrides[targetId] ?? undefined;
}

export function getLinkTextOverride(linkEffects, targetId) {
  const linkTextOverrides = linkEffects?.linkTextOverrides ?? {};
  return linkTextOverrides[targetId] ?? undefined;
}
