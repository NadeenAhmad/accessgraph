import { CHECKOUT_BENCHMARK_SEEDS } from "../seeds.js";
import { hasActiveSeed } from "../profiles.js";

export const CHECKOUT_PRODUCT_MEDIA_TARGETS = Object.freeze({
  walkthroughCaptionTrack: "checkout.products.walkthrough.captionTrack",
});

const MEDIA_SOURCE_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.walkthroughCaptionsCartDestination]: Object.freeze({
    [CHECKOUT_PRODUCT_MEDIA_TARGETS.walkthroughCaptionTrack]:
      "/media/brightlane-checkout-walkthrough.co-sem-139.en.vtt",
  }),
});

const PRODUCT_IMAGE_ALT_OVERRIDES_BY_SEED = Object.freeze({
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltDog]: Object.freeze({
    "prod-desk-lamp": "A dog",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltFloorLamp]: Object.freeze({
    "prod-desk-lamp": "Floor lamp",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltUserProfileAvatar]: Object.freeze({
    "prod-desk-lamp": "User profile avatar",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltPurpleDeskLamp]: Object.freeze({
    "prod-desk-lamp": "Purple desk lamp",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltTwoDeskLamps]: Object.freeze({
    "prod-desk-lamp": "Two desk lamps",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.deskLampImageAltGenericImage]: Object.freeze({
    "prod-desk-lamp": "Image",
  }),
  [CHECKOUT_BENCHMARK_SEEDS.productImageAltsSwapped]: Object.freeze({
    "prod-desk-lamp": "Three notebooks with blue, teal, and coral covers",
    "prod-notebook-set": "Desk lamp with adjustable brass shade",
  }),
});

export function resolveProductsEffects(activeSeeds = []) {
  const effects = {};
  const imageAltOverrides = {};
  const mediaSourceOverrides = {};

  if (
    hasActiveSeed(
      activeSeeds,
      CHECKOUT_BENCHMARK_SEEDS.deskLampAddButtonNameRemove,
    )
  ) {
    effects.deskLampAddButtonAccessibleName = "Remove Desk lamp";
  }

  for (const seedId of activeSeeds) {
    const overrides = PRODUCT_IMAGE_ALT_OVERRIDES_BY_SEED[seedId];
    if (overrides) {
      Object.assign(imageAltOverrides, overrides);
    }

    const mediaOverrides = MEDIA_SOURCE_OVERRIDES_BY_SEED[seedId];
    if (mediaOverrides) {
      Object.assign(mediaSourceOverrides, mediaOverrides);
    }
  }

  if (Object.keys(imageAltOverrides).length > 0) {
    effects.imageAltOverrides = Object.freeze(imageAltOverrides);
  }

  if (Object.keys(mediaSourceOverrides).length > 0) {
    effects.mediaSourceOverrides = Object.freeze(mediaSourceOverrides);
  }

  return Object.freeze(effects);
}

export function getProductMediaSourceOverride(productEffects, targetId) {
  const mediaSourceOverrides = productEffects?.mediaSourceOverrides ?? {};
  return mediaSourceOverrides[targetId] ?? undefined;
}
