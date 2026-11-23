import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_ERROR_MESSAGE_TARGETS = Object.freeze({
  addressFullName: "checkout.address.fullName",
  addressEmail: "checkout.address.email",
  addressPostalCode: "checkout.address.postalCode",
  paymentCardNumber: "checkout.payment.cardNumber",
  paymentSecurityCode: "checkout.payment.securityCode",
  paymentExpiry: "checkout.payment.expiry",
});

const ERROR_TEXT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.addressEmailErrorZipCodeRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.addressEmail]: "ZIP code is required.",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressPostalCodeErrorEmailRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.addressPostalCode]: "Email is required.",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressFullNameErrorStreetAddressRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.addressFullName]: "Street address is required.",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentCardNumberErrorSecurityCodeRequired]:
    Object.freeze({
      [CHECKOUT_ERROR_MESSAGE_TARGETS.paymentCardNumber]:
        "Security code is required.",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentSecurityCodeErrorCardNumberRequired]:
    Object.freeze({
      [CHECKOUT_ERROR_MESSAGE_TARGETS.paymentSecurityCode]:
        "Card number is required.",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentExpiryErrorCardholderNameRequired]:
    Object.freeze({
      [CHECKOUT_ERROR_MESSAGE_TARGETS.paymentExpiry]:
        "Cardholder name is required.",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.addressPostalCodeFormatErrorRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.addressPostalCode]: "ZIP code is required.",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.addressEmailFormatErrorStaleRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.addressEmail]: "Email is required.",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.paymentSecurityCodeFormatErrorRequired]: Object.freeze({
    [CHECKOUT_ERROR_MESSAGE_TARGETS.paymentSecurityCode]:
      "Security code is required.",
  }),
});

export function resolveErrorMessageEffects(activeSeeds = []) {
  const errorTextOverrides = {};

  for (const seedId of activeSeeds) {
    const textOverrides = ERROR_TEXT_OVERRIDES_BY_SEED[seedId];
    if (textOverrides) {
      Object.assign(errorTextOverrides, textOverrides);
    }
  }

  if (Object.keys(errorTextOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    errorTextOverrides: Object.freeze(errorTextOverrides),
  });
}

export function getErrorMessageTextOverride(errorMessageEffects, targetId) {
  const errorTextOverrides = errorMessageEffects?.errorTextOverrides ?? {};
  return errorTextOverrides[targetId] ?? undefined;
}
