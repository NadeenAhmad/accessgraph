import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_BUTTON_TARGETS = Object.freeze({
  addressContinueToPayment: "checkout.address.continueToPayment",
  cartDeskLampIncrement: "checkout.cart.deskLamp.increment",
  productsNotebookSetAddButton: "checkout.products.notebookSet.addButton",
});

export const CHECKOUT_BUTTON_DESTINATIONS = Object.freeze({
  cart: "/cart",
});

export const CHECKOUT_BUTTON_ACTION_TARGETS = Object.freeze({
  notebookSet: "prod-notebook-set",
});

const BUTTON_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.notebookSetAddButtonTextWeatherForecast]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton]:
        "Weather forecast",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.notebookSetAddButtonTextRemove]: Object.freeze({
    [CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton]:
      "Remove Notebook set",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.notebookSetAddButtonTextAddCableOrganizer]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton]:
        "Add Cable organizer",
    }),
});

const BUTTON_ACCESSIBLE_NAME_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.notebookSetAddButtonAccessibleNameWeatherForecast]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton]:
        "Weather forecast",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.notebookSetAddButtonAccessibleNameRemove]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton]:
        "Remove Notebook set",
    }),
});

const BUTTON_DESTINATION_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.addressContinueToPaymentDestinationCart]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.addressContinueToPayment]:
        CHECKOUT_BUTTON_DESTINATIONS.cart,
    }),
});

const BUTTON_ACTION_TARGET_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.cartDeskLampIncrementTargetsNotebookSet]:
    Object.freeze({
      [CHECKOUT_BUTTON_TARGETS.cartDeskLampIncrement]:
        CHECKOUT_BUTTON_ACTION_TARGETS.notebookSet,
    }),
});

export function resolveButtonEffects(activeSeeds = []) {
  const buttonTextOverrides = {};
  const buttonAccessibleNameOverrides = {};
  const buttonActionTargetOverrides = {};
  const buttonDestinationOverrides = {};

  for (const seedId of activeSeeds) {
    const textOverrides = BUTTON_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(buttonTextOverrides, textOverrides);
    }

    const accessibleNameOverrides =
      BUTTON_ACCESSIBLE_NAME_OVERRIDES_BY_SEED[seedId];
    if (accessibleNameOverrides) {
      Object.assign(buttonAccessibleNameOverrides, accessibleNameOverrides);
    }

    const actionTargetOverrides = BUTTON_ACTION_TARGET_OVERRIDES_BY_SEED[seedId];
    if (actionTargetOverrides) {
      Object.assign(buttonActionTargetOverrides, actionTargetOverrides);
    }

    const destinationOverrides = BUTTON_DESTINATION_OVERRIDES_BY_SEED[seedId];
    if (destinationOverrides) {
      Object.assign(buttonDestinationOverrides, destinationOverrides);
    }
  }

  if (
    Object.keys(buttonTextOverrides).length === 0 &&
    Object.keys(buttonAccessibleNameOverrides).length === 0 &&
    Object.keys(buttonActionTargetOverrides).length === 0 &&
    Object.keys(buttonDestinationOverrides).length === 0
  ) {
    return Object.freeze({});
  }

  const effects = {};

  if (Object.keys(buttonTextOverrides).length > 0) {
    effects.buttonTextOverrides = Object.freeze(buttonTextOverrides);
  }

  if (Object.keys(buttonAccessibleNameOverrides).length > 0) {
    effects.buttonAccessibleNameOverrides = Object.freeze(
      buttonAccessibleNameOverrides,
    );
  }

  if (Object.keys(buttonActionTargetOverrides).length > 0) {
    effects.buttonActionTargetOverrides = Object.freeze(
      buttonActionTargetOverrides,
    );
  }

  if (Object.keys(buttonDestinationOverrides).length > 0) {
    effects.buttonDestinationOverrides = Object.freeze(
      buttonDestinationOverrides,
    );
  }

  return Object.freeze(effects);
}

export function getButtonTextOverride(buttonEffects, targetId) {
  const buttonTextOverrides = buttonEffects?.buttonTextOverrides ?? {};
  return buttonTextOverrides[targetId] ?? undefined;
}

export function getButtonAccessibleNameOverride(buttonEffects, targetId) {
  const buttonAccessibleNameOverrides =
    buttonEffects?.buttonAccessibleNameOverrides ?? {};
  return buttonAccessibleNameOverrides[targetId] ?? undefined;
}

export function getButtonActionTargetOverride(buttonEffects, targetId) {
  const buttonActionTargetOverrides =
    buttonEffects?.buttonActionTargetOverrides ?? {};
  return buttonActionTargetOverrides[targetId] ?? undefined;
}

export function getButtonDestinationOverride(buttonEffects, targetId) {
  const buttonDestinationOverrides =
    buttonEffects?.buttonDestinationOverrides ?? {};
  return buttonDestinationOverrides[targetId] ?? undefined;
}
