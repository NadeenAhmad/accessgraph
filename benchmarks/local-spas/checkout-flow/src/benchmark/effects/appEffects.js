import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";

export const DEFAULT_ROOT_LANG = "en";

const ROOT_LANG_OVERRIDES_BY_ROUTE_AND_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsPageRootLangDanish]: Object.freeze({
    products: "da",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.cartPageRootLangDanish]: Object.freeze({
    cart: "da",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsPageSpanishContentEnglishRoot]:
    Object.freeze({
      products: "en",
    }),
  [CHECKOUT_BENCHMARK_SEEDS.cartPageSpanishContentEnglishRoot]: Object.freeze({
    cart: "en",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productsLanguageSwitchSpanishRootStale]: Object.freeze({
    products: "en",
  }),
});

const ROOT_LANG_CARRYOVER_TRANSITIONS_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.productsRootLanguageRetainedAfterEnglishSelection]:
    Object.freeze([
      Object.freeze({
        fromLanguage: "es",
        toLanguage: "en",
      }),
    ]),
});

export function resolveAppEffects(activeSeeds = []) {
  const rootLangByRoute = {};
  const rootLangCarryoverTransitions = [];

  for (const seedId of activeSeeds) {
    const overrides = ROOT_LANG_OVERRIDES_BY_ROUTE_AND_SEED[seedId];
    if (overrides) {
      Object.assign(rootLangByRoute, overrides);
    }

    const carryoverTransitions = ROOT_LANG_CARRYOVER_TRANSITIONS_BY_SEED[seedId];
    if (carryoverTransitions) {
      rootLangCarryoverTransitions.push(...carryoverTransitions);
    }
  }

  const resolvedEffects = {
    rootLang: DEFAULT_ROOT_LANG,
    rootLangByRoute: Object.freeze(rootLangByRoute),
  };
  if (rootLangCarryoverTransitions.length > 0) {
    resolvedEffects.rootLangCarryoverTransitions = Object.freeze(
      rootLangCarryoverTransitions,
    );
  }

  return Object.freeze(resolvedEffects);
}

export function resolveRootLangForRoute(
  appEffects,
  routeId,
  fallbackRootLang = DEFAULT_ROOT_LANG,
) {
  const rootLangByRoute = appEffects.rootLangByRoute ?? {};
  if (rootLangByRoute[routeId]) {
    return rootLangByRoute[routeId];
  }

  if (appEffects.rootLang && appEffects.rootLang !== DEFAULT_ROOT_LANG) {
    return appEffects.rootLang;
  }

  return fallbackRootLang ?? appEffects.rootLang ?? DEFAULT_ROOT_LANG;
}

export function shouldCarryRootLangAcrossLanguageTransition(
  appEffects,
  fromLanguage,
  toLanguage,
) {
  const transitions = appEffects?.rootLangCarryoverTransitions ?? [];
  return transitions.some(
    (transition) =>
      transition.fromLanguage === fromLanguage &&
      transition.toLanguage === toLanguage,
  );
}
