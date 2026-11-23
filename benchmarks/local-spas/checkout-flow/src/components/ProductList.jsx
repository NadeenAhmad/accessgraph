import { useRef, useState } from "react";
import { PRODUCTS } from "../data/fixtures.js";
import { getProductQuantity } from "../state/cartStore.js";
import {
  CHECKOUT_ARIA_STATE_TARGETS,
  getAriaSelectedOverride,
} from "../benchmark/effects/ariaStateEffects.js";
import {
  CHECKOUT_HEADING_TARGETS,
  getHeadingTextOverride,
} from "../benchmark/effects/headingEffects.js";
import {
  CHECKOUT_LOCAL_LANGUAGE_TARGETS,
  getLocalLangOverride,
} from "../benchmark/effects/localLanguageEffects.js";
import {
  CHECKOUT_LANDMARK_TARGETS,
  getLandmarkAccessibleNameOverride,
} from "../benchmark/effects/landmarkEffects.js";
import { resolveProductsEffects } from "../benchmark/effects/productsEffects.js";
import {
  CHECKOUT_WIDGET_TARGETS,
  getWidgetAccessibleNameOverride,
  getWidgetContentBindingOverride,
  getWidgetTextOverride,
} from "../benchmark/effects/widgetEffects.js";
import { ProductCard } from "./ProductCard.jsx";

const PRODUCT_CATEGORY_TABS = [
  {
    id: "desk-accessories",
    label: "Desk accessories",
    description: "Lighting and cable tools for a tidy workspace.",
    productIds: ["prod-desk-lamp", "prod-cable-organizer"],
  },
  {
    id: "office-supplies",
    label: "Office supplies",
    description: "Everyday supplies for notes and planning.",
    productIds: ["prod-notebook-set"],
  },
];

const PRODUCT_CATEGORY_WIDGET_TARGETS = Object.freeze({
  "desk-accessories": CHECKOUT_WIDGET_TARGETS.productsDeskAccessoriesCategoryTab,
  "office-supplies": CHECKOUT_WIDGET_TARGETS.productsOfficeSuppliesCategoryTab,
});

const PRODUCT_CATEGORY_ARIA_STATE_TARGETS = Object.freeze({
  "desk-accessories":
    CHECKOUT_ARIA_STATE_TARGETS.productsDeskAccessoriesCategoryTab,
  "office-supplies":
    CHECKOUT_ARIA_STATE_TARGETS.productsOfficeSuppliesCategoryTab,
});

