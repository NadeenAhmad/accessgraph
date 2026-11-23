import {
  CHECKOUT_HEADING_TARGETS,
  getHeadingTextOverride,
} from "../benchmark/effects/headingEffects.js";

export function EmptyCart({ copy = {}, headingEffects = {}, onContinueShopping }) {
  const heading =
    getHeadingTextOverride(
      headingEffects,
      CHECKOUT_HEADING_TARGETS.cartEmptyHeading,
    ) ?? copy.heading ?? "Your cart is empty";

  return (
    <section className="empty-cart" aria-labelledby="empty-cart-heading">
      <div>
        <h2 id="empty-cart-heading">{heading}</h2>
        <p>
          {copy.description ??
            "Add a product before continuing through checkout."}
        </p>
        <button
          type="button"
          className="primary-action"
          data-testid="empty-cart-continue"
          onClick={onContinueShopping}
        >
          {copy.continue ?? "Browse products"}
        </button>
      </div>
    </section>
  );
}
