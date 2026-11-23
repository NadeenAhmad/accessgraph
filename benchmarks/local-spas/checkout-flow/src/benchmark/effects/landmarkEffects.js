import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_LANDMARK_TARGETS = Object.freeze({
  navigationRoutes: "checkout.navigation.routes",
  checkoutProgress: "checkout.progress",
  productsFeaturedRegion: "checkout.products.featuredRegion",
  cartOrderTotals: "checkout.cart.orderTotals",
  addressOrderTotals: "checkout.address.orderTotals",
  footerSite: "checkout.footer.site",
});

const LANDMARK_ACCESSIBLE_NAME_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.navigationRoutesAccessibleNameOrderTotals]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.navigationRoutes]: "Order totals",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.navigationRoutesAccessibleNameCheckoutProgress]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.navigationRoutes]: "Checkout progress",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.checkoutProgressAccessibleNameOrderTotals]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.checkoutProgress]: "Order totals",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.addressOrderTotalsAccessibleNameShippingDetails]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.addressOrderTotals]: "Shipping details",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.productsFeaturedRegionAccessibleNameCheckoutRoutes]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.productsFeaturedRegion]: "Checkout routes",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.footerContentinfoAccessibleNameCheckoutRoutes]:
    Object.freeze({
      [CHECKOUT_LANDMARK_TARGETS.footerSite]: "Checkout routes",
    }),
});

const LANDMARK_ROLE_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartOrderTotalsRoleSearch]: Object.freeze({
    [CHECKOUT_LANDMARK_TARGETS.cartOrderTotals]: "search",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.footerContentinfoRoleSearch]: Object.freeze({
    [CHECKOUT_LANDMARK_TARGETS.footerSite]: "search",
  }),
});

export function resolveLandmarkEffects(activeSeeds = []) {
  const landmarkAccessibleNameOverrides = {};
  const landmarkRoleOverrides = {};

  for (const seedId of activeSeeds) {
    const accessibleNameOverrides =
      LANDMARK_ACCESSIBLE_NAME_OVERRIDES_BY_SEED[seedId];
    if (accessibleNameOverrides) {
      Object.assign(landmarkAccessibleNameOverrides, accessibleNameOverrides);
    }

    const roleOverrides = LANDMARK_ROLE_OVERRIDES_BY_SEED[seedId];
    if (roleOverrides) {
      Object.assign(landmarkRoleOverrides, roleOverrides);
    }
  }

  const resolvedEffects = {};

  if (Object.keys(landmarkAccessibleNameOverrides).length > 0) {
    resolvedEffects.landmarkAccessibleNameOverrides = Object.freeze(
      landmarkAccessibleNameOverrides,
    );
  }

  if (Object.keys(landmarkRoleOverrides).length > 0) {
    resolvedEffects.landmarkRoleOverrides = Object.freeze(landmarkRoleOverrides);
  }

  return Object.freeze(resolvedEffects);
}

export function getLandmarkAccessibleNameOverride(landmarkEffects, targetId) {
  const landmarkAccessibleNameOverrides =
    landmarkEffects?.landmarkAccessibleNameOverrides ?? {};
  return landmarkAccessibleNameOverrides[targetId] ?? undefined;
}

export function getLandmarkRoleOverride(landmarkEffects, targetId) {
  const landmarkRoleOverrides = landmarkEffects?.landmarkRoleOverrides ?? {};
  return landmarkRoleOverrides[targetId] ?? undefined;
}
