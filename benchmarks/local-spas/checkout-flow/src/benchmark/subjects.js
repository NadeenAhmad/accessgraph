function subject(id, testId, description) {
  return Object.freeze({ id, testId, description });
}

export const CHECKOUT_SUBJECTS = Object.freeze({
  pageRoot: subject(
    "checkout.page.root",
    "",
    "Document root language declaration.",
  ),
  pageProductsTitle: subject(
    "checkout.page.products",
    "",
    "Products route document title.",
  ),
  pageAddressTitle: subject(
    "checkout.page.address",
    "",
    "Shipping address route document title.",
  ),
  pagePaymentTitle: subject(
    "checkout.page.payment",
    "",
    "Payment route document title.",
  ),
  navigationProducts: subject(
    "checkout.navigation.products",
    "nav-products",
    "Primary navigation link to product browsing.",
  ),
  navigationCart: subject(
    "checkout.navigation.cart",
    "nav-cart",
    "Primary navigation link to the cart.",
  ),
  navigationRoutes: subject(
    "checkout.navigation.routes",
    "",
    "Primary route-navigation landmark containing Products and Cart links.",
  ),
  checkoutProgress: subject(
    "checkout.progress",
    "checkout-progress",
    "Checkout workflow progress landmark containing step states.",
  ),
  checkoutProgressCart: subject(
    "checkout.progress.cart",
    "checkout-progress-cart",
    "Cart step in the checkout workflow progress indicator.",
  ),
  checkoutProgressAddress: subject(
    "checkout.progress.address",
    "checkout-progress-address",
    "Shipping address step in the checkout workflow progress indicator.",
  ),
  footerSite: subject(
    "checkout.footer.site",
    "app-footer",
    "Application footer contentinfo landmark with site and copyright information.",
  ),
  productsFeaturedRegion: subject(
    "checkout.products.featuredRegion",
    "products-list-region",
    "Named Featured products landmark containing category tabs and product cards.",
  ),
  productsList: subject(
    "checkout.products.list",
    "product-list",
    "Product browsing list region.",
  ),
  productsDescription: subject(
    "checkout.products.description",
    "products-description",
    "Products page explanatory paragraph.",
  ),
  productsLanguageEnglish: subject(
    "checkout.products.language.en",
    "products-language-en",
    "English option in the Products language selector.",
  ),
  productsLanguageSpanish: subject(
    "checkout.products.language.es",
    "products-language-es",
    "Spanish option in the Products language selector.",
  ),
  productsPageHeading: subject(
    "checkout.products.pageHeading",
    "",
    "Products route h1 heading.",
  ),
  productsPageSummary: subject(
    "checkout.products.pageSummary",
    "",
    "Products route heading summary.",
  ),
  productsFeaturedProductsHeading: subject(
    "checkout.products.featuredProductsHeading",
    "",
    "Featured products section h2 heading.",
  ),
  cartPageHeading: subject(
    "checkout.cart.pageHeading",
    "",
    "Cart route h1 heading.",
  ),
  cartPageSummary: subject(
    "checkout.cart.pageSummary",
    "",
    "Cart route heading summary.",
  ),
  cartEmptyHeading: subject(
    "checkout.cart.emptyHeading",
    "",
    "Empty Cart state h2 heading.",
  ),
  paymentMethodHeading: subject(
    "checkout.payment.methodHeading",
    "",
    "Payment method section h2 heading.",
  ),
  productsCartSummary: subject(
    "checkout.products.cartSummary",
    "cart-summary",
    "Products page compact cart-summary component.",
  ),
  productsCategoryTablist: subject(
    "checkout.products.categoryTablist",
    "product-category-tablist",
    "Product category tablist that groups the category selection tabs.",
  ),
  productsDeskAccessoriesCategoryTab: subject(
    "checkout.products.categoryTabs.deskAccessories",
    "product-category-tab-desk-accessories",
    "Desk accessories category tab that controls the desk accessories panel.",
  ),
  productsOfficeSuppliesCategoryTab: subject(
    "checkout.products.categoryTabs.officeSupplies",
    "product-category-tab-office-supplies",
    "Office supplies category tab that controls the office supplies panel.",
  ),
  supportShippingInformation: subject(
    "checkout.support.shippingInformation",
    "support-shipping",
    "Support link to the controlled shipping information destination.",
  ),
  supportReturns: subject(
    "checkout.support.returns",
    "support-returns",
    "Support link to the controlled returns and refunds destination.",
  ),
  productsWalkthroughCaptionTrack: subject(
    "checkout.products.walkthrough.captionTrack",
    "checkout-walkthrough-captions",
    "English captions track for the Checkout walkthrough video.",
  ),
  productsDeskLampImage: subject(
    "checkout.products.deskLamp.image",
    "product-image-prod-desk-lamp",
    "Desk lamp product image in the browsing surface.",
  ),
  productsNotebookSetImage: subject(
    "checkout.products.notebookSet.image",
    "product-image-prod-notebook-set",
    "Notebook set product image in the browsing surface.",
  ),
  productsDeskLampAddButton: subject(
    "checkout.products.deskLamp.addButton",
    "product-add-prod-desk-lamp",
    "Button that adds the desk lamp to the cart.",
  ),
  productsNotebookSetAddButton: subject(
    "checkout.products.notebookSet.addButton",
    "product-add-prod-notebook-set",
    "Button that adds the notebook set to the cart.",
  ),
  productsCableOrganizerAddButton: subject(
    "checkout.products.cableOrganizer.addButton",
    "product-add-prod-cable-organizer",
    "Button that adds the cable organizer to the cart.",
  ),
  cartItems: subject(
    "checkout.cart.items",
    "cart-list",
    "Cart item list for the deterministic cart state.",
  ),
  cartDescription: subject(
    "checkout.cart.description",
    "cart-description",
    "Cart page instruction paragraph.",
  ),
  cartDeskLampQuantity: subject(
    "checkout.cart.deskLamp.quantity",
    "cart-quantity-prod-desk-lamp",
    "Desk lamp quantity output in the cart.",
  ),
  cartDeskLampIncrement: subject(
    "checkout.cart.deskLamp.increment",
    "cart-increment-prod-desk-lamp",
    "Button that increases the Desk lamp quantity in the cart.",
  ),
  cartOrderTotals: subject(
    "checkout.cart.orderTotals",
    "cart-totals-region",
    "Order totals landmark beside the cart items.",
  ),
  cartGiftReceipt: subject(
    "checkout.cart.giftReceipt",
    "gift-receipt-switch",
    "Gift receipt switch in the cart preferences.",
  ),
  cartSaveCart: subject(
    "checkout.cart.saveCart",
    "save-cart-toggle",
    "Save cart toggle button in the cart preferences.",
  ),
  cartContinueToAddress: subject(
    "checkout.cart.continueToAddress",
    "continue-to-address",
    "Button that advances from cart to address.",
  ),
  cartDeliveryEstimate: subject(
    "checkout.cart.deliveryEstimate",
    "delivery-estimate-trigger",
    "Button that reveals the delivery estimate result in the cart.",
  ),
  cartShippingInformationDialog: subject(
    "checkout.cart.shippingInformationDialog",
    "shipping-information-dialog",
    "Shipping information dialog opened from the cart.",
  ),
  cartShippingInformationBody: subject(
    "checkout.cart.shippingInformationBody",
    "shipping-information-body",
    "Substantive delivery-information passage in the Shipping information dialog.",
  ),
  addressFullName: subject(
    "checkout.address.fullName",
    "address-full-name",
    "Shipping recipient full-name field.",
  ),
  addressEmail: subject(
    "checkout.address.email",
    "address-email",
    "Shipping contact email field.",
  ),
  addressStreet: subject(
    "checkout.address.street",
    "address-street",
    "Shipping street-address field.",
  ),
  addressCity: subject(
    "checkout.address.city",
    "address-city",
    "Shipping city field.",
  ),
  addressState: subject(
    "checkout.address.state",
    "address-state",
    "Shipping state field.",
  ),
  addressCountry: subject(
    "checkout.address.country",
    "address-country",
    "Shipping country or region select.",
  ),
  addressDeliveryInstructions: subject(
    "checkout.address.deliveryInstructions",
    "address-delivery-instructions",
    "Optional delivery-instructions textarea in the Shipping details form.",
  ),
  addressPostalCode: subject(
    "checkout.address.postalCode",
    "address-postal-code",
    "Shipping postal-code field.",
  ),
  addressContinueToPayment: subject(
    "checkout.address.continueToPayment",
    "continue-to-payment",
    "Button that submits the address and advances to payment.",
  ),
  addressOrderTotals: subject(
    "checkout.address.orderTotals",
    "address-totals-region",
    "Order totals complementary landmark beside the shipping-address form.",
  ),
  paymentCardholder: subject(
    "checkout.payment.cardholder",
    "payment-cardholder",
    "Cardholder name field.",
  ),
  paymentCardNumber: subject(
    "checkout.payment.cardNumber",
    "payment-card-number",
    "Payment card number field.",
  ),
  paymentExpiry: subject(
    "checkout.payment.expiry",
    "payment-expiry",
    "Payment card expiry field.",
  ),
  paymentSecurityCode: subject(
    "checkout.payment.securityCode",
    "payment-security-code",
    "Payment card security code field.",
  ),
  paymentContinueToReview: subject(
    "checkout.payment.continueToReview",
    "continue-to-review",
    "Button that submits payment details and advances to review.",
  ),
  reviewShippingSummary: subject(
    "checkout.review.shippingSummary",
    "review-shipping-summary",
    "Submitted shipping-address summary in review.",
  ),
  reviewPaymentSummary: subject(
    "checkout.review.paymentSummary",
    "review-payment-summary",
    "Submitted payment summary in review.",
  ),
  reviewContent: subject(
    "checkout.review.content",
    "checkout-review-content",
    "Valid review-route content wrapper.",
  ),
  reviewOrderSummary: subject(
    "checkout.review.orderSummary",
    "review-order-summary",
    "Final order-item summary in review.",
  ),
  reviewOrderDeskLampQuantityCell: subject(
    "checkout.review.orderItems.deskLamp.quantityCell",
    "review-order-quantity-prod-desk-lamp",
    "Desk lamp quantity data cell in the Review order table.",
  ),
  reviewOrderDeskLampLineTotalCell: subject(
    "checkout.review.orderItems.deskLamp.lineTotalCell",
    "review-order-line-total-prod-desk-lamp",
    "Desk lamp line-total data cell in the Review order table.",
  ),
  reviewOrderNotebookSetLineTotalCell: subject(
    "checkout.review.orderItems.notebookSet.lineTotalCell",
    "review-order-line-total-prod-notebook-set",
    "Notebook set line-total data cell in the Review order table.",
  ),
});

export const CHECKOUT_SUBJECT_LIST = Object.freeze(
  Object.values(CHECKOUT_SUBJECTS),
);

export const CHECKOUT_SUBJECT_BY_ID = Object.freeze(
  Object.fromEntries(CHECKOUT_SUBJECT_LIST.map((item) => [item.id, item])),
);

export function getCheckoutSubject(subjectId) {
  return CHECKOUT_SUBJECT_BY_ID[subjectId] ?? null;
}
