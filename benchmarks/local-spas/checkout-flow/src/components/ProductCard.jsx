import {
  CHECKOUT_BUTTON_TARGETS,
  getButtonAccessibleNameOverride,
  getButtonTextOverride,
} from "../benchmark/effects/buttonEffects.js";
import { MAX_QUANTITY } from "../data/fixtures.js";
import { formatCurrency } from "../state/cartStore.js";

const PRODUCT_ADD_BUTTON_TARGETS = Object.freeze({
  "prod-notebook-set": CHECKOUT_BUTTON_TARGETS.productsNotebookSetAddButton,
});

export function ProductCard({
  product,
  quantity,
  buttonEffects = {},
  productEffects = {},
  onAdd,
}) {
  const isAtMax = quantity >= MAX_QUANTITY;
  const productsContent = productEffects.productsContentOverrides ?? {};
  const productCopy = productsContent.products?.[product.id] ?? {};
  const productCardCopy = productsContent.productCard ?? {};
  const productName = productCopy.name ?? product.name;
  const productCategory = productCopy.category ?? product.category;
  const addButtonTarget = PRODUCT_ADD_BUTTON_TARGETS[product.id];
  const buttonTextOverride = addButtonTarget
    ? getButtonTextOverride(buttonEffects, addButtonTarget)
    : undefined;
  const buttonAccessibleNameOverride = addButtonTarget
    ? getButtonAccessibleNameOverride(buttonEffects, addButtonTarget)
    : undefined;
  const legacyAddButtonAccessibleName =
    product.id === "prod-desk-lamp"
      ? productEffects.deskLampAddButtonAccessibleName
      : undefined;
  const addButtonAccessibleName =
    buttonAccessibleNameOverride ?? legacyAddButtonAccessibleName;
  const imageAlt =
    productEffects.imageAltOverrides?.[product.id] ??
    productCopy.imageAlt ??
    product.imageAlt;
  const defaultAddButtonText = isAtMax
    ? formatProductText(
        productCardCopy.maxButtonLabel ?? "{productName} at maximum",
        { productName },
      )
    : formatProductText(
        productCardCopy.addButtonLabel ?? "Add {productName}",
        { productName },
      );
  const addButtonText = buttonTextOverride ?? defaultAddButtonText;
  const quantityStatus =
    quantity === 0
      ? productCardCopy.notInCart ?? "Not in cart"
      : `${productCardCopy.inCartPrefix ?? "In cart"}: ${quantity} ${
          quantity === 1
            ? productCardCopy.itemSingular ?? "item"
            : productCardCopy.itemPlural ?? "items"
        }`;

  return (
    <li
      className="product-card"
      data-testid={`product-${product.id}`}
      aria-labelledby={`product-title-${product.id}`}
    >
      {product.imageSrc ? (
        <img
          className="product-image"
          src={product.imageSrc}
          alt={imageAlt}
          width="72"
          height="72"
          data-testid={`product-image-${product.id}`}
        />
      ) : null}
      <div className="product-copy">
        <p className="product-category">{productCategory}</p>
        <h2 id={`product-title-${product.id}`}>{productName}</h2>
        <p className="product-price">{formatCurrency(product.priceCents)}</p>
        <p className="product-cart-state" data-testid={`product-quantity-${product.id}`}>
          {quantityStatus}
        </p>
      </div>
      <button
        type="button"
        className="secondary-action"
        aria-label={addButtonAccessibleName}
        data-testid={`product-add-${product.id}`}
        onClick={() => onAdd(product.id)}
      >
        {addButtonText}
      </button>
    </li>
  );
}

function formatProductText(template, values) {
  return template.replace(/\{([a-zA-Z]+)\}/g, (_match, key) =>
    String(values[key] ?? ""),
  );
}
