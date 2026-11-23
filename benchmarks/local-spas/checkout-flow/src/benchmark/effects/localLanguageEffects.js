import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const CHECKOUT_LOCAL_LANGUAGE_TARGETS = Object.freeze({
  productsDescription: "checkout.products.description",
  productsCartSummary: "checkout.products.cartSummary",
  cartDescription: "checkout.cart.description",
  cartShippingInformationBody: "checkout.cart.shippingInformationBody",
});

const LOCAL_LANG_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsDescriptionLangFrench]: Object.freeze({
    [CHECKOUT_LOCAL_LANGUAGE_TARGETS.productsDescription]: "fr",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsCartSummaryLangGerman]: Object.freeze({
    [CHECKOUT_LOCAL_LANGUAGE_TARGETS.productsCartSummary]: "de",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartDescriptionLangFrench]: Object.freeze({
    [CHECKOUT_LOCAL_LANGUAGE_TARGETS.cartDescription]: "fr",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsDescriptionSpanishLocalLangStaleEnglish]:
    Object.freeze({
      [CHECKOUT_LOCAL_LANGUAGE_TARGETS.productsDescription]: "en",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.shippingInformationBodySpanishLocalLangEnglish]:
    Object.freeze({
      [CHECKOUT_LOCAL_LANGUAGE_TARGETS.cartShippingInformationBody]: "en",
    }),
});

export function resolveLocalLanguageEffects(activeSeeds = []) {
  const localLangOverrides = {};

  for (const seedId of activeSeeds) {
    const overrides = LOCAL_LANG_OVERRIDES_BY_SEED[seedId];
    if (overrides) {
      Object.assign(localLangOverrides, overrides);
    }
  }

  if (Object.keys(localLangOverrides).length === 0) {
    return Object.freeze({});
  }

  return Object.freeze({
    localLangOverrides: Object.freeze(localLangOverrides),
  });
}

export function getLocalLangOverride(localLanguageEffects, targetId) {
  const localLangOverrides = localLanguageEffects?.localLangOverrides ?? {};
  return localLangOverrides[targetId] ?? undefined;
}
