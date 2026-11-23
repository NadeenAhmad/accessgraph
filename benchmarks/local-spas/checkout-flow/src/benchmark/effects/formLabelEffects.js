import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_FORM_LABEL_TARGETS = Object.freeze({
  addressCity: "checkout.address.city",
  addressCountry: "checkout.address.country",
  addressDeliveryInstructions: "checkout.address.deliveryInstructions",
  addressEmail: "checkout.address.email",
  paymentCardholder: "checkout.payment.cardholder",
  paymentCardNumber: "checkout.payment.cardNumber",
  paymentSecurityCode: "checkout.payment.securityCode",
});

const FORM_LABEL_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.addressCountryLabelState]: Object.freeze({
    [CHECKOUT_FORM_LABEL_TARGETS.addressCountry]: "State",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressDeliveryInstructionsLabelStreetAddress]:
    Object.freeze({
      [CHECKOUT_FORM_LABEL_TARGETS.addressDeliveryInstructions]:
        "Street address",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.addressCityLabelState]: Object.freeze({
    [CHECKOUT_FORM_LABEL_TARGETS.addressCity]: "State",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressEmailLabelFullName]: Object.freeze({
    [CHECKOUT_FORM_LABEL_TARGETS.addressEmail]: "Full name",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardNumberLabelStreetAddress]: Object.freeze({
    [CHECKOUT_FORM_LABEL_TARGETS.paymentCardNumber]: "Street address",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardholderLabelCardNumber]: Object.freeze({
    [CHECKOUT_FORM_LABEL_TARGETS.paymentCardholder]: "Card number",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardNumberSecurityCodeLabelSwap]:
    Object.freeze({
      [CHECKOUT_FORM_LABEL_TARGETS.paymentCardNumber]: "Security code",
      [CHECKOUT_FORM_LABEL_TARGETS.paymentSecurityCode]: "Card number",
    }),
});

const FORM_ACCESSIBLE_NAME_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardholderAccessibleNameCardNumber]:
    Object.freeze({
      [CHECKOUT_FORM_LABEL_TARGETS.paymentCardholder]: "Card number",
    }),
});

export function resolveFormLabelEffects(activeSeeds = []) {
  const formLabelTextOverrides = {};
  const formAccessibleNameOverrides = {};

  for (const seedId of activeSeeds) {
    const textOverrides = FORM_LABEL_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(formLabelTextOverrides, textOverrides);
    }

    const accessibleNameOverrides =
      FORM_ACCESSIBLE_NAME_OVERRIDES_BY_SEED[seedId];
    if (accessibleNameOverrides) {
      Object.assign(formAccessibleNameOverrides, accessibleNameOverrides);
    }
  }

  const resolvedEffects = {};
  if (Object.keys(formLabelTextOverrides).length > 0) {
    resolvedEffects.formLabelTextOverrides = Object.freeze(
      formLabelTextOverrides,
    );
  }
  if (Object.keys(formAccessibleNameOverrides).length > 0) {
    resolvedEffects.formAccessibleNameOverrides = Object.freeze(
      formAccessibleNameOverrides,
    );
  }

  if (Object.keys(resolvedEffects).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze(resolvedEffects);
}

export function getFormLabelTextOverride(formLabelEffects, targetId) {
  const formLabelTextOverrides =
    formLabelEffects?.formLabelTextOverrides ?? {};
  return formLabelTextOverrides[targetId] ?? undefined;
}

export function getFormAccessibleNameOverride(formLabelEffects, targetId) {
  const formAccessibleNameOverrides =
    formLabelEffects?.formAccessibleNameOverrides ?? {};
  return formAccessibleNameOverrides[targetId] ?? undefined;
}