export function ProductList({
  cartItems,
  activeSeeds = [],
  ariaStateEffects = {},
  buttonEffects = {},
  headingEffects = {},
  landmarkEffects = {},
  localLanguageEffects = {},
  productEffects = null,
  widgetEffects = {},
  onAdd,
}) {
  const [selectedCategoryId, setSelectedCategoryId] = useState(
    PRODUCT_CATEGORY_TABS[0].id,
  );
  const tabRefs = useRef({});
  const resolvedProductEffects =
    productEffects ?? resolveProductsEffects(activeSeeds);
  const productsContent =
    resolvedProductEffects.productsContentOverrides ?? {};
  const listCopy = productsContent.list ?? {};
  const categoryCopyById = productsContent.categories ?? {};
  const productCopyById = productsContent.products ?? {};
  const productsListHeading =
    getHeadingTextOverride(
      headingEffects,
      CHECKOUT_HEADING_TARGETS.productsFeaturedProductsHeading,
    ) ??
    listCopy.heading ??
    "Featured products";
  const productsListAccessibleNameOverride =
    getLandmarkAccessibleNameOverride(
      landmarkEffects,
      CHECKOUT_LANDMARK_TARGETS.productsFeaturedRegion,
    );
  const productsDescriptionLang = getLocalLangOverride(
    localLanguageEffects,
    CHECKOUT_LOCAL_LANGUAGE_TARGETS.productsDescription,
  );
  const productCategoryTablistAccessibleName =
    getWidgetAccessibleNameOverride(
      widgetEffects,
      CHECKOUT_WIDGET_TARGETS.productsCategoryTablist,
    ) ??
    listCopy.categoryTablistLabel ??
    "Product categories";
  const selectedCategoryIndex = PRODUCT_CATEGORY_TABS.findIndex(
    (category) => category.id === selectedCategoryId,
  );

  function activateCategory(categoryId) {
    setSelectedCategoryId(categoryId);
  }

  function focusAndActivateCategory(index) {
    const nextCategory = PRODUCT_CATEGORY_TABS[index];

    activateCategory(nextCategory.id);
    tabRefs.current[nextCategory.id]?.focus();
  }

  function handleTabKeyDown(event) {
    const currentIndex = Math.max(selectedCategoryIndex, 0);

    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusAndActivateCategory((currentIndex + 1) % PRODUCT_CATEGORY_TABS.length);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusAndActivateCategory(
        (currentIndex - 1 + PRODUCT_CATEGORY_TABS.length) %
          PRODUCT_CATEGORY_TABS.length,
      );
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      focusAndActivateCategory(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      focusAndActivateCategory(PRODUCT_CATEGORY_TABS.length - 1);
    }
  }

  return (
    <section
      className="product-list-section"
      aria-label={productsListAccessibleNameOverride}
      aria-labelledby={
        productsListAccessibleNameOverride ? undefined : "product-list-heading"
      }
      data-testid="products-list-region"
    >
      <div className="section-heading">
        <h2 id="product-list-heading">{productsListHeading}</h2>
        <p
          id="products-description"
          data-testid="products-description"
          lang={productsDescriptionLang}
        >
          {listCopy.description ?? "Browse featured products for your workspace."}
        </p>
      </div>

      <div
        className="product-category-browser"
        aria-labelledby="product-category-browser-heading"
        data-testid="product-category-browser"
      >
        <h3 id="product-category-browser-heading">
          {listCopy.categoryBrowserHeading ?? "Browse by category"}
        </h3>
        <div
          className="product-category-tablist"
          role="tablist"
          aria-label={productCategoryTablistAccessibleName}
          data-testid="product-category-tablist"
        >
          {PRODUCT_CATEGORY_TABS.map((category) => {
            const categoryCopy = categoryCopyById[category.id] ?? {};
            const isSelected = category.id === selectedCategoryId;
            const ariaStateTargetId =
              PRODUCT_CATEGORY_ARIA_STATE_TARGETS[category.id];
            const ariaSelectedOverride = getAriaSelectedOverride(
              ariaStateEffects,
              ariaStateTargetId,
            );
            const declaredSelected =
              ariaSelectedOverride !== undefined ? ariaSelectedOverride : isSelected;
            const tabId = `${category.id}-tab`;
            const panelId = `${category.id}-panel`;
            const widgetTargetId = PRODUCT_CATEGORY_WIDGET_TARGETS[category.id];
            const visibleLabel =
              getWidgetTextOverride(widgetEffects, widgetTargetId) ??
              categoryCopy.label ??
              category.label;
            const accessibleName =
              getWidgetAccessibleNameOverride(widgetEffects, widgetTargetId);

            return (
              <button
                key={category.id}
                ref={(node) => {
                  tabRefs.current[category.id] = node;
                }}
                type="button"
                className={
                  isSelected
                    ? "product-category-tab is-selected"
                    : "product-category-tab"
                }
                role="tab"
                id={tabId}
                aria-label={accessibleName}
                aria-selected={declaredSelected ? "true" : "false"}
                aria-controls={panelId}
                tabIndex={isSelected ? 0 : -1}
                data-testid={`product-category-tab-${category.id}`}
                onClick={() => activateCategory(category.id)}
                onKeyDown={handleTabKeyDown}
              >
                {visibleLabel}
              </button>
            );
          })}
        </div>

        {PRODUCT_CATEGORY_TABS.map((category) => {
          const widgetTargetId = PRODUCT_CATEGORY_WIDGET_TARGETS[category.id];
          const contentCategoryId =
            getWidgetContentBindingOverride(widgetEffects, widgetTargetId) ??
            category.id;
          const contentCategory =
            PRODUCT_CATEGORY_TABS.find(
              (candidate) => candidate.id === contentCategoryId,
            ) ?? category;
          const categoryCopy = categoryCopyById[contentCategory.id] ?? {};
          const isSelected = category.id === selectedCategoryId;
          const categoryProducts = PRODUCTS.filter((product) =>
            contentCategory.productIds.includes(product.id),
          );

          return (
            <div
              key={category.id}
              className="product-category-panel"
              role="tabpanel"
              id={`${category.id}-panel`}
              aria-labelledby={`${category.id}-tab`}
              tabIndex={0}
              hidden={!isSelected}
              data-testid={`product-category-panel-${category.id}`}
            >
              <p>{categoryCopy.description ?? contentCategory.description}</p>
              <ul>
                {categoryProducts.map((product) => (
                  <li key={product.id}>
                    {productCopyById[product.id]?.name ?? product.name}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <ul className="product-list" data-testid="product-list">
        {PRODUCTS.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            quantity={getProductQuantity(cartItems, product.id)}
            buttonEffects={buttonEffects}
            productEffects={resolvedProductEffects}
            onAdd={onAdd}
          />
        ))}
      </ul>
    </section>
  );
}
