import { useEffect, useMemo, useRef, useState } from "react";
import { INITIAL_CART_ITEMS, MAX_QUANTITY } from "./data/fixtures.js";
import { AddressPage } from "./components/AddressPage.jsx";
import { AppNav } from "./components/AppNav.jsx";
import { CartPage } from "./components/CartPage.jsx";
import { PaymentPage } from "./components/PaymentPage.jsx";
import { ProductsPage } from "./components/ProductsPage.jsx";
import { ReviewPage } from "./components/ReviewPage.jsx";
import { StatusRegion } from "./components/StatusRegion.jsx";
import {
  DEFAULT_PRODUCTS_LANGUAGE,
  PRODUCTS_LANGUAGE_OPTIONS,
  getProductsCopyForLanguage,
  getProductsRootLang,
} from "./content/productsCopy.js";
import {
  resolveAppEffects,
  resolveRootLangForRoute,
  shouldCarryRootLangAcrossLanguageTransition,
} from "./benchmark/effects/appEffects.js";
import { resolveAutocompleteEffects } from "./benchmark/effects/autocompleteEffects.js";
import {
  CHECKOUT_ARIA_STATE_TARGETS,
  getAriaPressedOverride,
  resolveAriaStateEffects,
} from "./benchmark/effects/ariaStateEffects.js";
import {
  CHECKOUT_BUTTON_TARGETS,
  getButtonDestinationOverride,
  resolveButtonEffects,
} from "./benchmark/effects/buttonEffects.js";
import { resolveCartEffects } from "./benchmark/effects/cartEffects.js";
import { resolveErrorMessageEffects } from "./benchmark/effects/errorMessageEffects.js";
import { resolveFormLabelEffects } from "./benchmark/effects/formLabelEffects.js";
import {
  CHECKOUT_HEADING_TARGETS,
  getHeadingTextOverride,
  resolveHeadingEffects,
} from "./benchmark/effects/headingEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkAccessibleNameOverride,
  getLandmarkRoleOverride,
  resolveLandmarkEffects,
} from "./benchmark/effects/landmarkEffects.js";
import { resolveLocalLanguageEffects } from "./benchmark/effects/localLanguageEffects.js";
import { resolveLinkEffects } from "./benchmark/effects/linkEffects.js";
import {
  getPageTitleTextOverride,
  resolvePageTitleEffects,
  shouldCarryPageTitleAcrossTransition,
} from "./benchmark/effects/pageTitleEffects.js";
import { resolveProductsEffects } from "./benchmark/effects/productsEffects.js";
import { resolveWidgetEffects } from "./benchmark/effects/widgetEffects.js";
import { getActiveSeeds } from "./benchmark/profiles.js";
import {
  addProduct,
  decrementProduct,
  getCartLineItems,
  getProductById,
  getProductQuantity,
  incrementProduct,
} from "./state/cartStore.js";
import { CHECKOUT_ROUTES, getRouteId, normalizeRoute } from "./utils/routes.js";

function getCurrentPath() {
  return normalizeRoute(window.location.pathname);
}

