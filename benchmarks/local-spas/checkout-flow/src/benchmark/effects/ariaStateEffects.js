import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_ARIA_STATE_TARGETS = Object.freeze({
  navigationProducts: "checkout.navigation.products",
  navigationCart: "checkout.navigation.cart",
  productsDeskAccessoriesCategoryTab:
    "checkout.products.categoryTabs.deskAccessories",
  productsOfficeSuppliesCategoryTab:
    "checkout.products.categoryTabs.officeSupplies",
  productsLanguageEnglish: "checkout.products.language.en",
  productsLanguageSpanish: "checkout.products.language.es",
  cartDeliveryEstimate: "checkout.cart.deliveryEstimate",
  cartGiftReceipt: "checkout.cart.giftReceipt",
  cartSaveCart: "checkout.cart.saveCart",
  checkoutProgressCart: "checkout.progress.cart",
  checkoutProgressAddress: "checkout.progress.address",
});

const ARIA_CURRENT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsNavCurrentOnCart]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.navigationProducts]: Object.freeze({
      cart: "page",
    }),
    [CHECKOUT_ARIA_STATE_TARGETS.navigationCart]: Object.freeze({
      cart: null,
    }),
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartProgressCurrentAddress]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressCart]: Object.freeze({
      cart: null,
    }),
    [CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressAddress]: Object.freeze({
      cart: "step",
    }),
  }),
  [CHECKOUT_BENCHMARK_SEEDS.checkoutProgressCartStaleOnAddress]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressCart]: Object.freeze({
      address: "step",
    }),
    [CHECKOUT_ARIA_STATE_TARGETS.checkoutProgressAddress]: Object.freeze({
      address: null,
    }),
  }),
});

const ARIA_SELECTED_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsDeskAccessoriesTabSelectedFalse]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.productsDeskAccessoriesCategoryTab]: false,
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsTabSelectionStaleAfterOffice]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.productsDeskAccessoriesCategoryTab]: true,
    [CHECKOUT_ARIA_STATE_TARGETS.productsOfficeSuppliesCategoryTab]: false,
  }),
});

const ARIA_EXPANDED_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartDeliveryEstimateExpandedDeclaredCollapsed]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.cartDeliveryEstimate]: false,
    }),
  [CHECKOUT_BENCHMARK_SEEDS.cartDeliveryEstimateCollapsedDeclaredExpanded]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.cartDeliveryEstimate]: true,
    }),
});

const ARIA_CHECKED_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartGiftReceiptEnabledDeclaredUnchecked]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.cartGiftReceipt]: false,
    }),
  [CHECKOUT_BENCHMARK_SEEDS.cartGiftReceiptDisabledDeclaredChecked]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.cartGiftReceipt]: true,
    }),
});

const ARIA_PRESSED_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsLanguageSpanishDeclaredPressed]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.productsLanguageEnglish]: false,
      [CHECKOUT_ARIA_STATE_TARGETS.productsLanguageSpanish]: true,
    }),
  [CHECKOUT_BENCHMARK_SEEDS.productsLanguageSelectionStaleAfterSpanish]:
    Object.freeze({
      [CHECKOUT_ARIA_STATE_TARGETS.productsLanguageEnglish]: true,
      [CHECKOUT_ARIA_STATE_TARGETS.productsLanguageSpanish]: false,
    }),
  [CHECKOUT_BENCHMARK_SEEDS.cartSaveCartActiveDeclaredUnpressed]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.cartSaveCart]: false,
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartSaveCartInactiveDeclaredPressed]: Object.freeze({
    [CHECKOUT_ARIA_STATE_TARGETS.cartSaveCart]: true,
  }),
});

