export const PRODUCTS = [
  {
    id: "prod-desk-lamp",
    name: "Desk lamp",
    priceCents: 3200,
    category: "Home office",
    imageSrc: "/desk-lamp.svg",
    imageAlt: "Desk lamp with adjustable brass shade",
  },
  {
    id: "prod-notebook-set",
    name: "Notebook set",
    priceCents: 1800,
    category: "Stationery",
    imageSrc: "/notebook-set.svg",
    imageAlt: "Three notebooks with blue, teal, and coral covers",
  },
  {
    id: "prod-cable-organizer",
    name: "Cable organizer",
    priceCents: 1200,
    category: "Accessories",
  },
];

export const INITIAL_CART_ITEMS = [
  {
    productId: "prod-desk-lamp",
    quantity: 1,
  },
];

export const MAX_QUANTITY = 3;
export const SHIPPING_CENTS = 500;