export default function App() {
  const [cartItems, setCartItems] = useState(INITIAL_CART_ITEMS);
  const [currentPath, setCurrentPath] = useState(getCurrentPath);
  const [statusMessage, setStatusMessage] = useState("");
  const [pendingFocusTarget, setPendingFocusTarget] = useState(null);
  const [submittedAddress, setSubmittedAddress] = useState(null);
  const [carriedPageTitle, setCarriedPageTitle] = useState(null);
  const [carriedRootLang, setCarriedRootLang] = useState(null);
  const [submittedPayment, setSubmittedPayment] = useState(null);
  const [productsLanguage, setProductsLanguage] = useState(
    DEFAULT_PRODUCTS_LANGUAGE,
  );
  const routeHeadingRef = useRef(null);
  const hasMountedRef = useRef(false);

  const routeId = getRouteId(currentPath);
  const lineItems = useMemo(() => getCartLineItems(cartItems), [cartItems]);
  const activeSeeds = useMemo(() => getActiveSeeds(), []);
  const appEffects = useMemo(() => resolveAppEffects(activeSeeds), [activeSeeds]);
  const autocompleteEffects = useMemo(
    () => resolveAutocompleteEffects(activeSeeds),
    [activeSeeds],
  );
  const ariaStateEffects = useMemo(
    () => resolveAriaStateEffects(activeSeeds),
    [activeSeeds],
  );
  const buttonEffects = useMemo(
    () => resolveButtonEffects(activeSeeds),
    [activeSeeds],
  );
  const benchmarkCartEffects = useMemo(
    () => resolveCartEffects(activeSeeds),
    [activeSeeds],
  );
  const formLabelEffects = useMemo(
    () => resolveFormLabelEffects(activeSeeds),
    [activeSeeds],
  );
  const errorMessageEffects = useMemo(
    () => resolveErrorMessageEffects(activeSeeds),
    [activeSeeds],
  );
  const headingEffects = useMemo(
    () => resolveHeadingEffects(activeSeeds),
    [activeSeeds],
  );
  const landmarkEffects = useMemo(
    () => resolveLandmarkEffects(activeSeeds),
    [activeSeeds],
  );
  const localLanguageEffects = useMemo(
    () => resolveLocalLanguageEffects(activeSeeds),
    [activeSeeds],
  );
  const linkEffects = useMemo(
    () => resolveLinkEffects(activeSeeds),
    [activeSeeds],
  );
  const pageTitleEffects = useMemo(
    () => resolvePageTitleEffects(activeSeeds),
    [activeSeeds],
  );
  const widgetEffects = useMemo(
    () => resolveWidgetEffects(activeSeeds),
    [activeSeeds],
  );
  const benchmarkProductsEffects = useMemo(
    () => resolveProductsEffects(activeSeeds),
    [activeSeeds],
  );
  const normalProductsCopy = useMemo(
    () => getProductsCopyForLanguage(productsLanguage),
    [productsLanguage],
  );
  const cartEffects = useMemo(
    () => ({
      ...benchmarkCartEffects,
      cartContentOverrides:
        benchmarkCartEffects.cartContentOverrides ?? normalProductsCopy.cart,
    }),
    [benchmarkCartEffects, normalProductsCopy],
  );
  const productsEffects = useMemo(
    () => ({
      ...benchmarkProductsEffects,
      productsContentOverrides:
        benchmarkProductsEffects.productsContentOverrides ?? normalProductsCopy,
    }),
    [benchmarkProductsEffects, normalProductsCopy],
  );
  const routeCopy = getRouteCopy(routeId, productsEffects, cartEffects);
  const routeHeading = getRouteHeading(routeId, routeCopy.heading, headingEffects);
  const routeSummary = getRouteSummaryText(
    routeId,
    routeCopy.summary,
    headingEffects,
  );
  const normalDocumentPageTitle = getDocumentPageTitle(routeId, normalProductsCopy);
  const resolvedDocumentPageTitle =
    getPageTitleTextOverride(pageTitleEffects, routeId) ?? normalDocumentPageTitle;
  const documentPageTitle = carriedPageTitle ?? resolvedDocumentPageTitle;
  const normalRootLang = getNormalRootLang(routeId, productsLanguage);
  const resolvedRootLang = resolveRootLangForRoute(
    appEffects,
    routeId,
    normalRootLang,
  );
  const rootLang = carriedRootLang ?? resolvedRootLang;
  const footerAccessibleName = getLandmarkAccessibleNameOverride(
    landmarkEffects,
    CHECKOUT_LANDMARK_TARGETS.footerSite,
  );
  const footerRole = getLandmarkRoleOverride(
    landmarkEffects,
    CHECKOUT_LANDMARK_TARGETS.footerSite,
  );
  const FooterElement = footerRole === "search" ? "div" : "footer";

  useEffect(() => {
    if (window.location.pathname !== currentPath) {
      window.history.replaceState({}, "", currentPath);
    }
  }, []);

  useEffect(() => {
    function handlePopState() {
      setCarriedPageTitle(null);
      setCarriedRootLang(null);
      setStatusMessage("");
      setCurrentPath(getCurrentPath());
    }

    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  useEffect(() => {
    document.title = `${documentPageTitle} | Brightlane Checkout`;
    document.documentElement.lang = rootLang;

    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }

    window.setTimeout(() => {
      routeHeadingRef.current?.focus({ preventScroll: true });
    }, 0);
  }, [documentPageTitle, rootLang]);

  useEffect(() => {
    if (!pendingFocusTarget) {
      return;
    }

    const selector = getFocusTargetSelector(pendingFocusTarget);
    const focusTarget = selector ? document.querySelector(selector) : null;

    if (focusTarget instanceof HTMLElement) {
      focusTarget.focus({ preventScroll: true });
      setPendingFocusTarget(null);
    }
  }, [pendingFocusTarget, lineItems]);

  function handleNavigate(path) {
    const nextPath = normalizeRoute(path);
    const nextRouteId = getRouteId(nextPath);
    setCarriedPageTitle(
      shouldCarryPageTitleAcrossTransition(
        pageTitleEffects,
        routeId,
        nextRouteId,
      ) ? documentPageTitle : null,
    );
    setCarriedRootLang(null);
    window.history.pushState({}, "", nextPath);
    setStatusMessage("");
    setCurrentPath(nextPath);
  }

  function handleProductsLanguageChange(nextLanguage) {
    setCarriedRootLang(
      shouldCarryRootLangAcrossLanguageTransition(
        appEffects,
        productsLanguage,
        nextLanguage,
      ) ? rootLang : null,
    );
    setProductsLanguage(nextLanguage);
  }

  function handleAddProduct(productId) {
    const product = getProductById(productId);
    const currentQuantity = getProductQuantity(cartItems, productId);

    if (!product) {
      return;
    }

    if (currentQuantity >= MAX_QUANTITY) {
      setStatusMessage(
        formatProductsStatusMessage(
          productsEffects,
          "maxQuantity",
          "{productName} is already at maximum quantity {maxQuantity}.",
          {
            maxQuantity: MAX_QUANTITY,
            productName: getProductDisplayName(productsEffects, product),
          },
        ),
      );
      return;
    }

    setCartItems((currentItems) => addProduct(currentItems, productId));
    setStatusMessage(
      currentQuantity === 0
        ? formatProductsStatusMessage(
            productsEffects,
            "addedToCart",
            "{productName} added to cart.",
            {
              productName: getProductDisplayName(productsEffects, product),
            },
          )
        : formatProductsStatusMessage(
            productsEffects,
            "quantityUpdated",
            "{productName} quantity updated to {quantity}.",
            {
              productName: getProductDisplayName(productsEffects, product),
              quantity: currentQuantity + 1,
            },
          ),
    );
  }

  function handleIncrementProduct(productId) {
    const product = getProductById(productId);
    const currentQuantity = getProductQuantity(cartItems, productId);

    if (!product) {
      return;
    }

    if (currentQuantity >= MAX_QUANTITY) {
      setStatusMessage(
        formatCartStatusMessage(
          cartEffects,
          "maxQuantity",
          "{productName} is already at maximum quantity {maxQuantity}.",
          {
            maxQuantity: MAX_QUANTITY,
            productName: getCartProductDisplayName(cartEffects, product),
          },
        ),
      );
      return;
    }

    setCartItems((currentItems) => incrementProduct(currentItems, productId));
    setStatusMessage(
      formatCartStatusMessage(
        cartEffects,
        "quantityUpdated",
        "{productName} quantity updated to {quantity}.",
        {
          productName: getCartProductDisplayName(cartEffects, product),
          quantity: currentQuantity + 1,
        },
      ),
    );
  }

  function handleDecrementProduct(productId) {
    const product = getProductById(productId);
    const currentQuantity = getProductQuantity(cartItems, productId);

    if (!product || currentQuantity === 0) {
      return;
    }

    if (currentQuantity === 1) {
      setPendingFocusTarget(getPostRemovalFocusTarget(lineItems, productId));
      setCartItems((currentItems) => decrementProduct(currentItems, productId));
      setStatusMessage(
        formatCartStatusMessage(
          cartEffects,
          "removed",
          "{productName} removed from cart.",
          {
            productName: getCartProductDisplayName(cartEffects, product),
          },
        ),
      );
      return;
    }

    setCartItems((currentItems) => decrementProduct(currentItems, productId));
    setStatusMessage(
      formatCartStatusMessage(
        cartEffects,
        "quantityUpdated",
        "{productName} quantity updated to {quantity}.",
        {
          productName: getCartProductDisplayName(cartEffects, product),
          quantity: currentQuantity - 1,
        },
      ),
    );
  }

  function handleContinueShopping() {
    handleNavigate(CHECKOUT_ROUTES.products);
  }

  function handleContinueToAddress() {
    handleNavigate(CHECKOUT_ROUTES.address);
  }

  function handleAddressSubmit(address) {
    setSubmittedAddress(address);
    setSubmittedPayment(null);
    const destination =
      getButtonDestinationOverride(
        buttonEffects,
        CHECKOUT_BUTTON_TARGETS.addressContinueToPayment,
      ) ?? CHECKOUT_ROUTES.payment;
    handleNavigate(destination);
  }

  function handlePaymentSubmit(payment) {
    setSubmittedPayment(payment);
    handleNavigate(CHECKOUT_ROUTES.review);
  }

  return (
    <div
      className="app-shell"
      data-testid="checkout-benchmark-app"
    >
      <header className="app-header">
        <div>
          <p className="eyebrow">
            {normalProductsCopy.shell?.eyebrow ?? "Brightlane Shop"}
          </p>
          <p className="app-name">
            {normalProductsCopy.shell?.appName ?? "Checkout Flow"}
          </p>
        </div>
        <AppNav
          ariaStateEffects={ariaStateEffects}
          currentPath={currentPath}
          landmarkEffects={landmarkEffects}
          linkEffects={linkEffects}
          navCopy={normalProductsCopy.nav}
          onNavigate={handleNavigate}
        />
      </header>

      <main className="main-content" data-testid={`route-${routeId}`}>
        <div className="route-heading">
          <h1 ref={routeHeadingRef} tabIndex="-1">
            {routeHeading}
          </h1>
          <p>{routeSummary}</p>
          {routeId === "products" ? (
            <ProductsLanguageSwitcher
              ariaStateEffects={ariaStateEffects}
              language={productsLanguage}
              copy={normalProductsCopy.languageSwitcher}
              onLanguageChange={handleProductsLanguageChange}
            />
          ) : null}
        </div>

        {routeId === "cart" ? (
          <CartPage
            ariaStateEffects={ariaStateEffects}
            buttonEffects={buttonEffects}
            cartItems={cartItems}
            cartEffects={cartEffects}
            headingEffects={headingEffects}
            landmarkEffects={landmarkEffects}
            localLanguageEffects={localLanguageEffects}
            onIncrement={handleIncrementProduct}
            onDecrement={handleDecrementProduct}
            onContinueShopping={handleContinueShopping}
            onContinueToAddress={handleContinueToAddress}
          />
        ) : routeId === "address" ? (
          <AddressPage
            ariaStateEffects={ariaStateEffects}
            cartItems={cartItems}
            autocompleteEffects={autocompleteEffects}
            errorMessageEffects={errorMessageEffects}
            formLabelEffects={formLabelEffects}
            initialAddress={submittedAddress}
            landmarkEffects={landmarkEffects}
            onStatus={setStatusMessage}
            onValidAddress={handleAddressSubmit}
          />
        ) : routeId === "payment" ? (
          <PaymentPage
            autocompleteEffects={autocompleteEffects}
            cartItems={cartItems}
            errorMessageEffects={errorMessageEffects}
            formLabelEffects={formLabelEffects}
            headingEffects={headingEffects}
            submittedAddress={submittedAddress}
            onReturnToAddress={handleContinueToAddress}
            onStatus={setStatusMessage}
            onValidPayment={handlePaymentSubmit}
          />
        ) : routeId === "review" ? (
          <ReviewPage
            cartItems={cartItems}
            activeSeeds={activeSeeds}
            submittedAddress={submittedAddress}
            submittedPayment={submittedPayment}
            onReturnToAddress={handleContinueToAddress}
            onReturnToPayment={() => handleNavigate(CHECKOUT_ROUTES.payment)}
          />
        ) : (
          <ProductsPage
            cartItems={cartItems}
            activeSeeds={activeSeeds}
            ariaStateEffects={ariaStateEffects}
            buttonEffects={buttonEffects}
            headingEffects={headingEffects}
            landmarkEffects={landmarkEffects}
            linkEffects={linkEffects}
            localLanguageEffects={localLanguageEffects}
            productEffects={productsEffects}
            widgetEffects={widgetEffects}
            onAdd={handleAddProduct}
          />
        )}
      </main>

      <StatusRegion message={statusMessage} />

      <FooterElement
        className="app-footer"
        role={footerRole}
        aria-label={footerAccessibleName}
        data-testid="app-footer"
      >
        <div>
          <p className="footer-brand">
            {normalProductsCopy.footer?.brand ?? "AccessGraph Shop"}
          </p>
          <p>
            {normalProductsCopy.footer?.description ??
              "Demo checkout experience"}
          </p>
        </div>
        <p>{normalProductsCopy.footer?.copyright ?? "© 2026 AccessGraph Shop"}</p>
      </FooterElement>
    </div>
  );
}

function getPageTitle(routeId, productsCopy = {}) {
  const localizedTitle = productsCopy.pageTitles?.[routeId];
  if (localizedTitle) {
    return localizedTitle;
  }

  if (routeId === "review") {
    return "Review";
  }

  if (routeId === "payment") {
    return "Payment";
  }

  if (routeId === "address") {
    return "Shipping address";
  }

  if (routeId === "cart") {
    return "Cart";
  }

  return "Products";
}

function getDocumentPageTitle(routeId, productsCopy) {
  return getPageTitle(routeId, productsCopy);
}

function getRouteHeading(routeId, heading, headingEffects) {
  const targetId = getRouteHeadingTarget(routeId);
  return getHeadingTextOverride(headingEffects, targetId) ?? heading;
}

function getRouteHeadingTarget(routeId) {
  if (routeId === "products") {
    return CHECKOUT_HEADING_TARGETS.productsPageHeading;
  }

  if (routeId === "cart") {
    return CHECKOUT_HEADING_TARGETS.cartPageHeading;
  }

  return "";
}

function getRouteSummaryText(routeId, summary, headingEffects) {
  const targetId = getRouteSummaryTarget(routeId);
  return getHeadingTextOverride(headingEffects, targetId) ?? summary;
}

function getRouteSummaryTarget(routeId) {
  if (routeId === "products") {
    return CHECKOUT_HEADING_TARGETS.productsPageSummary;
  }

  if (routeId === "cart") {
    return CHECKOUT_HEADING_TARGETS.cartPageSummary;
  }

  return "";
}

function getNormalRootLang(routeId, productsLanguage) {
  if (routeId === "products" || routeId === "cart") {
    return getProductsRootLang(productsLanguage);
  }

  return "en";
}

function getRouteSummary(routeId) {
  if (routeId === "review") {
    return "Review shipping, payment, and order totals.";
  }

  if (routeId === "payment") {
    return "Enter card details for the current checkout.";
  }

  if (routeId === "address") {
    return "Enter shipping details for the current cart.";
  }

  if (routeId === "cart") {
    return "Review cart items and quantity controls.";
  }

  return "Browse featured products and update the cart summary.";
}

function getRouteCopy(routeId, productsEffects = {}, cartEffects = {}) {
  const productsRouteCopy =
    productsEffects.productsContentOverrides?.route ?? {};
  const cartRouteCopy = cartEffects.cartContentOverrides?.route ?? {};

  if (routeId === "products") {
    return {
      heading: productsRouteCopy.heading ?? getPageTitle(routeId),
      summary: productsRouteCopy.summary ?? getRouteSummary(routeId),
    };
  }

  if (routeId === "cart") {
    return {
      heading: cartRouteCopy.heading ?? getPageTitle(routeId),
      summary: cartRouteCopy.summary ?? getRouteSummary(routeId),
    };
  }

  return {
    heading: getPageTitle(routeId),
    summary: getRouteSummary(routeId),
  };
}

function getProductDisplayName(productsEffects, product) {
  return (
    productsEffects.productsContentOverrides?.products?.[product.id]?.name ??
    product.name
  );
}

function getCartProductDisplayName(cartEffects, product) {
  return (
    cartEffects.cartContentOverrides?.cartItem?.products?.[product.id]?.name ??
    product.name
  );
}

function formatProductsStatusMessage(
  productsEffects,
  key,
  fallbackTemplate,
  values,
) {
  const template =
    productsEffects.productsContentOverrides?.statusMessages?.[key] ??
    fallbackTemplate;

  return template.replace(/\{([a-zA-Z]+)\}/g, (_match, token) =>
    String(values[token] ?? ""),
  );
}

function formatCartStatusMessage(cartEffects, key, fallbackTemplate, values) {
  const template =
    cartEffects.cartContentOverrides?.statusMessages?.[key] ?? fallbackTemplate;

  return template.replace(/\{([a-zA-Z]+)\}/g, (_match, token) =>
    String(values[token] ?? ""),
  );
}

function getPostRemovalFocusTarget(lineItems, removedProductId) {
  const removedIndex = lineItems.findIndex((item) => item.id === removedProductId);
  const remainingItems = lineItems.filter((item) => item.id !== removedProductId);

  if (remainingItems.length === 0) {
    return { type: "empty-cart-continue" };
  }

  const nextIndex =
    removedIndex < 0 ? 0 : Math.min(removedIndex, remainingItems.length - 1);

  return {
    type: "cart-decrement",
    productId: remainingItems[nextIndex].id,
  };
}

function getFocusTargetSelector(target) {
  if (target.type === "empty-cart-continue") {
    return '[data-testid="empty-cart-continue"]';
  }

  if (target.type === "cart-decrement") {
    return `[data-testid="cart-decrement-${target.productId}"]`;
  }

  return null;
}

const PRODUCTS_LANGUAGE_ARIA_TARGETS = Object.freeze({
  en: CHECKOUT_ARIA_STATE_TARGETS.productsLanguageEnglish,
  es: CHECKOUT_ARIA_STATE_TARGETS.productsLanguageSpanish,
});

const PRODUCTS_LANGUAGE_TEST_IDS = Object.freeze({
  en: "products-language-en",
  es: "products-language-es",
});

function ProductsLanguageSwitcher({
  ariaStateEffects,
  language,
  copy = {},
  onLanguageChange,
}) {
  return (
    <div
      className="language-switcher"
      role="group"
      aria-label={copy.ariaLabel ?? "Products language"}
      data-testid="products-language-switcher"
    >
      <span className="language-switcher-label">
        {copy.label ?? "Language"}
      </span>
      {PRODUCTS_LANGUAGE_OPTIONS.map((option) => {
        const isSelected = option.code === language;
        const declaredPressed =
          getAriaPressedOverride(
            ariaStateEffects,
            PRODUCTS_LANGUAGE_ARIA_TARGETS[option.code],
          ) ?? isSelected;
        const label = copy.options?.[option.code] ?? option.code;

        return (
          <button
            key={option.code}
            id={PRODUCTS_LANGUAGE_TEST_IDS[option.code]}
            type="button"
            role="button"
            className={
              isSelected
                ? "language-switcher-option is-selected"
                : "language-switcher-option"
            }
            aria-pressed={declaredPressed ? "true" : "false"}
            data-testid={PRODUCTS_LANGUAGE_TEST_IDS[option.code]}
            onClick={() => onLanguageChange(option.code)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
