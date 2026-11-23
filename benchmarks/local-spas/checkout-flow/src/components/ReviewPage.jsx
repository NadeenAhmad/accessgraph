import { CartSummary } from "./CartSummary.jsx";
import { CheckoutProgress } from "./CheckoutProgress.jsx";
import {
  CHECKOUT_REVIEW_TABLE_TARGETS,
  getReviewTableHeaderAssociationOverride,
  resolveReviewEffects,
} from "../benchmark/effects/reviewEffects.js";
import { formatCurrency, getCartLineItems } from "../state/cartStore.js";

const REVIEW_ORDER_CELL_TARGETS_BY_PRODUCT_ID = Object.freeze({
  "prod-desk-lamp": Object.freeze({
    quantity: CHECKOUT_REVIEW_TABLE_TARGETS.deskLampQuantityCell,
    lineTotal: CHECKOUT_REVIEW_TABLE_TARGETS.deskLampLineTotalCell,
  }),
  "prod-notebook-set": Object.freeze({
    lineTotal: CHECKOUT_REVIEW_TABLE_TARGETS.notebookSetLineTotalCell,
  }),
});

export function ReviewPage({
  cartItems,
  activeSeeds = [],
  submittedAddress,
  submittedPayment,
  onReturnToAddress,
  onReturnToPayment,
}) {
  const lineItems = getCartLineItems(cartItems);
  const reviewEffects = resolveReviewEffects(activeSeeds);

  if (!submittedAddress) {
    return (
      <div className="checkout-step-route">
        <CheckoutProgress currentStep="review" />
        <div className="route-layout route-layout-with-aside">
          <section className="review-section" aria-labelledby="review-address-missing-heading">
            <div className="section-heading">
              <h2 id="review-address-missing-heading">Shipping address needed</h2>
              <p>Enter a shipping address before reviewing your order.</p>
            </div>
            <button
              type="button"
              className="primary-action"
              data-testid="review-return-to-address"
              onClick={onReturnToAddress}
            >
              Enter shipping address
            </button>
          </section>
          <aside className="route-aside" aria-label="Order totals">
            <CartSummary cartItems={cartItems} />
          </aside>
        </div>
      </div>
    );
  }

  if (!submittedPayment) {
    return (
      <div className="checkout-step-route">
        <CheckoutProgress currentStep="review" />
        <div className="route-layout route-layout-with-aside">
          <section className="review-section" aria-labelledby="review-payment-missing-heading">
            <div className="section-heading">
              <h2 id="review-payment-missing-heading">Payment method needed</h2>
              <p>Add payment details before reviewing your order.</p>
            </div>
            <button
              type="button"
              className="primary-action"
              data-testid="review-return-to-payment"
              onClick={onReturnToPayment}
            >
              Enter payment method
            </button>
          </section>
          <aside className="route-aside" aria-label="Order totals">
            <CartSummary cartItems={cartItems} />
          </aside>
        </div>
      </div>
    );
  }

  const ReviewContent = reviewEffects.reviewContentElement ?? "div";
  const deliveryInstructions = submittedAddress.deliveryInstructions?.trim();

  return (
    <ReviewContent
      className="checkout-step-route"
      aria-label={reviewEffects.reviewContentLabel}
      data-testid="checkout-review-content"
    >
      <CheckoutProgress currentStep="review" />

      <div className="route-layout route-layout-with-aside">
        <div className="review-main">
          <section
            className="review-section"
            aria-labelledby="review-shipping-heading"
            data-testid="review-shipping-summary"
          >
            <div className="section-heading">
              <h2 id="review-shipping-heading">Shipping address</h2>
              <p>Review the submitted shipping details.</p>
            </div>

            <address className="summary-lines">
              <span data-testid="review-shipping-full-name">
                {submittedAddress.fullName}
              </span>
              <span data-testid="review-shipping-email">{submittedAddress.email}</span>
              <span data-testid="review-shipping-street">
                {submittedAddress.streetAddress}
              </span>
              <span>
                <span data-testid="review-shipping-city">{submittedAddress.city}</span>
                {", "}
                <span data-testid="review-shipping-state">{submittedAddress.state}</span>
                {" "}
                <span data-testid="review-shipping-postal-code">
                  {submittedAddress.postalCode}
                </span>
              </span>
              <span data-testid="review-shipping-country">
                {submittedAddress.country}
              </span>
            </address>
            {deliveryInstructions ? (
              <dl className="summary-dl review-delivery-instructions">
                <div>
                  <dt>Delivery instructions</dt>
                  <dd data-testid="review-shipping-delivery-instructions">
                    {deliveryInstructions}
                  </dd>
                </div>
              </dl>
            ) : null}
          </section>

          <section
            className="review-section"
            aria-labelledby="review-payment-heading"
            data-testid="review-payment-summary"
          >
            <div className="section-heading">
              <h2 id="review-payment-heading">Payment method</h2>
              <p>Card information is shown as a short review summary.</p>
            </div>
            <dl className="summary-dl">
              <div>
                <dt>Cardholder</dt>
                <dd data-testid="review-payment-cardholder">
                  {submittedPayment.cardholder}
                </dd>
              </div>
              <div>
                <dt>Card</dt>
                <dd data-testid="review-payment-card">
                  Card ending in {submittedPayment.cardLastFour}
                </dd>
              </div>
              <div>
                <dt>Expiry</dt>
                <dd data-testid="review-payment-expiry">{submittedPayment.expiry}</dd>
              </div>
            </dl>
          </section>

          <section
            className="review-section"
            aria-labelledby="review-order-heading"
            data-testid="review-order-summary"
          >
            <div className="section-heading">
              <h2 id="review-order-heading">Order items</h2>
              <p>Confirm the products included in this checkout.</p>
            </div>

            <table className="review-order-table" data-testid="review-order-table">
              <caption>Product quantities and totals</caption>
              <thead>
                <tr>
                  <th id="review-item-header" scope="col">
                    Item
                  </th>
                  <th id="review-quantity-header" scope="col">
                    Quantity
                  </th>
                  <th id="review-line-total-header" scope="col">
                    Line total
                  </th>
                </tr>
              </thead>
              <tbody>
                {lineItems.map((item) => (
                  <ReviewOrderRow
                    item={item}
                    key={item.id}
                    reviewEffects={reviewEffects}
                  />
                ))}
              </tbody>
            </table>
          </section>
        </div>

        <aside className="route-aside" aria-label="Order totals">
          <CartSummary cartItems={cartItems} />
          <button
            type="button"
            className="primary-action checkout-action"
            data-testid="review-place-order"
          >
            Place order
          </button>
        </aside>
      </div>
    </ReviewContent>
  );
}