export function resolveAriaStateEffects(activeSeeds = []) {
  const ariaCurrentOverrides = {};
  const ariaSelectedOverrides = {};
  const ariaExpandedOverrides = {};
  const ariaCheckedOverrides = {};
  const ariaPressedOverrides = {};

  for (const seedId of activeSeeds) {
    const currentOverrides = ARIA_CURRENT_OVERRIDES_BY_SEED[seedId];
    if (currentOverrides) {
      for (const [targetId, routeOverrides] of Object.entries(currentOverrides)) {
        ariaCurrentOverrides[targetId] = Object.freeze({
          ...(ariaCurrentOverrides[targetId] ?? {}),
          ...routeOverrides,
        });
      }
    }

    const selectedOverrides = ARIA_SELECTED_OVERRIDES_BY_SEED[seedId];
    if (selectedOverrides) {
      for (const [targetId, declaredSelected] of Object.entries(
        selectedOverrides,
      )) {
        ariaSelectedOverrides[targetId] = declaredSelected;
      }
    }

    const expandedOverrides = ARIA_EXPANDED_OVERRIDES_BY_SEED[seedId];
    if (expandedOverrides) {
      for (const [targetId, declaredExpanded] of Object.entries(
        expandedOverrides,
      )) {
        ariaExpandedOverrides[targetId] = declaredExpanded;
      }
    }

    const checkedOverrides = ARIA_CHECKED_OVERRIDES_BY_SEED[seedId];
    if (checkedOverrides) {
      for (const [targetId, declaredChecked] of Object.entries(
        checkedOverrides,
      )) {
        ariaCheckedOverrides[targetId] = declaredChecked;
      }
    }

    const pressedOverrides = ARIA_PRESSED_OVERRIDES_BY_SEED[seedId];
    if (pressedOverrides) {
      for (const [targetId, declaredPressed] of Object.entries(
        pressedOverrides,
      )) {
        ariaPressedOverrides[targetId] = declaredPressed;
      }
    }
  }

  const resolvedEffects = {};

  if (Object.keys(ariaCurrentOverrides).length > 0) {
    resolvedEffects.ariaCurrentOverrides = Object.freeze(ariaCurrentOverrides);
  }

  if (Object.keys(ariaSelectedOverrides).length > 0) {
    resolvedEffects.ariaSelectedOverrides = Object.freeze(ariaSelectedOverrides);
  }

  if (Object.keys(ariaExpandedOverrides).length > 0) {
    resolvedEffects.ariaExpandedOverrides = Object.freeze(ariaExpandedOverrides);
  }

  if (Object.keys(ariaCheckedOverrides).length > 0) {
    resolvedEffects.ariaCheckedOverrides = Object.freeze(ariaCheckedOverrides);
  }

  if (Object.keys(ariaPressedOverrides).length > 0) {
    resolvedEffects.ariaPressedOverrides = Object.freeze(ariaPressedOverrides);
  }

  return Object.freeze(resolvedEffects);
}

export function getAriaCurrentOverride(ariaStateEffects, targetId, routeId) {
  const routeOverrides =
    ariaStateEffects?.ariaCurrentOverrides?.[targetId] ?? {};

  if (Object.hasOwn(routeOverrides, routeId)) {
    return routeOverrides[routeId];
  }

  return undefined;
}

export function getAriaSelectedOverride(ariaStateEffects, targetId) {
  const selectedOverrides = ariaStateEffects?.ariaSelectedOverrides ?? {};

  if (Object.hasOwn(selectedOverrides, targetId)) {
    return selectedOverrides[targetId];
  }

  return undefined;
}

export function getAriaExpandedOverride(ariaStateEffects, targetId) {
  const expandedOverrides = ariaStateEffects?.ariaExpandedOverrides ?? {};

  if (Object.hasOwn(expandedOverrides, targetId)) {
    return expandedOverrides[targetId];
  }

  return undefined;
}

export function getAriaCheckedOverride(ariaStateEffects, targetId) {
  const checkedOverrides = ariaStateEffects?.ariaCheckedOverrides ?? {};

  if (Object.hasOwn(checkedOverrides, targetId)) {
    return checkedOverrides[targetId];
  }

  return undefined;
}

export function getAriaPressedOverride(ariaStateEffects, targetId) {
  const pressedOverrides = ariaStateEffects?.ariaPressedOverrides ?? {};

  if (Object.hasOwn(pressedOverrides, targetId)) {
    return pressedOverrides[targetId];
  }

  return undefined;
}
