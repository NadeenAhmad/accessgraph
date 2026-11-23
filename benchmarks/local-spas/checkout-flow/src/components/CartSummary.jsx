import {
  formatCurrency,
  getCartItemCount,
  getCartSubtotalCents,
  getOrderTotalCents,
} from "../state/cartStore.js";

export function CartSummary({
  cartItems,
  variant = "full",
  copy = {},
  localLang,
}) {
  const itemCount = getCartItemCount(cartItems);
  const subtotalCents = getCartSubtotalCents(cartItems);
  const orderTotalCents = getOrderTotalCents(cartItems);
  const itemLabel = `${itemCount} ${
    itemCount === 1
      ? copy.itemSingular ?? "item"
      : copy.itemPlural ?? "items"
  }`;

  return (
    <section
      className={`cart-summary cart-summary-${variant}`}
      aria-labelledby="cart-summary-heading"
      data-testid="cart-summary"
      lang={localLang}
    >
      <h2 id="cart-summary-heading">{copy.heading ?? "Cart summary"}</h2>
      <dl>
        <div>
          <dt>{copy.items ?? "Items"}</dt>
          <dd data-testid="cart-summary-count">{itemLabel}</dd>
        </div>
        <div>
          <dt>{copy.subtotal ?? "Subtotal"}</dt>
          <dd data-testid="cart-summary-subtotal">
            {formatCurrency(subtotalCents)}
          </dd>
        </div>
        <div>
          <dt>{copy.shipping ?? "Shipping"}</dt>
          <dd data-testid="cart-summary-shipping">
            {subtotalCents > 0 ? "$5.00" : "$0.00"}
          </dd>
        </div>
        <div>
          <dt>{copy.orderTotal ?? "Order total"}</dt>
          <dd data-testid="cart-summary-total">
            {formatCurrency(orderTotalCents)}
          </dd>
        </div>
      </dl>
    </section>
  );
}
