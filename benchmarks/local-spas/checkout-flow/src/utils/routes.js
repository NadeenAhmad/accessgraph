export const CHECKOUT_ROUTES = {
  products: "/products",
  cart: "/cart",
  address: "/checkout/address",
  payment: "/checkout/payment",
  review: "/checkout/review",
};

export const NAV_ITEMS = [
  {
    id: "products",
    label: "Products",
    path: CHECKOUT_ROUTES.products,
    subjectId: "checkout.navigation.products",
    testId: "nav-products",
  },
  {
    id: "cart",
    label: "Cart",
    path: CHECKOUT_ROUTES.cart,
    subjectId: "checkout.navigation.cart",
    testId: "nav-cart",
  },
];

export function normalizeRoute(pathname) {
  if (pathname === CHECKOUT_ROUTES.cart) {
    return CHECKOUT_ROUTES.cart;
  }

  if (pathname === CHECKOUT_ROUTES.address) {
    return CHECKOUT_ROUTES.address;
  }

  if (pathname === CHECKOUT_ROUTES.payment) {
    return CHECKOUT_ROUTES.payment;
  }

  if (pathname === CHECKOUT_ROUTES.review) {
    return CHECKOUT_ROUTES.review;
  }

  return CHECKOUT_ROUTES.products;
}

export function getRouteId(pathname) {
  const route = normalizeRoute(pathname);

  if (route === CHECKOUT_ROUTES.cart) {
    return "cart";
  }

  if (route === CHECKOUT_ROUTES.address) {
    return "address";
  }

  if (route === CHECKOUT_ROUTES.payment) {
    return "payment";
  }

  if (route === CHECKOUT_ROUTES.review) {
    return "review";
  }

  return "products";
}
