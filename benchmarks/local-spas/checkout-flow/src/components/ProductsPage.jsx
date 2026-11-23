import {
  CHECKOUT_LINK_TARGETS,
  getLinkDestinationOverride,
  getLinkTextOverride,
} from "../benchmark/effects/linkEffects.js";
import {
  CHECKOUT_LOCAL_LANGUAGE_TARGETS,
  getLocalLangOverride,
} from "../benchmark/effects/localLanguageEffects.js";
import {
  CHECKOUT_PRODUCT_MEDIA_TARGETS,
  getProductMediaSourceOverride,
} from "../benchmark/effects/productsEffects.js";
import {
  RETURNS_SUPPORT_LABEL,
  SHIPPING_INFORMATION_SUPPORT_LABEL,
  getReturnsSupportHref,
  getSupportHref,
  getShippingInformationSupportHref,
} from "../supportLinks.js";
import { CartSummary } from "./CartSummary.jsx";
import { ProductList } from "./ProductList.jsx";

export function ProductsPage({
  cartItems,
  activeSeeds = [],
  ariaStateEffects = {},
  buttonEffects = {},
  headingEffects = {},
  landmarkEffects = {},
  linkEffects = {},
  localLanguageEffects = {},
  productEffects = {},
  widgetEffects = {},
  onAdd,
}) {
  const productsContent = productEffects.productsContentOverrides ?? {};
  const cartSummaryCopy = productsContent.cartSummary ?? {};
  const supportCopy = productsContent.support ?? {};
  const walkthroughCaptionTrackSrc =
    getProductMediaSourceOverride(
      productEffects,
      CHECKOUT_PRODUCT_MEDIA_TARGETS.walkthroughCaptionTrack,
    ) ?? "/media/brightlane-checkout-walkthrough.en.vtt";
  const cartSummaryLang = getLocalLangOverride(
    localLanguageEffects,
    CHECKOUT_LOCAL_LANGUAGE_TARGETS.productsCartSummary,
  );
  const supportReturnsLabel =
    getLinkTextOverride(linkEffects, CHECKOUT_LINK_TARGETS.supportReturns) ??
    supportCopy.returnsLabel ??
    RETURNS_SUPPORT_LABEL;
  const supportShippingLabel =
    supportCopy.shippingLabel ?? SHIPPING_INFORMATION_SUPPORT_LABEL;
  const supportShippingDestination = getLinkDestinationOverride(
    linkEffects,
    CHECKOUT_LINK_TARGETS.supportShippingInformation,
  );

  return (
    <div className="route-layout route-layout-with-aside">
      <ProductList
        cartItems={cartItems}
        activeSeeds={activeSeeds}
        ariaStateEffects={ariaStateEffects}
        buttonEffects={buttonEffects}
        headingEffects={headingEffects}
        landmarkEffects={landmarkEffects}
        localLanguageEffects={localLanguageEffects}
        productEffects={productEffects}
        widgetEffects={widgetEffects}
        onAdd={onAdd}
      />
      <aside
        className="route-aside"
        aria-label={cartSummaryCopy.ariaLabel ?? "Current cart"}
      >
        <CartSummary
          cartItems={cartItems}
          variant="compact"
          copy={cartSummaryCopy}
          localLang={cartSummaryLang}
        />
        <section className="support-links" aria-labelledby="support-links-heading">
          <h2 id="support-links-heading">{supportCopy.heading ?? "Support"}</h2>
          <p>{supportCopy.prompt ?? "Need help after checkout?"}</p>
          <div className="support-topic">
            <h3>{supportCopy.shippingHeading ?? "Shipping help"}</h3>
            <p>
              {supportCopy.shippingDescription ??
                "Learn about delivery times and available shipping options."}
            </p>
            <a
              className="support-link"
              data-testid="support-shipping"
              href={
                supportShippingDestination
                  ? getSupportHref(supportShippingDestination)
                  : getShippingInformationSupportHref()
              }
            >
              {supportShippingLabel}
            </a>
          </div>
          <a
            className="support-link"
            data-testid="support-returns"
            href={getReturnsSupportHref()}
          >
            {supportReturnsLabel}
          </a>
          <section
            className="checkout-walkthrough"
            aria-labelledby="checkout-walkthrough-heading"
            lang="en"
          >
            <h3 id="checkout-walkthrough-heading">
              How Brightlane Checkout Works
            </h3>
            <p>Watch this short guide to the checkout process.</p>
            <video
              className="checkout-walkthrough-video"
              src="/media/brightlane-checkout-walkthrough.mp4"
              aria-labelledby="checkout-walkthrough-heading"
              controls
              preload="metadata"
            >
              <track
                data-testid="checkout-walkthrough-captions"
                kind="captions"
                src={walkthroughCaptionTrackSrc}
                srcLang="en"
                label="English"
                default
              />
              Your browser does not support HTML video.
            </video>
          </section>
        </section>
      </aside>
    </div>
  );
}