function ReviewOrderRow({ item, reviewEffects }) {
  const rowHeaderId = `review-item-header-${item.id}`;
  const cellTargets = REVIEW_ORDER_CELL_TARGETS_BY_PRODUCT_ID[item.id] ?? {};
  const quantityHeaders = getEffectiveReviewCellHeaders(
    reviewEffects,
    cellTargets.quantity,
    [rowHeaderId, "review-quantity-header"],
  );
  const lineTotalHeaders = getEffectiveReviewCellHeaders(
    reviewEffects,
    cellTargets.lineTotal,
    [rowHeaderId, "review-line-total-header"],
  );

  return (
    <tr data-testid={`review-order-item-${item.id}`}>
      <th
        className="review-order-item-header"
        id={rowHeaderId}
        scope="row"
      >
        <span className="review-order-item-header-content">
          {item.imageSrc ? (
            <img
              className="review-product-image"
              src={item.imageSrc}
              alt={item.imageAlt}
              width="64"
              height="64"
              data-testid={`review-product-image-${item.id}`}
            />
          ) : null}
          <span className="review-order-item-name">{item.name}</span>
        </span>
      </th>
      <td
        className="review-order-number"
        headers={quantityHeaders}
        data-testid={`review-order-quantity-${item.id}`}
      >
        {item.quantity}
      </td>
      <td
        className="review-order-number"
        headers={lineTotalHeaders}
        data-testid={`review-order-line-total-${item.id}`}
      >
        {formatCurrency(item.lineTotalCents)}
      </td>
    </tr>
  );
}

function getEffectiveReviewCellHeaders(reviewEffects, targetId, normalHeaderIds) {
  const overrideHeaderIds = targetId
    ? getReviewTableHeaderAssociationOverride(reviewEffects, targetId)
    : undefined;
  const headerIds = overrideHeaderIds ?? normalHeaderIds;

  return headerIds.join(" ");
}
