import { MAX_QUANTITY, PRODUCTS, SHIPPING_CENTS } from "../data/fixtures.js";

const PRODUCT_BY_ID = new Map(PRODUCTS.map((product) => [product.id, product]));

export function getProductById(productId) {
  return PRODUCT_BY_ID.get(productId) ?? null;
}

export function getCartLineItems(cartItems) {
  return cartItems
    .map((item) => {
      const product = getProductById(item.productId);

      if (!product) {
        return null;
      }

      return {
        ...product,
        quantity: item.quantity,
        lineTotalCents: product.priceCents * item.quantity,
      };
    })
    .filter(Boolean);
}

export function getCartItemCount(cartItems) {
  return cartItems.reduce((count, item) => count + item.quantity, 0);
}

export function getCartSubtotalCents(cartItems) {
  return getCartLineItems(cartItems).reduce(
    (total, item) => total + item.lineTotalCents,
    0,
  );
}

export function getOrderTotalCents(cartItems) {
  const subtotalCents = getCartSubtotalCents(cartItems);
  return subtotalCents > 0 ? subtotalCents + SHIPPING_CENTS : 0;
}

export function getProductQuantity(cartItems, productId) {
  return cartItems.find((item) => item.productId === productId)?.quantity ?? 0;
}

export function addProduct(cartItems, productId) {
  const quantity = getProductQuantity(cartItems, productId);

  if (quantity >= MAX_QUANTITY) {
    return cartItems;
  }

  if (quantity === 0) {
    return [...cartItems, { productId, quantity: 1 }];
  }

  return cartItems.map((item) =>
    item.productId === productId
      ? { ...item, quantity: item.quantity + 1 }
      : item,
  );
}

export function incrementProduct(cartItems, productId) {
  return addProduct(cartItems, productId);
}

export function decrementProduct(cartItems, productId) {
  const quantity = getProductQuantity(cartItems, productId);

  if (quantity <= 1) {
    return cartItems.filter((item) => item.productId !== productId);
  }

  return cartItems.map((item) =>
    item.productId === productId
      ? { ...item, quantity: item.quantity - 1 }
      : item,
  );
}

export function formatCurrency(cents) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}
