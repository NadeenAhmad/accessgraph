import { MAX_QUANTITY } from "../data/fixtures.js";
import { formatCurrency } from "../state/cartStore.js";
import {
  CHECKOUT_BUTTON_TARGETS,
  getButtonActionTargetOverride,
} from "../benchmark/effects/buttonEffects.js";

const CART_INCREMENT_BUTTON_TARGETS = Object.freeze({
  "prod-desk-lamp": CHECKOUT_BUTTON_TARGETS.cartDeskLampIncrement,
});

export function CartItem({
  item,
  buttonEffects = {},
  copy = {},
  onIncrement,
  onDecrement,
}) {
  const itemCopy = copy.products?.[item.id] ?? {};
  const itemName = itemCopy.name ?? item.name;
  const itemCategory =
    itemCopy.category ?? copy.categories?.[item.id] ?? item.category;
  const incrementButtonTarget = CART_INCREMENT_BUTTON_TARGETS[item.id];
  const incrementProductId =
    getButtonActionTargetOverride(buttonEffects, incrementButtonTarget) ??
    item.id;

  return (
    <li
      className="cart-item"
      data-testid={`cart-item-${item.id}`}
      aria-labelledby={`cart-item-title-${item.id}`}
    >
      <div className="cart-item-copy">
        <p className="product-category">{itemCategory}</p>
        <h2 id={`cart-item-title-${item.id}`}>{itemName}</h2>
        <p>
          {copy.unitPrice ?? "Unit price"}:{" "}
          <span data-testid={`cart-item-price-${item.id}`}>
            {formatCurrency(item.priceCents)}
          </span>
        </p>
        <p className="quantity-note">
          {formatCartItemText(copy.maxQuantity ?? "Maximum {maxQuantity} per item.", {
            maxQuantity: MAX_QUANTITY,
          })}
        </p>
      </div>

      <div
        className="quantity-controls"
        role="group"
        aria-label={formatCartItemText(
          copy.quantityGroupLabel ?? "{itemName} quantity controls",
          { itemName },
        )}
      >
        <button
          type="button"
          className="quantity-button"
          aria-label={formatCartItemText(
            copy.decreaseLabel ?? "Decrease {itemName} quantity",
            { itemName },
          )}
          data-testid={`cart-decrement-${item.id}`}
          onClick={() => onDecrement(item.id)}
        >
          -
        </button>
        <output
          className="quantity-output"
          data-testid={`cart-quantity-${item.id}`}
          aria-label={formatCartItemText(
            copy.quantityLabel ?? "{itemName} quantity",
            { itemName },
          )}
        >
          {item.quantity}
        </output>
        <button
          type="button"
          className="quantity-button"
          aria-label={formatCartItemText(
            copy.increaseLabel ?? "Increase {itemName} quantity",
            { itemName },
          )}
          data-testid={`cart-increment-${item.id}`}
          onClick={() => onIncrement(incrementProductId)}
        >
          +
        </button>
      </div>

      <p className="line-total">
        {copy.lineTotal ?? "Line total"}{" "}
        <strong data-testid={`cart-line-total-${item.id}`}>
          {formatCurrency(item.lineTotalCents)}
        </strong>
      </p>
    </li>
  );
}

function formatCartItemText(template, values) {
  return template.replace(/\{([a-zA-Z]+)\}/g, (_match, key) =>
    String(values[key] ?? ""),
  );
}
