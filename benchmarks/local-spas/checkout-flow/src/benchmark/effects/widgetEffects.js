import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_WIDGET_TARGETS = Object.freeze({
  productsCategoryTablist: "checkout.products.categoryTablist",
  productsDeskAccessoriesCategoryTab:
    "checkout.products.categoryTabs.deskAccessories",
  productsOfficeSuppliesCategoryTab:
    "checkout.products.categoryTabs.officeSupplies",
});

const WIDGET_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.deskAccessoriesTabTextFishingSupplies]:
    Object.freeze({
      [CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab]:
        "Fishing supplies",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.deskAccessoriesTabTextStationery]:
    Object.freeze({
      [CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab]: "Stationery",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.productCategoryTabLabelsSwapped]: Object.freeze({
    [CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab]:
      "Office supplies",
    [CHECKOUT_WIDGET_TARGETS.productsOfficeSuppliesCategoryTab]:
      "Desk accessories",
  }),
});

const WIDGET_ACCESSIBLE_NAME_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.deskAccessoriesTabAccessibleNameFishingSupplies]:
    Object.freeze({
      [CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab]:
        "Fishing supplies",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.productCategoryTablistAccessibleNamePaymentMethods]:
    Object.freeze({
      [CHECKOUT_WIDGET_TARGETS.productsCategoryTablist]: "Payment methods",
    }),
});

const WIDGET_CONTENT_BINDING_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.deskAccessoriesTabContentOfficeSupplies]:
    Object.freeze({
      [CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab]:
        "office-supplies",
    }),
});

export function resolveWidgetEffects(activeSeeds = []) {
  const widgetAccessibleNameOverrides = {};
  const widgetContentBindingOverrides = {};
  const widgetTextOverrides = {};

  for (const seedId of activeSeeds) {
    const accessibleNameOverrides =
      WIDGET_ACCESSIBLE_NAME_OVERRIDES_BY_SEED[seedId];
    if (accessibleNameOverrides) {
      Object.assign(widgetAccessibleNameOverrides, accessibleNameOverrides);
    }

    const textOverrides = WIDGET_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(widgetTextOverrides, textOverrides);
    }

    const contentBindingOverrides =
      WIDGET_CONTENT_BINDING_OVERRIDES_BY_SEED[seedId];
    if (contentBindingOverrides) {
      Object.assign(widgetContentBindingOverrides, contentBindingOverrides);
    }
  }

  if (
    Object.keys(widgetAccessibleNameOverrides).length === 0 &&
    Object.keys(widgetContentBindingOverrides).length === 0 &&
    Object.keys(widgetTextOverrides).length === 0
  ) {
    return Object.freeze({});
  }

  const effects = {};

  if (Object.keys(widgetAccessibleNameOverrides).length > 0) {
    effects.widgetAccessibleNameOverrides = Object.freeze(
      widgetAccessibleNameOverrides,
    );
  }

  if (Object.keys(widgetContentBindingOverrides).length > 0) {
    effects.widgetContentBindingOverrides = Object.freeze(
      widgetContentBindingOverrides,
    );
  }

  if (Object.keys(widgetTextOverrides).length > 0) {
    effects.widgetTextOverrides = Object.freeze(widgetTextOverrides);
  }

  return Object.freeze(effects);
}

export function getWidgetAccessibleNameOverride(widgetEffects, targetId) {
  const widgetAccessibleNameOverrides =
    widgetEffects?.widgetAccessibleNameOverrides ?? {};
  return widgetAccessibleNameOverrides[targetId] ?? undefined;
}

export function getWidgetTextOverride(widgetEffects, targetId) {
  const widgetTextOverrides = widgetEffects?.widgetTextOverrides ?? {};
  return widgetTextOverrides[targetId] ?? undefined;
}

export function getWidgetContentBindingOverride(widgetEffects, targetId) {
  const widgetContentBindingOverrides =
    widgetEffects?.widgetContentBindingOverrides ?? {};
  return widgetContentBindingOverrides[targetId] ?? undefined;
}
